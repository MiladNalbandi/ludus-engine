"""AC-3, AC-4 and AC-5: a project's item schema is untrusted input, and is read as such.

Two refusals carry the release, and both were wrong in the Java:

- **An array is not a schema.** The Java's test for this used `[1, 2, 3]` and asserted only that
  *something* was thrown — while its library compiled the array into a schema that validates
  nothing. Here the test asserts what was refused and why, and that the array never reaches
  the library at all.
- **A remote reference is never fetched.** Refused when the schema is set, by reading the
  parsed tree rather than the text, and then — independently — by a validator that has no way
  to fetch. The tests watch the network for both, and one of them proves the watch works by
  catching the library's own default fetching a URL.
"""

from __future__ import annotations

import json
import socket
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from wavemaker.apps.inventory.adapters.validation import JsonSchemaValidator
from wavemaker.apps.inventory.domain import attribute_schema
from wavemaker.apps.inventory.domain.attribute_schema import MAX_SCHEMA_BYTES, AttributeSchema
from wavemaker.apps.inventory.domain.errors import Rejected, SchemaUnusable

VALIDATOR = JsonSchemaValidator()

REMOTE = "https://attacker.example/schema.json"


def usable(text: str | bytes) -> AttributeSchema:
    """Read as the HTTP layer reads it, then checked as the use case checks it."""
    schema = attribute_schema.read(text.encode() if isinstance(text, str) else text)
    VALIDATOR.require_usable(schema)
    return schema


def refusal(text: str | bytes) -> Rejected:
    with pytest.raises(Rejected) as problem:
        usable(text)
    return problem.value


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every way Python code could reach the network, replaced by a tripwire that records."""
    attempts: list[str] = []

    def tripwire(*args: Any, **_: Any) -> Any:
        attempts.append(repr(args[:2]))
        raise OSError("this test does not allow the network")

    monkeypatch.setattr(urllib.request, "urlopen", tripwire)
    monkeypatch.setattr(socket, "create_connection", tripwire)
    monkeypatch.setattr(socket, "getaddrinfo", tripwire)
    monkeypatch.setattr(socket.socket, "connect", tripwire)
    yield attempts


# --- AC-4: a schema is an object or a boolean ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("[1, 2, 3]", "an array"),
        ("[]", "an array"),
        ("5", "a number"),
        ('"x"', "a string"),
        ("null", "null"),
    ],
)
def test_ac4_a_schema_that_is_not_an_object_or_a_boolean_is_refused(text: str, kind: str) -> None:
    problem = refusal(text)
    assert [violation.pointer for violation in problem.violations] == [""]
    assert f"this is {kind}" in str(problem)


def test_ac4_the_array_never_reaches_the_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point of checking the shape here rather than trusting a library: whatever a library
    does with an array, it is never asked."""

    def must_not_run(*_: Any, **__: Any) -> None:
        raise AssertionError("an array reached the schema library")

    monkeypatch.setattr(Draft202012Validator, "check_schema", must_not_run)
    with pytest.raises(Rejected):
        usable("[1, 2, 3]")


@pytest.mark.parametrize("text", ["{}", "true", "false", '{"type": "object"}'])
def test_ac4_an_object_or_a_boolean_is_a_schema(text: str) -> None:
    schema = usable(text)
    assert schema.text == text


def test_ac4_the_text_is_kept_exactly() -> None:
    text = '{\n  "type": "object",\n  "properties": {"damage": {"minimum": 1.0}}\n}\n'
    assert usable(text).text == text


@pytest.mark.parametrize("text", ["", "   ", "{", "{'type': 'object'}", "NaN"])
def test_ac4_text_that_is_not_json_is_refused(text: str) -> None:
    refusal(text)


def test_ac4_a_schema_that_is_not_utf_8_is_refused() -> None:
    refusal(b'{"description": "\xff"}')


def test_ac4_a_schema_is_capped_in_size() -> None:
    """It runs against every item on every save, and it persists in a table."""
    enormous = json.dumps({"type": "object", "description": "x" * MAX_SCHEMA_BYTES})
    assert "at most" in str(refusal(enormous))


