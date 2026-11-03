"""AC-4, AC-5 and AC-6: what an upload may be, decided from its bytes and not its label.

A sprite is served back from this service's own origin. Anything that a browser would render
as a document there — SVG most of all, because it is XML that may carry script — is a way to
run code as this service. So the label a client sends is checked, and then the content is
checked again, because a label is only what the client chose to say.
"""

from __future__ import annotations

import uuid

import pytest

from wavemaker.apps.media.domain.asset import AssetKind, display_name, parse_id
from wavemaker.apps.media.domain.formats import (
    UnsupportedFormat,
    accept_content,
    accept_declared,
    sniff_image,
)
from wavemaker.apps.media.domain.mix import MixRefused, filter_graph, read_mix

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 28
GIF = b"GIF89a" + b"\x00" * 26
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.mark.ac("AC-4")
@pytest.mark.parametrize(
    ("head", "expected"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (GIF, "image/gif"), (WEBP, "image/webp")],
)
def test_ac4_raster_formats_are_recognised_from_their_bytes(head: bytes, expected: str) -> None:
    assert sniff_image(head) == expected


@pytest.mark.ac("AC-4")
@pytest.mark.parametrize(
    "head",
    [
        SVG,
        b'<?xml version="1.0"?><svg/>',
        b"\xef\xbb\xbf  <svg/>",  # a byte-order mark and whitespace are still an SVG
        b"<html><script>alert(1)</script></html>",
        b"RIFF\x00\x00\x00\x00WAVEfmt ",  # RIFF, but audio: not a WebP
        b"",
    ],
)
def test_ac4_anything_else_is_not_an_image(head: bytes) -> None:
    assert sniff_image(head) is None


@pytest.mark.ac("AC-4")
def test_ac4_svg_is_refused_when_it_says_it_is_svg() -> None:
    with pytest.raises(UnsupportedFormat, match="SVG"):
        accept_declared(AssetKind.SPRITE, "image/svg+xml")


@pytest.mark.ac("AC-4")
def test_ac4_svg_is_refused_when_it_claims_to_be_a_png() -> None:
    """The label passes. The content does not, and the content is what a browser renders."""
    declared = accept_declared(AssetKind.SPRITE, "image/png")
    with pytest.raises(UnsupportedFormat, match="SVG"):
        accept_content(AssetKind.SPRITE, declared, SVG)


@pytest.mark.ac("AC-4")
def test_ac4_a_png_labelled_as_a_jpeg_is_refused() -> None:
    """Two sources for one fact. Picking either would mean serving a type nobody checked."""
    declared = accept_declared(AssetKind.SPRITE, "image/jpeg")
    with pytest.raises(UnsupportedFormat, match="image/png"):
        accept_content(AssetKind.SPRITE, declared, PNG)


@pytest.mark.ac("AC-4")
def test_ac4_a_real_png_is_accepted_with_its_type() -> None:
    assert accept_content(AssetKind.SPRITE, "image/png", PNG) == "image/png"


@pytest.mark.ac("AC-5")
@pytest.mark.parametrize(
    ("kind", "declared"),
    [
        (AssetKind.AUDIO, "text/html"),
        (AssetKind.AUDIO, "image/png"),
        (AssetKind.AUDIO, ""),
        (AssetKind.SPRITE, "audio/ogg"),
        (AssetKind.SPRITE, "application/octet-stream"),
        (AssetKind.SPRITE, "text/xml"),
    ],
)
def test_ac5_a_type_outside_the_allow_list_is_refused(kind: AssetKind, declared: str) -> None:
    with pytest.raises(UnsupportedFormat):
        accept_declared(kind, declared)


@pytest.mark.ac("AC-5")
def test_ac5_parameters_and_case_are_not_part_of_the_type() -> None:
    """`audio/mpeg; charset=binary` is a thing browsers send."""
    assert accept_declared(AssetKind.AUDIO, "Audio/MPEG; charset=binary") == "audio/mpeg"


