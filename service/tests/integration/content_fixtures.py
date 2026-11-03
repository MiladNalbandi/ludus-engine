"""The content the read tests are run against.

Three waves, two published and one draft, which is the same shape as samples/waves/ and the
same shape the editor screenshots show. The draft exists so that "a draft is a 404" has
something real to be absent.
"""

from datetime import UTC, datetime

from wavemaker.apps.content.domain.wave import PlayableLevel, WaveSummary

CREATED = datetime(2026, 9, 13, 16, 58, 40, tzinfo=UTC)
UPDATED = datetime(2026, 9, 13, 16, 58, 40, 548722, tzinfo=UTC)


def _summary(wave_id: str, name: str, order: int, *, published: bool) -> WaveSummary:
    return WaveSummary(
        id=wave_id,
        name=name,
        order=order,
        schema_version=1,
        published=published,
        created_at=CREATED,
        updated_at=UPDATED,
    )


WAVES = [
    _summary("demo_first_steps", "First Steps", 0, published=True),
    _summary("demo_crossfire", "Crossfire", 1, published=True),
    _summary("demo_pressure", "Pressure", 2, published=False),
]

# Stored verbatim: these are the bytes a client gets back, down to the spacing. The raw route
# must not re-serialise them, because re-serialising moves every client's ETag.
DOCUMENTS = {
    "demo_first_steps": b'{"id":"demo_first_steps","schema_version":1,"name":"First Steps"}',
    "demo_crossfire": b'{"id":"demo_crossfire","schema_version":1,"name":"Crossfire"}',
    "demo_pressure": b'{"id":"demo_pressure","schema_version":1,"name":"Pressure"}',
}

# The level includes the draft. A client is served only the two published waves, which is the
# "2 of 3 reach players" the editor shows.
LEVEL = PlayableLevel(
    id="35163115-e362-492b-b6b8-4bfd75c96fc6",
    name="Act One",
    wave_ids=["demo_first_steps", "demo_crossfire", "demo_pressure"],
)
