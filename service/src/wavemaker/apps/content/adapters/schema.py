"""Validating a wave document against the project's own schema.

The schema is a file in this repository, not something an author supplies, which makes this a
much smaller problem than it looks: there is no untrusted schema to defend against, no remote
`$ref` to refuse, and one document shape to check.

It is loaded once. Compiling a 33 KB schema on every save would make the validator the most
expensive part of authoring.

Errors are reported with a JSON Pointer to the offending field. "spawn_rules.0.movement_rules
is not valid" is a thing an author can fix; "the document is invalid" is not.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from wavemaker.apps.content.domain.document import DocumentError

# contracts/ is the project's, shared with the Java engine and the editor's type generator.
# Reached by walking out of service/src/wavemaker/apps/content/adapters/ to the repository root.
#
# That only works while this app lives in this repository. Once an app is a package somebody
# installs (R5), it has to carry its own schema — so the location is overridable, and a missing
# file says exactly which path was tried rather than failing deep inside the validator.
REPOSITORY_SCHEMA = Path(__file__).resolve().parents[6] / "contracts/schemas/wave/v1.json"
SCHEMA = Path(os.environ.get("WAVEMAKER_WAVE_SCHEMA", REPOSITORY_SCHEMA))


@functools.cache
def validator() -> Draft202012Validator:
    if not SCHEMA.is_file():
        raise DocumentError(
            f"The wave schema is not at {SCHEMA}. Set WAVEMAKER_WAVE_SCHEMA to point at it."
        )
    with SCHEMA.open("rb") as handle:
        return Draft202012Validator(json.load(handle))


def check(document: Any) -> None:
    """Raise `DocumentError` naming the first problem, or return quietly.

    First by position in the document rather than whichever the library yields first, so two
    runs over the same document report the same thing.
    """
    problems = sorted(validator().iter_errors(document), key=lambda error: list(error.path))
    if not problems:
        return
    raise DocumentError(_describe(problems[0]))


def _describe(problem: ValidationError) -> str:
    where = "/" + "/".join(str(step) for step in problem.path) if problem.path else "the document"
    return f"{where}: {problem.message}"
