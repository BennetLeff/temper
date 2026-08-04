"""Tests for the shared bounded-concurrency DRC runner helper.

The helper runs kicad-cli DRC subprocesses under a concurrency bound and
raises loudly on timeout or missing output instead of silently skipping.
All tests substitute a fake ``kicad-cli`` executable via a PATH shim, so
no real kicad-cli or board is needed.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from tests.placer.cp_sat._parallel_drc import LoudDrcError, run_drc_loud, run_drc_samples

_FAKE_KICAD_CLI = """#!/usr/bin/env python3
import json
import os
import sys
import time

# args: pcb drc --format json -o OUT PCB  (real kicad-cli arg shape)
out = sys.argv[6]
os.makedirs(os.path.dirname(out), exist_ok=True)

with open(os.path.join(os.path.dirname(out), "outpaths.log"), "a") as f:
    f.write(out + "\\n")

if os.environ.get("FAKE_DRC_BAD_JSON"):
    with open(out, "w") as f:
        f.write('{"violations": [')
    sys.exit(0)

if os.environ.get("FAKE_DRC_FAIL_MARKER"):
    marker = os.environ["FAKE_DRC_FAIL_MARKER"]
    if not os.path.exists(marker):
        with open(marker, "w"):
            pass
        sys.exit(1)

if os.environ.get("FAKE_DRC_EMPTY"):
    sys.exit(0)

if os.environ.get("FAKE_DRC_SLEEP"):
    time.sleep(float(os.environ["FAKE_DRC_SLEEP"]))

if os.environ.get("FAKE_DRC_COUNTER"):
    import fcntl

    counter = os.environ["FAKE_DRC_COUNTER"]
    maxlog = os.environ.get("FAKE_DRC_MAXLOG")
    with open(counter, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        cur = int(f.read().strip() or 0) + 1
        f.seek(0)
        f.truncate()
        f.write(str(cur))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)
    if maxlog:
        with open(maxlog, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            best = int(f.read().strip() or 0)
            if cur > best:
                f.seek(0)
                f.truncate()
                f.write(str(cur))
                f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
    time.sleep(0.3)
    with open(counter, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        cur = int(f.read().strip() or 0) - 1
        f.seek(0)
        f.truncate()
        f.write(str(cur))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)

with open(out, "w") as f:
    json.dump({"violations": [], "unconnected_items": []}, f)
"""

_FAKE_KICAD_CLI_ORPHAN = """#!/usr/bin/env python3
import os
import subprocess
import sys
import time

grandchild = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"]
)
with open(os.environ["FAKE_GRANDCHILD_PIDFILE"], "w") as f:
    f.write(str(grandchild.pid))
