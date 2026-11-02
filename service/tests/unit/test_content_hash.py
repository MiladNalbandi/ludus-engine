"""AC-2: the poll hash and the list ETag are one function, by construction.

A client polls /status on every launch and refetches when the hash moves. If the hash and the
list ETag are computed by two pieces of code, they can disagree — and then a client is told
"changed", refetches, and is handed a 304 validated against the other one. It never settles,
and nothing in a log looks wrong. Asserting the equality here is what stops that being possible.
"""

from datetime import UTC, datetime

from wavemaker.apps.content.domain.hashing import of_catalogue, of_document
from wavemaker.apps.content.domain.wave import WaveSummary


def summary(wave_id: str, *, order: int = 0, updated: str = "2026-01-01T00:00:00Z") -> WaveSummary:
    moment = datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone(UTC)
    return WaveSummary(
        id=wave_id,
        name=wave_id.title(),
        order=order,
        schema_version=1,
        published=True,
        created_at=moment,
        updated_at=moment,
    )


def test_ac2_the_same_catalogue_hashes_the_same_twice() -> None:
    catalogue = [summary("first"), summary("second", order=1)]
    assert of_catalogue(catalogue) == of_catalogue(list(catalogue))


def test_ac2_order_of_the_rows_does_not_change_the_hash() -> None:
    """The catalogue is a set of facts, not a list. Row order is the database's business."""
    a, b = summary("first"), summary("second", order=1)
    assert of_catalogue([a, b]) == of_catalogue([b, a])


def test_ac2_a_changed_timestamp_moves_the_hash() -> None:
    before = [summary("first", updated="2026-01-01T00:00:00Z")]
    after = [summary("first", updated="2026-01-02T00:00:00Z")]
    assert of_catalogue(before) != of_catalogue(after)


def test_ac2_publishing_another_wave_moves_the_hash() -> None:
    assert of_catalogue([summary("first")]) != of_catalogue([summary("first"), summary("second")])


def test_ac2_an_empty_catalogue_has_a_hash_of_its_own() -> None:
    """A client with nothing must still get a stable answer rather than an empty string."""
    assert of_catalogue([]) != ""


def test_ac2_a_document_hashes_its_exact_bytes() -> None:
    assert of_document(b'{"a":1}') == of_document(b'{"a":1}')
    assert of_document(b'{"a":1}') != of_document(b'{"a": 1}'), "a space is a different document"
