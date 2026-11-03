"""A level as an author sends it: a name, perhaps a description, and waves in play order.

A level is a sequence. Its order is the list order and nothing else carries a position: a
position stored beside a list is a second source for one fact, and the two drift the first time
somebody reorders by editing only one of them. The database does keep a position column, since
a table has no order of its own; it is written from this list's indices and never accepted
from a caller.

What can be checked without storage is checked here. Whether each wave exists is a question for
storage, and is asked there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wavemaker.apps.content.domain.wave import Rejected

# The width of `wave_level.name`. Longer is refused here rather than truncated by the database
# or failed by it as a 500.
MAX_NAME_LENGTH = 255


@dataclass(frozen=True, slots=True)
class LevelDraft:
    """What a create or a replace asks for. A replace is wholesale: a field left out is
    cleared, not kept, because "rename and resequence" is one decision about the whole level."""

    name: str
    description: str | None
    wave_ids: tuple[str, ...]

    @classmethod
    def read(cls, body: Any) -> LevelDraft:
        if not isinstance(body, dict):
            raise Rejected("/: a level is a JSON object with a name and a list of waves.")

        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise Rejected("/name: a level needs a name.")
        if len(name) > MAX_NAME_LENGTH:
            raise Rejected(f"/name: a level's name is at most {MAX_NAME_LENGTH} characters.")

        description = body.get("description")
        if description is not None and not isinstance(description, str):
            raise Rejected("/description: a description is text, or left out.")

        # Absent is not empty. A client that forgot the field would otherwise empty a level it
        # only meant to rename.
        waves = body.get("waves")
        if not isinstance(waves, list):
            raise Rejected("/waves: a level needs its list of waves, even an empty one.")

        first_seen: dict[str, int] = {}
        for index, wave_id in enumerate(waves):
            if not isinstance(wave_id, str):
                raise Rejected(f"/waves/{index}: a wave is named by its id, as a string.")
            if wave_id in first_seen:
                # Refused rather than deduplicated: two slots that advance together and a
                # progress count that can never be right, and quietly dropping one of an
                # author's entries is a worse surprise than being told.
                raise Rejected(
                    f"/waves/{index}: '{wave_id}' is already in this level at "
                    f"/waves/{first_seen[wave_id]}; a level plays each wave once."
                )
            first_seen[wave_id] = index

        return cls(name=name, description=description, wave_ids=tuple(waves))
