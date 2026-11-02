"""Reading a wave document: the bytes, and the few fields the engine indexes.

The indexed fields are read out of the document and never accepted beside it. A request that
could say `name=X` while the document says `name=Y` is a request that can make the catalogue
disagree with what a client is actually served.
"""

from __future__ import annotations

import pytest

from wavemaker.apps.content.domain.document import DocumentError, WaveDocument

GOOD = b'{"id":"first","name":"First Steps","progression_config":{"order":3},"schema_version":2}'


def test_the_indexed_fields_are_read_out_of_the_document() -> None:
    document = WaveDocument.read(GOOD)
    assert (document.id, document.name, document.order, document.schema_version) == (
        "first",
        "First Steps",
        3,
        2,
    )


def test_the_bytes_are_kept_exactly_as_they_arrived() -> None:
    """Not reformatted on the way in. The ETag is a hash of these."""
    assert WaveDocument.read(GOOD).raw == GOOD


def test_a_document_without_a_schema_version_is_a_version_one_document() -> None:
    """The field arrived after the first documents did. Absent is old, not broken."""
    raw = b'{"id":"a","name":"A","progression_config":{"order":0}}'
    assert WaveDocument.read(raw).schema_version == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"not json at all",
        b"[1, 2, 3]",
        b'"a string"',
        b'{"name":"A","progression_config":{"order":0}}',
        b'{"id":"a","progression_config":{"order":0}}',
        b'{"id":"a","name":"A"}',
        b'{"id":"a","name":"A","progression_config":{}}',
        b'{"id":"a","name":"A","progression_config":{"order":"third"}}',
        b'{"id":"","name":"A","progression_config":{"order":0}}',
        b'{"id":"a","name":"A","progression_config":{"order":0},"schema_version":0}',
    ],
)
def test_a_document_that_cannot_be_indexed_is_refused(raw: bytes) -> None:
    with pytest.raises(DocumentError):
        WaveDocument.read(raw)


def test_the_refusal_says_which_field_is_wrong() -> None:
    with pytest.raises(DocumentError, match=r"progression_config\.order"):
        WaveDocument.read(b'{"id":"a","name":"A","progression_config":{}}')