def test_ac4_a_schema_nested_past_the_limit_is_refused_not_a_crash() -> None:
    for depth in (100, 5_000):
        nested = '{"not": ' * depth + "{}" + "}" * depth
        assert "nested" in str(refusal(nested))


@pytest.mark.parametrize(
    ("schema", "where"),
    [
        ({"type": "nope"}, "/type"),
        ({"properties": {"damage": {"type": "nope"}}}, "/properties/damage/type"),
        ({"pattern": "["}, "/pattern"),
        ({"minimum": "one"}, "/minimum"),
        ({"required": "damage"}, "/required"),
    ],
)
def test_ac4_json_that_is_not_a_usable_schema_is_refused_when_it_is_set(
    schema: dict[str, Any], where: str
) -> None:
    """Refused now, rather than on the first item an editor tries to save."""
    problem = refusal(json.dumps(schema))
    assert [violation.pointer for violation in problem.violations] == [where]


def test_ac4_a_local_reference_that_points_at_nothing_is_refused_when_it_is_set() -> None:
    problem = refusal('{"properties": {"damage": {"$ref": "#/$defs/missing"}}}')
    assert "#/$defs/missing" in str(problem)


@pytest.mark.parametrize(
    "dialect", ["http://json-schema.org/draft-07/schema#", "https://example.test/my-dialect"]
)
def test_ac4_another_dialect_is_refused_rather_than_quietly_read_as_2020_12(dialect: str) -> None:
    problem = refusal(json.dumps({"$schema": dialect, "type": "object"}))
    assert [violation.pointer for violation in problem.violations] == ["/$schema"]


@pytest.mark.parametrize(
    "dialect",
    [
        "https://json-schema.org/draft/2020-12/schema",
        "https://json-schema.org/draft/2020-12/schema#",
    ],
)
def test_ac4_naming_the_dialect_it_is_read_as_is_fine(dialect: str) -> None:
    usable(json.dumps({"$schema": dialect, "type": "object"}))


# --- AC-5: no remote reference, and no network either way ---------------------------------------


@pytest.mark.parametrize(
    ("text", "where"),
    [
        (f'{{"$ref": "{REMOTE}"}}', "/$ref"),
        ('{"$ref": "http://169.254.169.254/latest/meta-data/"}', "/$ref"),
        ('{"properties": {"a": {"$ref": "file:///etc/passwd"}}}', "/properties/a/$ref"),
        ('{"properties": {"a": {"$ref": "other.json"}}}', "/properties/a/$ref"),
        ('{"items": {"$ref": "//attacker.example/s.json"}}', "/items/$ref"),
        ('{"$defs": {"x": {"$ref": "urn:example:thing"}}}', "/$defs/x/$ref"),
        (f'{{"$dynamicRef": "{REMOTE}"}}', "/$dynamicRef"),
        (f'{{"$recursiveRef": "{REMOTE}"}}', "/$recursiveRef"),
        ('{"$ref": 7}', "/$ref"),
        # The Java matched `"$ref"` in the text. This is the same key once parsed, and the
        # pattern never saw it.
        (f'{{"\\u0024ref": "{REMOTE}"}}', "/$ref"),
        (f'{{"properties": {{"a/b": {{"$ref": "{REMOTE}"}}}}}}', "/properties/a~1b/$ref"),
    ],
)
def test_ac5_a_reference_that_does_not_point_inside_the_schema_is_refused(
    text: str, where: str, network: list[str]
) -> None:
    problem = refusal(text)
    assert [violation.pointer for violation in problem.violations] == [where]
    assert "local reference" in str(problem)
    assert network == []


def test_ac5_every_remote_reference_is_named_not_only_the_first(network: list[str]) -> None:
    text = json.dumps(
        {"properties": {"a": {"$ref": REMOTE}, "b": {"$ref": "#/$defs/b"}, "c": {"$ref": REMOTE}}}
    )
    problem = refusal(text)
    assert [violation.pointer for violation in problem.violations] == [
        "/properties/a/$ref",
        "/properties/c/$ref",
    ]
    assert network == []


