"""The media app over HTTP, against a real PostgreSQL, a real directory and real credentials.

Every shape here is the frozen v1 contract's: `AudioClipSummary` and `SpriteSummary`, the four
admin routes and the two public ones, and the mix. Status codes follow what the Java engine
answered rather than what its generated document says — the document lists `200` for every
operation because springdoc writes the default, while the engine created with `201` and
deleted with `204`, and the content app already answers the same way.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import shutil
import struct
import sys
import time
import tracemalloc
import uuid
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration.asgi_stream import PATTERN, exchange, multipart, pattern
from wavemaker.apps.media import media_settings
from wavemaker.apps.media.adapters.settings import MediaSettings
from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.identity.accounts import ensure_account
from wavemaker.platform.identity.tokens import Role
from wavemaker.platform.kernel.errors import ConfigurationError

SECRET = "a-media-test-signing-key-of-respectable-length"  # keel:allow-secret
ADMIN = "admin@example.test"
PASSWORD = "correct-horse-battery-staple"  # keel:allow-secret
VIEWER = "viewer@example.test"

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.cookie)</script></svg>'
OGG = b"OggS" + bytes(range(256)) * 8
SUMMARY_FIELDS = {"id", "filename", "contentType", "sizeBytes", "createdAt"}
IMMUTABLE = "public, max-age=31536000, immutable"
TWELVE_MEGABYTES = 12 * 1024 * 1024


def build(database_url: str, blobs: Path | None, **media: Any) -> FastAPI:
    app = create_app(
        Settings(
            plugins_directory=None,
            database_url=database_url,
            jwt_secret=SECRET,
            admin_email=ADMIN,
            admin_password=PASSWORD,
            blob_directory=blobs,
        )
    )
    settings = MediaSettings(**media)
    app.dependency_overrides[media_settings] = lambda: settings
    with app.state.session_factory() as session:
        ensure_account(session, app.state.project_id, VIEWER, PASSWORD, Role.VIEWER)
    return app


@pytest.fixture
def blobs(tmp_path: Path) -> Path:
    return tmp_path / "blobs"


@pytest.fixture
def client(database_url: str, blobs: Path) -> Iterator[TestClient]:
    with TestClient(build(database_url, blobs)) as running:
        yield running


def bearer(client: TestClient, email: str = ADMIN) -> dict[str, str]:
    response = client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def upload(
    client: TestClient,
    route: str,
    content: bytes,
    content_type: str,
    filename: str = "upload.bin",
    headers: dict[str, str] | None = None,
) -> Any:
    return client.post(
        f"/api/v1/admin/{route}",
        files={"file": (filename, content, content_type)},
        headers=headers if headers is not None else bearer(client),
    )


def stored_files(blobs: Path) -> list[Path]:
    return sorted(path for path in blobs.rglob("*") if path.is_file())


# --- AC-1: who may reach these routes, and the admin surface ------------------------------


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize("route", ["audio", "sprites"])
def test_ac1_the_admin_routes_are_closed_without_a_token(client: TestClient, route: str) -> None:
    assert client.get(f"/api/v1/admin/{route}").status_code == 401
    assert upload(client, route, OGG, "audio/ogg", headers={}).status_code == 401
    assert client.delete(f"/api/v1/admin/{route}/{uuid.uuid4()}").status_code == 401


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize("route", ["audio", "sprites"])
def test_ac1_a_viewer_may_list_but_not_change(client: TestClient, route: str) -> None:
    viewer = bearer(client, VIEWER)
    assert client.get(f"/api/v1/admin/{route}", headers=viewer).status_code == 200
    assert upload(client, route, PNG, "image/png", headers=viewer).status_code == 403
    assert client.delete(f"/api/v1/admin/{route}/{uuid.uuid4()}", headers=viewer).status_code == 403


@pytest.mark.ac("AC-1")
def test_ac1_a_viewer_may_not_mix(client: TestClient) -> None:
    refused = client.post(
        "/api/v1/admin/audio/mix",
        json={"filename": "m.ogg", "tracks": []},
        headers=bearer(client, VIEWER),
    )
    assert refused.status_code == 403


@pytest.mark.ac("AC-1")
def test_ac1_an_audio_clip_is_uploaded_listed_and_deleted(client: TestClient, blobs: Path) -> None:
    created = upload(client, "audio", OGG, "audio/ogg", filename="kick.ogg")
    assert created.status_code == 201, created.text
    summary = created.json()
    assert set(summary) == SUMMARY_FIELDS
    assert summary["filename"] == "kick.ogg"
    assert summary["contentType"] == "audio/ogg"
    assert summary["sizeBytes"] == len(OGG), "the size is what was written, not what was declared"
    assert summary["createdAt"].endswith("Z")

    listed = client.get("/api/v1/admin/audio", headers=bearer(client)).json()
    assert listed == [summary]

    gone = client.delete(f"/api/v1/admin/audio/{summary['id']}", headers=bearer(client))
    assert gone.status_code == 204
    assert client.get("/api/v1/admin/audio", headers=bearer(client)).json() == []
    assert client.get(f"/api/v1/public/audio/{summary['id']}").status_code == 404
    assert stored_files(blobs) == [], "deleting a clip deletes its bytes"


@pytest.mark.ac("AC-1")
def test_ac1_a_sprite_is_uploaded_listed_and_deleted(client: TestClient, blobs: Path) -> None:
    created = upload(client, "sprites", PNG, "image/png", filename="sword.png")
    assert created.status_code == 201, created.text
    summary = created.json()
    assert set(summary) == SUMMARY_FIELDS
    assert summary["contentType"] == "image/png"
    assert summary["sizeBytes"] == len(PNG)

    assert client.get("/api/v1/admin/sprites", headers=bearer(client)).json() == [summary]
    assert (
        client.delete(f"/api/v1/admin/sprites/{summary['id']}", headers=bearer(client)).status_code
        == 204
    )
    assert client.get("/api/v1/admin/sprites", headers=bearer(client)).json() == []
    assert stored_files(blobs) == []


@pytest.mark.ac("AC-1")
def test_ac1_the_list_is_newest_first(client: TestClient) -> None:
    first = upload(client, "audio", OGG, "audio/ogg", filename="first.ogg").json()
    second = upload(client, "audio", OGG, "audio/ogg", filename="second.ogg").json()
    listed = client.get("/api/v1/admin/audio", headers=bearer(client)).json()
    assert [clip["id"] for clip in listed] == [second["id"], first["id"]]


@pytest.mark.ac("AC-1")
def test_ac1_audio_and_sprites_are_separate_catalogues(client: TestClient) -> None:
    sprite = upload(client, "sprites", PNG, "image/png").json()
    assert client.get("/api/v1/admin/audio", headers=bearer(client)).json() == []
    assert client.get(f"/api/v1/public/audio/{sprite['id']}").status_code == 404
    assert client.delete(f"/api/v1/admin/audio/{sprite['id']}", headers=bearer(client)).status_code == 404
    assert client.get(f"/api/v1/public/sprites/{sprite['id']}").status_code == 200


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize("route", ["audio", "sprites"])
@pytest.mark.parametrize("clip", [str(uuid.UUID(int=0)), "not-an-id", "..%2F..%2Fetc"])
def test_ac1_deleting_what_is_not_there_is_a_404(client: TestClient, route: str, clip: str) -> None:
    assert client.delete(f"/api/v1/admin/{route}/{clip}", headers=bearer(client)).status_code == 404


# --- AC-2: serving, cached immutably, with a tag ------------------------------------------


@pytest.mark.ac("AC-2")
def test_ac2_a_clip_is_served_to_anybody_byte_for_byte(client: TestClient) -> None:
    clip = upload(client, "audio", OGG, "audio/ogg", filename="kick.ogg").json()
    served = client.get(f"/api/v1/public/audio/{clip['id']}")
    assert served.status_code == 200
    assert served.content == OGG
    assert served.headers["content-type"] == "audio/ogg"
    assert served.headers["content-length"] == str(len(OGG))
    assert served.headers["cache-control"] == IMMUTABLE
    assert served.headers["etag"] == f'"{hashlib.sha256(OGG).hexdigest()}"'
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["content-disposition"].startswith("inline;")


@pytest.mark.ac("AC-2")
def test_ac2_a_sprite_is_served_with_the_type_its_bytes_have(client: TestClient) -> None:
    sprite = upload(client, "sprites", PNG, "image/png").json()
    served = client.get(f"/api/v1/public/sprites/{sprite['id']}")
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == IMMUTABLE
    assert served.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in served.headers["content-security-policy"]


@pytest.mark.ac("AC-2")
@pytest.mark.parametrize("route,body,kind", [("audio", OGG, "audio/ogg"), ("sprites", PNG, "image/png")])
@pytest.mark.parametrize("form", ['"{tag}"', 'W/"{tag}"', '"stale", "{tag}"', "*"])
def test_ac2_a_client_that_has_the_bytes_gets_a_304(
    client: TestClient, route: str, body: bytes, kind: str, form: str
) -> None:
    asset = upload(client, route, body, kind).json()
    tag = hashlib.sha256(body).hexdigest()
    revalidated = client.get(
        f"/api/v1/public/{route}/{asset['id']}", headers={"If-None-Match": form.format(tag=tag)}
    )
    assert revalidated.status_code == 304
    assert revalidated.content == b""
    assert revalidated.headers["etag"] == f'"{tag}"'
    assert revalidated.headers["cache-control"] == IMMUTABLE


@pytest.mark.ac("AC-2")
def test_ac2_a_different_tag_gets_the_bytes(client: TestClient) -> None:
    clip = upload(client, "audio", OGG, "audio/ogg").json()
    served = client.get(f"/api/v1/public/audio/{clip['id']}", headers={"If-None-Match": '"old"'})
    assert served.status_code == 200
    assert served.content == OGG


@pytest.mark.ac("AC-2")
@pytest.mark.parametrize("route", ["audio", "sprites"])
@pytest.mark.parametrize("clip", [str(uuid.UUID(int=0)), "not-an-id", "..", "%2e%2e%2fsecret"])
def test_ac2_an_unknown_or_malformed_id_is_a_404(client: TestClient, route: str, clip: str) -> None:
    """One answer for both. Telling them apart tells a caller which ids are shaped right."""
    assert client.get(f"/api/v1/public/{route}/{clip}").status_code == 404


@pytest.mark.ac("AC-2")
def test_ac2_metadata_whose_bytes_are_gone_is_a_404_not_a_500(
    client: TestClient, blobs: Path
) -> None:
    clip = upload(client, "audio", OGG, "audio/ogg").json()
    for path in stored_files(blobs):
        path.unlink()
    assert client.get(f"/api/v1/public/audio/{clip['id']}").status_code == 404


@pytest.mark.ac("AC-2")
def test_ac2_a_filename_that_is_not_ascii_still_reaches_the_header(client: TestClient) -> None:
    clip = upload(client, "audio", OGG, "audio/ogg", filename='thème "boss".ogg').json()
    assert clip["filename"] == 'thème "boss".ogg'
    disposition = client.get(f"/api/v1/public/audio/{clip['id']}").headers["content-disposition"]
    assert "filename*=UTF-8''th%C3%A8me%20%22boss%22.ogg" in disposition


# --- AC-3: twelve megabytes in and out, never whole in memory -----------------------------


@pytest.mark.ac("AC-3")
def test_ac3_a_twelve_megabyte_upload_and_download_are_streamed(
    database_url: str, blobs: Path
) -> None:
    """Measured, not argued. `tracemalloc` sees every Python allocation in every thread, and
    the request body arrives one shared 64 KiB buffer at a time, so a handler that gathered
    the file — `await request.body()`, `UploadFile.read()`, `bytes.join` — would show a peak of
    at least twelve megabytes here."""
    app = build(database_url, blobs, max_audio_bytes=64 * 1024 * 1024)
    with TestClient(app) as client:
        headers = {**bearer(client), "content-type": "multipart/form-data; boundary=wm-boundary"}

    def send_upload(size: int) -> Any:
        return exchange(
            app,
            method="POST",
            path="/api/v1/admin/audio",
            headers=headers,
            body=multipart(pattern(size), filename="long.ogg", content_type="audio/ogg"),
        )

    # Warm up first, so the measurement is of the upload and not of the first-ever query.
    assert send_upload(1024).status == 201

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        uploaded = send_upload(TWELVE_MEGABYTES)
        upload_peak = tracemalloc.get_traced_memory()[1]
        assert uploaded.status == 201, uploaded.body_prefix
        clip = json.loads(uploaded.body_prefix)

        tracemalloc.reset_peak()
        downloaded = exchange(app, method="GET", path=f"/api/v1/public/audio/{clip['id']}")
        download_peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert clip["sizeBytes"] == TWELVE_MEGABYTES
    assert upload_peak < 4 * 1024 * 1024, f"the upload peaked at {upload_peak / 2**20:.1f} MiB"

    assert downloaded.status == 200
    assert downloaded.body_bytes == TWELVE_MEGABYTES
    assert downloaded.largest_chunk <= 1024 * 1024, "the response was sent as one piece"
    assert download_peak < 4 * 1024 * 1024, f"the download peaked at {download_peak / 2**20:.1f} MiB"

    # And the bytes on disk are the bytes that were sent.
    digest = hashlib.sha256()
    for chunk in pattern(TWELVE_MEGABYTES):
        digest.update(chunk)
    assert downloaded.headers["etag"] == f'"{digest.hexdigest()}"'


# --- AC-4: SVG is refused, by content -----------------------------------------------------


@pytest.mark.ac("AC-4")
def test_ac4_svg_is_refused_as_a_sprite(client: TestClient, blobs: Path) -> None:
    refused = upload(client, "sprites", SVG, "image/svg+xml", filename="icon.svg")
    assert refused.status_code == 415
    assert "SVG" in refused.json()["detail"]
    assert stored_files(blobs) == []


@pytest.mark.ac("AC-4")
def test_ac4_svg_labelled_as_a_png_is_still_refused(client: TestClient, blobs: Path) -> None:
    """The label is what the client chose to say. The bytes are what a browser renders."""
    refused = upload(client, "sprites", SVG, "image/png", filename="icon.png")
    assert refused.status_code == 415
    assert "SVG" in refused.json()["detail"]
    assert client.get("/api/v1/admin/sprites", headers=bearer(client)).json() == []
    assert stored_files(blobs) == [], "a refused upload leaves nothing on disk"


@pytest.mark.ac("AC-4")
def test_ac4_html_labelled_as_a_gif_is_refused(client: TestClient) -> None:
    assert upload(client, "sprites", b"<html><script>x</script></html>", "image/gif").status_code == 415


# --- AC-5: refusals are 4xx, never 500, and leave nothing behind --------------------------


@pytest.mark.ac("AC-5")
@pytest.mark.parametrize(
    ("route", "content_type"),
    [("audio", "text/html"), ("audio", "image/svg+xml"), ("sprites", "audio/ogg"),
     ("sprites", "application/octet-stream")],
)
def test_ac5_a_wrong_content_type_is_a_415(
    client: TestClient, blobs: Path, route: str, content_type: str
) -> None:
    refused = upload(client, route, PNG, content_type)
    assert refused.status_code == 415, refused.text
    assert stored_files(blobs) == []


@pytest.mark.ac("AC-5")
@pytest.mark.parametrize("route,body,kind", [("audio", OGG, "audio/ogg"), ("sprites", PNG, "image/png")])
def test_ac5_an_oversized_upload_is_a_413(
    database_url: str, blobs: Path, route: str, body: bytes, kind: str
) -> None:
    app = build(database_url, blobs, max_audio_bytes=1024, max_sprite_bytes=1024)
    with TestClient(app) as client:
        refused = upload(client, route, body * 4, kind)
        assert refused.status_code == 413, refused.text
        assert client.get(f"/api/v1/admin/{route}", headers=bearer(client)).json() == []
    assert stored_files(blobs) == [], "an oversized upload leaves no partial file behind"


@pytest.mark.ac("AC-5")
def test_ac5_an_oversized_upload_with_no_declared_length_is_cut_off(
    database_url: str, blobs: Path
) -> None:
    """Chunked, so there is no Content-Length to check up front. The limit is counted as the
    bytes arrive, and the request stops being read once it is passed."""
    app = build(database_url, blobs, max_audio_bytes=256 * 1024)
    with TestClient(app) as client:
        headers = {**bearer(client), "content-type": "multipart/form-data; boundary=wm-boundary"}
    refused = exchange(
        app,
        method="POST",
        path="/api/v1/admin/audio",
        headers=headers,
        body=multipart(pattern(TWELVE_MEGABYTES), filename="huge.ogg", content_type="audio/ogg"),
    )
    assert refused.status == 413
    assert refused.chunks_pulled < 20, "the rest of a refused upload must not be read"
    assert stored_files(blobs) == []


@pytest.mark.ac("AC-5")
def test_ac5_a_declared_length_over_the_limit_is_refused_before_reading(
    database_url: str, blobs: Path
) -> None:
    app = build(database_url, blobs, max_audio_bytes=1024)
    with TestClient(app) as client:
        headers = {
            **bearer(client),
            "content-type": "multipart/form-data; boundary=wm-boundary",
            "content-length": str(TWELVE_MEGABYTES),
        }
    refused = exchange(
        app,
        method="POST",
        path="/api/v1/admin/audio",
        headers=headers,
        body=multipart(pattern(TWELVE_MEGABYTES), filename="huge.ogg", content_type="audio/ogg"),
    )
    assert refused.status == 413
    assert refused.chunks_pulled == 0


@pytest.mark.ac("AC-5")
@pytest.mark.parametrize("route,kind", [("audio", "audio/ogg"), ("sprites", "image/png")])
def test_ac5_an_empty_file_is_a_422(client: TestClient, blobs: Path, route: str, kind: str) -> None:
    refused = upload(client, route, b"", kind)
    assert refused.status_code == 422
    assert stored_files(blobs) == []


@pytest.mark.ac("AC-5")
def test_ac5_a_body_that_is_not_multipart_is_a_415(client: TestClient) -> None:
    refused = client.post("/api/v1/admin/audio", json={"file": "nope"}, headers=bearer(client))
    assert refused.status_code == 415


@pytest.mark.ac("AC-5")
def test_ac5_a_form_with_no_file_part_is_a_422(client: TestClient) -> None:
    refused = client.post(
        "/api/v1/admin/audio",
        files={"other": ("x.ogg", OGG, "audio/ogg")},
        headers=bearer(client),
    )
    assert refused.status_code == 422
    assert "file" in refused.json()["detail"]


@pytest.mark.ac("AC-5")
def test_ac5_a_broken_multipart_body_is_a_400(client: TestClient, blobs: Path) -> None:
    refused = client.post(
        "/api/v1/admin/audio",
        content=b"--wm-boundary\r\nthis is not a header block",
        headers={**bearer(client), "Content-Type": "multipart/form-data; boundary=wm-boundary"},
    )
    assert refused.status_code == 400
    assert stored_files(blobs) == []


@pytest.mark.ac("AC-5")
def test_ac5_a_multipart_type_with_no_boundary_is_a_400(client: TestClient) -> None:
    refused = client.post(
        "/api/v1/admin/audio",
        content=b"whatever",
        headers={**bearer(client), "Content-Type": "multipart/form-data"},
    )
    assert refused.status_code == 400


# --- AC-6: the client names nothing on disk -----------------------------------------------


@pytest.mark.ac("AC-6")
def test_ac6_a_hostile_filename_is_a_label_and_the_file_is_named_by_its_id(
    client: TestClient, blobs: Path
) -> None:
    clip = upload(client, "audio", OGG, "audio/ogg", filename="../../../../tmp/evil.ogg").json()
    assert clip["filename"] == "evil.ogg"
    assert [path.name for path in stored_files(blobs)] == [clip["id"]]
    assert all(path.is_relative_to(blobs) for path in stored_files(blobs))


# --- AC-7: mixing, through FFmpeg or a stand-in for it ------------------------------------


def stand_in(tmp_path: Path, body: str, name: str = "ffmpeg") -> Path:
    """An executable that takes FFmpeg's place, so mixing is provable without FFmpeg."""
    binary = tmp_path / name
    binary.write_text(f"#!{sys.executable}\n{body}\n")
    binary.chmod(0o755)
    return binary


