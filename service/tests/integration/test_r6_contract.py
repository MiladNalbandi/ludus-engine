"""R6 AC-10 and the frozen contract: every R6 operation where the contract puts it, every body
spelled the way it spells it, and every new table belonging to a project.

Generated clients are built from the frozen document. An operation served at another path, or
a field renamed here, is a client broken in the field with nothing on this side failing.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.players import EDITOR, account, player, serving

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi-v1.json"

R6_OPERATIONS = {
    "listLeaderboards",
    "getLeaderboardPage",
    "getOwnLeaderboardEntry",
    "submitOwnScore",
    "listLeaderboardsAsAdmin",
    "getLeaderboardPageAsAdmin",
    "saveLeaderboard",
    "deleteLeaderboard",
    "getXpCurve",
    "replaceXpCurve",
    "getPlayerProgress",
    "rewardPlayer",
    "listPlayers",
    "getPlayer",
}

NEW_TABLES = ["leaderboard_board", "leaderboard_entry", "progression_stage", "progression_xp"]


def operations(document: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {
        operation["operationId"]: (method.upper(), path)
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
        if "operationId" in operation
    }


def fields_of(schema: str) -> set[str]:
    document: dict[str, Any] = json.loads(CONTRACT.read_text())
    return set(document["components"]["schemas"][schema]["properties"])


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def test_every_r6_operation_is_served_at_the_contracts_method_and_path(
    client: TestClient,
) -> None:
    frozen = operations(json.loads(CONTRACT.read_text()))
    served = operations(client.get("/openapi.json").json())
    for operation in sorted(R6_OPERATIONS):
        assert operation in frozen, f"{operation} is not in the contract"
        assert served.get(operation) == frozen[operation], operation


def test_every_r6_body_spells_its_fields_the_way_the_contract_does(client: TestClient) -> None:
    editor = account(client, EDITOR)
    headers, player_id = player(client)

    board = client.put(
        "/api/v1/admin/leaderboards/high_score", json={"name": "High"}, headers=editor
    ).json()
    entry = client.post(
        "/api/v1/player/leaderboards/high_score/me", json={"score": 10}, headers=headers
    ).json()
    page = client.get("/api/v1/player/leaderboards/high_score", headers=headers).json()
    curve = client.put(
        "/api/v1/admin/xp-curve",
        json={"stages": [{"stage": 1, "xpRequired": 0, "label": "One"}]},
        headers=editor,
    ).json()
    rewarded = client.post(
        f"/api/v1/admin/players/{player_id}/reward", json={"xp": 1}, headers=editor
    ).json()
    progress = client.get("/api/v1/player/me/progress", headers=headers).json()
    players = client.get("/api/v1/admin/players", headers=editor).json()
    one = client.get(f"/api/v1/admin/players/{player_id}", headers=editor).json()

    assert set(board) == fields_of("LeaderboardView")
    assert set(entry) == fields_of("LeaderboardEntryView")
    assert set(page) == fields_of("LeaderboardPage")
    assert set(page["board"]) == fields_of("LeaderboardView")
    assert set(page["entries"][0]) == fields_of("LeaderboardEntryView")
    assert set(curve) == fields_of("XpCurve")
    assert set(curve["stages"][0]) == fields_of("XpStageView")
    assert set(rewarded) == fields_of("PlayerRewardResult")
    assert set(rewarded["stage"]) == fields_of("XpStageView")
    assert set(progress) == fields_of("PlayerProgress")
    assert set(players) == fields_of("PlayerPage")
    assert set(players["players"][0]) == fields_of("PlayerProfile")
    assert set(one) == fields_of("PlayerProfile")


@pytest.mark.parametrize("table", NEW_TABLES)
def test_ac10_every_new_table_belongs_to_a_project(
    session_factory: sessionmaker[Session], table: str
) -> None:
    with session_factory() as session:
        references = session.execute(
            text("""
                select confrelid::regclass::text as target, a.attname as column_name
                from pg_constraint c
                join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
                where c.contype = 'f' and c.conrelid = cast(:table as regclass)
                  and array_length(c.conkey, 1) = 1
            """),
            {"table": table},
        ).all()
        nullable = session.execute(
            text("""
                select is_nullable from information_schema.columns
                where table_name = :table and column_name = 'project_id'
            """),
            {"table": table},
        ).scalar_one()

    assert ("project", "project_id") in [(r.target, r.column_name) for r in references]
    assert nullable == "NO"


@pytest.mark.parametrize("table", ["leaderboard_entry", "progression_xp"])
def test_ac10_a_per_player_row_cannot_belong_to_another_project_than_its_player(
    session_factory: sessionmaker[Session], table: str
) -> None:
    with session_factory() as session:
        target = session.execute(
            text("""
                select confrelid::regclass::text from pg_constraint
                where contype = 'f' and conrelid = cast(:table as regclass)
                  and conname like '%player'
            """),
            {"table": table},
        ).scalar_one()
        columns = session.execute(
            text("""
                select array_agg(a.attname::text order by a.attname)
                from pg_constraint c
                join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
                where c.contype = 'f' and c.conrelid = cast(:table as regclass)
                  and c.conname like '%player'
            """),
            {"table": table},
        ).scalar_one()
    assert target == "player"
    assert columns == ["player_id", "project_id"]
