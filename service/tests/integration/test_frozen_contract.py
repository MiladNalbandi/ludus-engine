"""The `v1.0.0` promise, checked against the Python service: the whole frozen document, walked.

`docs/api/openapi-v1.json` is the HTTP contract as it was frozen at 1.0.0. While the Java engine
was in this repository, its `FrozenContractTest` compared the Java's generated document with
that file and failed on anything a client could break on: a removed path or operation, a
removed property, a removed enum value, an optional field made required. This is the same
promise held by the service that replaces it.

A document-to-document comparison cannot be ported as it stood. The Python builds most bodies
by hand rather than from response models — so stored bytes go out untouched and every field
is spelled the way the contract spells it — and FastAPI's generated document therefore names
almost no schemas. Comparing it with the frozen one would prove nothing either way. So the
checks are made against what the service actually does:

1. **Every operation is routed.** For each of the frozen document's operations, the request a
   client would send is dispatched by the service's own router to a route of that method and
   that path, not to a neighbour that happens to match first, and the route's operation id is
   the contract's wherever the route sets one.
2. **Every operation answers, and every schema is still there.** One walk through a real
   service on a real PostgreSQL calls every operation at the contract's own path. Each request
   body carries exactly the properties its frozen schema lists, so no property a client sends
   has stopped being accepted; each response is held to its frozen schema, so no property a
   client reads has gone missing or changed type; every conditional read answers its own ETag
   with a 304. The walk then asserts that it called every operation and met every schema, so
   an operation or a schema added to nothing here cannot quietly go unchecked.
3. **No optional field was made required.** The fields the Java genuinely accepted missing are
   sent missing, and are still accepted.
4. **No enum value was removed.** The frozen document has no enums; the check is written anyway
   and says so, rather than being silently absent.

Adding paths, operations, optional properties and enum values is not breaking, and nothing here
complains about any of it. When this fails and the change is genuinely wanted, the answer is a
major version and a new frozen baseline, not an edit to this file.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response

from wavemaker.apps.media import media_settings
from wavemaker.apps.media.adapters.settings import MediaSettings
from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.identity.accounts import ensure_account
from wavemaker.platform.identity.tokens import Role

ROOT = Path(__file__).resolve().parents[3]
CONTRACT: dict[str, Any] = json.loads((ROOT / "docs" / "api" / "openapi-v1.json").read_text())
SCHEMAS: dict[str, dict[str, Any]] = CONTRACT["components"]["schemas"]
SAMPLES = ROOT / "samples" / "waves"

SECRET = "a-frozen-contract-test-signing-key-of-respectable-length"  # keel:allow-secret
ADMIN = "admin@example.test"
EDITOR = "editor@example.test"
PASSWORD = "correct-horse-battery-staple"  # keel:allow-secret

# What the frozen document holds, counted, so a truncated or swapped file fails loudly here
# rather than as a walk that checks less than it claims to.
FROZEN_OPERATIONS = 70
FROZEN_SCHEMAS = 46

# A path segment no route spells literally, standing in for every path parameter.
PLACEHOLDER = "zz_placeholder"


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    spec: dict[str, Any]


def operations() -> list[Operation]:
    return [
        Operation(method.upper(), path, spec["operationId"], spec)
        for path, methods in CONTRACT["paths"].items()
        for method, spec in methods.items()
    ]


BY_ID = {operation.operation_id: operation for operation in operations()}


def shape(path: str) -> str:
    """A path with its parameters' names erased: `/waves/{id}` and `/waves/{wave_id}` are one
    path to a client, which sends a value and never a name."""
    return re.sub(r"\{[^}]*\}", "{}", path)


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]*\}", PLACEHOLDER, path)


def test_the_frozen_document_is_the_one_this_was_written_against() -> None:
    assert len(operations()) == FROZEN_OPERATIONS
    assert len(SCHEMAS) == FROZEN_SCHEMAS
    assert len(BY_ID) == FROZEN_OPERATIONS, "operation ids are unique"


# --- 1. every operation is routed -----------------------------------------------------------


class Dispatcher:
    """A service with every built-in app loaded, asked which route answered a request.

    The request really is sent, through the service's own router, and the route is read back
    from the request's scope where FastAPI records it. Matching paths here instead would be a
    second router that ought to agree with the real one. No database: what is mounted does not
    depend on one, so every route answers 503 or 401 before touching anything, and the claim
    is only about who answered."""

    def __init__(self) -> None:
        self.app = create_app(Settings(plugins_directory=None))
        self.route: APIRoute | None = None
        self.client = TestClient(self._recording)

    async def _recording(self, scope: Any, receive: Any, send: Any) -> None:
        await self.app(scope, receive, send)
        if scope["type"] == "http":
            route = scope.get("route")
            self.route = route if isinstance(route, APIRoute) else None

    def __call__(self, method: str, path: str) -> APIRoute | None:
        self.route = None
        self.client.request(method, path)
        return self.route


@pytest.fixture(scope="module")
def dispatched() -> Dispatcher:
    return Dispatcher()


@pytest.mark.parametrize(
    "operation", operations(), ids=lambda operation: f"{operation.method} {operation.path}"
)
def test_every_frozen_operation_is_routed_to_its_own_method_and_path(
    dispatched: Dispatcher, operation: Operation
) -> None:
    route = dispatched(operation.method, concrete(operation.path))

    assert route is not None, f"{operation.operation_id}: nothing serves this"
    # A literal path captured by a neighbour's parameter — `/waves/next-order` answered by
    # `/waves/{id}` — is routed, and wrong.
    assert shape(route.path) == shape(operation.path), (
        f"{operation.operation_id}: answered by {route.path} instead"
    )
    # Generated clients name their methods after the operation id. A route that sets one must
    # set the contract's; one that leaves FastAPI to generate it is reported in r9.md.
    assert route.operation_id in (None, operation.operation_id)


# --- 2. the walk ------------------------------------------------------------------------------


def schema_of(reference: dict[str, Any]) -> str | None:
    return reference["$ref"].rsplit("/", 1)[-1] if "$ref" in reference else None


TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def has_type(value: Any, wanted: str) -> bool:
    if wanted in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, TYPES[wanted])


@dataclass
class Walk:
    """A client of the whole contract that records what it touched.

    `call` sends one operation by its operation id, to the path the frozen document gives it,
    and checks the request it sent and the response it got against the document."""

    client: TestClient
    called: set[str] = field(default_factory=set)
    schemas: set[str] = field(default_factory=set)
    enum_values: dict[str, set[str]] = field(default_factory=dict)

    def call(
        self,
        operation_id: str,
        *,
        path: dict[str, str] | None = None,
        json: Any = None,
        content: bytes | None = None,
        files: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        minimal: bool = False,
    ) -> Response:
        operation = BY_ID[operation_id]
        url = operation.path.format(**(path or {}))
        declared = {p["name"] for p in operation.spec.get("parameters", []) if p["in"] == "query"}
        assert set(params or {}) <= declared, f"{operation_id} declares only {declared}"

        if json is not None:
            self.request(operation_id, json, minimal=minimal)
        sent_headers = dict(headers or {})
        if content is not None:
            sent_headers.setdefault("Content-Type", "application/json")

        response: Response = self.client.request(
            operation.method,
            url,
            json=json,
            content=content,
            files=files,
            params=params,
            headers=sent_headers,
        )
        assert 200 <= response.status_code < 300, (
            f"{operation_id}: {response.status_code} {response.text}"
        )
        self.called.add(operation_id)
        self.response(operation, response)

        # The frozen document declares If-None-Match on exactly the reads a client caches, so
        # each of them is revalidated here: the tag it just sent must buy a 304 and no body.
        if any(p["name"] == "If-None-Match" for p in operation.spec.get("parameters", [])):
            tag = response.headers.get("ETag")
            assert tag, f"{operation_id} sends no ETag"
            again = self.client.request(
                operation.method, url, params=params, headers={**sent_headers, "If-None-Match": tag}
            )
            assert again.status_code == 304, f"{operation_id} does not revalidate"
            assert again.content == b""
        return response

    def request(self, operation_id: str, body: Any, *, minimal: bool) -> None:
        content = BY_ID[operation_id].spec["requestBody"]["content"]
        schema = next(iter(content.values()))["schema"]
        name = schema_of(schema)
        assert name is not None, f"{operation_id} takes no JSON object"
        self.sent(name, body, minimal=minimal)

    def sent(self, name: str, body: dict[str, Any], *, minimal: bool) -> None:
        """A request body must carry every property its frozen schema lists — that is what
        proves each one is still accepted — unless it is deliberately minimal, to prove an
        optional one stayed optional. Either way it carries nothing the schema does not."""
        properties = SCHEMAS[name].get("properties", {})
        assert set(body) <= set(properties), f"{name} has no {set(body) - set(properties)}"
        if minimal:
            return
        assert set(body) == set(properties), f"send every property of {name}"
        self.schemas.add(name)
        for key, value in body.items():
            self._nested(properties[key], value, lambda n, v: self.sent(n, v, minimal=False))

    def response(self, operation: Operation, response: Response) -> None:
        documented = operation.spec.get("responses", {}).get("200", {}).get("content", {})
        if not documented or response.status_code == 204:
            return
        schema = next(iter(documented.values()))["schema"]
        name = schema_of(schema)
        if name == "StreamingResponseBody":
            assert response.content, f"{operation.operation_id} streamed nothing"
            self.schemas.add(name)
            return
        if name is None and schema.get("type") == "string":
            return  # stored bytes, compared byte for byte by the step that sent them
        self._value(schema, response.json(), operation.operation_id)

    def _value(self, schema: dict[str, Any], value: Any, where: str) -> None:
        name = schema_of(schema)
        if name is not None:
            self.received(name, value)
        elif schema.get("type") == "array":
            assert isinstance(value, list), f"{where} is not an array"
            for element in value:
                self._value(schema["items"], element, where)
        else:
            assert has_type(value, schema["type"]), f"{where} is not {schema['type']}: {value!r}"

    def received(self, name: str, body: Any) -> None:
        """Every property the frozen schema lists, each of the type it lists or null. More is
        allowed: adding a field breaks no client."""
        assert isinstance(body, dict), f"{name} is not an object: {body!r}"
        properties = SCHEMAS[name].get("properties", {})
        missing = set(properties) - set(body)
        assert not missing, f"{name} lost {sorted(missing)}"
        self.schemas.add(name)
        for key, spec in properties.items():
            value = body[key]
            if value is None:
                continue
            if "type" in spec:
                assert has_type(value, spec["type"]), f"{name}.{key} is not {spec['type']}"
            if "enum" in spec:
                self.enum_values.setdefault(f"{name}.{key}", set()).add(str(value))
                assert str(value) in spec["enum"], f"{name}.{key} = {value} is not in its enum"
            self._nested(spec, value, self.received)

    @staticmethod
    def _nested(spec: dict[str, Any], value: Any, check: Any) -> None:
        if value is None:
            return
        name = schema_of(spec)
        if name is not None:
            check(name, value)
        elif spec.get("type") == "array" and isinstance(value, list):
            inner = schema_of(spec.get("items", {}))
            if inner is not None:
                for element in value:
                    check(inner, element)


def sample(name: str, wave_id: str | None = None, order: int | None = None) -> bytes:
    """A shipped sample, renamed and moved when asked, sent as compact bytes so "the bytes
    came back unchanged" is a real claim."""
    document: dict[str, Any] = json.loads((SAMPLES / f"{name}.json").read_text())
    if wave_id is not None:
        document["id"] = wave_id
    if order is not None:
        document["progression_config"]["order"] = order
    return json.dumps(document, separators=(",", ":")).encode()


