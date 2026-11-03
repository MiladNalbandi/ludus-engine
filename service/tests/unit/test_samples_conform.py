"""Every sample wave conforms to the schema the service validates against.

Carried over from the Java's `WaveSchemaConformanceTest`. The samples are the only executable
documentation of the wire format, so a sample that has drifted from the contract is worse than
no sample: it teaches the wrong shape and gets copied. The editor runs the same files through
its own validator, which keeps the two honest about one schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from wavemaker.apps.content.adapters import schema
from wavemaker.apps.content.domain.document import DocumentError

SAMPLES = sorted((Path(__file__).resolve().parents[3] / "samples" / "waves").glob("*.json"))


def test_there_are_samples_to_check() -> None:
    assert len(SAMPLES) >= 3


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda path: path.name)
def test_each_sample_conforms_to_the_wave_schema(sample: Path) -> None:
    schema.check(json.loads(sample.read_text()))


def test_a_problem_is_reported_at_a_json_pointer() -> None:
    """A pointer such as /spawn_rules/0/count is something an author can act on."""
    document: dict[str, Any] = json.loads(SAMPLES[0].read_text())
    document["spawn_rules"][0]["count"] = "many"
    with pytest.raises(DocumentError, match=r"^/spawn_rules/0/count: "):
        schema.check(document)
