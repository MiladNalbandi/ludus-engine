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

    # No default either. A service with no database answers an empty catalogue honestly; one
    # pointed at a guessed local database would look like it was working and serve nothing
    # anybody wrote.
    database_url: str | None = None

    # The one project a self-hosted install serves. It is provisioned at startup.
    project_slug: str = "default"
    project_name: str = "Default"
