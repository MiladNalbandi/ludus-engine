"""Reading JSON text a project wrote: item attributes, and the schema they are checked against.

Both are kept as the exact text that arrived, and both are read here first, for one reason:
everything a caller can send must be refused *here*, as a 4xx naming the place, rather than
somewhere further in where it becomes a 500. Python's JSON reader accepts several things the
rest of the system does not:

- `NaN` and `Infinity`, which are not JSON at all, and which PostgreSQL's `jsonb` refuses;
- `1e400`, which is JSON and which Python reads as infinity;
- `"\\u0000"`, valid JSON, which no PostgreSQL text value can hold;
- `"\\ud800"`, a lone surrogate, valid JSON escaping and not a character, which cannot be
  encoded as UTF-8 to be sent anywhere;
- nesting deep enough to exhaust the interpreter's stack, here or in the schema validator.

Each of those would otherwise be found by the database or by a `RecursionError` mid-request.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from typing import Any

from .errors import Violation, escape, rejected

# Deep enough for any real item; shallow enough that validating one cannot exhaust the stack,
# which costs the schema validator several frames per level.
MAX_DEPTH = 64


def _not_json(constant: str) -> Any:
    raise ValueError(f"{constant} is not a JSON value")


def parse(where: str, text: str) -> Any:
    """The document `text` holds, or a refusal at `where`."""
    unstorable = unstorable_text(text)
    if unstorable:
        raise rejected(where, unstorable)
    try:
        return json.loads(text, parse_constant=_not_json)
    except RecursionError as deep:
        raise rejected(where, f"nested more than {MAX_DEPTH} levels deep") from deep
    except ValueError as broken:  # JSONDecodeError is a ValueError
        raise rejected(where, f"this is not JSON: {broken}") from broken


def unstorable_text(text: str) -> str | None:
    """Why `text` cannot be stored or sent, or None when it can."""
    if "\x00" in text:
        return "text cannot contain the NUL character"
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return "text must be valid Unicode; this contains a lone surrogate"
    return None


def nodes(document: Any) -> Iterator[tuple[str, int, Any]]:
    """Every value in `document`, with its JSON Pointer and depth, parents before children.

    Iterative rather than recursive, so a document that is too deep is reported as too deep
    instead of crashing the walk that was meant to find out.
    """
    pending: list[tuple[str, int, Any]] = [("", 0, document)]
    while pending:
        where, depth, node = pending.pop()
        yield where, depth, node
        if isinstance(node, dict):
            children = [(f"{where}/{escape(key)}", value) for key, value in node.items()]
        elif isinstance(node, list):
            children = [(f"{where}/{index}", value) for index, value in enumerate(node)]
        else:
            continue
        for child_where, value in reversed(children):
            pending.append((child_where, depth + 1, value))


def problems(document: Any, prefix: str) -> list[Violation]:
    """Everything in a parsed document that could not be stored, at its pointer."""
    found: list[Violation] = []
    for where, depth, node in nodes(document):
        if depth > MAX_DEPTH:
            found.append(Violation(prefix + where, f"nested more than {MAX_DEPTH} levels deep"))
            break
        if isinstance(node, float) and not math.isfinite(node):
            # 1e400 parses as infinity: the number the caller wrote is not the one that would
            # be checked, and no game needs one that size.
            found.append(Violation(prefix + where, "a number too large to store"))
            continue
        texts = [node] if isinstance(node, str) else []
        if isinstance(node, dict):
            texts.extend(node.keys())
        for value in texts:
            reason = unstorable_text(value)
            if reason:
                found.append(Violation(prefix + where, reason))
                break
    return found
