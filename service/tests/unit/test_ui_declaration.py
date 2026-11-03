"""R8: the `[ui]` table, read as strictly as `[permissions]`.

A plugin's screen is found through this declaration, so a mistake in it must be an error that
names the field — not a plugin whose screen silently never appears.
"""

from __future__ import annotations

from typing import Any

import pytest

from wavemaker.platform.kernel.errors import ManifestError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.kernel.ui import UiDeclaration


def manifest(ui: Any) -> AppManifest:
    return AppManifest.from_mapping({"name": "bulletin", "version": "1.0.0"}, ui=ui)


def test_r8_an_app_with_no_ui_table_has_no_screen() -> None:
    assert manifest(None).ui is None


def test_r8_the_entry_defaults_to_module_js_and_the_interface_version_is_kept() -> None:
    assert manifest({"api": 2}).ui == UiDeclaration(entry="module.js", api=2)
    assert manifest({"entry": "screen.mjs", "api": 3}).ui == UiDeclaration(
        entry="screen.mjs", api=3
    )
    assert UiDeclaration(entry="module.js", api=2).path == "ui/module.js"


@pytest.mark.parametrize(
    "ui",
    [
        {"api": 2, "entyr": "module.js"},
        {"entry": "module.js"},
        {"api": "2"},
        {"api": True},
        {"api": 0},
        "module.js",
    ],
)
def test_r8_a_malformed_ui_table_is_refused(ui: Any) -> None:
    with pytest.raises(ManifestError, match=r"\[ui\]"):
        manifest(ui)


@pytest.mark.parametrize(
    "entry",
    ["../backend/__init__.py", "nested/module.js", "/module.js", "module.html", ".module.js", ""],
)
def test_r8_the_entry_is_one_javascript_file_directly_under_ui(entry: str) -> None:
    with pytest.raises(ManifestError, match="entry"):
        manifest({"entry": entry, "api": 2})
