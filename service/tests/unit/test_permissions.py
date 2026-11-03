"""AC-6 and AC-10 below any adapter: what a `[permissions]` table may say, and the rules that
decide whether a route or a table is a plugin's.

Plain functions over names and paths. The adapters gather the facts; these decide.
"""

from __future__ import annotations

import pytest

from wavemaker.platform.kernel.errors import DuplicateAppError, ManifestError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.kernel.permissions import (
    Permissions,
    is_own,
    refused_routes,
    route_is_allowed,
    table_prefix,
)
from wavemaker.platform.kernel.registry import AppRegistry

INVENTORY_ROUTES = [
    "/api/v1/admin/items",
    "/api/v1/admin/item-schema",
    "/api/v1/admin/players/{player_id}/inventory",
    "/api/v1/player/me/inventory",
]


def test_ac10_no_permissions_table_means_the_narrowest_grant() -> None:
    granted = AppManifest.from_mapping({"name": "maps", "version": "1.0.0"}).permissions
    assert granted == Permissions()
    assert granted.outbound_http is False, "the network is off unless asked for"
    assert granted.routes == ()


def test_ac10_a_full_permissions_table_is_read() -> None:
    granted = Permissions.from_mapping(
        {
            "tables": "own",
            "routes": ["/api/v1/admin/maps"],
            "events": {"publish": ["map.saved"], "subscribe": ["content.wave_published"]},
            "storage": {"blobs": True, "quota_mb": 500},
            "outbound_http": True,
        }
    )
    assert granted.routes == ("/api/v1/admin/maps",)
    assert granted.publishes == ("map.saved",)
    assert granted.subscribes == ("content.wave_published",)
    assert (granted.blobs, granted.quota_mb, granted.outbound_http) == (True, 500, True)


@pytest.mark.parametrize(
    ("permissions", "named"),
    [
        ({"outbound_htpp": False}, "outbound_htpp"),
        ({"tables": "all"}, "tables"),
        ({"tables": ["inventory_item", "player"]}, "tables"),
        ({"outbound_http": "no"}, "outbound_http"),
        ({"routes": "/api/v1/admin"}, "routes"),
        ({"storage": {"quota_mb": 0}}, "quota_mb"),
        ({"events": {"publish": ["no dots"]}}, "no dots"),
    ],
)
def test_ac10_a_permission_that_is_not_one_is_refused(
    permissions: dict[str, object], named: str
) -> None:
    """A typo quietly falling back to a default is how a grant nobody made ends up made."""
    with pytest.raises(ManifestError) as refused:
        Permissions.from_mapping(permissions, source="maps/manifest.toml")
    assert named in str(refused.value)
    assert "maps/manifest.toml" in str(refused.value)


@pytest.mark.parametrize(
    "route",
    [
        "/api/v1",
        "/api/v1/",
        "/api/v1/{anything}",
        "/api/v2/maps",
        "/admin/maps",
        "api/v1/maps",
        "/api/v1/maps/",
        "/api/v1//maps",
        "/api/v1/../admin",
        "/api/v1/maps/{bad name}",
    ],
)
def test_ac10_a_declared_route_must_be_a_fixed_path_under_the_api(route: str) -> None:
    """A prefix that is the whole API, or begins with a parameter, is every app's path."""
    with pytest.raises(ManifestError):
        Permissions.from_mapping({"routes": [route]})


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/api/v1/inventory", True),
        ("/api/v1/inventory/things/{id}", True),
        ("/api/v1/admin/items", True),
        ("/api/v1/admin/items/{item_id}", True),
        ("/api/v1/admin/item-schema", True),
        ("/api/v1/admin/players/{player_id}/inventory", True),
        ("/api/v1/admin/players/{id}/inventory/grant", True),
        ("/api/v1/player/me/inventory", True),
        # Another app's paths, and the near misses a string prefix would let through.
        ("/api/v1/admin/waves", False),
        ("/api/v1/admin/players/{player_id}/wallet", False),
        ("/api/v1/admin/items-and-more", False),
        ("/api/v1/inventory-evil/x", False),
        ("/api/v1/player/me/wallet", False),
        ("/api/v1/admin/{anything}", False),
        ("/api/v1/admin/players/{id}", False),
        ("/health", False),
    ],
)
def test_ac6_a_route_is_allowed_only_under_a_granted_prefix(path: str, allowed: bool) -> None:
    granted = Permissions.from_mapping({"routes": INVENTORY_ROUTES})
    prefixes = ("/api/v1/inventory", *granted.routes)
    assert route_is_allowed(path, prefixes) is allowed


def test_ac6_refused_routes_names_every_path_outside_the_grant() -> None:
    refused = refused_routes(
        "maps",
        Permissions(),
        ["/api/v1/maps/a", "/api/v1/admin/waves", "/api/v1/public/status", "/api/v1/maps"],
    )
    assert refused == ["/api/v1/admin/waves", "/api/v1/public/status"]


def test_ac7_a_table_is_an_apps_when_it_carries_the_apps_prefix() -> None:
    prefix = table_prefix("map-editor")
    assert prefix == "map_editor_", "a hyphen cannot appear in an unquoted SQL name"
    assert is_own("map_editor_tile", prefix)
    assert not is_own("map_editor_", prefix), "the bare prefix is not a table name"
    assert not is_own("map_tile", prefix)
    assert not is_own("player", prefix)


def test_ac5_a_plugin_is_imported_under_its_name_with_hyphens_made_underscores() -> None:
    manifest = AppManifest.from_mapping({"name": "map-editor", "version": "1.0.0"})
    assert manifest.import_name == "map_editor"
    assert manifest.table_prefix == "map_editor_"


def test_ac4_two_apps_whose_table_prefixes_overlap_are_refused() -> None:
    """`inv` would own every table `inv-x` makes; the second to register is refused."""
    registry = AppRegistry(platform_version="0.1.0")
    registry.register(AppManifest.from_mapping({"name": "inv", "version": "1.0.0"}))
    with pytest.raises(DuplicateAppError) as refused:
        registry.register(AppManifest.from_mapping({"name": "inv-x", "version": "1.0.0"}))
    assert "inv_" in str(refused.value)
    assert "inv_x_" in str(refused.value)


def test_ac4_a_python_dependency_that_is_not_a_requirement_is_refused() -> None:
    with pytest.raises(ManifestError):
        AppManifest.from_mapping(
            {"name": "maps", "version": "1.0.0", "python_dependencies": ["not a requirement!"]}
        )