def recording_ffmpeg(tmp_path: Path) -> tuple[Path, Path]:
    record = tmp_path / "argv.json"
    binary = stand_in(
        tmp_path,
        "import json, os, sys, pathlib\n"
        f"pathlib.Path({str(record)!r}).write_text(json.dumps({{'argv': sys.argv, 'cwd': os.getcwd()}}))\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'OggS' + b'mixed' * 100)\n",
    )
    return binary, record


def mix(client: TestClient, body: Any) -> Any:
    return client.post("/api/v1/admin/audio/mix", json=body, headers=bearer(client))


@pytest.mark.ac("AC-7")
def test_ac7_mixing_without_a_mixer_configured_is_a_503(client: TestClient) -> None:
    clip = upload(client, "audio", OGG, "audio/ogg").json()
    refused = mix(client, {"filename": "m.ogg", "tracks": [{"clipId": clip["id"]}]})
    assert refused.status_code == 503
    assert "WAVEMAKER_MEDIA_FFMPEG_BINARY" in refused.json()["detail"]


@pytest.mark.ac("AC-7")
def test_ac7_a_mix_becomes_an_ordinary_clip(
    database_url: str, blobs: Path, tmp_path: Path
) -> None:
    binary, record = recording_ffmpeg(tmp_path)
    app = build(database_url, blobs, ffmpeg_binary=binary)
    with TestClient(app) as client:
        hostile = "; rm -rf ~ $(touch pwned).ogg"
        first = upload(client, "audio", OGG, "audio/ogg", filename=hostile).json()
        second = upload(client, "audio", OGG + b"2", "audio/ogg", filename="b.ogg").json()

        mixed = mix(
            client,
            {"filename": "boss.ogg", "tracks": [{"clipId": first["id"]},
                                                {"clipId": second["id"], "gainDb": -6}]},
        )
        assert mixed.status_code == 201, mixed.text
        clip = mixed.json()
        assert set(clip) == SUMMARY_FIELDS
        assert clip["filename"] == "boss.ogg"
        assert clip["contentType"] == "audio/ogg"

        listed = [c["id"] for c in client.get("/api/v1/admin/audio", headers=bearer(client)).json()]
        assert clip["id"] in listed
        assert client.get(f"/api/v1/public/audio/{clip['id']}").content == b"OggS" + b"mixed" * 100

    ran = json.loads(record.read_text())
    argv: list[str] = ran["argv"]
    assert argv[0] == str(binary)
    graph = argv[argv.index("-filter_complex") + 1]
    assert graph == (
        "[0:a]volume=0.000dB[a0];[1:a]volume=-6.000dB[a1];"
        "[a0][a1]amix=inputs=2:duration=longest:normalize=0[out]"
    )
    inputs = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-i"]
    assert [Path(p).name for p in inputs] == ["0.in", "1.in"]
    assert not any(hostile in arg or first["id"] in arg or "rm -rf" in arg for arg in argv), (
        "no client string, and no path into the store, may reach the command line"
    )
    assert not Path(ran["cwd"]).exists(), "the mix's working directory is removed afterwards"
    assert not (tmp_path / "pwned").exists()


