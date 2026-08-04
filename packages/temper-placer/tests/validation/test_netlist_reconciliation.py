"""Tests for the netlist <-> board reconciliation oracle (plan 2026-08-02-021,
R16, units U1 + U2).

Covers board-side netlist extraction (U1): every real-board footprint
resolves a ref + Sheetpath, a synthetic footprint without a Sheetpath is
flagged UNKEYABLE (never silently dropped), pad-to-net extraction matches the
board's net table, and extraction is deterministic across two parses. Covers
the sheetpath-keyed and net-level reconciliation (U2): MISSING, RENUMBERED,
REUSE, EXTRA, NET-MEMBERSHIP, NET-MISSING, and the zero-findings clean pair.

The identity key is the instance path (Sheetpath), NOT refdes: board ``C27``
= ``tank.c_tank3`` while the design netlist's ``C27`` was historically a
different component (``ct_sense.c_filter``) -- one ref, two components is
exactly the class these checks exist for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.validation.netlist_reconciliation import (
    BoardNetlist,
    DesignComponent,
    DesignNetlist,
    ReconciliationGateError,
    build_board_netlist,
    extract_board_netlist,
    parse_design_netlist,
    reconcile,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _component(ref: str, sheetpath: str | None, nets: list[tuple[str, str]]) -> Component:
    """A synthetic board component. ``nets`` is [(pin, net_name), ...]."""
    pins = [
        Pin(name=pin, number=pin, position=(0.0, 0.0), net=net) for pin, net in nets
    ]
    return Component(
        ref=ref,
        footprint="temper:Test",
        bounds=(1.0, 1.0),
        pins=pins,
        sheetpath=sheetpath,
    )


def _design(
    comps: list[tuple[str, str]], nets: dict[str, list[tuple[str, str]]]
) -> DesignNetlist:
    """Synthetic design netlist. ``comps`` is [(ref, instance_path), ...];
    ``nets`` maps net name -> [(ref, pin), ...]."""
    return DesignNetlist(
        components=[DesignComponent(ref=ref, instance_path=path) for ref, path in comps],
        nets=nets,
    )


def _write_design_netlist(path: Path, comps: list[tuple[str, str, str]]) -> None:
    """Write a parseable .net file. ``comps`` is [(ref, footprint, suffix), ...]
    where suffix is the instance path after 'Top::' -- reproduces the real
    compiled netlist's (sheetpath (names "...:Top::<suffix>")) shape so the
    test exercises the same parser path."""
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


def _clean_board() -> BoardNetlist:
    return build_board_netlist(
        [
            _component("C1", "a.cap1", [("1", "gnd"), ("2", "vcc")]),
            _component("C2", "b.cap2", [("1", "gnd"), ("2", "vcc")]),
            _component("R1", "c.r1", [("1", "gnd"), ("2", "sig")]),
        ]
    )


def _clean_design() -> DesignNetlist:
    return _design(
        [("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")],
        {
            "gnd": [("C1", "1"), ("C2", "1"), ("R1", "1")],
            "vcc": [("C1", "2"), ("C2", "2")],
            "sig": [("R1", "2")],
        },
    )


# ===========================================================================
# U1 -- board-netlist extraction
# ===========================================================================


class TestBoardExtraction:
    def test_real_board_every_footprint_resolves_ref_and_sheetpath(self) -> None:
        """Parsing the current pcb/temper.kicad_pcb yields a component list
        where every footprint resolves a ref and a Sheetpath, and the tank cap
        is present: board C27 resolves Sheetpath tank.c_tank3."""
        board = extract_board_netlist(REAL_BOARD)
        assert len(board.components) > 100
        by_path = {c.sheetpath: c.ref for c in board.components}
        assert "tank.c_tank3" in by_path, (
            "tank.c_tank3 must be present in the board file (off-outline; "
            "the current-board verdict is PASS-for-missing, not file absence)"
        )
        assert by_path["tank.c_tank3"] == "C27"
        assert all(c.sheetpath for c in board.components), (
            "every real-board footprint carries a Sheetpath property"
        )

    def test_footprint_without_sheetpath_is_unkeyable_not_dropped(self) -> None:
        """A synthetic component with no Sheetpath is carried through as an
        un-keyable candidate (sheetpath == ''), never silently dropped."""
        board = build_board_netlist(
            [
                _component("R1", "a.r1", [("1", "gnd")]),
                _component("R99", None, [("1", "gnd")]),
            ]
        )
        assert len(board.components) == 2
        unkeyable = [c for c in board.components if not c.sheetpath]
        assert [c.ref for c in unkeyable] == ["R99"]

    def test_pad_to_net_extraction_matches_board_net_table(self, tmp_path: Path) -> None:
        """Every pad's net assignment resolves to a real net name (the board
        net table's names), and the extracted net membership matches the
        pads' assignments."""
        board = build_board_netlist(
            [
                _component("C1", "a.cap1", [("1", "gnd"), ("2", "vcc")]),
                _component("C2", "b.cap2", [("1", "gnd"), ("2", "vcc")]),
            ]
        )
        assert board.nets["gnd"] == {"a.cap1", "b.cap2"}
        assert board.nets["vcc"] == {"a.cap1", "b.cap2"}
        # every extracted net name came from a pad assignment, never a guess
        all_pad_nets = {
            pin.net for c in (_component("C1", "a.cap1", [("1", "gnd"), ("2", "vcc")]),) for pin in c.pins
        }
        assert set(board.nets) <= all_pad_nets | {"vcc"}

    def test_extraction_is_deterministic_across_two_parses(self) -> None:
        """U1 verification: extraction output is deterministic across two
        parses of the same board file."""
        first = extract_board_netlist(REAL_BOARD)
        second = extract_board_netlist(REAL_BOARD)
        assert [(c.ref, c.sheetpath) for c in first.components] == [
            (c.ref, c.sheetpath) for c in second.components
        ]
        assert first.nets == second.nets


