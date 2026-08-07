"""Tests for part_stress_gate.py.

Covers, per R9/R10 (docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md
-- "every safety-critical constraint has a gate demonstrated to fail
against a seeded defect" / "a coverage claim is reported as vacuous unless
it carries a demonstrated failing case"):

  - anti-vacuity: a synthetic entry seeded with an over-rating defect
    (applied > rated) must actually flip the gate's exit code to 3, not
    merely appear in a report nobody's exit-code check reads.
  - anti-vacuity: a synthetic entry seeded with a below-guideline-but-under-
    rating defect must produce WARN and exit 0 -- proving the gate
    distinguishes "over rating" from "under guideline" rather than
    collapsing both into one bucket.
  - fail-closed: a missing BOM, a missing limits file, a designator absent
    from the BOM, and an MPN mismatch (the part-swap case -- the same class
    of drift capacity_budget_gate.py and check_footprint_drift.py guard
    against elsewhere in this repo) must all exit 5, never a silent pass.
  - `conditional: true` entries are labeled distinctly in the report and do
    not get silently merged into the same bucket as an unconditional
    finding.
  - integration: the real gate run against elec/build/default.csv (if
    built) and the real scripts/part_stress_limits.yaml reproduces the
    docs/hardware/PART_STRESS_AUDIT.md Sec 1 findings (at least the bus-cap
    ripple current FAIL) -- skipped, not failed, if elec/build/ has not
    been built in this environment (gitignored, requires `ato build`). As
    of the 2026-08-07 CI-wiring session, all 3 of those Sec 1 findings are
    dated backlog entries (`backlog: true` + `seeded: '2026-08-07'` in
    part_stress_limits.yaml) -- the gate still reports and prints them as
    FAIL(backlog), it just no longer exits 3 on the 3 known ones; a
    genuinely NEW FAIL not on that dated list still flips the exit code.
  - backlog: `backlog: true` without `seeded` (or vice versa) is a
    malformed entry and must fail closed (exit 5), never silently treated
    as either "not backlogged" or "backlogged".
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from part_stress_gate import (  # noqa: E402
    GateError,
    build_entries,
    load_bom,
    load_limits,
    main,
    render_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "scripts" / "part_stress_gate.py"
REAL_BOM = REPO_ROOT / "elec" / "build" / "default.csv"
REAL_LIMITS = REPO_ROOT / "scripts" / "part_stress_limits.yaml"


# ---------------------------------------------------------------------------
# Fixtures: a small synthetic BOM + limits pair, independent of the real
# board, so these tests do not depend on the real findings ever changing.
# ---------------------------------------------------------------------------


def _write_bom(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """rows: (mpn, designators_csv, footprint)."""
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC", "Price"])
        for mpn, designators, footprint in rows:
            writer.writerow([mpn, designators, footprint, mpn, "0.00"])


def _write_limits(path: Path, entries: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"entries": entries}))


def _base_bom(tmp_path: Path) -> Path:
    bom_path = tmp_path / "default.csv"
    _write_bom(
        bom_path,
        [
            ("FAKE_CAP_100V", "C1", "Capacitor_SMD:C_0603_1608Metric"),
            ("FAKE_RES_1K", "R1,R2", "Resistor_SMD:R_0603_1608Metric"),
        ],
    )
    return bom_path


# ---------------------------------------------------------------------------
# Seeded-defect anti-vacuity tests (R9/R10)
# ---------------------------------------------------------------------------


def test_seeded_over_rating_defect_trips_fail_exit_code(tmp_path: Path) -> None:
    """A part stressed above its own rated limit must flip the exit code.

    This is the falsifier: if this test passed with exit 0, the gate would
    be exactly the "coverage claim... vacuous... no seeded defect has been
    shown to trip it" failure mode R9/R10 name.
    """
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "seeded_over_rating",
                "designators": ["C1"],
                "mpn": "FAKE_CAP_100V",
                "domain": "voltage_ceramic_dc_bias",
                "unit": "V",
                "rated": 100.0,
                "applied": 150.0,  # seeded defect: 50% OVER rated
                "guideline_margin": 0.5,
                "conditional": False,
                "source": "synthetic fixture",
                "notes": "seeded defect",
            }
        ],
    )

    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 3, "seeded over-rating defect did not trip the gate"


def test_seeded_below_guideline_defect_produces_warn_not_fail(tmp_path: Path) -> None:
    """A part under its rating but below the derating guideline is WARN,
    exit 0 -- distinct from an actual over-rating FAIL. If the gate
    collapsed these two cases together it would either miss real
    over-rating defects among a sea of guideline warnings, or falsely
    fail the build on a merely-thin (but safe) margin."""
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "seeded_below_guideline",
                "designators": ["C1"],
                "mpn": "FAKE_CAP_100V",
                "domain": "voltage_ceramic_dc_bias",
                "unit": "V",
                "rated": 100.0,
                "applied": 60.0,  # under rated, but only 40% margin < 50% guideline
                "guideline_margin": 0.5,
                "conditional": False,
                "source": "synthetic fixture",
                "notes": "seeded defect",
            }
        ],
    )

    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 0

    entries, errors = build_entries(load_limits(limits_path), load_bom(bom_path))
    assert not errors
    assert entries[0].status == "WARN"


# ---------------------------------------------------------------------------
# Backlog entries (2026-08-07 CI-wiring session)
# ---------------------------------------------------------------------------


def _seeded_fail_entry(**overrides: object) -> dict:
    entry = {
        "id": "seeded_over_rating",
        "designators": ["C1"],
        "mpn": "FAKE_CAP_100V",
        "domain": "voltage_ceramic_dc_bias",
        "unit": "V",
        "rated": 100.0,
        "applied": 150.0,  # seeded defect: 50% OVER rated
        "guideline_margin": 0.5,
        "conditional": False,
        "source": "synthetic fixture",
        "notes": "seeded defect",
    }
    entry.update(overrides)
    return entry


def test_backlog_fail_does_not_trip_exit_code(tmp_path: Path) -> None:
    """A FAIL entry carrying a valid backlog/seeded pair is reported (still
    FAIL) but does not by itself flip the exit code -- the whole point of
    the backlog convention is "block new defects, not the known ones"."""
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [_seeded_fail_entry(backlog=True, seeded="2026-08-07")],
    )

    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 0


def test_backlog_fail_still_shown_as_fail_in_report(tmp_path: Path) -> None:
    """A backlog FAIL must never be silently invisible -- it is still
    printed, still classified FAIL, and tagged, plus a summary line."""
    bom = load_bom(_base_bom(tmp_path))
    raw = [_seeded_fail_entry(backlog=True, seeded="2026-08-07")]
    entries, errors = build_entries(raw, bom)
    assert not errors
    assert entries[0].status == "FAIL"
    assert entries[0].blocking is False
    report = render_report(entries)
    assert "FAIL" in report
    assert "BACKLOG" in report
    assert "Backlog: 1 " in report


def test_non_backlog_fail_alongside_backlog_fail_still_trips_gate(tmp_path: Path) -> None:
    """A NEW (non-backlog) FAIL must still block the gate even when a
    dated backlog FAIL is also present -- the backlog must never mask an
    unrelated, genuinely new finding."""
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            _seeded_fail_entry(id="backlogged", backlog=True, seeded="2026-08-07"),
            _seeded_fail_entry(id="new_finding", designators=["R1"], mpn="FAKE_RES_1K"),
        ],
    )
    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 3


def test_backlog_true_without_seeded_fails_closed(tmp_path: Path) -> None:
    bom = load_bom(_base_bom(tmp_path))
    raw = [_seeded_fail_entry(backlog=True)]
    with pytest.raises(GateError, match="must travel together"):
        build_entries(raw, bom)


def test_seeded_without_backlog_true_fails_closed(tmp_path: Path) -> None:
    bom = load_bom(_base_bom(tmp_path))
    raw = [_seeded_fail_entry(seeded="2026-08-07")]
    with pytest.raises(GateError, match="must travel together"):
        build_entries(raw, bom)


def test_malformed_seeded_date_fails_closed(tmp_path: Path) -> None:
    bom = load_bom(_base_bom(tmp_path))
    raw = [_seeded_fail_entry(backlog=True, seeded="not-a-date")]
    with pytest.raises(GateError, match="malformed 'seeded' date"):
        build_entries(raw, bom)


def test_passing_entry_reports_ok(tmp_path: Path) -> None:
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "comfortable_margin",
                "designators": ["R1", "R2"],
                "mpn": "FAKE_RES_1K",
                "domain": "power",
                "unit": "W",
                "rated": 1.0,
                "applied": 0.2,
                "guideline_margin": 0.5,
                "conditional": False,
                "source": "synthetic fixture",
                "notes": "control case",
            }
        ],
    )

    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 0
    entries, errors = build_entries(load_limits(limits_path), load_bom(bom_path))
    assert not errors
    assert entries[0].status == "OK"


def test_conditional_defect_labeled_distinctly_in_report(tmp_path: Path) -> None:
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "seeded_conditional_over_rating",
                "designators": ["C1"],
                "mpn": "FAKE_CAP_100V",
                "domain": "current",
                "unit": "A",
                "rated": 10.0,
                "applied": 12.0,
                "guideline_margin": 0.2,
                "conditional": True,
                "source": "synthetic fixture",
                "notes": "seeded conditional defect",
            }
        ],
    )
    entries, errors = build_entries(load_limits(limits_path), load_bom(bom_path))
    assert not errors
    assert entries[0].status == "FAIL"
    assert entries[0].display_status == "FAIL(conditional)"
    report = render_report(entries)
    assert "FAIL(conditional)" in report


# ---------------------------------------------------------------------------
# Fail-closed tests
# ---------------------------------------------------------------------------


def test_missing_bom_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(GateError):
        load_bom(tmp_path / "does_not_exist.csv")


def test_empty_bom_fails_closed(tmp_path: Path) -> None:
    bom_path = tmp_path / "default.csv"
    bom_path.write_text("")
    with pytest.raises(GateError):
        load_bom(bom_path)


def test_missing_limits_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(GateError):
        load_limits(tmp_path / "does_not_exist.yaml")


def test_empty_limits_fails_closed(tmp_path: Path) -> None:
    limits_path = tmp_path / "limits.yaml"
    limits_path.write_text("entries: []\n")
    with pytest.raises(GateError):
        load_limits(limits_path)


def test_designator_absent_from_bom_fails_closed(tmp_path: Path) -> None:
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "phantom_part",
                "designators": ["C99"],  # not in the synthetic BOM
                "mpn": "FAKE_CAP_100V",
                "domain": "voltage_film",
                "unit": "V",
                "rated": 100.0,
                "applied": 10.0,
                "guideline_margin": 0.2,
                "conditional": False,
                "source": "synthetic fixture",
                "notes": "designator drift",
            }
        ],
    )
    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 5


def test_mpn_mismatch_part_swap_fails_closed(tmp_path: Path) -> None:
    """The core anti-drift guarantee: if the physical part on a designator
    changes without this limits file being updated, the gate must refuse
    to silently compare a stale rating against the new part -- same class
    of defect capacity_budget_gate.py's own docstring names for
    default.net's footprint-aliasing trap."""
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "swapped_part",
                "designators": ["C1"],
                "mpn": "SOME_OTHER_PART_ENTIRELY",  # BOM actually has FAKE_CAP_100V
                "domain": "voltage_film",
                "unit": "V",
                "rated": 100.0,
                "applied": 10.0,
                "guideline_margin": 0.2,
                "conditional": False,
                "source": "synthetic fixture",
                "notes": "part swap",
            }
        ],
    )
    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 5