@pytest.mark.ac("AC-7")
def test_ac7_a_track_that_is_not_a_clip_here_is_named(
    database_url: str, blobs: Path, tmp_path: Path
) -> None:
    binary, record = recording_ffmpeg(tmp_path)
    app = build(database_url, blobs, ffmpeg_binary=binary)
    with TestClient(app) as client:
        clip = upload(client, "audio", OGG, "audio/ogg").json()
        sprite = upload(client, "sprites", PNG, "image/png").json()
        refused = mix(
            client, {"filename": "m.ogg", "tracks": [{"clipId": clip["id"]}, {"clipId": sprite["id"]}]}
        )
        assert refused.status_code == 422
        assert refused.json()["detail"].startswith("/tracks/1")
    assert not record.exists(), "nothing is run until every track is found"


@pytest.mark.ac("AC-7")
def test_ac7_a_bad_mix_request_is_a_422_with_the_field(
    database_url: str, blobs: Path, tmp_path: Path
) -> None:
    binary, _ = recording_ffmpeg(tmp_path)
    app = build(database_url, blobs, ffmpeg_binary=binary)
    with TestClient(app) as client:
        refused = mix(client, {"filename": "m.ogg", "tracks": [{"clipId": "x"}]})
        assert refused.status_code == 422
        assert refused.json()["detail"].startswith("/tracks/0/clipId")


