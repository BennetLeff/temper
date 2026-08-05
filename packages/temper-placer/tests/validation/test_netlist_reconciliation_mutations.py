"""Component-level bite proof against the R16/R39 mutation classes (plan
2026-08-02-021, U4).

Each mutation class the identity checks exist for -- wholesale renumbering,
dropped components, reused refdes -- is applied to a parsed board/netlist
copy and asserted to fail the reconciliation gate (and, where the class is
set-preserving, to defeat the refdes-overlap check's assumptions). The
unmutated pair still passes (anti-vacuity).

This is the component-level half of the standing mutation suite: the
netlist-level harness and corpus runner (U5-U7) apply the same classes to the
compiled design netlist file and prove the owning checks bite end to end.
"""

from __future__ import annotations

from pathlib import Path

from temper_placer.core.netlist import Component, Pin
from temper_placer.validation.netlist_reconciliation import (
    DesignComponent,
    DesignNetlist,
    build_board_netlist,
    reconcile,
)


def _component(ref: str, sheetpath: str, nets: list[tuple[str, str]]) -> Component:
    pins = [Pin(name=p, number=p, position=(0.0, 0.0), net=n) for p, n in nets]
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
    return DesignNetlist(
        components=[DesignComponent(ref=ref, instance_path=path) for ref, path in comps],
        nets=nets,
    )


def _clean_board() -> list[Component]:
    return [
        _component("C1", "a.cap1", [("1", "gnd"), ("2", "vcc")]),
        _component("C2", "b.cap2", [("1", "gnd"), ("2", "vcc")]),
        _component("R1", "c.r1", [("1", "gnd"), ("2", "sig")]),
        _component("R2", "d.r2", [("1", "sig"), ("2", "gnd")]),
    ]


def _clean_design() -> DesignNetlist:
    return _design(
        [("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1"), ("R2", "d.r2")],
        {
            "gnd": [("C1", "1"), ("C2", "1"), ("R1", "1"), ("R2", "2")],
            "vcc": [("C1", "2"), ("C2", "2")],
            "sig": [("R1", "2"), ("R2", "1")],
        },
    )


def test_anti_vacuity_unmutated_pair_passes() -> None:
    """The unmutated board and netlist still pass (anti-vacuity control)."""
    report = reconcile(build_board_netlist(_clean_board()), _clean_design())
    assert report.passed, report.findings


def test_wholesale_renumber_yields_renumbered_and_gate_fails() -> None:
    """A wholesale renumber (permutation of refs within a prefix) yields
    RENUMBERED findings and a failing gate, even though the refdes set is
    unchanged -- the class preflight_identity's 95% overlap check passes by
    construction."""
    board = build_board_netlist(_clean_board())
    # Swap the C-prefix refs: a.cap1 C1 <-> C2 b.cap2.
    design = _design(
        [("C2", "a.cap1"), ("C1", "b.cap2"), ("R1", "c.r1"), ("R2", "d.r2")],
        {
            "gnd": [("C2", "1"), ("C1", "1"), ("R1", "1"), ("R2", "2")],
            "vcc": [("C2", "2"), ("C1", "2")],
            "sig": [("R1", "2"), ("R2", "1")],
        },
    )
    report = reconcile(board, design)
    assert not report.passed
    renumbered = report.findings_of("RENUMBERED")
    assert len(renumbered) == 2
    # The refdes SET is exactly preserved -- the overlap check's blind spot.
    assert {c.ref for c in board.components} == {c.ref for c in design.components}


def test_dropped_component_yields_missing_and_gate_fails() -> None:
    """Removing one component from the board side yields a MISSING finding
    and a failing gate."""
    board_components = [c for c in _clean_board() if c.ref != "C2"]
    board = build_board_netlist(board_components)
    report = reconcile(board, _clean_design())
    assert not report.passed
    missing = report.findings_of("MISSING")
    assert len(missing) == 1
    assert "b.cap2" in missing[0].detail
    assert "C2" in missing[0].detail


