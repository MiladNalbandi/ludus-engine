"""Which apps may run together, decided before any of them is wired up.

A plain object with no I/O, so the rules can be read without a filesystem in the way. Both
refusals happen here rather than in the loader, because only the registry knows what has
already been accepted — the loader sees one file at a time.
"""

from __future__ import annotations

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from wavemaker.platform.kernel.errors import DuplicateAppError, IncompatiblePlatformError
from wavemaker.platform.kernel.manifest import ANY_PLATFORM, AppManifest


class AppRegistry:
    """The apps this service will run, keyed by name."""

    def __init__(self, platform_version: str) -> None:
        self._platform_version = platform_version
        self._apps: dict[str, AppManifest] = {}

    @property
    def apps(self) -> tuple[AppManifest, ...]:
        """Every registered app, in name order.

        Ordered so that two services given the same plugins mount their routes and run their
        migrations in the same sequence. Directory order is whatever the filesystem feels
        like, which would make a startup difference impossible to reproduce.
        """
        return tuple(self._apps[name] for name in sorted(self._apps))

    def register(self, manifest: AppManifest) -> None:
        self._refuse_duplicate(manifest)
        self._refuse_incompatible(manifest)
        self._apps[manifest.name] = manifest

    def _refuse_duplicate(self, manifest: AppManifest) -> None:
        existing = self._apps.get(manifest.name)
        if existing is None:
            return
        # Both files are named because the fix is to change one of them, and the person
        # reading this has no other way to find out which two collided.
        raise DuplicateAppError(
            f"Two apps are both called '{manifest.name}': "
            f"{existing.source or 'unknown'} and {manifest.source or 'unknown'}. "
            "An app name is also its route and table prefix, so it has to be unique."
        )

    def _refuse_incompatible(self, manifest: AppManifest) -> None:
        if manifest.requires_platform == ANY_PLATFORM:
            return

        try:
            wanted = SpecifierSet(manifest.requires_platform)
            running = Version(self._platform_version)
        except (InvalidSpecifier, InvalidVersion) as broken:
            # A range nobody can parse must not quietly become "runs anywhere": that is how a
            # typo turns into an app loaded onto a platform it was never built for.
            raise IncompatiblePlatformError(
                f"App '{manifest.name}' ({manifest.source or 'unknown'}) asks for platform "
                f"'{manifest.requires_platform}', which is not a version range."
            ) from broken

        if not wanted.contains(running, prereleases=True):
            raise IncompatiblePlatformError(
                f"App '{manifest.name}' ({manifest.source or 'unknown'}) needs platform "
                f"'{manifest.requires_platform}', but this platform is {self._platform_version}."
            )