@pytest.mark.ac("AC-7")
def test_ac7_a_mixer_that_fails_does_not_leak_what_it_said(
    database_url: str, blobs: Path, tmp_path: Path
) -> None:
    """The tool's message names paths inside the container. An error body is not a place to
    disclose the filesystem."""
    binary = stand_in(tmp_path, "import sys\nprint('/srv/secret/path is broken')\nsys.exit(1)")
    app = build(database_url, blobs, ffmpeg_binary=binary)
    with TestClient(app) as client:
        clip = upload(client, "audio", OGG, "audio/ogg").json()
        refused = mix(client, {"filename": "m.ogg", "tracks": [{"clipId": clip["id"]}]})
        assert refused.status_code == 422
        assert "/srv/secret" not in refused.text
        assert len(client.get("/api/v1/admin/audio", headers=bearer(client)).json()) == 1


@pytest.mark.ac("AC-7")
def test_ac7_a_mix_over_the_output_cap_is_refused(
    database_url: str, blobs: Path, tmp_path: Path
) -> None:
    binary = stand_in(tmp_path, "import sys, pathlib\npathlib.Path(sys.argv[-1]).write_bytes(b'x' * 5000)")
    app = build(database_url, blobs, ffmpeg_binary=binary, mix_max_output_bytes=1000)
    with TestClient(app) as client:
        clip = upload(client, "audio", OGG, "audio/ogg").json()
        refused = mix(client, {"filename": "m.ogg", "tracks": [{"clipId": clip["id"]}]})
        assert refused.status_code == 422
        assert len(client.get("/api/v1/admin/audio", headers=bearer(client)).json()) == 1