def stand_in_ffmpeg(directory: Path) -> Path:
    """Takes FFmpeg's place, so the mix is part of the walk without FFmpeg on this machine."""
    binary = directory / "ffmpeg"
    binary.write_text(
        f"#!{sys.executable}\nimport pathlib, sys\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'OggS' + b'mixed' * 100)\n"
    )
    binary.chmod(0o755)
    return binary


@pytest.fixture
def walk(database_url: str, tmp_path: Path) -> Iterator[Walk]:
    app = create_app(
        Settings(
            plugins_directory=None,
            database_url=database_url,
            jwt_secret=SECRET,
            admin_email=ADMIN,
            admin_password=PASSWORD,
            blob_directory=tmp_path / "blobs",
        )
    )
    mixing = MediaSettings(ffmpeg_binary=stand_in_ffmpeg(tmp_path))
    app.dependency_overrides[media_settings] = lambda: mixing
    with app.state.session_factory() as session:
        ensure_account(session, app.state.project_id, EDITOR, PASSWORD, Role.EDITOR)
    with TestClient(app) as client:
        yield Walk(client)


OGG = b"OggS" + bytes(range(256)) * 8
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4

ITEM_SCHEMA = json.dumps(
    {"type": "object", "properties": {"damage": {"type": "integer"}}, "additionalProperties": False}
)