def test_reused_refdes_on_design_side_yields_reuse_and_gate_fails() -> None:
    """Assigning one ref to two design components yields a REUSE finding and a
    failing gate (the R39 mutation is applied to the DESIGN netlist, so the
    owning check must fire on the design side too)."""
    design = DesignNetlist(
        components=[
            DesignComponent(ref="C1", instance_path="a.cap1"),
            DesignComponent(ref="C1", instance_path="b.cap2"),
            DesignComponent(ref="R1", instance_path="c.r1"),
            DesignComponent(ref="R2", instance_path="d.r2"),
        ],
        nets={
            "gnd": [("C1", "1"), ("C1", "1"), ("R1", "1"), ("R2", "2")],
            "vcc": [("C1", "2"), ("C1", "2")],
            "sig": [("R1", "2"), ("R2", "1")],
        },
        duplicate_refs=[("C1", "a.cap1", "b.cap2")],
    )
    report = reconcile(build_board_netlist(_clean_board()), design)
    assert not report.passed
    reuse = report.findings_of("REUSE")
    assert len(reuse) == 1
    assert "C1" in reuse[0].detail
    assert "a.cap1" in reuse[0].detail and "b.cap2" in reuse[0].detail


def test_reused_refdes_on_board_side_yields_reuse_and_gate_fails() -> None:
    """Two board footprints sharing one ref yield a REUSE finding and a
    failing gate."""
    board = build_board_netlist(
        [
            _component("C1", "a.cap1", [("1", "gnd")]),
            _component("C1", "b.cap2", [("1", "gnd")]),
            _component("R1", "c.r1", [("1", "gnd"), ("2", "sig")]),
            _component("R2", "d.r2", [("1", "sig"), ("2", "gnd")]),
        ]
    )
    report = reconcile(board, _clean_design())
    assert not report.passed
    reuse = report.findings_of("REUSE")
    assert len(reuse) == 1
    assert "C1" in reuse[0].detail


def test_renumber_fails_the_preflight_gate_surface(tmp_path: Path) -> None:
    """The bite proof is not just the report -- the preflight surface
    (run_all_preflight_checks' reconciliation check) fails on the mutated
    pair and passes on the clean pair."""
    from temper_placer.validation.preflight import check_netlist_board_reconciliation

    # Write a mutated design netlist: refs swapped at the file level.
    mutated_net = tmp_path / "renumbered.net"
    mutated_net.write_text(
        "(export (version \"E\")\n"
        "  (components\n"
        '    (comp (ref "C2") (value "?") (footprint "?")\n'
        '      (sheetpath (names "/x/main.ato:Top::a.cap1") (tstamps "0")))\n'
        '    (comp (ref "C1") (value "?") (footprint "?")\n'
        '      (sheetpath (names "/x/main.ato:Top::b.cap2") (tstamps "0")))\n'
        "  )\n"
        "  (nets\n"
        '    (net (code "1") (name "gnd")\n'
        '      (node (ref "C2") (pin "1")) (node (ref "C1") (pin "1")))\n'
        "  )\n)\n"
    )
    # Board: C1@a.cap1, C2@b.cap2 (unmutated) -- written via kiutils so the
    # preflight check can read the file.
    from kiutils.board import Board
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.common import Net as KiNet
    from kiutils.items.common import Position

    board_path = tmp_path / "board.kicad_pcb"
    board = Board(version="20230121", generator="pytest", nets=[])
    fps = []
    for ref, sheetpath, pad_nets in [
        ("C1", "a.cap1", {("1", 1), ("2", 2)}),
        ("C2", "b.cap2", {("1", 1), ("2", 2)}),
    ]:
        fp = Footprint(
            entryName="temper:Test", tstamp=f"fp-{ref}", position=Position(0, 0)
        )
        fp.properties = {"Reference": ref, "Value": "?", "Sheetpath": sheetpath}
        fp.pads = [
            Pad(number=n, type="smd", tstamp=f"fp-{ref}-p{n}", net=KiNet(number=num, name="gnd"))
            for n, num in sorted(pad_nets)
        ]
        fps.append(fp)
    board.footprints = fps
    board.to_file(str(board_path))

    mutated_result = check_netlist_board_reconciliation(board_path, mutated_net)
    assert not mutated_result.passed
    assert any(i.code.startswith("RECON_RENUMBERED") for i in mutated_result.issues)