@pytest.mark.ac("AC-6")
@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        ("kick.ogg", "kick.ogg"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\boss theme.ogg", "boss theme.ogg"),
        ("folder/", "untitled"),
        ("", "untitled"),
        (None, "untitled"),
        ("a\x00b\nc.ogg", "abc.ogg"),
        ("x" * 400 + ".ogg", "x" * 255),
    ],
)
def test_ac6_a_filename_is_reduced_to_a_label(submitted: str | None, expected: str) -> None:
    """A filename is never a path here. It is still cut to its last segment, because storing
    `../../etc/passwd` as a display name invites some later reader to treat it as one."""
    assert display_name(submitted) == expected


@pytest.mark.ac("AC-6")
@pytest.mark.parametrize("raw", ["../secret", "not-a-uuid", "", "0" * 32 + "/..", "%2e%2e"])
def test_ac6_an_id_that_is_not_a_uuid_is_not_an_id(raw: str) -> None:
    assert parse_id(raw) is None


@pytest.mark.ac("AC-6")
def test_ac6_a_uuid_is_read_back_in_its_canonical_form() -> None:
    clip = uuid.uuid4()
    assert parse_id(str(clip).upper()) == clip


# --- the mix request ------------------------------------------------------------------------


@pytest.mark.ac("AC-7")
def test_ac7_the_filter_graph_is_built_from_numbers_only() -> None:
    assert filter_graph([0.0, -6.5]) == (
        "[0:a]volume=0.000dB[a0];[1:a]volume=-6.500dB[a1];"
        "[a0][a1]amix=inputs=2:duration=longest:normalize=0[out]"
    )


@pytest.mark.ac("AC-7")
def test_ac7_a_mix_request_is_read_into_tracks() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    mix = read_mix(
        {
            "filename": "boss.ogg",
            "tracks": [{"clipId": str(first)}, {"clipId": str(second), "gainDb": -3}],
        },
        max_tracks=8,
    )
    assert mix.filename == "boss.ogg"
    assert [(t.clip_id, t.gain_db) for t in mix.tracks] == [(first, 0.0), (second, -3.0)]


@pytest.mark.ac("AC-7")
@pytest.mark.parametrize(
    ("body", "pointer"),
    [
        ([], ""),
        ({"tracks": [{"clipId": str(uuid.UUID(int=1))}]}, "/filename"),
        ({"filename": "  ", "tracks": [{"clipId": str(uuid.UUID(int=1))}]}, "/filename"),
        ({"filename": "m.ogg"}, "/tracks"),
        ({"filename": "m.ogg", "tracks": []}, "/tracks"),
        ({"filename": "m.ogg", "tracks": [{"clipId": "nope"}]}, "/tracks/0/clipId"),
        (
            {"filename": "m.ogg", "tracks": [{"clipId": str(uuid.UUID(int=1)), "gainDb": "loud"}]},
            "/tracks/0/gainDb",
        ),
        (
            {
                "filename": "m.ogg",
                "tracks": [{"clipId": str(uuid.UUID(int=1)), "gainDb": float("nan")}],
            },
            "/tracks/0/gainDb",
        ),
        (
            {"filename": "m.ogg", "tracks": [{"clipId": str(uuid.UUID(int=1)), "gainDb": 1e300}]},
            "/tracks/0/gainDb",
        ),
        (
            {"filename": "m.ogg", "tracks": [{"clipId": str(uuid.UUID(int=1)), "gainDb": True}]},
            "/tracks/0/gainDb",
        ),
        (
            {"filename": "m.ogg", "tracks": [{"clipId": str(uuid.UUID(int=i))} for i in range(9)]},
            "/tracks",
        ),
    ],
)
def test_ac7_a_bad_mix_request_names_the_field(body: object, pointer: str) -> None:
    with pytest.raises(MixRefused) as refused:
        read_mix(body, max_tracks=8)
    assert refused.value.pointer == pointer
