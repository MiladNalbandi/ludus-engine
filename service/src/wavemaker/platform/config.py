"""Everything the platform reads from its environment.

No default plugins directory on purpose. An unset path is a deliberate "this service runs no
plugins", and guessing at one would mean a service quietly loading whatever happened to be in
a folder it invented.
"""

from __future__ import annotations

from datetime import timedelta
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

    # No default, and startup fails without it when a database is configured. A development
    # default would be a signing key published in a repository, and a service that boots with
    # it looks exactly like a service that is fine.
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # The first account, created on first start. Left unset, no account exists and nobody can
    # sign in — which is the right state for a service nobody has configured yet.
    admin_email: str = ""
    admin_password: str = ""

    def access_lifetime(self) -> timedelta:
        return timedelta(minutes=self.access_token_minutes)

    def refresh_lifetime(self) -> timedelta:
        return timedelta(days=self.refresh_token_days)
