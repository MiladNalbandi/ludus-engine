"""AC-1 to AC-6: the public read surface, against the contract frozen at v1.0.0.

Every shape here is taken from docs/api/openapi-v1.json. The editor and the SDK are generated
from that document, so a field renamed in Python is a client broken in the field.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.content_fixtures import DOCUMENTS, LEVEL, WAVES
from wavemaker.apps.content import get_wave_repository
from wavemaker.apps.content.adapters.memory import InMemoryWaveRepository
from wavemaker.apps.content.application.ports import WaveRepository
from wavemaker.apps.content.domain.wave import PlayableLevel
from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app


def serving(repository: WaveRepository) -> Iterator[TestClient]:
    """A real service with the content app mounted, reading from `repository`.

    The repository is swapped through the app's own port rather than through `create_app`,
    because the platform must not grow a parameter named after one app. That is the wall the
    whole plugin model rests on, and a test is the easiest place to put the first crack in it.
    """
    app = create_app(Settings(plugins_directory=None))
    app.dependency_overrides[get_wave_repository] = lambda: repository
    with TestClient(app) as running:
        yield running


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from serving(InMemoryWaveRepository(waves=WAVES, documents=DOCUMENTS, level=LEVEL))


@pytest.fixture
def empty_client() -> Iterator[TestClient]:
    yield from serving(InMemoryWaveRepository(waves=[], documents={}, level=None))


# --- AC-1: the catalogue -----------------------------------------------------------------


def test_ac1_published_waves_are_listed_in_order(client: TestClient) -> None:
    response = client.get("/api/v1/public/waves")
    assert response.status_code == 200
    body = response.json()
    assert [wave["id"] for wave in body] == ["demo_first_steps", "demo_crossfire"]


def test_ac1_a_summary_carries_exactly_the_contract_fields(client: TestClient) -> None:
    first = client.get("/api/v1/public/waves").json()[0]
    assert set(first) == {
        "id",
        "name",
        "order",
        "schemaVersion",
        "published",
        "createdAt",
        "updatedAt",
    }
    assert first["published"] is True
    assert first["schemaVersion"] == 1


def test_ac1_a_draft_is_never_listed(client: TestClient) -> None:
    ids = [wave["id"] for wave in client.get("/api/v1/public/waves").json()]
    assert "demo_pressure" not in ids, "demo_pressure is a draft"


# --- AC-2: the poll hash is the list ETag --------------------------------------------------


def test_ac2_the_status_hash_equals_the_list_etag(client: TestClient) -> None:
    """String equality, deliberately. Anything weaker lets the two drift apart unnoticed."""
    status = client.get("/api/v1/public/status").json()["contentHash"]
    etag = client.get("/api/v1/public/waves").headers["etag"]
    assert etag == f'"{status}"'


def test_ac2_status_is_never_cached(client: TestClient) -> None:
    """The one request whose answer must always be fresh, or the poll means nothing."""
    assert client.get("/api/v1/public/status").headers["cache-control"] == "no-store"


# --- AC-3: conditional requests ------------------------------------------------------------


def test_ac3_refetching_the_list_with_its_etag_is_a_304(client: TestClient) -> None:
    etag = client.get("/api/v1/public/waves").headers["etag"]
    again = client.get("/api/v1/public/waves", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


def test_ac3_refetching_a_document_with_its_etag_is_a_304(client: TestClient) -> None:
    first = client.get("/api/v1/public/waves/demo_first_steps/raw")
    assert first.status_code == 200
    again = client.get(
        "/api/v1/public/waves/demo_first_steps/raw",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert again.status_code == 304


def test_ac3_a_weak_validator_still_revalidates(client: TestClient) -> None:
    etag = client.get("/api/v1/public/waves").headers["etag"]
    again = client.get("/api/v1/public/waves", headers={"If-None-Match": f"W/{etag}"})
    assert again.status_code == 304


def test_ac3_a_stale_etag_gets_the_body(client: TestClient) -> None:
    again = client.get("/api/v1/public/waves", headers={"If-None-Match": '"long-gone"'})
    assert again.status_code == 200


# --- AC-4: one wave, and the bytes ----------------------------------------------------------


def test_ac4_one_published_wave_is_served(client: TestClient) -> None:
    response = client.get("/api/v1/public/waves/demo_crossfire")
    assert response.status_code == 200
    assert response.json()["name"] == "Crossfire"


def test_ac4_a_draft_is_404_and_not_403(client: TestClient) -> None:
    """A client that can tell "hidden" from "absent" has been told about unreleased content."""
    assert client.get("/api/v1/public/waves/demo_pressure").status_code == 404
    assert client.get("/api/v1/public/waves/demo_pressure/raw").status_code == 404


def test_ac4_a_wave_that_never_existed_is_also_404(client: TestClient) -> None:
    assert client.get("/api/v1/public/waves/no_such_wave").status_code == 404


def test_ac4_the_document_is_served_as_the_exact_bytes_that_were_stored(
    client: TestClient,
) -> None:
    """Not re-serialised. Re-serialising changes the bytes, which changes every client's ETag."""
    response = client.get("/api/v1/public/waves/demo_first_steps/raw")
    assert response.content == DOCUMENTS["demo_first_steps"]
    assert response.headers["content-type"].startswith("application/json")


# --- AC-5: batch -----------------------------------------------------------------------------


def test_ac5_a_batch_returns_the_documents_that_are_published(client: TestClient) -> None:
    response = client.post(
        "/api/v1/public/waves/batch",
        json={"ids": ["demo_first_steps", "demo_crossfire"]},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"demo_first_steps", "demo_crossfire"}


def test_ac5_a_batch_silently_leaves_out_a_draft_or_a_missing_id(client: TestClient) -> None:
    response = client.post(
        "/api/v1/public/waves/batch",
        json={"ids": ["demo_first_steps", "demo_pressure", "nope"]},
    )
    assert list(response.json()) == ["demo_first_steps"]


def test_ac5_an_empty_batch_is_an_empty_answer_not_an_error(client: TestClient) -> None:
    response = client.post("/api/v1/public/waves/batch", json={"ids": []})
    assert response.status_code == 200
    assert response.json() == {}


# --- AC-6: the active level -------------------------------------------------------------------


def test_ac6_the_active_level_lists_only_its_published_waves(client: TestClient) -> None:
    body = client.get("/api/v1/public/wave-levels/active").json()
    assert body["name"] == "Act One"
    assert [wave["id"] for wave in body["waves"]] == ["demo_first_steps", "demo_crossfire"]


def test_ac6_no_active_level_is_a_404(empty_client: TestClient) -> None:
    assert empty_client.get("/api/v1/public/wave-levels/active").status_code == 404


def test_ac6_the_active_level_revalidates_too(client: TestClient) -> None:
    first = client.get("/api/v1/public/wave-levels/active")
    again = client.get(
        "/api/v1/public/wave-levels/active", headers={"If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304


def test_ac6_an_empty_catalogue_still_answers_status_and_the_list(
    empty_client: TestClient,
) -> None:
    assert empty_client.get("/api/v1/public/waves").json() == []
    assert empty_client.get("/api/v1/public/status").json()["contentHash"]


def test_ac6_a_level_is_a_playable_level_shape(client: TestClient) -> None:
    body = client.get("/api/v1/public/wave-levels/active").json()
    assert set(body) == {"id", "name", "waves"}
    assert isinstance(LEVEL, PlayableLevel)
