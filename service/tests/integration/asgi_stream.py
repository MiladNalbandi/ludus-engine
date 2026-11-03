"""Talking to the application one chunk at a time, with no HTTP client in between.

`TestClient` cannot prove streaming. It reads a streamed request body whole before handing it
to the application (httpx's `Request.read()`), so a test that measured memory through it would
measure the test's own copy of the upload. Calling the ASGI application directly lets the test
hand over one 64 KiB chunk at a time and throw each response chunk away as it arrives — so the
only thing left that could hold twelve megabytes is the code under test.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

import anyio

CHUNK = 64 * 1024
# The same object every time, so the test itself allocates one chunk, not twelve megabytes.
PATTERN = bytes(range(256)) * (CHUNK // 256)


@dataclass
class Exchange:
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body_bytes: int = 0
    largest_chunk: int = 0
    chunks_pulled: int = 0
    body_prefix: bytes = b""


def pattern(total: int) -> Iterator[bytes]:
    """`total` bytes of a repeating pattern, yielded in chunks of the one shared buffer."""
    sent = 0
    while sent < total:
        step = min(CHUNK, total - sent)
        yield PATTERN if step == CHUNK else PATTERN[:step]
        sent += step


def multipart(
    content: Iterable[bytes], *, filename: str, content_type: str, boundary: str = "wm-boundary"
) -> Iterator[bytes]:
    yield (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    yield from content
    yield f"\r\n--{boundary}--\r\n".encode()


def exchange(
    app: Any,
    *,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: Iterable[bytes] = (),
) -> Exchange:
    return anyio.run(_exchange, app, method, path, headers or {}, body)


async def _exchange(
    app: Any, method: str, path: str, headers: dict[str, str], body: Iterable[bytes]
) -> Exchange:
    result = Exchange()
    chunks = iter(body)
    finished = anyio.Event()
    body_done = False

    async def receive() -> dict[str, Any]:
        nonlocal body_done
        if body_done:
            # Starlette listens for a disconnect while it streams a response. There is none
            # until the response is over.
            await finished.wait()
            return {"type": "http.disconnect"}
        try:
            chunk = next(chunks)
        except StopIteration:
            body_done = True
            return {"type": "http.request", "body": b"", "more_body": False}
        result.chunks_pulled += 1
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            result.status = message["status"]
            result.headers = {k.decode().lower(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            if len(result.body_prefix) < 256:
                result.body_prefix += chunk[: 256 - len(result.body_prefix)]
            result.body_bytes += len(chunk)
            result.largest_chunk = max(result.largest_chunk, len(chunk))
            if not message.get("more_body", False):
                finished.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
    }
    await app(scope, receive, send)
    finished.set()
    return result
