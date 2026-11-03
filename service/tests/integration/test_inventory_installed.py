"""AC-9, the issue's first done-criterion: a service with no `inventory` folder installs the
inventory package and serves inventory.

"No inventory folder" is taken literally. The test copies the `wavemaker` package to a
temporary directory *without* `apps/inventory`, and runs a separate Python process with only
that copy importable as `wavemaker` — so nothing it does can reach the built-in code, and the
process checks that for itself before it starts. The package it installs is built in this test
from the real `apps/inventory/` folder, signed, and published to a registry directory.

In that process: `wavemaker plugin install inventory@1.0.0` verifies and installs it, and runs
its migrations; then the service starts with the plugins directory, and an editor defines an
item, grants it to a player, and the player reads it back — real routes over real PostgreSQL.

The platform's history still carries `0005_inventory`, which cannot be edited, so on this
database the tables were made by the platform before the plugin arrived, and the plugin's own
history adopts them. That those two builds are identical is proved separately, in
`test_app_migrations.py`, on a database that never ran 0005.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from sqlalchemy import create_engine, text

import wavemaker
import wavemaker.apps.inventory
from tests.integration.players import PASSWORD, SECRET
from tests.integration.plugin_kit import Publisher

INVENTORY = Path(wavemaker.apps.inventory.__file__).resolve().parent
PACKAGE = Path(wavemaker.__file__).resolve().parent

SCRIPT = textwrap.dedent(
    """
    import importlib.util
    import json
    import sys
    from pathlib import Path

    import wavemaker

    arguments = json.loads(sys.argv[1])
    result = {
        "wavemaker_from": wavemaker.__file__,
        "builtin_inventory_importable": importlib.util.find_spec("wavemaker.apps.inventory")
        is not None,
    }

    from wavemaker.platform.cli import main

    result["install_status"] = main([
        "plugin", "install", "inventory@1.0.0",
        "--registry", arguments["registry"],
        "--plugins-dir", arguments["plugins"],
        "--trusted-keys", arguments["trusted"],
        "--database-url", arguments["url"],
    ])

    from fastapi.testclient import TestClient

    from wavemaker.platform.config import Settings
    from wavemaker.platform.http.factory import create_app

    app = create_app(Settings(
        plugins_directory=Path(arguments["plugins"]),
        database_url=arguments["url"],
        jwt_secret=arguments["secret"],
        admin_email="admin@example.test",
        admin_password=arguments["password"],
    ))

    with TestClient(app) as client:
        signed_in = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.test", "password": arguments["password"]},
        )
        admin = {"Authorization": "Bearer " + signed_in.json()["accessToken"]}

        saved = client.put(
            "/api/v1/admin/items/sword",
            json={"name": "Sword", "itemType": "weapon", "spriteRef": "sprites/sword",
                  "attributes": '{"damage": 7}'},
            headers=admin,
        )
        listed = client.get("/api/v1/admin/items", headers=admin)

        key = client.post("/api/v1/admin/api-keys", json={"name": "game"}, headers=admin)
        session = client.post(
            "/api/v1/public/players/session",
            json={"externalId": "device-1"},
            headers={"X-API-Key": key.json()["key"]},
        ).json()
        granted = client.post(
            "/api/v1/admin/players/" + session["playerId"] + "/inventory/grant",
            json={"items": [{"itemId": "sword", "quantity": 2}]},
            headers=admin,
        )
        held = client.get(
            "/api/v1/player/me/inventory",
            headers={"Authorization": "Bearer " + session["token"]},
        )
        health = client.get("/health").json()

    result.update({
        "saved": [saved.status_code, saved.json()],
        "listed": [listed.status_code, listed.json()],
        "granted": granted.status_code,
        "held": [held.status_code, held.json()],
        "health": health,
        "inventory_module_file": sys.modules["inventory"].__file__,
        "builtin_inventory_loaded": "wavemaker.apps.inventory" in sys.modules,
    })
    print(json.dumps(result))
    """
)


def service_without_inventory(root: Path) -> Path:
    """The `wavemaker` package as it ships, minus the inventory app."""
    copy = root / "site"
    shutil.copytree(PACKAGE, copy / "wavemaker", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.rmtree(copy / "wavemaker" / "apps" / "inventory")
    return copy


def test_ac9_a_service_with_no_inventory_folder_installs_the_package_and_serves_inventory(
    tmp_path: Path, isolated_database_url: str
) -> None:
    publisher = Publisher(tmp_path / "publishing")
    published = publisher.publish_folder(INVENTORY)
    assert published.file == "inventory-1.0.0.wmp"

    site = service_without_inventory(tmp_path)
    runner = tmp_path / "runner"
    runner.mkdir()
    (runner / "serve_installed.py").write_text(SCRIPT)
    arguments = {
        "registry": str(publisher.registry),
        "plugins": str(tmp_path / "plugins"),
        "trusted": str(publisher.trusted),
        "url": isolated_database_url,
        "secret": SECRET,
        "password": PASSWORD,
    }

    completed = subprocess.run(
        [sys.executable, str(runner / "serve_installed.py"), json.dumps(arguments)],
        cwd=runner,
        env={**os.environ, "PYTHONPATH": str(site)},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    # The process really had no inventory of its own.
    assert Path(result["wavemaker_from"]).is_relative_to(site)
    assert result["builtin_inventory_importable"] is False
    assert result["builtin_inventory_loaded"] is False

    # It installed the package, and serves inventory from the installed copy.
    assert result["install_status"] == 0
    assert Path(result["inventory_module_file"]).is_relative_to(tmp_path / "plugins" / "inventory")
    assert {"name": "inventory", "version": "1.0.0"} in result["health"]["apps"]

    status, item = result["saved"]
    assert status == 200, item
    assert item["id"] == "sword"
    assert item["attributes"] == '{"damage": 7}'
    assert [listed["id"] for listed in result["listed"][1]] == ["sword"]
    assert result["granted"] == 200
    status, held = result["held"]
    assert status == 200
    assert [(entry["itemId"], entry["quantity"]) for entry in held["items"]] == [("sword", 2)]

    # Its own history ran, in its own version table, and it owns its tables.
    engine = create_engine(isolated_database_url)
    with engine.connect() as connection:
        version = connection.execute(
            text("select version_num from inventory_alembic_version")
        ).scalar_one()
        owned = set(
            connection.execute(
                text("select object from wavemaker_app_object where app = 'inventory'")
            ).scalars()
        )
    engine.dispose()
    assert version == "0001"
    assert {
        "relation public.inventory_item",
        "relation public.inventory_entry",
        "relation public.inventory_item_schema",
    } <= owned
