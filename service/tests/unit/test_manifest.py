"""AC-4, AC-5 at the level below the loader: what a manifest is allowed to say.

A manifest is read from a file someone else wrote, so every field it declares is untrusted
input. These tests fix the shape before any file is involved.
"""

import pytest

from wavemaker.platform.kernel.errors import ManifestError
from wavemaker.platform.kernel.manifest import AppManifest


def test_ac3_a_manifest_carries_a_name_a_version_and_a_platform_range() -> None:
    manifest = AppManifest.from_mapping(
        {"name": "inventory", "version": "1.0.0", "requires_platform": ">=0.1"},
        source="inventory/manifest.toml",
    )
    assert manifest.name == "inventory"
    assert manifest.version == "1.0.0"
    assert manifest.requires_platform == ">=0.1"
    assert manifest.source == "inventory/manifest.toml"


def test_ac3_a_manifest_that_names_no_platform_range_accepts_any() -> None:
    """An omitted range means "I have not thought about it", which must not mean "refuse me"."""
    manifest = AppManifest.from_mapping({"name": "inventory", "version": "1.0.0"})
    assert manifest.requires_platform == "*"


@pytest.mark.parametrize(
    ("data", "missing"),
    [({"version": "1.0.0"}, "name"), ({"name": "inventory"}, "version")],
)
def test_ac3_a_manifest_missing_a_required_field_is_refused(
    data: dict[str, str], missing: str
) -> None:
    with pytest.raises(ManifestError) as refused:
        AppManifest.from_mapping(data, source="somewhere/manifest.toml")
    assert missing in str(refused.value)
    assert "somewhere/manifest.toml" in str(refused.value), "the error must name the file"


@pytest.mark.parametrize("name", ["", "   ", "Inventory", "my app", "../escape"])
def test_ac3_a_name_that_is_not_a_plain_slug_is_refused(name: str) -> None:
    """The name becomes a route prefix and a table prefix, so it cannot be arbitrary text."""
    with pytest.raises(ManifestError):
        AppManifest.from_mapping({"name": name, "version": "1.0.0"})
