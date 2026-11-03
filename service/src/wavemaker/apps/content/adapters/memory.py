"""A repository that holds everything in memory.

It exists so the read surface, the hashing and the conditional requests can be built and
proved before a database is chosen. The PostgreSQL adapter replaces it behind the same port,
and nothing above this line changes when it does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from wavemaker.apps.content.domain.wave import PlayableLevel, WaveSummary


class InMemoryWaveRepository:
    def __init__(
        self,
        waves: Sequence[WaveSummary],
        documents: Mapping[str, bytes],
        level: PlayableLevel | None,
        app_config: bytes | None = None,
    ) -> None:
        self._waves = list(waves)
        self._documents = dict(documents)
        self._level = level
        self._app_config = app_config

    def published_catalogue(self) -> Sequence[WaveSummary]:
        return [wave for wave in sorted(self._waves, key=lambda w: w.order) if wave.published]

    def find_published(self, wave_id: str) -> WaveSummary | None:
        return next((w for w in self._waves if w.id == wave_id and w.published), None)

    def published_document(self, wave_id: str) -> bytes | None:
        if self.find_published(wave_id) is None:
            return None
        return self._documents.get(wave_id)

    def published_documents(self, wave_ids: Sequence[str]) -> Mapping[str, bytes]:
        found = {}
        for wave_id in wave_ids:
            document = self.published_document(wave_id)
            if document is not None:
                found[wave_id] = document
        return found

    def active_level(self) -> PlayableLevel | None:
        return self._level

    def app_config(self) -> bytes | None:
        return self._app_config
