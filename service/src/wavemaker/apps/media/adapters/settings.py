"""Media's own knobs, read from `WAVEMAKER_MEDIA_*`.

Here rather than in the platform's settings because they are media's business: the core knows
only where blobs go (`WAVEMAKER_BLOB_DIRECTORY`), not how large a sprite may be.

Size limits have defaults, because a limit is always wanted and a sensible one is easy to name.
The FFmpeg binary does not: unset means this service does not mix, and the mix route says so
with a 503. The standard image carries no FFmpeg, and guessing `/usr/bin/ffmpeg` would make
"mixing works" depend on what happened to be installed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIB = 1024 * 1024


class MediaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WAVEMAKER_MEDIA_", extra="ignore")

    # The Java's multipart limit, and comfortably more than a long music track in Ogg.
    max_audio_bytes: int = Field(default=64 * MIB, gt=0)
    # Item art. A 4096² sprite sheet as PNG fits; a mistakenly uploaded video does not.
    max_sprite_bytes: int = Field(default=16 * MIB, gt=0)

    ffmpeg_binary: Path | None = None
    # A hard stop. FFmpeg can be made to run for a very long time on a small input, and a
    # request that never returns is a denial of service with extra steps.
    mix_timeout_seconds: float = Field(default=60.0, gt=0)
    mix_max_tracks: int = Field(default=8, gt=0)
    mix_max_output_bytes: int = Field(default=64 * MIB, gt=0)

    @field_validator("ffmpeg_binary")
    @classmethod
    def _absolute(cls, binary: Path | None) -> Path | None:
        if binary is not None and not binary.is_absolute():
            raise ValueError(
                f"WAVEMAKER_MEDIA_FFMPEG_BINARY must be an absolute path, not '{binary}': a "
                "name looked up on PATH is whatever ffmpeg means on this machine today."
            )
        return binary


@lru_cache(maxsize=1)
def media_settings() -> MediaSettings:
    """Read once. A dependency, so a test can override it without touching the environment."""
    return MediaSettings()
