"""AC-2, AC-3, AC-4: reading manifests off a real disk.

Parsing is an adapter's job, not the kernel's — the kernel never opens a file. These tests use
a real directory for that reason; a mocked filesystem would test the mock.
"""

from pathlib import Path

import pytest

from wavemaker.platform.kernel.errors import ManifestError
from wavemaker.platform.plugins.loader import load_manifests


def write_plugin(root: Path, name: str, body: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "manifest.toml").write_text(body)
    return directory


def test_ac2_no_plugins_directory_configured_loads_nothing_and_does_not_fail() -> None:
    """Today's state. It must stay a working service with zero apps."""
    assert load_manifests(None) == []


def test_ac3_every_plugin_directory_with_a_manifest_is_read(tmp_path: Path) -> None:
    write_plugin(tmp_path, "inventory", '[plugin]\nname = "inventory"\nversion = "1.0.0"\n')
    write_plugin(tmp_path, "economy", '[plugin]\nname = "economy"\nversion = "2.1.0"\n')

    manifests = load_manifests(tmp_path)

    assert sorted(m.name for m in manifests) == ["economy", "inventory"]
    assert {m.version for m in manifests} == {"1.0.0", "2.1.0"}


def test_ac3_a_manifest_records_the_file_it_came_from(tmp_path: Path) -> None:
    """Without this, a duplicate or a bad range cannot say which plugin to go and fix."""
    write_plugin(tmp_path, "inventory", '[plugin]\nname = "inventory"\nversion = "1.0.0"\n')
    [manifest] = load_manifests(tmp_path)
    assert manifest.source.endswith("inventory/manifest.toml")


def test_ac3_a_directory_without_a_manifest_is_skipped(tmp_path: Path) -> None:
    """A stray folder is not a broken plugin — it is not a plugin."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "README.md").write_text("nothing to see")
    write_plugin(tmp_path, "inventory", '[plugin]\nname = "inventory"\nversion = "1.0.0"\n')

    assert [m.name for m in load_manifests(tmp_path)] == ["inventory"]


def test_ac4_a_manifest_that_is_not_valid_toml_names_the_file(tmp_path: Path) -> None:
    write_plugin(tmp_path, "broken", "[plugin\nname =")
    with pytest.raises(ManifestError) as refused:
        load_manifests(tmp_path)
    assert "broken/manifest.toml" in str(refused.value)


def test_ac4_a_manifest_without_a_plugin_table_names_the_file(tmp_path: Path) -> None:
    write_plugin(tmp_path, "empty", 'title = "I am not a manifest"\n')
    with pytest.raises(ManifestError) as refused:
        load_manifests(tmp_path)
    assert "empty/manifest.toml" in str(refused.value)


def test_ac2_a_configured_directory_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    """Unset means "no plugins". A path that was set and is wrong is a mistake worth hearing."""
    missing = tmp_path / "nowhere"
    with pytest.raises(ManifestError) as refused:
        load_manifests(missing)
    assert str(missing) in str(refused.value)
