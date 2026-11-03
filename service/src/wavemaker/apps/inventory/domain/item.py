"""Items a project defines, and how many of each a player holds.

An item is an identifier, a display name, a type from the project's own vocabulary, an opaque
sprite reference and a document of attributes the engine does not read. Nothing here knows what
a sword is. The model the Java reshaped this from had an enum of one game's power-ups, and a
second game needed a fork.

What stops the attributes being a junk drawer is not the engine understanding them: it is the
project's own schema, checked by the application before an item is stored.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeGuard, cast

from wavemaker.platform.kernel import storable

from . import documents
from .errors import Rejected, Violation, rejected

# Identifiers and types are the project's own words, in the shape that is safe in a URL path,
# as a JSON key and in a log line without escaping. Not enums: an enum means a release of this
# service every time a game invents a kind of item.
SLUG = re.compile(r"^[a-z0-9_]+$")
MAX_ID_LENGTH = 64
MAX_TYPE_LENGTH = 64
MAX_NAME_LENGTH = 255
MAX_SPRITE_REF_LENGTH = 255

# The attributes of one item, not a catalogue. A project that needs more than this for a single
# item has a modelling question rather than a limit question.
MAX_ATTRIBUTES_BYTES = 64 * 1024

EMPTY_ATTRIBUTES = "{}"


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    name: str
    item_type: str
    sprite_ref: str | None
    attributes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ItemDraft:
    """An item as a caller asked for it, checked and not yet stored.

    `attributes` is the text exactly as it arrived, which is what gets stored. `document` is
    what that text says, which is what gets validated. They are never re-joined: serialising
    `document` back out would reorder keys and rewrite `2.0` as `2`, and the stored text would
    stop being what the editor wrote.
    """

    id: str
    name: str
    item_type: str
    sprite_ref: str | None
    attributes: str
    document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    """How many of one item a player holds.

    Zero is a real value, not an absence: "had one and used it" is worth telling apart from
    "never had one" when a game shows a collection.
    """

    item_id: str
    quantity: int
    updated_at: datetime


def is_slug(value: object, longest: int) -> TypeGuard[str]:
    return isinstance(value, str) and len(value) <= longest and SLUG.match(value) is not None


def item_id_of(value: object) -> str:
    if not is_slug(value, MAX_ID_LENGTH):
        raise rejected(
            "/id",
            f"{value!r} is not an item id; expected ^[a-z0-9_]+$, at most {MAX_ID_LENGTH} "
            "characters",
        )
    return value


def draft_of(item_id: str, body: Mapping[str, Any]) -> ItemDraft:
    """An item to create or replace, from the `ItemRequest` a caller sent.

    Every field is checked before any is refused, so one response names every problem.
    """
    found: list[Violation] = []
    identifier = _collect(found, lambda: item_id_of(item_id))
    name = _collect(found, lambda: _name(body.get("name")))
    item_type = _collect(found, lambda: _item_type(body.get("itemType")))
    sprite_ref = _collect(found, lambda: _sprite_ref(body.get("spriteRef")))
    attributes = _collect(found, lambda: _attributes(body.get("attributes")))
    if found:
        raise Rejected(found)
    text, document = cast(tuple[str, dict[str, Any]], attributes)
    return ItemDraft(
        id=cast(str, identifier),
        name=cast(str, name),
        item_type=cast(str, item_type),
        sprite_ref=sprite_ref,
        attributes=text,
        document=document,
    )


def _collect[T](found: list[Violation], read: Callable[[], T]) -> T | None:
    """`read()`, or None with its violations added to `found`."""
    try:
        return read()
    except Rejected as problem:
        found.extend(problem.violations)
        return None


def _text(where: str, value: str, longest: int) -> str:
    reason = storable.unstorable(value)
    if reason:
        raise rejected(where, reason)
    if len(value) > longest:
        raise rejected(where, f"at most {longest} characters")
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise rejected("/name", "an item needs a name")
    return _text("/name", value.strip(), MAX_NAME_LENGTH)


def _item_type(value: object) -> str:
    if not is_slug(value, MAX_TYPE_LENGTH):
        raise rejected(
            "/itemType",
            f"{value!r} is not an item type; expected ^[a-z0-9_]+$, at most {MAX_TYPE_LENGTH} "
            "characters",
        )
    return value


def _sprite_ref(value: object) -> str | None:
    """A reference the game resolves, never a URL this service fetches.

    An engine that dereferenced it would be a request-forgery hole with extra steps, so it is
    stored as an opaque label and nothing more. Blank means none.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise rejected("/spriteRef", "a sprite reference is text")
    trimmed = value.strip()
    return _text("/spriteRef", trimmed, MAX_SPRITE_REF_LENGTH) if trimmed else None


def _attributes(value: object) -> tuple[str, dict[str, Any]]:
    """The attributes text exactly as sent, and the object it holds.

    A string, because the frozen contract says so: `ItemRequest.attributes` is
    `{"type": "string"}`, and the Java bound it to a `String` precisely so the characters an
    editor wrote reached the database untouched. Accepting a nested object as well would mean
    serialising it to store it, which is the one thing this field exists to avoid.

    Absent or blank is `{}`: a game that has not decided what its items carry should still be
    able to create one.
    """
    if value is None:
        return EMPTY_ATTRIBUTES, {}
    if not isinstance(value, str):
        raise rejected(
            "/attributes",
            'attributes are JSON text inside a string, such as "{\\"damage\\": 12}"',
        )
    if not value.strip():
        return EMPTY_ATTRIBUTES, {}
    if len(value.encode("utf-8", errors="surrogatepass")) > MAX_ATTRIBUTES_BYTES:
        raise rejected("/attributes", f"attributes are at most {MAX_ATTRIBUTES_BYTES} bytes")

    document = documents.parse("/attributes", value)
    if not isinstance(document, dict):
        # The GIN index and every query a project will write against it — "every item whose
        # element is fire" — presume named fields. A bare 12 has none.
        raise rejected("/attributes", "attributes are a JSON object")
    found = documents.problems(document, "/attributes")
    if found:
        raise Rejected(found)
    return value, document
