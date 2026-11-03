"""What an author may send as a level, before anything is stored.

A level is a sequence: the order is the list order, and nothing else carries a position. These
are the refusals that need no database — a missing name, a list that is not a list, the same
wave listed twice — each naming the field an author has to change.
"""

from __future__ import annotations

from typing import Any

import pytest

from wavemaker.apps.content.domain.bulk import MAX_BATCH, read_batch_ids
from wavemaker.apps.content.domain.level import LevelDraft
from wavemaker.apps.content.domain.wave import MissingWaves, Rejected


def draft(**overrides: Any) -> LevelDraft:
    body: dict[str, Any] = {"name": "Act One", "description": "The opening", "waves": ["a", "b"]}
    body.update(overrides)
    return LevelDraft.read(body)


@pytest.mark.ac("AC-1")
def test_a_level_names_its_waves_in_the_order_given() -> None:
    read = draft(waves=["c", "a", "b"])
    assert read.name == "Act One"
    assert read.description == "The opening"
    assert read.wave_ids == ("c", "a", "b")


@pytest.mark.ac("AC-1")
def test_a_description_may_be_left_out_or_null() -> None:
    assert LevelDraft.read({"name": "Act One", "waves": []}).description is None
    assert draft(description=None).description is None


@pytest.mark.ac("AC-1")
def test_an_empty_level_is_a_level() -> None:
    """Built before its waves are written, which is how levels are actually made."""
    assert draft(waves=[]).wave_ids == ()


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize("body", [[], "Act One", None, 3])
def test_a_body_that_is_not_an_object_is_refused(body: Any) -> None:
    with pytest.raises(Rejected):
        LevelDraft.read(body)


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize("name", [None, "", "   ", 7, "x" * 256])
def test_a_level_needs_a_usable_name(name: Any) -> None:
    with pytest.raises(Rejected, match=r"^/name"):
        draft(name=name)


@pytest.mark.ac("AC-1")
def test_a_name_of_the_longest_storable_length_is_accepted() -> None:
    assert draft(name="x" * 255).name == "x" * 255


@pytest.mark.ac("AC-1")
def test_a_description_must_be_text() -> None:
    with pytest.raises(Rejected, match=r"^/description"):
        draft(description=["not", "text"])


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize("waves", [None, "a,b", {"a": 0}])
def test_the_wave_list_must_be_a_list(waves: Any) -> None:
    """Absent is not empty. A PUT that forgot the field must not empty the level."""
    with pytest.raises(Rejected, match=r"^/waves:"):
        draft(waves=waves)


@pytest.mark.ac("AC-1")
def test_the_wave_list_is_required() -> None:
    with pytest.raises(Rejected, match=r"^/waves:"):
        LevelDraft.read({"name": "Act One"})


@pytest.mark.ac("AC-1")
def test_an_entry_that_is_not_a_wave_id_is_named_by_position() -> None:
    with pytest.raises(Rejected, match=r"^/waves/1:"):
        draft(waves=["a", 2, "b"])


@pytest.mark.ac("AC-2")
def test_the_same_wave_twice_is_refused_at_its_second_position() -> None:
    """Two slots that advance together and a progress counter that can never be right.
    Refused rather than deduplicated: silently dropping an author's entry is worse."""
    with pytest.raises(Rejected) as refused:
        draft(waves=["a", "b", "a"])
    message = str(refused.value)
    assert message.startswith("/waves/2:")
    assert "'a'" in message
    assert "/waves/0" in message, "say where the first one is, too"


@pytest.mark.ac("AC-3")
def test_missing_waves_are_each_named_by_position() -> None:
    message = str(MissingWaves("/waves", [(1, "ghost"), (3, "phantom")]))
    assert "/waves/1" in message and "'ghost'" in message
    assert "/waves/3" in message and "'phantom'" in message


@pytest.mark.ac("AC-6")
def test_a_batch_names_the_waves_it_deletes() -> None:
    assert read_batch_ids({"ids": ["a", "b"]}) == ("a", "b")


@pytest.mark.ac("AC-6")
@pytest.mark.parametrize(
    ("body", "pointer"),
    [
        ([], "/"),
        ({}, "/ids"),
        ({"ids": "a"}, "/ids"),
        ({"ids": []}, "/ids"),
        ({"ids": ["a", 1]}, "/ids/1"),
        ({"ids": ["a", "b", "a"]}, "/ids/2"),
        ({"ids": [f"w{n}" for n in range(MAX_BATCH + 1)]}, "/ids"),
    ],
)
def test_a_batch_that_is_not_a_known_set_of_ids_is_refused(body: Any, pointer: str) -> None:
    """'Delete these six' is a statement about a known set. An empty set, a repeated id or a
    list too long to read back are not that."""
    with pytest.raises(Rejected) as refused:
        read_batch_ids(body)
    assert str(refused.value).startswith(pointer)
