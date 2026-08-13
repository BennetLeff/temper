"""Tests for the instance-path identity join in
``temper_placer.io.real_board.load_real_board_placement`` (2026-08-13
board/netlist desync postmortem, gaps A+B).

Before this fix, board <-> design identity was joined by matching refdes
STRINGS: a board footprint's position was classified using
``ref_to_domain_nets[board_ref]``, a dict keyed by the DESIGN netlist's own
refs. That is silently wrong whenever the two sides' ref namespaces
disagree -- exactly the shape of the 2026-08-13 incident (``U6``/``U7``
renamed to different physical parts, dozens of renumbers, missing
footprints): a renumbered component was silently DROPPED (present on the
board, absent from the matched set, no record of why), and worse, a board
ref that happened to coincide with an unrelated design ref was silently
MIS-CLASSIFIED -- attributing one physical part's domain (HV/SELV) to a
different one.

These tests construct exactly those two failure shapes with synthetic
board/netlist fixtures and prove the fix (a) recovers the renumbered
component via its stable instance path, and (b) never lets a coincidental
ref-string match stand in for the real identity, which prevents the
dangerous mis-classification case, not just the missing-component one.

Fixture helpers (`_write_netlist`/`_write_board`) are a deliberate,
self-contained COPY of the ones in
`scripts/tests/test_check_netlist_board_reconciliation.py` -- this repo's
stated convention for gate/loader test fixtures: a test's correctness must
not depend on another module's internal representation changing out from
under it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "packages" / "temper-placer" / "src")
)

from temper_placer.io.real_board import load_real_board_placement  # noqa: E402


def _write_netlist(path: Path, comps: list[tuple[str, str, str]], nets: dict[str, list[str]]) -> None:
    """[(ref, footprint, instance_path_suffix), ...] plus {net_name: [ref, ...]}
    -- same s-expression shape ``parse_design_netlist`` (and
    ``check_netlist_board_reconciliation``'s own test fixtures) parse."""
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
    net_blocks = []
    for i, (net_name, refs) in enumerate(nets.items(), start=1):
        nodes = "".join(f'\n      (node (ref "{r}") (pin "1"))' for r in refs)
        net_blocks.append(f'    (net (code "{i}") (name "{net_name}"){nodes})')
    path.write_text(
        "(export (version \"E\")\n"
        "  (components\n" + "\n".join(blocks) + "\n  )\n"
        "  (nets\n" + "\n".join(net_blocks) + "\n  )\n)\n"
    )


def _write_board(path: Path, comps: list[tuple[str, str, str]]) -> None:
    """[(ref, sheetpath, net_name), ...] footprints with a single pad."""
    from kiutils.board import Board
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.common import Net as KiNet
    from kiutils.items.common import Position

    board = Board(version="20230121", generator="pytest", nets=[])
    fps = []
    for i, (ref, sheetpath, net_name) in enumerate(comps):
        fp = Footprint(
            entryName="temper:Test",
            tstamp=f"fp-{ref}",
            position=Position(10.0 + i * 5.0, 10.0),
        )
        fp.properties = {"Reference": ref, "Value": "?", "Sheetpath": sheetpath}
        fp.pads = [
            Pad(
                number="1",
                type="smd",
                tstamp=f"fp-{ref}-p1",
                net=KiNet(number=i + 1, name=net_name),
            )
        ]
        fps.append(fp)
    board.footprints = fps
    board.to_file(str(path))


def _write_manifest(path: Path, hv_nets: list[str], selv_nets: list[str]) -> None:
    domains: dict[str, dict[str, list[str]]] = {}
    if hv_nets:
        domains["HV"] = {"nets": hv_nets}
    if selv_nets:
        domains["SELV"] = {"nets": selv_nets}
    path.write_text(yaml.safe_dump({"domains": domains}))


class TestCleanBoardMatchesEveryPath:
    def test_no_renumber_matches_cleanly_and_reports_complete_join(
        self, tmp_path: Path
    ) -> None:
        board_path = tmp_path / "board.kicad_pcb"
        netlist_path = tmp_path / "default.net"
        manifest_path = tmp_path / "domain_manifest.yaml"

        _write_netlist(
            netlist_path,
            [
                ("C1", "temper:Test", "mod.hv_part"),
                ("C2", "temper:Test", "mod.lv_part"),
            ],
            nets={"hv_net": ["C1"], "lv_net": ["C2"]},
        )
        _write_board(
            board_path,
            [
                ("C1", "mod.hv_part", "hv_net"),
                ("C2", "mod.lv_part", "lv_net"),
            ],
        )
        _write_manifest(manifest_path, hv_nets=["hv_net"], selv_nets=["lv_net"])

        placement, voltage_domains, stats = load_real_board_placement(
            board_path, manifest_path, netlist_path
        )

        assert stats["identity_join_incomplete"] is False
        ij = stats["identity_join"]
        assert ij["renumbered_paths"] == []
        assert ij["board_only_paths"] == []
        assert ij["design_only_paths"] == []
        assert ij["matched_paths"] == 2
        refs = {c["ref"] for c in placement["components"]}
        assert refs == {"C1", "C2"}


class TestRenumberIsRecoveredNotDropped:
    """Gap B: a renumbered component must not be silently absent from the
    matched set -- the exact 'dozens of components renumbered while the
    board kept old designators' half of the 2026-08-13 incident."""

    def test_renumbered_board_ref_is_still_matched_via_instance_path(
        self, tmp_path: Path
    ) -> None:
        board_path = tmp_path / "board.kicad_pcb"
        netlist_path = tmp_path / "default.net"
        manifest_path = tmp_path / "domain_manifest.yaml"

        # Design says C1 -> mod.hv_part. The schematic was edited and
        # recompiled such that the board's copy of that SAME physical part
        # (same instance path) still carries the OLD ref "C9" -- a
        # designator renumber the board was never resynced for.
        _write_netlist(
            netlist_path,
            [
                ("C1", "temper:Test", "mod.hv_part"),
                ("C2", "temper:Test", "mod.lv_part"),
            ],
            nets={"hv_net": ["C1"], "lv_net": ["C2"]},
        )
        _write_board(
            board_path,
            [
                ("C9", "mod.hv_part", "hv_net"),  # renumbered: was C1
                ("C2", "mod.lv_part", "lv_net"),
            ],
        )
        _write_manifest(manifest_path, hv_nets=["hv_net"], selv_nets=["lv_net"])

        placement, voltage_domains, stats = load_real_board_placement(
            board_path, manifest_path, netlist_path
        )

        # The old ref-keyed join would have looked up ref_to_domain_nets["C9"]
        # against a dict keyed by DESIGN refs {"C1": [...], "C2": [...]} --
        # no "C9" key exists, so C9 would be silently dropped from the
        # matched set with no record anywhere of why. It must be matched now.
        refs = {c["ref"] for c in placement["components"]}
        assert "C9" in refs, "renumbered component was silently dropped, not recovered"
        c9 = next(c for c in placement["components"] if c["ref"] == "C9")
        assert c9["nets"] == ["hv_net"]

        # And the renumber is reported, not silently absorbed.
        assert stats["identity_join_incomplete"] is True
        ij = stats["identity_join"]
        assert ("mod.hv_part", "C9", "C1") in ij["renumbered_paths"]
        assert ij["board_only_paths"] == []
        assert ij["design_only_paths"] == []


class TestCoincidentalRefMatchIsNeverTrusted:
    """Gap A: the dangerous case -- a board ref that happens to equal a
    DIFFERENT design component's ref must never borrow that unrelated
    component's domain classification. This is the U6/U7-shaped defect:
    'U6/U7 came to name different physical parts in the two sources.'"""

    def test_swapped_refs_are_reclassified_correctly_not_cross_matched(
        self, tmp_path: Path
    ) -> None:
        board_path = tmp_path / "board.kicad_pcb"
        netlist_path = tmp_path / "default.net"
        manifest_path = tmp_path / "domain_manifest.yaml"

        # Design: C1 is the HV part, C2 is the LV part.
        _write_netlist(
            netlist_path,
            [
                ("C1", "temper:Test", "mod.hv_part"),
                ("C2", "temper:Test", "mod.lv_part"),
            ],
            nets={"hv_net": ["C1"], "lv_net": ["C2"]},
        )
        # Board: the refs got swapped between the two physical parts. The
        # footprint labelled "C1" on the board is actually mod.lv_part (the
        # LV component); "C2" is actually mod.hv_part.
        _write_board(
            board_path,
            [
                ("C1", "mod.lv_part", "lv_net"),
                ("C2", "mod.hv_part", "hv_net"),
            ],
        )
        _write_manifest(manifest_path, hv_nets=["hv_net"], selv_nets=["lv_net"])

        placement, voltage_domains, stats = load_real_board_placement(
            board_path, manifest_path, netlist_path
        )

        by_ref = {c["ref"]: c for c in placement["components"]}
        assert set(by_ref) == {"C1", "C2"}

        # The safety-critical assertion: board "C1" (physically mod.lv_part)
        # must be classified LV, NEVER borrow design-C1's HV classification
        # just because the ref strings match. A pre-fix ref-keyed join would
        # have reported the OPPOSITE (wrong, unsafe) classification here.
        assert by_ref["C1"]["nets"] == ["lv_net"], (
            "board C1 was classified using the wrong (coincidentally "
            "ref-matching) design component's nets -- exactly the "
            "mis-attribution class this fix exists to prevent"
        )
        assert by_ref["C2"]["nets"] == ["hv_net"], (
            "board C2 was classified using the wrong (coincidentally "
            "ref-matching) design component's nets"
        )

        # Both are reported as renumbered (their board ref differs from the
        # design ref actually occupying that instance path).
        ij = stats["identity_join"]
        assert ("mod.hv_part", "C2", "C1") in ij["renumbered_paths"]
        assert ("mod.lv_part", "C1", "C2") in ij["renumbered_paths"]
        assert stats["identity_join_incomplete"] is True


class TestMissingAndExtraAreExplicit:
    """Gap B: a design component with no board footprint, and a board
    footprint with no design counterpart, must land in an explicit bucket
    -- never merely absent with no record."""

    def test_design_only_and_board_only_are_both_reported(self, tmp_path: Path) -> None:
        board_path = tmp_path / "board.kicad_pcb"
        netlist_path = tmp_path / "default.net"
        manifest_path = tmp_path / "domain_manifest.yaml"

        _write_netlist(
            netlist_path,
            [
                ("C1", "temper:Test", "mod.hv_part"),
                ("C3", "temper:Test", "mod.missing_part"),  # no board footprint
            ],
            nets={"hv_net": ["C1"], "orphan_net": ["C3"]},
        )
        _write_board(
            board_path,
            [
                ("C1", "mod.hv_part", "hv_net"),
                ("C5", "mod.extra_part", "gnd"),  # no design counterpart
            ],
        )
        _write_manifest(manifest_path, hv_nets=["hv_net"], selv_nets=[])

        _placement, _voltage_domains, stats = load_real_board_placement(
            board_path, manifest_path, netlist_path
        )

        ij = stats["identity_join"]
        assert ij["design_only_paths"] == ["mod.missing_part"]
        assert ij["board_only_paths"] == ["mod.extra_part"]
        assert stats["identity_join_incomplete"] is True


class TestUnkeyableBoardComponent:
    def test_board_footprint_with_no_sheetpath_is_reported_unkeyable(
        self, tmp_path: Path
    ) -> None:
        from kiutils.board import Board
        from kiutils.footprint import Footprint, Pad
        from kiutils.items.common import Net as KiNet
        from kiutils.items.common import Position

        board_path = tmp_path / "board.kicad_pcb"
        netlist_path = tmp_path / "default.net"
        manifest_path = tmp_path / "domain_manifest.yaml"

        _write_netlist(
            netlist_path,
            [("C1", "temper:Test", "mod.hv_part")],
            nets={"hv_net": ["C1"]},
        )
        board = Board(version="20230121", generator="pytest", nets=[])
        fp = Footprint(entryName="temper:Test", tstamp="fp-C1", position=Position(10.0, 10.0))
        fp.properties = {"Reference": "C1", "Value": "?"}  # no Sheetpath property at all
        fp.pads = [
            Pad(number="1", type="smd", tstamp="fp-C1-p1", net=KiNet(number=1, name="hv_net"))
        ]
        board.footprints = [fp]
        board.to_file(str(board_path))
        _write_manifest(manifest_path, hv_nets=["hv_net"], selv_nets=[])

        _placement, _voltage_domains, stats = load_real_board_placement(
            board_path, manifest_path, netlist_path
        )
        ij = stats["identity_join"]
        assert "C1" in ij["board_unkeyable_refs"]
        assert stats["identity_join_incomplete"] is True
