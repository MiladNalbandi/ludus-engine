"""The R6 rules that need no database: cursors, page sizes, stages and what a request must be."""

from __future__ import annotations

import uuid

import pytest

from wavemaker.apps.leaderboard.domain.board import (
    InvalidRequest,
    board_id,
    direction,
    is_board_id,
    score_of,
)
from wavemaker.apps.progression.domain.curve import (
    Rejected,
    Stage,
    curve_of,
    following,
    progress,
    reached,
    reward_of,
)
from wavemaker.platform import paging

CURVE = [Stage(1, 0, "Rookie"), Stage(2, 100, None), Stage(3, 250, "Veteran")]


def test_a_cursor_round_trips_and_says_nothing_readable() -> None:
    player = str(uuid.uuid4())
    cursor = paging.encode_cursor("-42", player)
    assert player not in cursor
    assert paging.decode_cursor(cursor, 2) == ("-42", player)


@pytest.mark.parametrize("cursor", ["", "!!!", "not base64 at all", paging.encode_cursor("a")])
def test_a_cursor_this_service_did_not_issue_is_refused(cursor: str) -> None:
    with pytest.raises(paging.BadCursor):
        paging.decode_cursor(cursor, 2)


def test_a_cursor_with_an_empty_part_is_refused() -> None:
    with pytest.raises(paging.BadCursor):
        paging.decode_cursor(paging.encode_cursor("", "x"), 2)


@pytest.mark.parametrize(
    ("limit", "expected"), [(None, 20), (0, 1), (-5, 1), (7, 7), (200, 200), (10**12, 200)]
)
def test_a_page_size_is_the_default_or_clamped(limit: int | None, expected: int) -> None:
    assert paging.page_size(limit, default=20, maximum=200) == expected


@pytest.mark.parametrize(
    ("xp", "stage", "following_stage"), [(0, 1, 2), (99, 1, 2), (100, 2, 3), (999, 3, None)]
)
def test_a_stage_is_the_highest_threshold_met(
    xp: int, stage: int, following_stage: int | None
) -> None:
    found = reached(CURVE, xp)
    assert found is not None and found.stage == stage
    after = following(CURVE, xp)
    assert (after.stage if after else None) == following_stage


def test_below_the_first_threshold_there_is_no_stage_yet() -> None:
    assert progress([Stage(1, 50, None)], 10).stage is None
    assert progress([], 10).next_stage is None


def test_a_curve_is_returned_in_stage_order() -> None:
    sent = [{"stage": 3, "xpRequired": 250}, {"stage": 1, "xpRequired": 0}]
    assert [stage.stage for stage in curve_of(sent)] == [1, 3]


def test_a_blank_label_is_no_label() -> None:
    assert curve_of([{"stage": 1, "xpRequired": 0, "label": "  "}])[0].label is None


def test_a_reward_with_nothing_in_it_is_nothing() -> None:
    reward = reward_of({})
    assert reward.grants == [] and reward.xp == 0


def test_every_problem_with_a_reward_is_reported() -> None:
    with pytest.raises(Rejected) as rejected:
        reward_of({"grants": [{"currency": 5, "amount": -1}], "xp": -3})
    assert [problem.split(":")[0] for problem in rejected.value.problems] == [
        "/grants/0/currency",
        "/grants/0/amount",
        "/xp",
    ]


@pytest.mark.parametrize("candidate", ["high_score", "a", "x" * 64, "2026_season_1"])
def test_a_board_id_is_the_projects_own_word(candidate: str) -> None:
    assert is_board_id(candidate)
    assert board_id(candidate) == candidate


@pytest.mark.parametrize("candidate", ["", "High", "with-dash", "x" * 65, "a/b", "é"])
def test_anything_else_is_not_a_board_id(candidate: str) -> None:
    assert not is_board_id(candidate)


def test_descending_is_true_unless_a_board_says_false() -> None:
    assert direction(None) is True
    assert direction(False) is False
    with pytest.raises(InvalidRequest):
        direction("false")


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None, 2**63, -(2**63) - 1])
def test_a_score_is_a_whole_number_a_bigint_holds(value: object) -> None:
    with pytest.raises(InvalidRequest):
        score_of(value)