def test_ac5_a_local_reference_is_allowed_because_it_fetches_nothing(network: list[str]) -> None:
    schema = usable(
        json.dumps(
            {
                "$defs": {"positive": {"type": "integer", "minimum": 1}},
                "type": "object",
                "properties": {"damage": {"$ref": "#/$defs/positive"}},
            }
        )
    )
    assert VALIDATOR.violations(schema.text, {"damage": 5}) == []
    assert [v.pointer for v in VALIDATOR.violations(schema.text, {"damage": 0})] == ["/damage"]
    assert network == []


def test_ac5_a_local_reference_under_a_foreign_id_still_fetches_nothing(network: list[str]) -> None:
    """`$id` moves the base a reference resolves against. A reference beginning `#` resolves
    against whatever the base is, and the base is always a resource this schema itself
    declared — so there is still nothing to fetch."""
    schema = usable(
        json.dumps(
            {
                "$id": "https://attacker.example/root.json",
                "$defs": {"positive": {"type": "integer", "minimum": 1}},
                "properties": {"damage": {"$ref": "#/$defs/positive"}},
            }
        )
    )
    assert VALIDATOR.violations(schema.text, {"damage": 5}) == []
    assert network == []


def test_ac5_the_tripwire_works_because_the_librarys_default_does_fetch(network: list[str]) -> None:
    """The reason the second line of defence exists, and proof the tripwire would see a fetch:
    a validator built the default way goes to the network for a remote reference."""
    default = Draft202012Validator({"$ref": REMOTE})
    with pytest.raises(Exception):  # noqa: B017 - which exception the library wraps it in is its own
        list(default.iter_errors(5))
    assert network, "the library's default should have tried the network"


def test_ac5_a_remote_reference_that_got_past_the_first_check_is_still_not_fetched(
    network: list[str],
) -> None:
    """A schema written to the table past this service skips the first check entirely. The
    validator still cannot fetch: its registry refuses every retrieval."""
    with pytest.raises(SchemaUnusable):
        VALIDATOR.violations(json.dumps({"$ref": REMOTE}), {"damage": 1})
    with pytest.raises(SchemaUnusable):
        VALIDATOR.violations(json.dumps({"properties": {"a": {"$dynamicRef": REMOTE}}}), {"a": 1})
    assert network == []


# --- AC-3: what a document is told ----------------------------------------------------------------


def test_ac3_violations_are_at_json_pointers_into_the_document() -> None:
    schema = usable(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "stats": {"type": "object", "properties": {"damage": {"type": "integer"}}}
                },
            }
        )
    )
    found = VALIDATOR.violations(schema.text, {"stats": {"damage": "lots"}})
    assert [violation.pointer for violation in found] == ["/stats/damage"]


def test_ac3_every_violation_is_returned_in_pointer_order() -> None:
    schema = usable(
        json.dumps(
            {
                "type": "object",
                "properties": {k: {"type": "integer"} for k in ("z", "a", "m")},
            }
        )
    )
    document = {"z": "x", "a": "x", "m": "x"}
    found = VALIDATOR.violations(schema.text, document)
    assert [violation.pointer for violation in found] == ["/a", "/m", "/z"]
    assert VALIDATOR.violations(schema.text, document) == found


def test_ac3_an_empty_schema_accepts_anything_and_false_accepts_nothing() -> None:
    assert VALIDATOR.violations("{}", {"anything": True}) == []
    assert VALIDATOR.violations("true", {"anything": True}) == []
    assert len(VALIDATOR.violations("false", {})) == 1


def test_ac3_a_stored_schema_that_cannot_be_used_is_the_schemas_problem() -> None:
    """Only reachable by writing to the table past the service. It must still be a refusal,
    not whatever the library raises."""
    for broken in (
        "[1, 2, 3",
        '{"properties": {"name": {"pattern": "["}}}',
        '{"$ref": "#/nowhere"}',
    ):
        with pytest.raises(SchemaUnusable):
            VALIDATOR.violations(broken, {"name": "x"})