def sine_wav(frequency: float, seconds: float = 0.25, rate: int = 8000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(
            b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * frequency * n / rate)))
                for n in range(int(seconds * rate))
            )
        )
    return out.getvalue()


@pytest.mark.ac("AC-7")
@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg is not installed here. The argv, timeout and failure tests above use a "
    "stand-in and still run; only producing real Ogg Vorbis needs the real binary.",
)
def test_ac7_real_ffmpeg_mixes_two_clips_into_ogg(database_url: str, blobs: Path) -> None:
    binary = Path(str(shutil.which("ffmpeg"))).resolve()
    app = build(database_url, blobs, ffmpeg_binary=binary)
    with TestClient(app) as client:
        low = upload(client, "audio", sine_wav(220), "audio/wav", filename="low.wav").json()
        high = upload(client, "audio", sine_wav(440), "audio/wav", filename="high.wav").json()
        mixed = mix(
            client,
            {"filename": "chord.ogg", "tracks": [{"clipId": low["id"]},
                                                 {"clipId": high["id"], "gainDb": -3.5}]},
        )
        assert mixed.status_code == 201, mixed.text
        served = client.get(f"/api/v1/public/audio/{mixed.json()['id']}")
        assert served.headers["content-type"] == "audio/ogg"
        assert served.content.startswith(b"OggS")


