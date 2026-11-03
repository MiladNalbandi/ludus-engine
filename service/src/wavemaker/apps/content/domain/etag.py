"""Reading `If-None-Match` the way clients actually write it.

The specification allows a quoted tag, a weak validator, a comma-separated list and `*`. Real
clients and proxies also send a bare unquoted tag. Refusing any of those shapes does not fail
anything visibly: it turns caching off for one platform's HTTP stack, and the only symptom is
a bill. So this is deliberately tolerant on the way in and strict on the way out.
"""

from __future__ import annotations

WEAK_PREFIXES = ("W/", "w/")
ANY_REPRESENTATION = "*"


def quote(tag: str) -> str:
    """How a tag always leaves: quoted, strong."""
    return f'"{tag}"'


def matches(header: str | None, current: str) -> bool:
    """Does the client already hold `current`?

    A malformed header is a miss, never an error and never a false hit: answering 304 to a
    header nobody can parse hands the client a body it does not have.
    """
    if header is None or not header.strip():
        return False

    if header.strip() == ANY_REPRESENTATION:
        # "any representation you have" — true only when there is one.
        return bool(current)

    return any(tag == current for tag in _tags(header))


def _tags(header: str) -> list[str]:
    tags = []
    for raw in header.split(","):
        tag = _unwrap(raw.strip())
        if tag:
            tags.append(tag)
    return tags


def _unwrap(token: str) -> str | None:
    for prefix in WEAK_PREFIXES:
        if token.startswith(prefix):
            token = token[len(prefix) :].strip()
            break

    if not token:
        return None

    if token.startswith('"'):
        # An unterminated or empty quoted string is not a tag. Skip it rather than guess.
        if len(token) < 2 or not token.endswith('"'):
            return None
        inner = token[1:-1]
        return inner or None

    return token
