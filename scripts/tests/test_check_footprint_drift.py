"""Regression tests for check_footprint_drift.py.

Motivating incident: this defect class has hit this project THREE confirmed
times on `main` (docs/hardware/2026-07-29-open-safety-gate-actions.md for
C6/U3, PR #448 for c_x2/C1) and, as this test file's own fixtures below
demonstrate against the real repo state, a further TWO undetected instances
(C25/C26, `tank.c_tank1`/`tank.c_tank2` -- see docs/evidence/
2026-07-28-tank-cap-and-isolator-footprints.md) plus one component the board
was never resynced to include at all (C27/`tank.c_tank3`, docs/evidence/
2026-07-30-copper-net-consistency-drift.md). A component's footprint is
corrected in `elec/src/*.ato` (visible in the compiled netlist as a new
`(footprint ...)` field) and the correction never reaches
`pcb/temper.kicad_pcb`. Every existing board/netlist gate
(`check_domain_partition.py`, `check_copper_net_consistency.py`) reads NET
identity -- which pin belongs to which electrical net -- never the
footprint string itself, so a pad-compatible footprint substitution with a
smaller/different land pattern is invisible to those checks even though the
creepage/clearance geometry it changes is exactly what REQ-SAFE-01 exists to
protect on this mains-connected board.

Each test below builds a minimal netlist+board pair via kiutils/hand-written
S-expressions (same convention as test_check_copper_net_consistency.py) and
asserts `run_checks` classifies the intended outcome correctly -- in
particular that MISMATCH, MISSING-FROM-BOARD, and MISSING-FROM-NETLIST are
kept in separate buckets rather than lumped together or silently dropped
(the explicit design requirement: "classify them separately... silence is
the failure mode this whole exercise exists to fix").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_footprint_drift import (  # noqa: E402
    GateError,
    load_board,
    parse_netlist,
    run_checks,
)
from kiutils.board import Board  # noqa: E402
from kiutils.footprint import Footprint, Pad  # noqa: E402
from kiutils.items.common import Position  # noqa: E402


def _write_netlist(path: Path, comps: list[tuple[str, str, str]]) -> None:
    """comps: [(ref, footprint, sheetpath_suffix), ...].

    sheetpath_suffix is what appears after 'Top::' in the real netlist,
    e.g. "power_in.c_x2" -- this helper reproduces the real
    '(sheetpath (names ".../main.ato:Top::<suffix>") (tstamps "...")))'
    shape verbatim so the test exercises the exact same parser the gate
    itself uses on the real compiled netlist.
    """
    blocks = []
    for ref, footprint, suffix in comps:
        blocks.append(
            f'    (comp (ref "{ref}")\n'
            f'      (value "?")\n'
            f'      (footprint "{footprint}")\n'
            f'      (sheetpath (names "/repo/elec/src/main.ato:Top::{suffix}") '
            f'(tstamps "deadbeef"))\n'
            f'      (tstamps "deadbeef"))'
        )
    path.write_text(
        "(export (version \"E\")\n"
        "  (components\n" + "\n".join(blocks) + "\n  )\n"
        "  (nets\n"
        '    (net (code "1") (name "gnd")\n'
        '      (node (ref "X1") (pin "1")))\n'
        "  )\n)\n"
    )


def _footprint(ref: str, footprint_libid: str, sheetpath: str | None, tstamp: str) -> Footprint:
    fp = Footprint(entryName=footprint_libid, tstamp=tstamp, position=Position(0, 0))
    props = {"Reference": ref, "Value": "?", "Footprint": footprint_libid}
    if sheetpath is not None:
        props["Sheetpath"] = sheetpath
    fp.properties = props
    fp.pads = [Pad(number="1", type="smd", tstamp=f"{tstamp}-pad1")]
    return fp


def _board(fps: list[Footprint]) -> Board:
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.footprints = fps
    return board


# ---------------------------------------------------------------------------
# Core classification: mismatch / missing-from-board / missing-from-netlist
# ---------------------------------------------------------------------------


def test_footprint_mismatch_detected(tmp_path: Path) -> None:
    """Scaled-down reproduction of the real C6 incident: the netlist has the
    corrected 10mm-pitch disc footprint, the board still has the old
    5mm-pitch stub. Matched by sheetpath, not by ref, since ref alone
    cannot be trusted to survive designator renumbering."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [("C6", "Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm", "power_in.y_cap_pe")],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = _board(
        [_footprint("C6", "Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm", "power_in.y_cap_pe", "fp-c6")]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(netlist, board_data)
    mismatches = [v for v in report.violations if v.check == "mismatch"]
    assert len(mismatches) == 1, report.violations
    assert "C6" in mismatches[0].detail
    assert "C_Disc_D12.5mm_W5.0mm_P10.00mm" in mismatches[0].detail
    assert "C_Disc_D10.0mm_W5.0mm_P5.00mm" in mismatches[0].detail
    assert report.matched == 1