# --- AC-8: the limit is a limit, through HTTP too -----------------------------------------


@pytest.mark.ac("AC-8")
def test_ac8_a_mixer_that_hangs_is_stopped_at_its_limit(
    database_url: str, blobs: Path, tmp_path: Path
) -> None:
    binary = stand_in(tmp_path, "import time\ntime.sleep(60)")
    app = build(database_url, blobs, ffmpeg_binary=binary, mix_timeout_seconds=1)
    with TestClient(app) as client:
        clip = upload(client, "audio", OGG, "audio/ogg").json()
        started = time.monotonic()
        refused = mix(client, {"filename": "m.ogg", "tracks": [{"clipId": clip["id"]}]})
        elapsed = time.monotonic() - started
        assert refused.status_code == 503
        assert "1" in refused.json()["detail"]
        assert len(client.get("/api/v1/admin/audio", headers=bearer(client)).json()) == 1
    assert elapsed < 2.5, f"a one-second limit took {elapsed:.2f}s through HTTP"


# --- AC-9: what is configured decides what is on ------------------------------------------


@pytest.mark.ac("AC-9")
def test_ac9_with_no_blob_directory_media_is_off_and_says_so(database_url: str) -> None:
    with TestClient(build(database_url, None)) as client:
        refused = client.get("/api/v1/admin/audio", headers=bearer(client))
        assert refused.status_code == 503
        assert "WAVEMAKER_BLOB_DIRECTORY" in refused.json()["detail"]
        assert upload(client, "sprites", PNG, "image/png").status_code == 503
        assert client.get(f"/api/v1/public/audio/{uuid.uuid4()}").status_code == 404