def test_mpn_null_skips_identity_check(tmp_path: Path) -> None:
    """`mpn: null` deliberately opts out of the identity check for entries
    that legitimately span more than one physical part (e.g. a fuse and a
    choke sharing one current-margin finding) -- must not be treated as a
    mismatch."""
    bom_path = _base_bom(tmp_path)
    limits_path = tmp_path / "limits.yaml"
    _write_limits(
        limits_path,
        [
            {
                "id": "multi_part_entry",
                "designators": ["C1", "R1"],
                "mpn": None,
                "domain": "current",
                "unit": "A",
                "rated": 10.0,
                "applied": 5.0,
                "guideline_margin": 0.2,
                "conditional": False,
                "source": "synthetic fixture",
                "notes": "spans two different physical parts",
            }
        ],
    )
    exit_code = main(["--bom", str(bom_path), "--limits", str(limits_path)])
    assert exit_code == 0


# ---------------------------------------------------------------------------
# Integration against the real tree
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REAL_BOM.exists(),
    reason="elec/build/default.csv not built in this environment (gitignored; run `ato build` in elec/)",
)
def test_real_tree_reproduces_bus_cap_ripple_finding() -> None:
    """docs/hardware/PART_STRESS_AUDIT.md Sec 1.1: the bus capacitors'
    ripple-current rating is exceeded by ~4-6x on the committed design.
    This is the motivating finding for this whole gate -- if the real gate
    run against the real board does not reproduce it, the gate (or the
    limits file) has drifted from the design it claims to check.

    As of the 2026-08-07 CI-wiring session this finding (along with the
    other 2 Sec 1 FAILs) is a dated backlog entry, so the real-tree run no
    longer exits 3 on it alone -- but the finding must still be reported,
    still classified FAIL, and still tagged BACKLOG, never silently
    dropped from the output."""
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--bom", str(REAL_BOM), "--limits", str(REAL_LIMITS)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"expected the 3 known Sec 1 FAILs (all dated backlog entries) to not "
        f"block the gate by themselves "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )
    assert "bus_cap_ripple_current" in result.stdout
    assert "FAIL" in result.stdout
    assert "BACKLOG" in result.stdout
    assert "Backlog: 3 " in result.stdout


@pytest.mark.skipif(
    not REAL_BOM.exists(),
    reason="elec/build/default.csv not built in this environment (gitignored; run `ato build` in elec/)",
)
def test_real_tree_limits_designators_all_resolve() -> None:
    """Every designator named in the checked-in limits file must still
    exist in the real BOM with the expected MPN -- catches the limits file
    itself drifting from the board (a part renumbered or swapped) even
    when nobody is actively looking at ripple-current margins."""
    bom = load_bom(REAL_BOM)
    raw_entries = load_limits(REAL_LIMITS)
    _entries, errors = build_entries(raw_entries, bom)
    assert not errors, f"limits file has drifted from the real board: {errors}"
