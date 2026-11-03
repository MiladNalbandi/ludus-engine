"""An uploaded file's metadata, and the two strings a client sends that must never be trusted.

The id names the bytes on disk, so it is always generated here and only ever read back through
`parse_id`: a path segment that does not parse as a UUID is not an id, and there is no other
way for text from a request to become one.

The filename is a label. Clips and sprites are stored under their id, so a filename never
reaches a path — but it is still cut down to its last segment, because storing
`../../etc/passwd` as a display name is an invitation for some later reader to treat it as one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# The column is varchar(255). Cut here rather than refused at the database, which would be a
# 500 for an upload whose only fault is a long name.
MAX_FILENAME = 255
UNTITLED = "untitled"


class AssetKind(StrEnum):
    AUDIO = "audio"
    SPRITE = "sprite"


@dataclass(frozen=True, slots=True)
class Asset:
    id: uuid.UUID
    kind: AssetKind
    filename: str
    content_type: str
    # What was written, counted as it was written. Never a length the client declared: a
    # client that lies about its size should not be able to make the catalogue lie too.
    size_bytes: int
    # The tag a client revalidates with. Computed while streaming, so it costs nothing extra.
    sha256: str
    created_at: datetime


def parse_id(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError, AttributeError):
        return None


def display_name(submitted: str | None) -> str:
    if not submitted:
        return UNTITLED
    leaf = submitted.replace("\\", "/").rsplit("/", 1)[-1]
    # Control characters out: a NUL or a newline in a label ends up in a log line or a header.
    leaf = "".join(ch for ch in leaf if ch.isprintable()).strip()
    return leaf[:MAX_FILENAME] or UNTITLED