def test_matching_footprints_pass_clean(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate")],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = _board(
        [_footprint("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate", "fp-r1")]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(netlist, board_data)
    assert report.violations == []
    assert report.matched == 1


def test_designator_renumbering_does_not_cause_false_mismatch(tmp_path: Path) -> None:
    """The identity key is sheetpath, not ref. If atopile renumbers a
    designator (e.g. inserting a new same-prefix component upstream) but
    the footprint itself is unchanged, this must NOT be reported as a
    mismatch or as missing -- matching by ref alone would report this as
    'C27 missing, C28 new' even though nothing about this component
    actually changed."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [("C28", "Resistor_SMD:R_0805_2012Metric", "ct_sense.c_filter")],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    # Board still has the OLD designator "C27" for this same sheetpath --
    # exactly what a stale, not-yet-resynced board looks like when only
    # designators shifted and nothing else changed.
    board = _board(
        [_footprint("C27", "Resistor_SMD:R_0805_2012Metric", "ct_sense.c_filter", "fp-c27")]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(netlist, board_data)
    assert report.violations == []
    assert report.matched == 1


def test_component_missing_from_board(tmp_path: Path) -> None:
    """Scaled-down reproduction of the real C27/tank.c_tank3 incident: a
    component exists in the netlist with no board footprint carrying its
    sheetpath at all. This is NOT a footprint mismatch (there is nothing on
    the board to compare against) and must be classified in its own
    'missing-from-board' bucket, not silently dropped and not folded into
    'mismatch'."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [
            ("C26", "temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal", "tank.c_tank2"),
            ("C27", "temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal", "tank.c_tank3"),
        ],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = _board(
        [_footprint("C26", "temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal", "tank.c_tank2", "fp-c26")]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(netlist, board_data)
    missing = [v for v in report.violations if v.check == "missing-from-board"]
    mismatches = [v for v in report.violations if v.check == "mismatch"]
    assert len(missing) == 1, report.violations
    assert "tank.c_tank3" in missing[0].detail
    assert "C27" in missing[0].detail
    assert mismatches == []  # must not be conflated with a footprint mismatch
    assert report.matched == 1


def test_component_missing_from_netlist(tmp_path: Path) -> None:
    """A board footprint whose Sheetpath doesn't match anything in the
    compiled netlist (stale board carrying a deleted component, or a
    corrupted Sheetpath property) must be classified separately from a
    footprint mismatch -- there is no netlist-declared footprint to compare
    it against."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate")],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = _board(
        [
            _footprint("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate", "fp-r1"),
            _footprint("R99", "Resistor_SMD:R_0805_2012Metric", "deleted.r_old", "fp-r99"),
        ]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(netlist, board_data)
    missing = [v for v in report.violations if v.check == "missing-from-netlist"]
    mismatches = [v for v in report.violations if v.check == "mismatch"]
    assert len(missing) == 1, report.violations
    assert "R99" in missing[0].detail
    assert "deleted.r_old" in missing[0].detail
    assert mismatches == []
    assert report.matched == 1


def test_board_footprint_without_sheetpath_is_flagged_not_skipped(tmp_path: Path) -> None:
    """A board footprint with no 'Sheetpath' property at all cannot be
    identity-matched -- it must be reported (category 'no-sheetpath'), not
    silently ignored, since silent skipping is exactly the failure mode
    this gate exists to close."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate")],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = _board(
        [
            _footprint("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate", "fp-r1"),
            _footprint("R100", "Resistor_SMD:R_0805_2012Metric", None, "fp-r100"),
        ]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(netlist, board_data)
    no_sp = [v for v in report.violations if v.check == "no-sheetpath"]
    assert len(no_sp) == 1, report.violations
    assert "R100" in no_sp[0].detail


# ---------------------------------------------------------------------------
# Fail-closed / malformed-input handling
# ---------------------------------------------------------------------------


def test_parse_netlist_rejects_empty_file(tmp_path: Path) -> None:
    netlist_path = tmp_path / "empty.net"
    netlist_path.write_text("")
    with pytest.raises(GateError, match="empty"):
        parse_netlist(netlist_path)


def test_parse_netlist_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="not found"):
        parse_netlist(tmp_path / "missing.net")


