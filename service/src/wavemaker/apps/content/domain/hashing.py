"""One function behind both the poll hash and the list ETag.

A client polls `/status` on every launch and refetches when the hash moves. If the hash and
the list ETag were computed in two places they could disagree, and then a client is told
"changed", refetches, and is handed a 304 validated against the other one. It never settles,
and nothing in a log looks wrong. The only reliable fix is for there to be one function, so
there is one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from wavemaker.apps.content.domain.wave import WaveSummary

# A hash is an opaque token to every client, so the length is ours to choose. 32 hex characters
# is far past any collision that matters here and keeps a header short.
LENGTH = 32


def of_document(document: bytes) -> str:
    """The tag for one stored document, over its exact bytes.

    Not over a re-serialised copy: re-serialising changes the bytes, which changes the tag,
    which expires every client's cache for no reason at all.
    """
    return hashlib.sha256(document).hexdigest()[:LENGTH]


def of_catalogue(summaries: Iterable[WaveSummary]) -> str:
    """The tag for a whole catalogue.

    Sorted by id first, because the catalogue is a set of facts and row order is the
    database's business. Unsorted, a query plan change would look to every client like new
    content.
    """
    digest = hashlib.sha256()
    for summary in sorted(summaries, key=lambda wave: wave.id):
        digest.update(
            "\x1f".join(
                (
                    summary.id,
                    summary.name,
                    str(summary.order),
                    str(summary.schema_version),
                    str(summary.published),
                    summary.created_at.isoformat(),
                    summary.updated_at.isoformat(),
                )
            ).encode()
        )
        digest.update(b"\x1e")
    return digest.hexdigest()[:LENGTH]
