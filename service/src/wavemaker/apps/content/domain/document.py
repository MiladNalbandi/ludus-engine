"""A wave document: the bytes an author sent, and the few fields the engine indexes.

Two rules hold this together, and both come from the storage design.

**The bytes are the document.** They are kept exactly as they arrived and served back the same
way, because the ETag is a hash of them. Parsing and re-serialising — even once, on the way in
— rewrites `2.0` as `2` and reorders keys, which moves the tag on every save and sends every
installed client to re-download the catalogue.

**Indexed fields are read out of the document, never accepted beside it.** A request that could
say `name=X` while the document says `name=Y` is a request that can make the index disagree
with what a client is served. There is one source, and it is the document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from wavemaker.platform.kernel.errors import PlatformError


class DocumentError(PlatformError):
    """A document could not be read, or does not say what a wave must say."""


@dataclass(frozen=True, slots=True)
class WaveDocument:
    """The stored bytes, and the fields read out of them."""

    raw: bytes
    id: str
    name: str
    order: int
    schema_version: int

    @classmethod
    def read(cls, raw: bytes) -> WaveDocument:
        try:
            parsed: Any = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as broken:
            raise DocumentError(f"This is not JSON: {broken}") from broken

        if not isinstance(parsed, dict):
            raise DocumentError("A wave document must be a JSON object.")

        wave_id = parsed.get("id")
        name = parsed.get("name")
        progression = parsed.get("progression_config")

        if not isinstance(wave_id, str) or not wave_id:
            raise DocumentError("A wave document must carry a string 'id'.")
        if not isinstance(name, str) or not name:
            raise DocumentError("A wave document must carry a string 'name'.")
        if not isinstance(progression, dict) or not isinstance(progression.get("order"), int):
            raise DocumentError(
                "A wave document must carry an integer 'progression_config.order': it is the "
                "position a client plays it in."
            )

        # Absent means 1. The field was added after the first documents were written, and a
        # document without it is a version-1 document rather than a broken one.
        schema_version = parsed.get("schema_version", 1)
        if not isinstance(schema_version, int) or schema_version < 1:
            raise DocumentError("'schema_version' must be a whole number of at least 1.")

        return cls(
            raw=raw,
            id=wave_id,
            name=name,
            order=progression["order"],
            schema_version=schema_version,
        )


class OrderTaken(DocumentError):
    """Another wave already plays at this position.

    A distinct error because the fix is specific and the author can make it: change
    `progression_config.order`. Letting the database's unique-index violation reach the client
    as a 500 would turn an ordinary authoring mistake into an outage-shaped page.
    """
