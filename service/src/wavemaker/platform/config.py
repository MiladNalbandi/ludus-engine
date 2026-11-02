"""Everything the platform reads from its environment.

No default plugins directory on purpose. An unset path is a deliberate "this service runs no
plugins", and guessing at one would mean a service quietly loading whatever happened to be in
a folder it invented.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WAVEMAKER_", extra="ignore")

    plugins_directory: Path | None = None
