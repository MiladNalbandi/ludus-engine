"""The platform's one check for text that cannot be stored (issue #85).

Two kinds of string pass every type check and still cannot reach PostgreSQL: one holding a NUL,
which no `text` value can contain, and one holding a lone surrogate, which is not a character
and cannot be encoded as UTF-8 to be sent at all. Both arrive as valid JSON.
"""

from __future__ import annotations

from typing import Any

import pytest

from wavemaker.platform.kernel.errors import PlatformError
from wavemaker.platform.kernel.storable import (
    UnstorableText,
    refuse_unstorable_in,
    storable,
    unstorable,
)


@pytest.mark.parametrize("value", ["", "Sword", "Épée", "剣", "\U0001f5e1", "tab\tand\nnewline"])
def test_ordinary_text_is_storable(value: str) -> None:
    assert unstorable(value) is None
    assert storable("/name", value) == value


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("Swo\x00rd", "NUL"),
        ("\x00", "NUL"),
        ("Swo\ud800rd", "surrogate"),
        ("\udfff", "surrogate"),
        # A pair written as two escapes is joined by a JSON reader; held apart in a Python
        # string, each half is lone.
        ("\ud83d\udde1", "surrogate"),
    ],
)
def test_a_nul_or_a_lone_surrogate_is_not(value: str, reason: str) -> None:
    found = unstorable(value)
    assert found is not None and reason in found


def test_refusing_names_the_field() -> None:
    with pytest.raises(UnstorableText) as refused:
        storable("/displayName", "a\x00b")
    assert refused.value.pointer == "/displayName"
    assert str(refused.value).startswith("/displayName: ")
    assert "\x00" not in str(refused.value), "the message must itself be storable and loggable"
    assert isinstance(refused.value, PlatformError)


@pytest.mark.parametrize(
    ("document", "pointer"),
    [
        ({"name": "a\x00b"}, "/name"),
        ({"a": [1, "fine", {"b": "\ud800"}]}, "/a/2/b"),
        # Pointer escaping: "~" is "~0" and "/" is "~1".
        ({"a/b": {"c~d": "\x00"}}, "/a~1b/c~0d"),
        # A key that cannot be stored is reported at the object holding it: the key itself
        # cannot be put in a message.
        ({"a": {"k\x00": 1}}, "/a"),
        (["fine", "\x00"], "/1"),
        ("\x00", ""),
    ],
)
def test_a_document_is_refused_at_the_first_value_that_cannot_be_stored(
    document: Any, pointer: str
) -> None:
    with pytest.raises(UnstorableText) as refused:
        refuse_unstorable_in(document)
    assert refused.value.pointer == pointer


def test_a_document_is_refused_at_its_first_problem_in_document_order() -> None:
    with pytest.raises(UnstorableText) as refused:
        refuse_unstorable_in({"a": "\x00", "b": "\x00"}, "/0")
    assert refused.value.pointer == "/0/a"


def test_a_document_with_nothing_wrong_passes() -> None:
    refuse_unstorable_in({"a": [1, 2.5, None, True, "fine", {"é": "剣"}]})


def test_a_deep_document_is_walked_without_recursion() -> None:
    document: Any = "\x00"
    for _ in range(5_000):
        document = [document]
    with pytest.raises(UnstorableText) as refused:
        refuse_unstorable_in(document)
    assert refused.value.pointer == "/0" * 5_000
