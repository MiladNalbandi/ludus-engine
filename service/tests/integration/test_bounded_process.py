"""AC-7 and AC-8: running an external tool with a limit that is actually a limit.

The Java read the tool's output and *then* waited with a timeout. Reading blocks until the
process closes its output, so a process that hung was waited on forever before the timeout was
ever consulted: a one-second limit took thirty seconds to fail. Reading after the wait instead
deadlocks the other way, once the process fills a pipe buffer nobody is draining.

The runner here sends output to a file, so neither can happen. These tests use a stand-in
command — the Python running them — so they prove the timeout on any machine, with or without
FFmpeg installed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from wavemaker.apps.media.adapters.process import ProcessTimedOut, run_bounded

PYTHON = sys.executable


@pytest.mark.ac("AC-8")
def test_ac8_a_process_that_hangs_is_killed_at_a_one_second_limit(tmp_path: Path) -> None:
    started = time.monotonic()
    with pytest.raises(ProcessTimedOut):
        run_bounded(
            [PYTHON, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            log=tmp_path / "tool.log",
            timeout=1.0,
        )
    elapsed = time.monotonic() - started
    assert 0.9 <= elapsed < 2.0, f"a one-second limit took {elapsed:.2f}s"


@pytest.mark.ac("AC-8")
def test_ac8_a_process_that_floods_its_output_and_hangs_is_still_killed(tmp_path: Path) -> None:
    """Ten megabytes is far past any pipe buffer. Through a pipe that nobody drains, the
    process blocks on its write and never reaches the sleep; read before waiting and the
    caller blocks on the read. Through a file, the limit is the only thing that decides."""
    flood = "import sys, time; sys.stdout.write('x' * 10_000_000); sys.stdout.flush(); time.sleep(60)"
    started = time.monotonic()
    with pytest.raises(ProcessTimedOut):
        run_bounded([PYTHON, "-c", flood], cwd=tmp_path, log=tmp_path / "tool.log", timeout=1.0)
    elapsed = time.monotonic() - started
    assert elapsed < 2.0, f"a one-second limit took {elapsed:.2f}s"


@pytest.mark.ac("AC-8")
def test_ac8_the_children_of_a_hung_process_are_killed_with_it(tmp_path: Path) -> None:
    """A tool that forks and hangs in the child would otherwise outlive its own timeout."""
    marker = tmp_path / "child-was-alive"
    child = f"import time, pathlib; time.sleep(3); pathlib.Path({str(marker)!r}).write_text('x')"
    parent = (
        f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "time.sleep(60)"
    )
    with pytest.raises(ProcessTimedOut):
        run_bounded([PYTHON, "-c", parent], cwd=tmp_path, log=tmp_path / "tool.log", timeout=1.0)
    time.sleep(3)
    assert not marker.exists(), "the child kept running after its parent was stopped"


def test_a_process_that_finishes_reports_its_exit_and_keeps_its_output(tmp_path: Path) -> None:
    log = tmp_path / "tool.log"
    code = run_bounded(
        [PYTHON, "-c", "import sys; print('said this'); sys.exit(3)"],
        cwd=tmp_path,
        log=log,
        timeout=10.0,
    )
    assert code == 3
    assert "said this" in log.read_text()


@pytest.mark.ac("AC-7")
def test_ac7_arguments_reach_the_process_verbatim_with_no_shell_between(tmp_path: Path) -> None:
    """A semicolon, a backtick or `$(...)` is a character in an argument and nothing else."""
    record = tmp_path / "argv.json"
    hostile = ["; touch pwned", "`touch pwned`", "$(touch pwned)", "a b", "'\"", "*"]
    run_bounded(
        [PYTHON, "-c", f"import json, sys; open({str(record)!r}, 'w').write(json.dumps(sys.argv[1:]))",
         *hostile],
        cwd=tmp_path,
        log=tmp_path / "tool.log",
        timeout=10.0,
    )
    assert json.loads(record.read_text()) == hostile
    assert not (tmp_path / "pwned").exists()


@pytest.mark.ac("AC-7")
def test_ac7_a_binary_named_with_shell_metacharacters_is_a_name(tmp_path: Path) -> None:
    binary = tmp_path / "ff;touch pwned"
    binary.write_text(f"#!{PYTHON}\nimport sys\nsys.exit(0)\n")
    binary.chmod(0o755)
    assert run_bounded([str(binary)], cwd=tmp_path, log=tmp_path / "tool.log", timeout=10.0) == 0
    assert not (tmp_path / "pwned").exists()


def test_the_process_cannot_read_the_callers_stdin(tmp_path: Path) -> None:
    """FFmpeg reads stdin for interactive keys. A tool waiting on input would wait forever."""
    code = run_bounded(
        [PYTHON, "-c", "import sys; sys.exit(0 if sys.stdin.read() == '' else 1)"],
        cwd=tmp_path,
        log=tmp_path / "tool.log",
        timeout=5.0,
    )
    assert code == 0
