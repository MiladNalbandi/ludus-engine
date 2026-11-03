"""AC-2, AC-6 and AC-10: what an item and a grant must be, decided before anything is stored.

Every refusal names the field it is about with a JSON Pointer, and every refusal is a
`Rejected` — the one exception the HTTP layer turns into a 422. Anything else escaping from
here would be a 500 for something the caller sent.
"""

from __future__ import annotations

from typing import Any

import pytest

from wavemaker.apps.inventory.domain.errors import MAX_REPORTED, Rejected, Violation, pointer
from wavemaker.apps.inventory.domain.grant import MAX_LINES, MAX_QUANTITY, GrantLine, lines_of
from wavemaker.apps.inventory.domain.item import (
    MAX_ATTRIBUTES_BYTES,
    MAX_ID_LENGTH,
    draft_of,
    item_id_of,
)

SWORD = {"name": "Sword", "itemType": "weapon", "attributes": '{"damage": 12}'}


def pointers(problem: pytest.ExceptionInfo[Rejected]) -> list[str]:
    return [violation.pointer for violation in problem.value.violations]


# --- AC-2: an item, and its attributes as text ---------------------------------------------------


def test_ac2_the_attributes_text_is_kept_exactly_as_it_was_sent() -> None:
    """Re-serialising would rewrite 12.0 as 12.0 here and as 12 in another library, and move
    the keys. The text is the document; the parsed form is only for checking it."""
    sent = '{ "damage": 12.0,\n  "b": 1, "a": [1, 2.50] }'
    draft = draft_of("sword", {**SWORD, "attributes": sent})
    assert draft.attributes == sent
    assert draft.document == {"damage": 12.0, "b": 1, "a": [1, 2.5]}


@pytest.mark.parametrize("attributes", [None, "", "   "])
def test_ac2_no_attributes_means_an_empty_object(attributes: Any) -> None:
    body = {key: value for key, value in SWORD.items() if key != "attributes"}
    if attributes is not None:
        body["attributes"] = attributes
    draft = draft_of("sword", body)
    assert draft.attributes == "{}"
    assert draft.document == {}


def test_ac2_attributes_are_json_text_in_a_string_as_the_contract_says() -> None:
    """`ItemRequest.attributes` is a string in the frozen contract. A nested object would have
    to be serialised to be stored, which is the one thing this field exists to avoid."""
    with pytest.raises(Rejected) as problem:
        draft_of("sword", {**SWORD, "attributes": {"damage": 12}})
    assert pointers(problem) == ["/attributes"]


@pytest.mark.parametrize("attributes", ["[1, 2]", "12", '"sharp"', "null", "true"])
def test_ac2_attributes_are_an_object(attributes: str) -> None:
    with pytest.raises(Rejected) as problem:
        draft_of("sword", {**SWORD, "attributes": attributes})
    assert pointers(problem) == ["/attributes"]


def test_ac2_names_are_trimmed_and_a_blank_sprite_is_none() -> None:
    draft = draft_of("sword", {**SWORD, "name": "  Sword  ", "spriteRef": "  "})
    assert draft.name == "Sword"
    assert draft.sprite_ref is None


def test_ac2_every_field_is_checked_before_any_is_refused() -> None:
    with pytest.raises(Rejected) as problem:
        draft_of("Not An Id", {"name": " ", "itemType": "Weapon", "spriteRef": 7, "attributes": 1})
    assert pointers(problem) == ["/id", "/name", "/itemType", "/spriteRef", "/attributes"]


@pytest.mark.parametrize("item_id", ["sword", "sword_2", "a" * MAX_ID_LENGTH, "schema"])
def test_ac2_an_item_id_is_a_slug(item_id: str) -> None:
    assert item_id_of(item_id) == item_id


@pytest.mark.parametrize("item_id", ["", "Sword", "sword-2", "a/b", "a" * (MAX_ID_LENGTH + 1), 7])
def test_ac2_anything_else_is_not_an_item_id(item_id: Any) -> None:
    with pytest.raises(Rejected) as problem:
        item_id_of(item_id)
    assert pointers(problem) == ["/id"]


# --- AC-10: what Python reads and the rest of the system will not -------------------------------


