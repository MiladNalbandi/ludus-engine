"""What may be uploaded, as allow-lists, and how a sprite's bytes are checked against its label.

Everything uploaded here is served back from this service's own origin with the type it was
stored under. An allow-list rather than a deny-list, because the dangerous types are the ones
nobody thought of: accepting `text/html` would make this a way to host a page on the API's
origin.

**SVG is refused as a sprite.** It is XML that may carry `<script>`, and a browser rendering
one served from this origin runs it there. Stripping script from SVG reliably is a sanitiser's
whole job, and shipping one is a bigger commitment than declining the format. A project that
wants vector art can serve it from somewhere that is not this origin: an item's sprite
reference is deliberately opaque, and a URL is a perfectly good one.

**A sprite's content is checked, not just its label.** The label is whatever the client chose
to say; the bytes are what a browser renders. A sprite is accepted only when its first bytes
are a PNG, JPEG, WebP or GIF signature *and* that is the type it was labelled with. Anything
that begins like markup is refused as SVG would be, whatever it claims to be.

Audio is checked by label only, as the Java did. Audio formats have no single reliable
signature (an MP3 may start with an ID3 tag or straight with a frame), and a mislabelled clip
is served with `X-Content-Type-Options: nosniff` and the type it was accepted under, so a
browser never treats it as a document.
"""

from __future__ import annotations

from wavemaker.apps.media.domain.asset import AssetKind

AUDIO_TYPES = frozenset(
    {"audio/mpeg", "audio/ogg", "audio/wav", "audio/x-wav", "audio/webm", "audio/aac", "audio/flac"}
)
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
SVG = "image/svg+xml"

SVG_REFUSED = (
    "SVG is not accepted as a sprite: it is a document that can carry script, and it would run "
    "on this service's origin. Upload a PNG, JPEG, WebP or GIF instead."
)

UTF8_BOM = b"\xef\xbb\xbf"


class UnsupportedFormat(Exception):
    """The upload is not a type this service will store and serve."""


def normalise(declared: str | None) -> str:
    """`audio/mpeg; charset=binary` is a thing browsers send."""
    return (declared or "").split(";", 1)[0].strip().lower()


def accept_declared(kind: AssetKind, declared: str | None) -> str:
    """The label, before any bytes are read. Refusing here means a wrong type is never written."""
    content_type = normalise(declared)
    if kind is AssetKind.SPRITE and content_type == SVG:
        raise UnsupportedFormat(SVG_REFUSED)

    allowed = AUDIO_TYPES if kind is AssetKind.AUDIO else IMAGE_TYPES
    if content_type not in allowed:
        noun = "audio" if kind is AssetKind.AUDIO else "image"
        raise UnsupportedFormat(
            f"'{content_type or 'no type'}' is not an accepted {noun} type; expected one of "
            f"{', '.join(sorted(allowed))}."
        )
    return content_type


def accept_content(kind: AssetKind, declared: str, head: bytes) -> str:
    """The type to store and serve, decided from the first bytes of what actually arrived."""
    if kind is AssetKind.AUDIO:
        return declared

    if looks_like_markup(head):
        raise UnsupportedFormat(SVG_REFUSED)
    sniffed = sniff_image(head)
    if sniffed is None:
        raise UnsupportedFormat("The file is not a PNG, JPEG, WebP or GIF image.")
    if sniffed != declared:
        # Two sources for one fact. Picking either would mean serving a type nobody checked.
        raise UnsupportedFormat(
            f"The file was sent as {declared} but its bytes are {sniffed}. Send it as {sniffed}."
        )
    return sniffed


def sniff_image(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def looks_like_markup(head: bytes) -> bool:
    """SVG, HTML or any XML: whatever a browser might parse as a document."""
    return head.removeprefix(UTF8_BOM).lstrip().startswith(b"<")
