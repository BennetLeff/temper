"""Tests for check_state_machine_model.py's dated backlog allowlist
(2026-08-07 CI-wiring session).

At CI-introduction time this gate found one real, pre-existing manifest
divergence between firmware/transition_table.yaml and firmware/test/
gen_transition_table.py's TRANSITIONS list (see
state-machine-crosscheck-allowlist.yaml for the citation). These tests cover
the allowlist mechanism added to unblock CI without fixing (or masking) that
underlying firmware decision:

  - a backlog-matched divergence does not, by itself, flip the exit code;
  - it is still visible (printed, tagged, counted in the summary line);
  - `backlog: true` and `seeded` must travel together -- one without the
    other fails closed;
  - a malformed `seeded` date fails closed;
  - an allowlist entry only suppresses the SPECIFIC (kind, from_state,
    event) it names -- a different divergence is unaffected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_state_machine_model import (  # noqa: E402
    _crosscheck_allowlisted,
    load_crosscheck_allowlist,
)
from transition_manifest_crosscheck import CrosscheckError, RowDivergence  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ALLOWLIST = REPO_ROOT / "state-machine-crosscheck-allowlist.yaml"


def _write_allowlist(path: Path, body: str) -> Path:
    allowlist_path = path / "allowlist.yaml"
    allowlist_path.write_text(body)
    return allowlist_path


def test_missing_allowlist_file_is_empty_not_an_error(tmp_path: Path) -> None:
    assert load_crosscheck_allowlist(tmp_path / "does_not_exist.yaml") == []


def test_backlog_entry_matches_and_suppresses(tmp_path: Path) -> None:
    allowlist_path = _write_allowlist(
        tmp_path,
        "allowlist:\n"
        "  - kind: explicit\n"
        "    from_state: STATE_FAULT\n"
        "    event: EVENT_FAULT_RESET_PERSISTS\n"
        "    backlog: true\n"
        "    seeded: '2026-08-07'\n"
        "    reason: 'test fixture'\n",
    )
    entries = load_crosscheck_allowlist(allowlist_path)
    assert len(entries) == 1
    assert entries[0].backlog is True
    assert entries[0].seeded == "2026-08-07"

    d = RowDivergence(
        kind="value_mismatch",
        from_state="STATE_FAULT",
        event="EVENT_FAULT_RESET_PERSISTS",
        production=("STATE_FAULT", "FAULT_NONE"),
        test=("STATE_FAULT", "FAULT_OVER_TEMP"),
    )
    match = _crosscheck_allowlisted("explicit", d, entries)
    assert match is not None
    assert match.backlog is True


def test_different_event_not_matched(tmp_path: Path) -> None:
    """The allowlist entry only covers the exact (kind, from_state, event)
    it names -- a divergence on a different event must still be live."""
    allowlist_path = _write_allowlist(
        tmp_path,
        "allowlist:\n"
        "  - kind: explicit\n"
        "    from_state: STATE_FAULT\n"
        "    event: EVENT_FAULT_RESET_PERSISTS\n"
        "    backlog: true\n"
        "    seeded: '2026-08-07'\n"
        "    reason: 'test fixture'\n",
    )
    entries = load_crosscheck_allowlist(allowlist_path)
    d = RowDivergence(
        kind="missing_in_test",
        from_state="STATE_FAULT",
        event="EVENT_SOME_OTHER_EVENT",
        production=("STATE_IDLE", None),
    )
    assert _crosscheck_allowlisted("explicit", d, entries) is None


def test_backlog_true_without_seeded_fails_closed(tmp_path: Path) -> None:
    allowlist_path = _write_allowlist(
        tmp_path,
        "allowlist:\n"
        "  - kind: explicit\n"
        "    from_state: STATE_FAULT\n"
        "    event: EVENT_FAULT_RESET_PERSISTS\n"
        "    backlog: true\n"
        "    reason: 'test fixture'\n",
    )
    with pytest.raises(CrosscheckError, match="must travel together"):
        load_crosscheck_allowlist(allowlist_path)


def test_seeded_without_backlog_true_fails_closed(tmp_path: Path) -> None:
    allowlist_path = _write_allowlist(
        tmp_path,
        "allowlist:\n"
        "  - kind: explicit\n"
        "    from_state: STATE_FAULT\n"
        "    event: EVENT_FAULT_RESET_PERSISTS\n"
        "    seeded: '2026-08-07'\n"
        "    reason: 'test fixture'\n",
    )
    with pytest.raises(CrosscheckError, match="must travel together"):
        load_crosscheck_allowlist(allowlist_path)


def test_malformed_seeded_date_fails_closed(tmp_path: Path) -> None:
    allowlist_path = _write_allowlist(
        tmp_path,
        "allowlist:\n"
        "  - kind: explicit\n"
        "    from_state: STATE_FAULT\n"
        "    event: EVENT_FAULT_RESET_PERSISTS\n"
        "    backlog: true\n"
        "    seeded: 'not-a-date'\n"
        "    reason: 'test fixture'\n",
    )
    with pytest.raises(CrosscheckError, match="malformed 'seeded' date"):
        load_crosscheck_allowlist(allowlist_path)


def test_missing_reason_fails_closed(tmp_path: Path) -> None:
    allowlist_path = _write_allowlist(
        tmp_path,
        "allowlist:\n"
        "  - kind: explicit\n"
        "    from_state: STATE_FAULT\n"
        "    event: EVENT_FAULT_RESET_PERSISTS\n",
    )
    with pytest.raises(CrosscheckError, match="missing 'reason'"):
        load_crosscheck_allowlist(allowlist_path)


# ---------------------------------------------------------------------------
# Integration against the real tree
# ---------------------------------------------------------------------------


def test_real_allowlist_loads_and_covers_the_known_divergence() -> None:
    entries = load_crosscheck_allowlist(REAL_ALLOWLIST)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.backlog is True
    assert entry.seeded == "2026-08-07"
    assert entry.kind == "explicit"
    assert entry.from_state == "STATE_FAULT"
    assert entry.event == "EVENT_FAULT_RESET_PERSISTS"


def test_real_gate_run_exits_ok() -> None:
    """End-to-end: the real gate, against the real manifests and the real
    backlog allowlist, must exit 0 -- the one known divergence is backlogged
    and nothing else in the tree has newly diverged."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_state_machine_model.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"expected the real tree to pass with the known divergence backlogged "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )
    assert "(backlog, seeded 2026-08-07)" in result.stdout
    assert "Backlog: 1 " in result.stdout
