"""Running an external tool with a time limit that is actually a limit.

The Java read the tool's output and then waited with a timeout. Reading blocks until the
process closes its output, so a process that hung was waited on forever before the timeout
was ever consulted: a test with a one-second limit took thirty seconds to fail. Reading after
the wait deadlocks the other way, once the process fills a pipe buffer nobody is draining.

So output goes to a **file**, and the only thing this function ever blocks on is `wait` with
the limit. The process has nothing to block on either: a file never fills up the way a pipe
does.

- **An argument list, never a command line.** No shell parses anything, so a semicolon, a
  backtick or `$(...)` in an argument is a character in an argument and nothing else. A string
  is refused outright rather than split, because splitting it is what a shell would do.
- **Its own process group**, killed as a group, so a tool that forks cannot leave a child
  running past its parent's limit.
- **No stdin.** FFmpeg reads stdin for interactive keys; a tool waiting on input would wait
  for the whole limit and then be reported as slow.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path


class ProcessTimedOut(Exception):
    def __init__(self, timeout: float) -> None:
        super().__init__(f"stopped after {timeout:g} seconds")
        self.timeout = timeout


def run_bounded(argv: Sequence[str], *, cwd: Path, log: Path, timeout: float) -> int:
    """Run `argv` to completion or to `timeout` seconds, whichever is first. Returns the exit
    code; raises `ProcessTimedOut` once the process and its group have been killed."""
    if isinstance(argv, str | bytes):
        raise TypeError("an argument list, not a command line: nothing here goes through a shell")

    with log.open("wb") as output:
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(process)
            raise ProcessTimedOut(timeout) from None
        except BaseException:
            # Interrupted while waiting: never leave the tool running behind us.
            _kill(process)
            raise


def _kill(process: subprocess.Popen[bytes]) -> None:
    # The group id is the leader's pid, because `start_new_session` made it the leader.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()