@pytest.mark.parametrize(
    ("attributes", "where"),
    [
        # Not JSON, though Python's reader accepts them; jsonb would refuse them later.
        ('{"damage": NaN}', "/attributes"),
        ('{"damage": Infinity}', "/attributes"),
        ('{"damage": -Infinity}', "/attributes"),
        # JSON, and read by Python as infinity: not the number that was written.
        ('{"damage": 1e400}', "/attributes/damage"),
        # Valid JSON that no PostgreSQL text value can hold.
        ('{"note": "a\\u0000b"}', "/attributes/note"),
        ('{"a\\u0000b": 1}', "/attributes"),
        # A lone surrogate: valid escaping, not a character, and not encodable as UTF-8.
        ('{"note": "\\ud800"}', "/attributes/note"),
        # The same, arriving already decoded rather than escaped.
        ('{"note": "\ud800"}', "/attributes"),
        ('{"note": "a\x00b"}', "/attributes"),
        ("{not json", "/attributes"),
        ('{"a": 1} trailing', "/attributes"),
    ],
)
def test_ac10_documents_nothing_downstream_could_store_are_refused_here(
    attributes: str, where: str
) -> None:
    with pytest.raises(Rejected) as problem:
        draft_of("sword", {**SWORD, "attributes": attributes})
    assert pointers(problem) == [where]


def test_ac10_nesting_past_the_limit_is_refused_not_a_crash() -> None:
    """Deep enough to exhaust the stack is a RecursionError somewhere further in; deep enough
    to exhaust a validator's is the same a little later. Both are refused here."""
    for depth in (100, 5_000):
        nested = '{"a": ' * depth + "1" + "}" * depth
        with pytest.raises(Rejected) as problem:
            draft_of("sword", {**SWORD, "attributes": nested})
        assert problem.value.violations[0].pointer.startswith("/attributes")
        assert "nested" in str(problem.value)


def test_ac10_attributes_are_capped() -> None:
    padding = "x" * MAX_ATTRIBUTES_BYTES
    with pytest.raises(Rejected) as problem:
        draft_of("sword", {**SWORD, "attributes": f'{{"note": "{padding}"}}'})
    assert pointers(problem) == ["/attributes"]
    assert "at most" in str(problem.value)


@pytest.mark.parametrize(("field", "value"), [("name", "Swo\x00rd"), ("spriteRef", "\ud800")])
def test_ac10_text_fields_that_cannot_be_stored_are_refused(field: str, value: str) -> None:
    with pytest.raises(Rejected) as problem:
        draft_of("sword", {**SWORD, field: value})
    assert pointers(problem) == [f"/{field}"]


def test_ac10_a_rejection_lists_its_problems_and_says_how_many_it_left_out() -> None:
    many = [Violation(f"/items/{index}", "no") for index in range(MAX_REPORTED + 5)]
    message = str(Rejected(many))
    assert message.startswith("/items/0: no; /items/1: no")
    assert message.endswith("and 5 more")


def test_ac10_pointers_escape_what_rfc_6901_says_to() -> None:
    assert pointer("a/b", "m~n", 0) == "/a~1b/m~0n/0"


# --- AC-6: the lines of a grant ----------------------------------------------------------------


def test_ac6_a_grant_is_lines_of_an_item_and_a_quantity() -> None:
    body = {"items": [{"itemId": "sword", "quantity": 1}, {"itemId": "arrow", "quantity": -3}]}
    assert lines_of(body) == [GrantLine("sword", 1), GrantLine("arrow", -3)]


@pytest.mark.parametrize("items", [None, [], {}, "sword", [None]])
def test_ac6_a_grant_needs_lines(items: Any) -> None:
    with pytest.raises(Rejected) as problem:
        lines_of({"items": items})
    assert pointers(problem)[0].startswith("/items")


@pytest.mark.parametrize("quantity", [0, True, False, 1.5, "3", None, MAX_QUANTITY + 1])
def test_ac6_a_quantity_is_a_whole_number_that_changes_something(quantity: Any) -> None:
    """`true` is refused although Python calls it an int: it is a client bug, not one sword."""
    with pytest.raises(Rejected) as problem:
        lines_of({"items": [{"itemId": "sword", "quantity": quantity}]})
    assert pointers(problem) == ["/items/0/quantity"]


def test_ac6_every_bad_line_is_named_not_only_the_first() -> None:
    body = {
        "items": [
            {"itemId": "sword", "quantity": 1},
            {"itemId": "Bad Id", "quantity": 0},
            "not a line",
            {"itemId": "arrow", "quantity": 1},
        ]
    }
    with pytest.raises(Rejected) as problem:
        lines_of(body)
    assert pointers(problem) == ["/items/1/itemId", "/items/1/quantity", "/items/2"]


def test_ac6_a_grant_is_capped_in_lines() -> None:
    body = {"items": [{"itemId": "arrow", "quantity": 1}] * (MAX_LINES + 1)}
    with pytest.raises(Rejected) as problem:
        lines_of(body)
    assert pointers(problem) == ["/items"]
