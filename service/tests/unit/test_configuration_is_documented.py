"""Every setting the service reads is documented, and everything documented is read.

Carried over from the Java's `ConfigurationIsDocumentedTest`, and the direction people forget is
the second one. An undocumented setting is found by reading source code, or not at all. A
documented setting that no longer exists is worse: somebody sets it, watches nothing happen, and
cannot tell whether it was ignored or misspelled.

What the service reads is taken from the settings classes themselves and from the one place it
reads the environment directly, so a new field is checked without anybody listing it here. What
compose reads is taken from the compose file, so the exceptions below are proved rather than
asserted.
"""

from __future__ import annotations

import re
from pathlib import Path

from wavemaker.apps.media.adapters.settings import MediaSettings
from wavemaker.platform.config import Settings

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "service" / "src"
GUIDE = ROOT / "docs" / "operations" / "configuration.md"
ENV_EXAMPLE = ROOT / "deploy" / ".env.example"
COMPOSE = ROOT / "deploy" / "docker-compose.yml"

# The editor's own two settings, under the names the editor reads. Not the service's business,
# documented on the same page because an operator does not care which container reads them.
EDITOR_SETTINGS = {"LUDUS_ENGINE_URL", "LUDUS_EDITOR_HTTPS"}


def prefixed(settings: type[Settings] | type[MediaSettings]) -> set[str]:
    prefix = str(settings.model_config.get("env_prefix", ""))
    return {f"{prefix}{name}".upper() for name in settings.model_fields}


def read_by_the_service() -> set[str]:
    direct = {
        match
        for path in SOURCE.rglob("*.py")
        for match in re.findall(
            r"""os\.environ(?:\.get)?\(\s*["'](WAVEMAKER_[A-Z0-9_]+)""", path.read_text()
        )
    }
    return prefixed(Settings) | prefixed(MediaSettings) | direct


def read_by_compose() -> set[str]:
    return set(re.findall(r"\$\{(WAVEMAKER_[A-Z0-9_]+)", COMPOSE.read_text()))


def documented() -> set[str]:
    return set(re.findall(r"`((?:WAVEMAKER|LUDUS)_[A-Z0-9_]+)`", GUIDE.read_text()))


def test_the_service_reads_settings_and_this_test_can_see_them() -> None:
    read = read_by_the_service()
    assert "WAVEMAKER_JWT_SECRET" in read
    assert "WAVEMAKER_MEDIA_FFMPEG_BINARY" in read
    assert "WAVEMAKER_WAVE_SCHEMA" in read, "the content app's direct read was found"


def test_every_setting_the_service_reads_is_in_the_configuration_guide() -> None:
    undocumented = read_by_the_service() - documented()
    assert not undocumented, f"add a row to docs/operations/configuration.md for {undocumented}"


def test_every_setting_in_the_guide_is_one_something_actually_reads() -> None:
    stale = documented() - read_by_the_service() - read_by_compose() - EDITOR_SETTINGS
    assert not stale, f"documented, and nothing reads them: {sorted(stale)}"


def test_the_sample_env_file_names_every_setting_the_service_reads() -> None:
    """Set, commented out, or listed as set by compose and the image: an operator copying the
    file sees every knob there is."""
    mentioned = set(re.findall(r"WAVEMAKER_[A-Z0-9_]+", ENV_EXAMPLE.read_text()))
    missing = read_by_the_service() - mentioned
    assert not missing, f"deploy/.env.example does not mention {sorted(missing)}"


def test_the_sample_env_file_only_names_settings_that_exist() -> None:
    """The file people copy. A line in it that nothing reads is one somebody will rely on."""
    lines = set(re.findall(r"(?m)^#?((?:WAVEMAKER|LUDUS)_[A-Z0-9_]+)=", ENV_EXAMPLE.read_text()))
    assert lines
    unknown = lines - read_by_the_service() - read_by_compose() - EDITOR_SETTINGS
    assert not unknown, f"deploy/.env.example names settings nothing reads: {sorted(unknown)}"


def test_no_setting_of_the_java_engine_is_left_in_the_sample() -> None:
    """The Java read LUDUS_* settings. The editor's two are the only LUDUS_ names left."""
    ludus = set(re.findall(r"(?m)^#?(LUDUS_[A-Z0-9_]+)=", ENV_EXAMPLE.read_text()))
    assert ludus <= EDITOR_SETTINGS
