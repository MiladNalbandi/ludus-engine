"""AC-11: inventory is written as a package that could be installed from outside this repository.

R5 takes this folder out of the repository, publishes it, and installs it into a service that
has never seen it. That only works if nothing in the folder reaches outside it except to the
platform, and if nothing in it names where it lives. Both are read off the source, so a
convenient import added later fails here rather than in R5.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import wavemaker.apps.inventory

ROOT = Path(wavemaker.apps.inventory.__file__).resolve().parent


def imports() -> list[tuple[Path, int, str, int]]:
    """Every import in the package: file, line, module, and how many dots it starts with."""
    found: list[tuple[Path, int, str, int]] = []
    for source in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text(), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend((source, node.lineno, alias.name, 0) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.append((source, node.lineno, node.module or "", node.level))
    return found


def test_ac11_the_package_depends_on_the_platform_and_on_nothing_else_of_this_repository() -> None:
    outside = [
        f"{path.relative_to(ROOT)}:{line} imports {module}"
        for path, line, module, level in imports()
        if level == 0
        and module.split(".")[0] == "wavemaker"
        and not module.startswith("wavemaker.platform")
    ]
    assert outside == [], "an installed plugin has only the platform to lean on"


def test_ac11_the_package_does_not_name_where_it_is_installed() -> None:
    """Inside the package every import is relative, so moving it changes no line of it."""
    assert [
        module for _, _, module, level in imports() if level == 0 and "inventory" in module
    ] == []
    assert any(level > 0 for *_, level in imports()), "the check above must have something to see"


def test_ac11_the_package_reaches_no_file_outside_its_folder() -> None:
    """The content app finds its wave schema by walking up to the repository root, which is
    exactly what an installed package cannot do."""
    for source in ROOT.rglob("*.py"):
        assert "parents[" not in source.read_text(), source


def test_ac11_the_manifest_names_the_app_and_the_platform_it_needs() -> None:
    with (ROOT / "manifest.toml").open("rb") as handle:
        plugin = tomllib.load(handle)["plugin"]
    assert plugin["name"] == "inventory"
    assert plugin["version"] == "1.0.0"
    assert plugin["requires_platform"]
