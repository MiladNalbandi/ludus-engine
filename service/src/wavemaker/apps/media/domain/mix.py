"""A mix request, read and checked before anything is opened or run.

The filter graph FFmpeg is given is built here, from track positions and gains and nothing
else. A gain is a number by the time it reaches the graph — formatted with a dot, whatever the
locale — so the only influence a caller has on the command line is how many tracks there are
and how loud each is.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from wavemaker.apps.media.domain.asset import display_name, parse_id

# Silence for 16-bit audio at one end, sixteen times louder at the other. Outside that range a
# gain is a mistake, and a value like 1e300 would still be formatted into the graph faithfully.
MIN_GAIN_DB = -96.0
MAX_GAIN_DB = 24.0


class MixRefused(Exception):
    """A mix request that cannot be acted on, with the JSON Pointer of the field at fault."""

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}" if pointer else message)
        self.pointer = pointer


@dataclass(frozen=True, slots=True)
class MixTrack:
    clip_id: uuid.UUID
    gain_db: float


@dataclass(frozen=True, slots=True)
class MixRequest:
    filename: str
    tracks: tuple[MixTrack, ...]


def read_mix(body: Any, *, max_tracks: int) -> MixRequest:
    if not isinstance(body, dict):
        raise MixRefused("", "A mix request is a JSON object with a filename and tracks.")

    filename = body.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        raise MixRefused("/filename", "the mixed clip needs a name")

    tracks = body.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise MixRefused("/tracks", "a mix needs at least one track")
    if len(tracks) > max_tracks:
        raise MixRefused("/tracks", f"at most {max_tracks} tracks per mix, received {len(tracks)}")

    return MixRequest(
        filename=display_name(filename),
        tracks=tuple(_track(index, track) for index, track in enumerate(tracks)),
    )


def _track(index: int, track: Any) -> MixTrack:
    where = f"/tracks/{index}"
    if not isinstance(track, dict):
        raise MixRefused(where, "a track is an object with a clipId")

    raw_id = track.get("clipId")
    clip_id = parse_id(raw_id) if isinstance(raw_id, str) else None
    if clip_id is None:
        raise MixRefused(f"{where}/clipId", "not a clip id")

    gain = track.get("gainDb")
    if gain is None:
        return MixTrack(clip_id=clip_id, gain_db=0.0)
    # bool is an int in Python, and `true` is not a loudness.
    if isinstance(gain, bool) or not isinstance(gain, int | float):
        raise MixRefused(f"{where}/gainDb", "a gain is a number of decibels")
    if not math.isfinite(gain) or not MIN_GAIN_DB <= gain <= MAX_GAIN_DB:
        raise MixRefused(
            f"{where}/gainDb", f"a gain must be between {MIN_GAIN_DB:g} and {MAX_GAIN_DB:g} dB"
        )
    return MixTrack(clip_id=clip_id, gain_db=float(gain))


def filter_graph(gains: Sequence[float]) -> str:
    """`[0:a]volume=…dB[a0];…[a0][a1]amix=…[out]`. `normalize=0` so adding a track does not
    quietly turn every other one down."""
    volumes = "".join(f"[{i}:a]volume={gain:.3f}dB[a{i}];" for i, gain in enumerate(gains))
    labels = "".join(f"[a{i}]" for i in range(len(gains)))
    return f"{volumes}{labels}amix=inputs={len(gains)}:duration=longest:normalize=0[out]"
