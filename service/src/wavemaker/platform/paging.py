"""Keyset paging: what every cursor-paged list in the service shares.

A keyset page asks for "the rows after this one" rather than "the rows after the first n". An
offset is a position, and positions shift whenever a row is written ahead of them, so an
offset walk over a list that is being written repeats some rows and skips others. A keyset is
a value, and a row whose value does not change sorts after it or before it however many other
rows arrive.

That only holds when the order is total. Scores tie and timestamps tie, so every keyset here
carries a unique column as its last part: without it a cursor lands in the middle of a tie and
cannot say which of the tied rows it has already passed.

The cursor is opaque to clients — base64 of the last row's key — so that nobody builds one by
hand and starts depending on its shape. A cursor that does not decode is a 422 rather than the
first page: a client that silently restarts a walk sees every row twice and cannot tell.
"""

from __future__ import annotations

import base64
import binascii

from wavemaker.platform.kernel.errors import PlatformError

SEPARATOR = "|"


class BadCursor(PlatformError):
    """A cursor this service did not issue, or one that was damaged on the way back."""


def page_size(limit: int | None, *, default: int, maximum: int) -> int:
    """The number of rows to serve: the default when none is asked for, and never more than
    `maximum`, so one request cannot ask for the whole table."""
    if limit is None:
        return default
    return max(1, min(maximum, limit))


def encode_cursor(*parts: str) -> str:
    raw = SEPARATOR.join(parts).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, parts: int) -> tuple[str, ...]:
    """The parts of a cursor `encode_cursor` made, or `BadCursor`."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode()
    except (ValueError, binascii.Error, UnicodeError) as broken:
        raise BadCursor("/cursor: not a cursor this service issued") from broken
    found = tuple(decoded.split(SEPARATOR))
    if len(found) != parts or not all(found):
        raise BadCursor("/cursor: not a cursor this service issued")
    return found