@pytest.mark.ac("AC-9")
def test_ac9_with_no_database_a_public_asset_is_simply_not_there(tmp_path: Path) -> None:
    """A fresh install with nothing configured looks like a service with no art, not a broken
    one — the same answer the content app gives with no database."""
    app = create_app(Settings(plugins_directory=None, blob_directory=tmp_path / "blobs"))
    with TestClient(app) as client:
        assert client.get(f"/api/v1/public/sprites/{uuid.uuid4()}").status_code == 404
        assert client.get(f"/api/v1/public/audio/{uuid.uuid4()}").status_code == 404


@pytest.mark.ac("AC-9")
def test_ac9_a_blob_directory_that_is_a_file_stops_the_start(
    database_url: str, tmp_path: Path
) -> None:
    occupied = tmp_path / "occupied"
    occupied.write_text("")
    with pytest.raises(ConfigurationError, match="WAVEMAKER_BLOB_DIRECTORY"):
        build(database_url, occupied)


@pytest.mark.ac("AC-9")
def test_ac9_a_relative_ffmpeg_path_is_refused() -> None:
    """An absolute path, not a name resolved against PATH: "whatever ffmpeg means on this
    machine today" is not a configuration."""
    with pytest.raises(ValueError, match="absolute"):
        MediaSettings(ffmpeg_binary=Path("ffmpeg"))


def test_the_shared_pattern_is_one_buffer() -> None:
    """The streaming test relies on this: the test itself must not hold the upload."""
    assert all(chunk is PATTERN for chunk in list(pattern(4 * len(PATTERN))))
