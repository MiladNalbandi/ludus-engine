"""The settings a game client reads at launch.

Free-form, deliberately. Waves have a schema because the service interprets them: it reads an
order, a name and a publication state out of the document. Nothing in a configuration is
interpreted at all. It is carried from an editor to a client, and what the keys mean is between
the game and whoever tunes it. A schema here would mean a release of the service every time a
game wanted a new difficulty knob.

Replaced whole, never patched. A merge has to decide what a null means, whether an absent key
removes or keeps, and how deep to go, and the service cannot answer any of those for keys it
does not understand.

Stored verbatim, like a wave, and for the sharper version of the same reason: this document is
fetched by every client on every launch, so a tag that moved when nothing changed would cost
more here than anywhere else.
"""

from __future__ import annotations

import json

from wavemaker.apps.content.domain.document import DocumentError
from wavemaker.platform.kernel.storable import refuse_unstorable_in

# What a project that was never configured has. An empty object rather than a 404, because
# "no overrides" is exactly what an empty object says, and a client that must handle an absent
# document as a separate case will handle it wrongly on one of its platforms. Unlike the active
# level, absence is not a real state here: an unconfigured game plays on its built-in defaults.
EMPTY = b"{}"


def accept(raw: bytes) -> bytes:
    """`raw`, unchanged, when it is a document a client could be served; `DocumentError` naming
    the problem when it is not.

    Parsed only to be checked, then thrown away. The parser's line and column are kept in the
    message, because they are the only part of it an editor can act on.
    """
    if not raw.strip():
        raise DocumentError("A configuration document must not be empty.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as broken:
        raise DocumentError(f"This is not JSON: {broken}") from broken
    except UnicodeDecodeError as broken:
        raise DocumentError(f"This is not UTF-8 text: {broken}") from broken
    # Valid JSON that PostgreSQL cannot hold — a NUL, a lone surrogate — would otherwise fail
    # as the generated jsonb column is computed, as a 500.
    refuse_unstorable_in(parsed)
    return raw
