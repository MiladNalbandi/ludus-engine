"""What an app declares about itself.

A manifest arrives from a file somebody else wrote, so it is untrusted input and every field
is checked here rather than where it is used. The kernel never opens that file: reading and
parsing belong to an adapter, and this module is handed a plain mapping that is already in
memory. That split is what keeps the kernel free of a filesystem and a TOML parser.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

from wavemaker.platform.kernel.errors import ManifestError
from wavemaker.platform.kernel.permissions import Permissions, table_prefix

# The name becomes a route prefix (`/api/v1/<name>`) and a table prefix, so it has to survive
# both without quoting. A leading letter keeps it a valid Python identifier stem as well.
NAME = re.compile(r"^[a-z][a-z0-9_-]*$")

# An app that names no range runs anywhere. An omitted range means the author has not thought
# about it yet, which is not the same as an author who got it wrong.
ANY_PLATFORM = "*"


@dataclass(frozen=True, slots=True)
class AppManifest:
    """One app's declaration. Frozen: nothing may edit a manifest after it is read."""

    name: str
    version: str
    requires_platform: str = ANY_PLATFORM
    source: str = ""
    permissions: Permissions = field(default_factory=Permissions)
    # Distributions the app imports that the platform does not promise, as requirement
    # strings. Checked against what is installed; never installed by the platform.
    python_dependencies: tuple[str, ...] = ()

    @property
    def import_name(self) -> str:
        """The Python module an installed copy is imported as: `map-editor` is `map_editor`."""
        return self.name.replace("-", "_")

    @property
    def table_prefix(self) -> str:
        return table_prefix(self.name)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        permissions: Mapping[str, Any] | None = None,
        source: str = "",
    ) -> AppManifest:
        name = cls._required(data, "name", source)
        version = cls._required(data, "version", source)

        if not NAME.match(name):
            raise ManifestError(
                f"{cls._where(source)}: '{name}' is not a usable app name. "
                "Use lower-case letters, digits, '-' and '_', starting with a letter."
            )

        requires = data.get("requires_platform", ANY_PLATFORM)
        if not isinstance(requires, str) or not requires.strip():
            raise ManifestError(
                f"{cls._where(source)}: requires_platform must be a version range such as "
                f"'>=1.2,<2', or be left out entirely."
            )

        return cls(
            name=name,
            version=version,
            requires_platform=requires.strip(),
            source=source,
            permissions=Permissions.from_mapping(permissions, source=source),
            python_dependencies=cls._dependencies(data, source),
        )

    @classmethod
    def _dependencies(cls, data: Mapping[str, Any], source: str) -> tuple[str, ...]:
        value = data.get("python_dependencies", [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ManifestError(
                f"{cls._where(source)}: python_dependencies must be a list of requirements "
                "such as \"jsonschema>=4.23\"."
            )
        for requirement in value:
            try:
                Requirement(requirement)
            except InvalidRequirement as broken:
                raise ManifestError(
                    f"{cls._where(source)}: {requirement!r} is not a requirement ({broken})."
                ) from broken
        return tuple(value)

    @staticmethod
    def _where(source: str) -> str:
        return source or "manifest"

    @classmethod
    def _required(cls, data: Mapping[str, Any], field: str, source: str) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"{cls._where(source)}: '{field}' is required and must be text.")
        return value.strip()
