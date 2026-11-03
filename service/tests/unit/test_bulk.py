"""Splitting an import array back into each document's exact bytes.

The whole point is that the elements are never re-serialised. These tests use documents whose
formatting a JSON round-trip would change — a float that would become an integer, keys out of
order, and whitespace inside an object — so "the bytes survived" is a claim that can fail.
"""

from __future__ import annotations

import pytest

from wavemaker.apps.content.domain.bulk import BulkError, split_documents

FIRST = b'{"b":1,"a":2.0}'
SECOND = b'{ "x" : [1, 2] }'


def test_each_document_keeps_the_bytes_it_was_written_with() -> None:
    assert split_documents(b"[" + FIRST + b"," + SECOND + b"]") == [FIRST, SECOND]


def test_whitespace_between_documents_is_formatting_and_is_dropped() -> None:
    raw = b"[\n  " + FIRST + b" ,\n  " + SECOND + b"\n]\n"
    assert split_documents(raw) == [FIRST, SECOND]


def test_an_empty_array_imports_nothing_rather_than_failing() -> None:
    assert split_documents(b"[]") == []
    assert split_documents(b"  [ ]  ") == []


def test_one_document_is_still_an_array() -> None:
    assert split_documents(b"[" + FIRST + b"]") == [FIRST]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"not":"an array"}',
        b"",
        b"   ",
        b"[",
        b"[{}",
        b'[{"a":1} {"b":2}]',
        b'[{"a":1},]',
        b"[] []",
        b'[{"a":1}] trailing',
    ],
)
def test_a_batch_that_is_not_a_well_formed_array_is_refused(raw: bytes) -> None:
    with pytest.raises(BulkError):
        split_documents(raw)


def test_the_refusal_names_the_document_that_could_not_be_read() -> None:
    """In a file of thirty, "document 1" is the difference between a fix and a search."""
    with pytest.raises(BulkError, match="Document 1"):
        split_documents(b'[{"a":1},{nope}]')


def test_nested_arrays_inside_a_document_do_not_end_it() -> None:
    """The naive split — on commas, or on `}` — gets this wrong, and a wave document is full
    of nested arrays."""
    nested = b'{"spawn_rules":[{"movement_rules":{"sequence":[{"type":"patrol"}]}}]}'
    assert split_documents(b"[" + nested + b"," + FIRST + b"]") == [nested, FIRST]
