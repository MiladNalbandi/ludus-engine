"""Text a client sent that PostgreSQL cannot hold, refused once, the same way everywhere.

Two kinds of string pass every type check a route makes and still cannot be stored:

- one holding a NUL (`"\\u0000"` in JSON). A PostgreSQL `text` value cannot contain one, and
  neither can a string inside `jsonb`;
- one holding a lone surrogate (`"\\ud800"`). It is valid JSON escaping and not a character,
  so it cannot be encoded as UTF-8 to be sent to the database at all.

Both arrive as valid JSON, and both used to be found by the driver, mid-request, as a 500. This
module is the one place that says what is storable. Routes use it on each field they store, so
the refusal is a 422 that names the field; the database engine uses it on every parameter it
sends, so a route that forgets still answers the caller rather than failing as a server.
"""

from __future__ import annotations

from typing import Any

from wavemaker.platform.kernel.errors import PlatformError

NUL = "text cannot contain the NUL character"
LONE_SURROGATE = "text must be valid Unicode; this contains a lone surrogate"


class UnstorableText(PlatformError):
    """Text that cannot be stored, and where it was. The platform answers it with a 422.

    `pointer` is a JSON Pointer into what the caller sent, `""` for the whole of it, and `None`
    when nothing knows which field it was — the database boundary's refusal."""

    def __init__(self, pointer: str | None, reason: str) -> None:
        self.pointer = pointer
        self.reason = reason
        if pointer is None:
            super().__init__(f"a value in this request cannot be used: {reason}")
        else:
            super().__init__(f"{pointer}: {reason}" if pointer else reason)


def unstorable(value: str) -> str | None:
    """Why `value` cannot be stored, or None when it can."""
    if "\x00" in value:
        return NUL
    if not value.isascii():
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return LONE_SURROGATE
    return None


def storable(pointer: str, value: str) -> str:
    """`value`, or `UnstorableText` at `pointer`."""
    reason = unstorable(value)
    if reason:
        raise UnstorableText(pointer, reason)
    return value


def refuse_unstorable_in(document: Any, pointer: str = "") -> None:
    """Raise `UnstorableText` at the first string or key in a parsed JSON `document` that
    cannot be stored, in document order. A key is reported at the object holding it, since the
    key itself is the text that cannot go in a message.

    Iterative, so a document nested deeper than the interpreter's stack is still walked."""
    pending: list[tuple[str, Any]] = [(pointer, document)]
    while pending:
        where, node = pending.pop()
        if isinstance(node, str):
            storable(where, node)
        elif isinstance(node, dict):
            for key in node:
                storable(where, key)
            pending.extend(
                (f"{where}/{_escape(key)}", value) for key, value in reversed(node.items())
            )
        elif isinstance(node, list):
            pending.extend(
                (f"{where}/{index}", value) for index, value in reversed(list(enumerate(node)))
            )


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")