def test_the_whole_contract_is_served_and_every_schema_is_kept(walk: Walk) -> None:
    w = walk

    # --- identity ----------------------------------------------------------------------------
    tokens = w.call("signIn", json={"email": ADMIN, "password": PASSWORD}).json()
    w.call("refreshSession", json={"refreshToken": tokens["refreshToken"]})
    admin = {"Authorization": f"Bearer {tokens['accessToken']}"}
    caller = w.call("currentCaller", headers=admin).json()
    assert (caller["kind"], caller["role"]) == ("USER", "ADMIN"), "the values v1 clients got"
    editor_tokens = w.client.post(
        "/api/v1/auth/token", json={"email": EDITOR, "password": PASSWORD}
    ).json()
    editor = {"Authorization": f"Bearer {editor_tokens['accessToken']}"}

    # --- authoring waves ---------------------------------------------------------------------
    assert w.call("nextWaveOrder", headers=editor).json() == 0
    first = sample("demo_first_steps")
    w.call("createWave", content=first, headers=editor)
    imported = b"[" + sample("demo_crossfire") + b"," + sample("demo_pressure") + b"]"
    w.call("importWaves", content=imported, headers=editor)
    extra = sample("demo_first_steps", "doomed", 50)
    w.client.post("/api/v1/admin/waves", content=extra, headers=editor)
    w.call("listWaves", headers=editor)
    stored = w.call("getWaveDocument", path={"id": "demo_first_steps"}, headers=editor)
    assert stored.content == first
    w.call("replaceWave", path={"id": "demo_first_steps"}, content=first, headers=editor)
    for wave_id in ("demo_first_steps", "demo_crossfire", "demo_pressure"):
        w.call("publishWave", path={"id": wave_id}, headers=editor)
    w.call("unpublishWave", path={"id": "demo_pressure"}, headers=editor)

    # --- what a client reads -----------------------------------------------------------------
    w.call("contentStatus")
    w.call("listPublishedWaves")
    w.call("getPublishedWave", path={"id": "demo_first_steps"})
    raw = w.call("getPublishedWaveDocument", path={"id": "demo_first_steps"})
    assert raw.content == first
    batch = w.call("batchGetPublishedWaves", json={"ids": ["demo_first_steps", "demo_pressure"]})
    assert list(batch.json()) == ["demo_first_steps"], "a draft is absent from a batch"

    # --- levels ------------------------------------------------------------------------------
    level = w.call(
        "createWaveLevel",
        json={"name": "Act One", "description": "Opening", "waves": ["demo_first_steps"]},
        headers=editor,
    ).json()
    w.call(
        "createWaveLevel",
        json={"name": "No description", "waves": []},
        headers=editor,
        minimal=True,
    )
    w.call("listWaveLevels", headers=editor)
    w.call("getWaveLevel", path={"id": level["id"]}, headers=editor)
    w.call(
        "updateWaveLevel",
        path={"id": level["id"]},
        json={
            "name": "Act One",
            "description": "Opening",
            "waves": ["demo_first_steps", "demo_crossfire", "demo_pressure"],
        },
        headers=editor,
    )
    w.call("activateWaveLevel", path={"id": level["id"]}, headers=editor)
    playable = w.call("getActiveWaveLevel").json()
    assert [wave["id"] for wave in playable["waves"]] == ["demo_first_steps", "demo_crossfire"]

    # --- application configuration -----------------------------------------------------------
    config = b'{"difficulty":"normal", "lives":3}'
    assert w.call("replaceAppConfig", content=config, headers=editor).content == config
    assert w.call("getAppConfig", headers=editor).content == config
    assert w.call("getPublicAppConfig").content == config

    # --- API keys and players ----------------------------------------------------------------
    key = w.call("createApiKey", json={"name": "android-client"}, headers=admin).json()
    w.call("listApiKeys", headers=admin)
    session = w.call(
        "startPlayerSession", json={"externalId": "device-0001"}, headers={"X-API-Key": key["key"]}
    ).json()
    player = {"Authorization": f"Bearer {session['token']}"}
    player_id = {"id": session["playerId"]}
    w.call("getPlayerSelf", headers=player)
    w.call("renamePlayerSelf", json={"displayName": "Ada"}, headers=player)

    # --- economy -----------------------------------------------------------------------------
    grant = {"currency": "coins", "amount": 50}
    w.call("grantPlayerCurrency", path=player_id, json=grant, headers=admin)
    w.call("getPlayerWallet", headers=player)
    w.call("spendPlayerCurrency", json={"currency": "coins", "amount": 5}, headers=player)
    w.call("getPlayerWalletAsAdmin", path=player_id, headers=admin)

    # --- inventory ---------------------------------------------------------------------------
    w.call("replaceItemSchema", content=ITEM_SCHEMA.encode(), headers=editor)
    assert w.call("getItemSchema", headers=editor).content == ITEM_SCHEMA.encode()
    sword = {
        "name": "Sword",
        "itemType": "weapon",
        "spriteRef": "sprites/sword",
        "attributes": '{"damage": 3}',
    }
    w.call("saveItem", path={"id": "sword"}, json=sword, headers=editor)
    w.call(
        "saveItem",
        path={"id": "pebble"},
        json={"name": "Pebble", "itemType": "misc"},
        headers=editor,
        minimal=True,
    )
    w.call("listItems", headers=editor)
    w.call("getItem", path={"id": "sword"}, headers=editor)
    w.call(
        "grantPlayerItems",
        path=player_id,
        json={"items": [{"itemId": "sword", "quantity": 2}]},
        headers=editor,
    )
    w.call("getPlayerInventory", headers=player)
    w.call("getPlayerInventoryAsAdmin", path=player_id, headers=editor)
    w.call("deleteItem", path={"id": "pebble"}, headers=editor)

    # --- leaderboards ------------------------------------------------------------------------
    board = {"boardId": "high_score"}
    w.call("saveLeaderboard", path=board, json={"name": "High", "descending": True}, headers=editor)
    w.call(
        "saveLeaderboard",
        path={"boardId": "doomed"},
        json={"name": "D"},
        headers=editor,
        minimal=True,
    )
    w.call("listLeaderboardsAsAdmin", headers=editor)
    w.call("listLeaderboards", headers=player)
    w.call("submitOwnScore", path=board, json={"score": 10}, headers=player)
    w.call("getOwnLeaderboardEntry", path=board, headers=player)
    w.call("getLeaderboardPage", path=board, params={"limit": 10}, headers=player)
    w.call("getLeaderboardPageAsAdmin", path=board, params={"limit": 10}, headers=editor)
    w.call("deleteLeaderboard", path={"boardId": "doomed"}, headers=editor)

    # --- progression -------------------------------------------------------------------------
    stages = [
        {"stage": 1, "xpRequired": 0, "label": "Novice"},
        {"stage": 2, "xpRequired": 100, "label": "Adept"},
        {"stage": 3, "xpRequired": 1000, "label": "Master"},
    ]
    w.call("replaceXpCurve", json={"stages": stages}, headers=editor)
    w.call("getXpCurve", headers=editor)
    w.call(
        "rewardPlayer",
        path=player_id,
        json={"grants": [{"currency": "gems", "amount": 1}], "xp": 150},
        headers=editor,
    )
    w.call("rewardPlayer", path=player_id, json={"xp": 1}, headers=editor, minimal=True)
    grants_only = {"grants": [{"currency": "gems", "amount": 1}]}
    w.call("rewardPlayer", path=player_id, json=grants_only, headers=editor, minimal=True)
    progress = w.call("getPlayerProgress", headers=player).json()
    assert progress["nextStage"] is not None, "a stage is still ahead, so nextStage is checked"
    w.call("listPlayers", params={"limit": 10}, headers=editor)
    w.call("getPlayer", path=player_id, headers=editor)

    # --- media -------------------------------------------------------------------------------
    clip = w.call(
        "uploadAudioClip", files={"file": ("a.ogg", OGG, "audio/ogg")}, headers=editor
    ).json()
    w.call("listAudioClips", headers=editor)
    assert w.call("streamAudioClip", path={"id": clip["id"]}).content == OGG
    w.call(
        "mixAudioClips",
        json={"filename": "boss.ogg", "tracks": [{"clipId": clip["id"], "gainDb": -6.0}]},
        headers=editor,
    )
    w.call(
        "mixAudioClips",
        json={"filename": "quiet.ogg", "tracks": [{"clipId": clip["id"]}]},
        headers=editor,
        minimal=True,
    )
    w.call("deleteAudioClip", path={"id": clip["id"]}, headers=editor)
    sprite = w.call(
        "uploadSprite", files={"file": ("s.png", PNG, "image/png")}, headers=editor
    ).json()
    w.call("listSprites", headers=editor)
    assert w.call("streamSprite", path={"id": sprite["id"]}).content == PNG
    w.call("deleteSprite", path={"id": sprite["id"]}, headers=editor)

    # --- the deletes, last, so everything above had something to read -----------------------
    w.call("batchDeleteWaves", json={"ids": ["doomed"]}, headers=editor)
    w.call("deleteWaveLevel", path={"id": level["id"]}, headers=editor)
    w.call("deleteWave", path={"id": "demo_pressure"}, headers=editor)
    w.call("revokeApiKey", path={"id": key["id"]}, headers=admin)

    # --- and nothing was missed --------------------------------------------------------------
    assert sorted(set(BY_ID) - w.called) == [], "every frozen operation was called"
    assert sorted(set(SCHEMAS) - w.schemas) == [], "every frozen schema was met"


def test_the_frozen_document_has_no_enum_to_lose() -> None:
    """A removed enum value breaks every client that sends it. The frozen document declares no
    enums — roles, kinds and content types are plain strings in it — so there is no value to
    lose, and the walk's enum check (in `Walk.received`) has nothing to hold. If a future
    baseline adds one, the walk starts checking it without a change here; this test is what
    would have to change, and it would say why."""
    enums = [
        f"{name}.{key}"
        for name, schema in SCHEMAS.items()
        for key, spec in schema.get("properties", {}).items()
        if "enum" in spec
    ]
    assert enums == []


def test_only_three_request_fields_are_required_and_the_walk_sends_them() -> None:
    """The Java's 'newly required' check, as the frozen document states it: the only request
    properties a client was ever obliged to send. The walk sends every request with exactly its
    schema's properties, and with fewer wherever the Java accepted fewer, so a field that became
    required here would fail it."""
    required = {
        name: sorted(schema["required"]) for name, schema in SCHEMAS.items() if "required" in schema
    }
    assert required == {
        "ApiKeyRequest": ["name"],
        "RefreshRequest": ["refreshToken"],
        "TokenRequest": ["email", "password"],
    }
