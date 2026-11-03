"""Reading one file out of a `multipart/form-data` body as it arrives, straight into a sink.

Not Starlette's `request.form()`. That would work, and it would hold up to a megabyte of each
file in memory before spooling the rest to a temporary file — which then has to be copied
into the blob store, so every byte is written twice. Worse, it reads the whole body before
the route sees any of it, so an oversized upload is refused only after it has been written to
the temporary directory in full. Driving the parser here means each chunk goes from the socket
to its final directory once, and the limit is enforced at the chunk that crosses it.

The parser is python-multipart's, the same one Starlette uses: the format is easy to get subtly
wrong, and this only drives it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Protocol

import anyio.to_thread
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

if TYPE_CHECKING:
    # Declared only for type checkers by python-multipart itself.
    from python_multipart.multipart import MultipartCallbacks

FORM_DATA = b"multipart/form-data"
# The framing around a file — boundaries, part headers, other small fields — is allowed this
# much on top of the file's own limit before the body as a whole is refused.
FRAMING_ALLOWANCE = 64 * 1024

# How browsers and httpx escape a filename inside the quoted header (the WHATWG
# multipart/form-data encoding). Undone so a label reads the way its author typed it.
WHATWG_ESCAPES = (("%0A", "\n"), ("%0D", "\r"), ("%22", '"'))


class NotMultipart(Exception):
    """The body is not multipart/form-data at all. A 415."""


class MalformedMultipart(Exception):
    """The body says it is multipart and is not readable as such. A 400."""


class MissingFile(Exception):
    """The form was read and had no part with the expected name. A 422."""


class BodyTooLarge(Exception):
    """More arrived than any acceptable upload could need. A 413."""


class FileSink(Protocol):
    def write(self, chunk: bytes) -> None: ...


OpenSink = Callable[[str | None, str | None], FileSink]


async def receive_file(
    chunks: AsyncIterator[bytes],
    content_type: str | None,
    *,
    field: str,
    open_sink: OpenSink,
    max_body: int,
) -> FileSink:
    """Feed the body to the parser; the first part named `field` goes to `open_sink(...)`.

    `open_sink` is called with the part's filename and declared type as soon as its headers are
    read, before any of its bytes, so it can refuse a wrong type without anything being written.
    Whatever it or the sink raises propagates out of here unchanged.
    """
    kind, options = parse_options_header(content_type)
    if kind != FORM_DATA:
        raise NotMultipart("An upload is sent as multipart/form-data with a 'file' part.")
    boundary = options.get(b"boundary")
    if not boundary:
        raise MalformedMultipart("The multipart body has no boundary.")

    reader = _Reader(field.encode(), open_sink)
    try:
        parser = MultipartParser(boundary, reader.callbacks())
    except ValueError as unusable:
        raise MalformedMultipart(f"The multipart boundary is unusable: {unusable}") from unusable

    received = 0
    try:
        async for chunk in chunks:
            received += len(chunk)
            if received > max_body:
                raise BodyTooLarge(f"The request is larger than the limit of {max_body} bytes.")
            # In a worker thread: the parser calls the sink, and the sink writes to disk.
            await anyio.to_thread.run_sync(parser.write, chunk)
        parser.finalize()
    except MultipartParseError as broken:
        raise MalformedMultipart(f"The multipart body could not be read: {broken}") from broken

    if not reader.ended:
        raise MalformedMultipart("The body ended before the multipart form did.")
    if reader.sink is None or not reader.file_complete:
        raise MissingFile(f"The form has no '{field}' part.")
    return reader.sink


class _Reader:
    def __init__(self, field: bytes, open_sink: OpenSink) -> None:
        self._field = field
        self._open_sink = open_sink
        self._headers: dict[bytes, bytes] = {}
        self._name = b""
        self._value = b""
        self._in_file = False
        self.sink: FileSink | None = None
        self.file_complete = False
        self.ended = False

    def callbacks(self) -> MultipartCallbacks:
        return {
            "on_part_begin": self._part_begin,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
            "on_end": self._end,
        }

    def _part_begin(self) -> None:
        self._headers = {}
        self._in_file = False

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._name += data[start:end]

    def _header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def _header_end(self) -> None:
        self._headers[self._name.strip().lower()] = self._value.strip()
        self._name = self._value = b""

    def _headers_finished(self) -> None:
        disposition, options = parse_options_header(
            self._headers.get(b"content-disposition", b"").decode("latin-1")
        )
        # Only the first part with the name: a second "file" is ignored, not appended.
        if (
            disposition != b"form-data"
            or options.get(b"name") != self._field
            or self.sink is not None
        ):
            return
        raw_name = options.get(b"filename")
        filename = None if raw_name is None else _unescape(raw_name.decode("utf-8", "replace"))
        declared = self._headers.get(b"content-type")
        self.sink = self._open_sink(
            filename, None if declared is None else declared.decode("latin-1")
        )
        self._in_file = True

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if self._in_file and self.sink is not None:
            self.sink.write(data[start:end])

    def _part_end(self) -> None:
        if self._in_file:
            self.file_complete = True
        self._in_file = False

    def _end(self) -> None:
        self.ended = True


def _unescape(filename: str) -> str:
    for escaped, character in WHATWG_ESCAPES:
        filename = filename.replace(escaped, character)
    return filename
