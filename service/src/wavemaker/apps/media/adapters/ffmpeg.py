"""Mixing with FFmpeg, through `run_bounded` and never through a shell.

Carried over from the Java's `FfmpegAudioMixer`, with its timeout fixed (see `process.py`):

- **No client string ever becomes an argument.** Inputs are copied into a fresh working
  directory under names generated from their position — `0.in`, `1.in`. No uploaded filename,
  no clip id and no path into the blob store reaches the command line; the only caller
  influence on it is how many tracks there are and the gains, which are formatted numbers.
- **An absolute binary path**, not a name looked up on `PATH`. "Whatever ffmpeg means on this
  machine today" is not a configuration.
- **A cap on output**, passed to FFmpeg as `-fs` so it stops writing, and checked after it
  exits, because a filter graph can produce far more than it consumes and the disk is shared
  with every upload.
- **One directory per job**, removed when the mix's stream is closed, so two mixes cannot see
  each other's files and a failure leaves nothing behind.

The tool's own output is logged, never returned: it names paths inside the container, and an
error response is not a place to disclose the filesystem.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from wavemaker.apps.media.adapters.process import ProcessTimedOut, run_bounded
from wavemaker.apps.media.application.ports import (
    MixFailed,
    MixSource,
    MixTimedOut,
    MixUnavailable,
)
from wavemaker.apps.media.domain.mix import filter_graph

log = logging.getLogger(__name__)

CHUNK = 64 * 1024
# What mixing produces. One format, so nothing about the output depends on the inputs.
OUTPUT_CONTENT_TYPE = "audio/ogg"
LOGGED_OUTPUT = 4096


class FfmpegMixer:
    content_type = OUTPUT_CONTENT_TYPE

    def __init__(
        self, binary: Path, *, timeout: float, max_output_bytes: int, max_tracks: int
    ) -> None:
        self._binary = binary
        self._timeout = timeout
        self._max_output = max_output_bytes
        self._max_tracks = max_tracks

    def available(self) -> bool:
        return self._binary.is_file() and os.access(self._binary, os.X_OK)

    @contextmanager
    def mix(self, sources: Sequence[MixSource]) -> Iterator[BinaryIO]:
        if not sources:
            raise MixFailed("There is nothing to mix.")
        if len(sources) > self._max_tracks:
            raise MixFailed(f"At most {self._max_tracks} tracks per mix.")
        if not self.available():
            raise MixUnavailable(
                "Mixing is configured, but WAVEMAKER_MEDIA_FFMPEG_BINARY is not an executable "
                "file on this machine."
            )

        job = Path(tempfile.mkdtemp(prefix="wavemaker-mix-"))
        try:
            inputs = []
            for index, source in enumerate(sources):
                # Named from the position, not from anything a caller supplied.
                path = job / f"{index}.in"
                with path.open("wb") as copy:
                    shutil.copyfileobj(source.bytes, copy, CHUNK)
                inputs.append(path)

            output = job / "mixed.ogg"
            self._run(self.command(inputs, [s.gain_db for s in sources], output), job)

            size = output.stat().st_size if output.is_file() else 0
            if size == 0:
                raise MixFailed("Mixing produced an empty file.")
            if size > self._max_output:
                raise MixFailed(f"The mix came to more than the limit of {self._max_output} bytes.")
            with output.open("rb") as mixed:
                yield mixed
        finally:
            shutil.rmtree(job, ignore_errors=True)

    def command(self, inputs: Sequence[Path], gains: Sequence[float], output: Path) -> list[str]:
        """The argument list. Every element is a literal written here, a path this class
        generated, or a number it formatted."""
        argv = [str(self._binary), "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
        for path in inputs:
            argv += ["-i", str(path)]
        argv += [
            "-filter_complex", filter_graph(gains),
            "-map", "[out]",
            "-c:a", "libvorbis",
            "-fs", str(self._max_output),
            str(output),
        ]  # fmt: skip
        return argv

    def _run(self, argv: list[str], job: Path) -> None:
        tool_log = job / "mixer.log"
        try:
            code = run_bounded(argv, cwd=job, log=tool_log, timeout=self._timeout)
        except ProcessTimedOut as stopped:
            raise MixTimedOut(
                f"Mixing took longer than {stopped.timeout:g} seconds and was stopped."
            ) from stopped
        except OSError as cannot_start:
            raise MixUnavailable(
                "The mixer could not be started on this machine."
            ) from cannot_start

        if code != 0:
            said = tool_log.read_bytes()[:LOGGED_OUTPUT].decode(errors="replace")
            log.warning("ffmpeg exited with %s: %s", code, said)
            raise MixFailed("The mixer could not combine those tracks.")