time.sleep(60)
"""


@pytest.fixture
def fake_kicad_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "kicad-cli"
    exe.write_text(_FAKE_KICAD_CLI)
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return bin_dir


def _probe_board(tmp_path: Path) -> Path:
    board = tmp_path / "board.kicad_pcb"
    board.write_text("(kicad_pcb (version 20231120))")
    return board


def test_run_drc_samples_returns_all_results_in_order(fake_kicad_cli, tmp_path: Path):
    board = _probe_board(tmp_path)
    results = run_drc_samples(board, n=4, timeout=30, label="probe")
    assert len(results) == 4
    assert all(r.get("violations") == [] for r in results)


def test_concurrency_never_exceeds_cpu_count(fake_kicad_cli, tmp_path: Path):
    board = _probe_board(tmp_path)
    counter = tmp_path / "counter"
    maxlog = tmp_path / "maxlog"
    os.environ["FAKE_DRC_COUNTER"] = str(counter)
    os.environ["FAKE_DRC_MAXLOG"] = str(maxlog)
    try:
        run_drc_samples(board, n=8, timeout=30, label="bound")
    finally:
        os.environ.pop("FAKE_DRC_COUNTER", None)
        os.environ.pop("FAKE_DRC_MAXLOG", None)
    observed = int(maxlog.read_text().strip() or 0)
    assert observed <= os.cpu_count()


def test_timeout_raises_loud_error_naming_label_and_timeout(fake_kicad_cli, tmp_path: Path):
    board = _probe_board(tmp_path)
    os.environ["FAKE_DRC_SLEEP"] = "30"
    try:
        with pytest.raises(LoudDrcError) as exc:
            run_drc_loud(board, timeout=1, label="zone-pour")
    finally:
        os.environ.pop("FAKE_DRC_SLEEP", None)
    msg = str(exc.value)
    assert "zone-pour" in msg
    assert "1" in msg
    assert "timed out" in msg


def test_missing_output_raises_loud_error(fake_kicad_cli, tmp_path: Path):
    board = _probe_board(tmp_path)
    os.environ["FAKE_DRC_EMPTY"] = "1"
    try:
        with pytest.raises(LoudDrcError) as exc:
            run_drc_loud(board, timeout=30, label="routing-drc")
    finally:
        os.environ.pop("FAKE_DRC_EMPTY", None)
    assert "no output" in str(exc.value)


def test_truncated_json_raises_loud_error(fake_kicad_cli, tmp_path: Path):
    board = _probe_board(tmp_path)
    os.environ["FAKE_DRC_BAD_JSON"] = "1"
    try:
        with pytest.raises(LoudDrcError) as exc:
            run_drc_loud(board, timeout=30, label="zone-pour")
    finally:
        os.environ.pop("FAKE_DRC_BAD_JSON", None)
    assert "invalid JSON" in str(exc.value)


def test_failure_among_multiple_samples_propagates_without_hang(
    fake_kicad_cli, tmp_path: Path
):
    """A failing sample among n>1 raises LoudDrcError and returns promptly."""
    board = _probe_board(tmp_path)
    marker = tmp_path / "fail-marker"
    os.environ["FAKE_DRC_FAIL_MARKER"] = str(marker)
    start = time.monotonic()
    try:
        with pytest.raises(LoudDrcError):
            run_drc_samples(board, n=3, timeout=30, label="multi")
    finally:
        os.environ.pop("FAKE_DRC_FAIL_MARKER", None)
    assert time.monotonic() - start < 15, "failure path hung waiting on siblings"


def test_samples_use_distinct_output_paths(fake_kicad_cli, tmp_path: Path):
    board = _probe_board(tmp_path)
    run_drc_samples(board, n=3, timeout=30, label="isolation")
    paths = (tmp_path / "outpaths.log").read_text().splitlines()
    assert len(paths) == 3
    assert len(set(paths)) == 3, "two samples shared an output path"


def _process_state(pid: int) -> str:
    """Single-letter process state for ``pid``, or ``""`` if it is gone.

    Reads procfs where it exists (Linux, including the CI container) and
    falls back to ``ps`` elsewhere (macOS). A missing ``ps`` raises
    ``FileNotFoundError`` rather than reporting a false "gone", so this
    can never silently turn the caller's liveness check vacuous.
    """
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            # "<pid> (<comm>) <state> ..." — comm may itself contain
            # spaces and parens, so split after the *last* ')'.
            return stat.read_text().rpartition(")")[2].split()[0]
        except (OSError, IndexError):
            return ""
    proc = subprocess.run(
        ["ps", "-o", "state=", "-p", str(pid)], capture_output=True, text=True
    )
    return proc.stdout.strip()[:1]


def _process_is_alive(pid: int) -> bool:
    """True only if ``pid`` is still *running* — a zombie counts as dead.

    ``os.kill(pid, 0)`` on its own is not a liveness probe: it also
    succeeds for a zombie, a process that has already died but whose
    parent has not yet reaped it. That distinction is exactly what this
    file's reaping test turns on.

    When the helper's timeout kills the process group, the grandchild's
    parent (the fake kicad-cli) is killed alongside it, so the grandchild
    is orphaned and reparented to PID 1 of its PID namespace. On macOS
    that is launchd, which reaps immediately — so ``os.kill`` starts
    raising ``ProcessLookupError`` and the naive probe looks correct. A
    GitHub Actions container job instead runs the image with
    ``--entrypoint tail -f /dev/null``, making PID 1 a ``tail`` that
    never calls ``wait()``. There the correctly-killed grandchild stays
    a zombie for the life of the container and ``os.kill(pid, 0)`` keeps
    succeeding forever — which is what made this test fail in CI while
    passing locally, despite the process-group reaping working fine.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, owned by someone else — conservatively "alive".
        return True
    return _process_state(pid) not in ("", "Z")


def test_timeout_reaps_the_process_group(tmp_path: Path):
    """A timed-out DRC must not leave orphaned child processes behind.

    The fake kicad-cli spawns a grandchild and records its pid; when the
    helper's timeout fires it must kill the whole session/process group,
    not just the direct child (subprocess.run(timeout=...) alone kills
    only the direct child).

    "Behind" means *still running*: see :func:`_process_is_alive` for why
    an already-killed-but-unreaped grandchild is not a survivor.
    """
    pidfile = tmp_path / "grandchild.pid"
    board = _probe_board(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    orphan = bin_dir / "kicad-cli"
    orphan.write_text(_FAKE_KICAD_CLI_ORPHAN)
    orphan.chmod(0o755)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GRANDCHILD_PIDFILE", str(pidfile))
    try:
        with pytest.raises(LoudDrcError):
            run_drc_loud(board, timeout=1, label="orphan")
    finally:
        monkeypatch.undo()
    assert pidfile.exists(), "grandchild never started"
    grandchild_pid = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _process_is_alive(grandchild_pid):
            break
        time.sleep(0.1)
    else:
        pytest.fail(
            f"grandchild {grandchild_pid} survived the timeout still running "
            f"(state {_process_state(grandchild_pid)!r})"
        )