def test_parse_netlist_rejects_malformed_sexp(tmp_path: Path) -> None:
    netlist_path = tmp_path / "broken.net"
    netlist_path.write_text("(export (components (comp (ref \"R1\")")  # unbalanced
    with pytest.raises(GateError, match="unbalanced"):
        parse_netlist(netlist_path)


def test_parse_netlist_rejects_zero_components(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    netlist_path.write_text(
        '(export (version "E")\n  (components\n  )\n  (nets\n  )\n)\n'
    )
    with pytest.raises(GateError, match="zero components"):
        parse_netlist(netlist_path)


def test_parse_netlist_rejects_duplicate_sheetpath(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [
            ("C1", "Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm", "power_in.c_x2"),
            ("C2", "Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm", "power_in.c_x2"),
        ],
    )
    with pytest.raises(GateError, match="sharing sheetpath"):
        parse_netlist(netlist_path)


def test_load_board_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="not found"):
        load_board(tmp_path / "missing.kicad_pcb")


def test_load_board_rejects_zero_footprints(tmp_path: Path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board = _board([])
    board.to_file(str(board_path))
    with pytest.raises(GateError, match="zero footprints"):
        load_board(board_path)


def test_load_board_rejects_malformed_file(tmp_path: Path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board_path.write_text("this is not a kicad_pcb file at all {{{")
    with pytest.raises(GateError, match="failed to parse board"):
        load_board(board_path)


def test_board_rejects_duplicate_sheetpath(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(
        netlist_path,
        [("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate")],
    )
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = _board(
        [
            _footprint("R1", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate", "fp-r1"),
            _footprint("R1DUP", "Resistor_SMD:R_0805_2012Metric", "power_in.r_gate", "fp-r1dup"),
        ]
    )
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    with pytest.raises(GateError, match="sharing Sheetpath"):
        run_checks(netlist, board_data)


def test_gate_is_wired_into_ci_workflow() -> None:
    """Silent-skip-hole regression test (same class as the one already
    written for check_copper_net_consistency.py, and the same class of bug
    that let all three real footprint-drift instances -- C6, U3, c_x2 --
    sit undetected on `main`): asserts the gate script is actually
    referenced in a `run:` step of the board-gates job in
    python-tests.yml, not merely registered in scripts/manifest.yaml."""
    repo_root = Path(__file__).resolve().parents[2]
    workflow_path = repo_root / ".github" / "workflows" / "python-tests.yml"
    assert workflow_path.is_file(), f"workflow file not found: {workflow_path}"
    text = workflow_path.read_text(encoding="utf-8")

    run_lines = [
        line for line in text.splitlines()
        if "run:" in line or line.strip().startswith("uv run")
    ]
    invoked = any("check_footprint_drift.py" in line for line in run_lines)
    assert invoked, (
        "scripts/check_footprint_drift.py is not invoked from any `run:` "
        "step in .github/workflows/python-tests.yml -- the gate exists and "
        "has unit tests but CI never actually runs it."
    )