# ===========================================================================
# U2 -- sheetpath-keyed and net-level reconciliation
# ===========================================================================


class TestReconciliation:
    def test_identical_board_and_design_yield_zero_findings(self) -> None:
        report = reconcile(_clean_board(), _clean_design())
        assert report.passed, report.findings
        assert report.matched_paths == 3

    def test_missing_component_finding(self) -> None:
        """A design component at instance path X with no board counterpart
        yields a MISSING finding naming the path and ref (tank-capacitor
        class)."""
        design = _design(
            [("C1", "a.cap1"), ("C2", "b.cap2"), ("C3", "tank.c_tank3")],
            {"gnd": [("C1", "1"), ("C2", "1"), ("C3", "1")]},
        )
        report = reconcile(_clean_board(), design)
        missing = report.findings_of("MISSING")
        assert len(missing) == 1
        assert "tank.c_tank3" in missing[0].detail
        assert "C3" in missing[0].detail
        assert not report.passed

    def test_renumbered_finding(self) -> None:
        """The same instance path with a different ref on each side yields a
        RENUMBERED finding naming both refs."""
        design = _design(
            [("C9", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")],
            {"gnd": [("C9", "1"), ("C2", "1"), ("R1", "1")]},
        )
        report = reconcile(_clean_board(), design)
        renumbered = report.findings_of("RENUMBERED")
        assert len(renumbered) == 1
        assert "C9" in renumbered[0].detail
        assert "C1" in renumbered[0].detail
        assert "a.cap1" in renumbered[0].detail

    def test_reuse_finding_on_board_side(self) -> None:
        """Two board components with the same ref yield a REUSE finding."""
        board = build_board_netlist(
            [
                _component("C1", "a.cap1", [("1", "gnd")]),
                _component("C1", "b.cap2", [("1", "gnd")]),
            ]
        )
        report = reconcile(board, _clean_design())
        reuse = report.findings_of("REUSE")
        assert len(reuse) == 1
        assert "C1" in reuse[0].detail
        assert "a.cap1" in reuse[0].detail and "b.cap2" in reuse[0].detail

    def test_extra_finding(self) -> None:
        """A board component with no design counterpart yields an EXTRA
        finding."""
        board = build_board_netlist(
            [
                _component("C1", "a.cap1", [("1", "gnd")]),
                _component("R9", "deleted.r_old", [("1", "gnd")]),
            ]
        )
        report = reconcile(board, _clean_design())
        extra = report.findings_of("EXTRA")
        assert len(extra) == 1
        assert "deleted.r_old" in extra[0].detail

    def test_net_membership_finding(self) -> None:
        """A net whose design-side node set differs from the board side yields
        a NET-MEMBERSHIP finding naming the net and the differing nodes."""
        design = _design(
            [("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")],
            {
                "gnd": [("C1", "1"), ("C2", "1"), ("R1", "1")],
                "vcc": [("C1", "2"), ("C2", "2"), ("R1", "2")],  # R1 extra on vcc
            },
        )
        report = reconcile(_clean_board(), design)
        membership = report.findings_of("NET-MEMBERSHIP")
        assert len(membership) == 1
        assert "vcc" in membership[0].detail
        assert "c.r1" in membership[0].detail

    def test_net_missing_finding(self) -> None:
        """A net present in design with no board counterpart yields a
        NET-MISSING finding."""
        design = _design(
            [("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")],
            {
                "gnd": [("C1", "1"), ("C2", "1"), ("R1", "1")],
                "vcc": [("C1", "2"), ("C2", "2")],
                "new_net": [("R1", "2")],
            },
        )
        report = reconcile(_clean_board(), design)
        missing = report.findings_of("NET-MISSING")
        assert len(missing) == 1
        assert "new_net" in missing[0].detail

    def test_board_only_net_is_net_extra(self) -> None:
        """A board net with no design counterpart yields a NET-EXTRA finding
        (fail-closed: the board side is never silently dropped)."""
        board = build_board_netlist(
            [
                _component("C1", "a.cap1", [("1", "gnd"), ("2", "orphan")]),
                _component("C2", "b.cap2", [("1", "gnd")]),
            ]
        )
        report = reconcile(board, _clean_design())
        extra = report.findings_of("NET-EXTRA")
        assert len(extra) == 1
        assert "orphan" in extra[0].detail

    def test_unkeyable_board_footprint_reported_not_skipped(self) -> None:
        board = build_board_netlist(
            [_component("R99", None, [("1", "gnd")]), _component("C1", "a.cap1", [("1", "gnd")])]
        )
        design = _design([("C1", "a.cap1")], {"gnd": [("C1", "1")]})
        report = reconcile(board, design)
        unkeyable = report.findings_of("UNKEYABLE")
        assert len(unkeyable) == 1
        assert "R99" in unkeyable[0].detail
        assert not report.passed

    def test_relay_pin_numbering_artifact_is_not_a_finding(self) -> None:
        """Net membership is compared at the COMPONENT (sheetpath) level, not
        the pin level: the relay's board pad numbers (A1/A2/13/14) differ
        from its netlist pin numbers (1/2/3/4) -- identical connectivity must
        not be reported as a membership difference (this is why the real pair
        reconciles with zero findings)."""
        board = build_board_netlist(
            [
                _component("K1", "power_in.bypass_relay", [("A1", "coil1"), ("A2", "coil2")]),
                _component("C1", "a.cap1", [("1", "gnd")]),
            ]
        )
        design = _design(
            [("K1", "power_in.bypass_relay"), ("C1", "a.cap1")],
            {
                "coil1": [("K1", "1")],
                "coil2": [("K1", "2")],
                "gnd": [("C1", "1")],
            },
        )
        report = reconcile(board, design)
        assert report.passed, report.findings

    def test_declared_but_empty_design_net_with_no_board_presence_is_not_a_finding(self) -> None:
        """The real compiled netlist declares nets with zero nodes (e.g.
        gnd_ref) that legitimately have no board presence; they must not
        manufacture findings on a clean pair."""
        design = _design(
            [("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")],
            {
                "gnd": [("C1", "1"), ("C2", "1"), ("R1", "1")],
                "vcc": [("C1", "2"), ("C2", "2")],
                "sig": [("R1", "2")],
                "gnd_ref": [],
            },
        )
        report = reconcile(_clean_board(), design)
        assert report.passed, report.findings


# ===========================================================================
# Real-pair verification and parser fail-closed behaviour
# ===========================================================================


class TestRealPairAndParser:
    def test_real_board_and_fresh_design_reconcile_clean(self) -> None:
        """U2 verification: the reconciliation over the real board and a fresh
        design netlist reports zero findings on the current pair, and zero
        false positives on components that match by path."""
        board = extract_board_netlist(REAL_BOARD)
        design = parse_design_netlist(REPO_ROOT / "elec" / "build" / "default.net")
        report = reconcile(board, design)
        assert report.passed, [
            (f.kind, f.detail) for f in report.findings
        ]
        assert report.matched_paths == len(design.components)

    def test_parse_design_netlist_accepts_duplicate_refs(self, tmp_path: Path) -> None:
        """The design parser tolerates duplicate refs (recording them) so the
        R39 reused-refdes mutation can be reconciled -- the strict netlist
        parsers reject such a netlist outright."""
        path = tmp_path / "reused.net"
        _write_design_netlist(
            path,
            [
                ("R1", "fp", "a.r1"),
                ("R1", "fp", "b.r2"),
            ],
        )
        design = parse_design_netlist(path)
        assert design.duplicate_refs == [("R1", "a.r1", "b.r2")]

    def test_parse_design_netlist_rejects_duplicate_paths(self, tmp_path: Path) -> None:
        path = tmp_path / "duppath.net"
        _write_design_netlist(
            path,
            [
                ("R1", "fp", "a.r1"),
                ("R2", "fp", "a.r1"),
            ],
        )
        with pytest.raises(ReconciliationGateError, match="sharing instance path"):
            parse_design_netlist(path)

    def test_parse_design_netlist_rejects_missing_sheetpath(self, tmp_path: Path) -> None:
        path = tmp_path / "nopath.net"
        path.write_text(
            '(export (version "E")\n'
            "  (components\n"
            '    (comp (ref "R1") (value "?"))\n'
            "  )\n"
            "  (nets\n"
            '    (net (code "1") (name "gnd"))\n'
            "  )\n)\n"
        )
        with pytest.raises(ReconciliationGateError, match="no usable 'sheetpath'"):
            parse_design_netlist(path)

    def test_parse_design_netlist_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ReconciliationGateError, match="not found"):
            parse_design_netlist(tmp_path / "missing.net")

    def test_extract_board_netlist_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ReconciliationGateError, match="board not found"):
            extract_board_netlist(tmp_path / "missing.kicad_pcb")
