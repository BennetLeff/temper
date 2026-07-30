"""Tests for check_isolation_keepout.py.

These deliberately do NOT rely on the real ``pcb/temper.kicad_pcb`` or the
real ``elec/domain_manifest.yaml`` -- matching the convention in
``test_check_domain_partition.py`` (synthetic netlist/manifest) and
``test_resync_pcb_netlist.py`` (synthetic board built via the kiutils
Python API, then round-tripped through ``Board.to_file``/``Board.from_file``
so every fixture exercises the exact same parser the gate itself uses).
The real board/manifest pair is exercised directly by running the gate
(``docs/evidence/2026-07-28-isolation-keepout.md``): on the real board, as
of this change, the gate correctly reports the barrier as MISSING --
Task 1 of that evidence doc found the current placement interleaves the
HV and SELV domains across virtually the entire board (every 10mm-wide
column contains both), so no keepout was added rather than drawing one
that would immediately violate itself.

Every synthetic board here is a minimal square (0,0)-(100,100) with a
candidate barrier strip at x=[45,55] (10mm wide, i.e. wide enough to hold
an 8mm-wide, correctly-configured barrier with margin), one HV-domain
footprint on the left (x=20) and one SELV-domain footprint on the right
(x=80), so the "correct" fixture is a single, obviously-valid case and
every failure fixture changes exactly one property away from it.

Groups:
  TestMissingBarrier   -- no keepout zone, or none named correctly -> violation
  TestLayerSpan        -- keepout misses a copper layer -> violation
  TestKeepoutSettings  -- keepout still permits tracks/vias/pads/... -> violation
  TestWidth            -- keepout narrower than MIN_BARRIER_WIDTH_MM -> violation
  TestPartition        -- keepout doesn't span the full board -> violation
  TestIntrusion        -- real copper (segment/via/pad/zone) crosses the
                          keepout -> violation, one test per copper kind
  TestFarSideCrossing  -- HV/SELV components on the wrong/same side -> violation
  TestPass             -- a fully correct barrier -> EXIT_OK
  TestAntiVacuity      -- missing/empty inputs, zero HV or SELV pads, zero
                          copper items -> GateError (never "0 violations")
  TestFailBeforePassAfter -- explicit before/after pair (no keepout -> gate
                          fails; add a correct keepout -> gate passes),
                          without git stash, per the plan's falsifier.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_isolation_keepout import (  # noqa: E402
    BARRIER_ZONE_NAME,
    MIN_BARRIER_WIDTH_MM,
    GateError,
    load_board,
    load_manifest,
    run,
)
from kiutils.board import Board, LayerToken  # noqa: E402
from kiutils.footprint import Footprint, Pad  # noqa: E402
from kiutils.items.brditems import Segment, Via  # noqa: E402
from kiutils.items.common import Net, Position  # noqa: E402
from kiutils.items.gritems import GrPoly  # noqa: E402
from kiutils.items.zones import Hatch, KeepoutSettings, Zone, ZonePolygon  # noqa: E402

MANIFEST_TEXT = """
schema_version: 1
domains:
  HV:
    nets: ["ac_l"]
  SELV:
    nets: ["gnd"]
"""


def write_manifest(tmp_path: Path, text: str = MANIFEST_TEXT) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(text)
    return p


COPPER_LAYERS = [
    LayerToken(ordinal=0, name="F.Cu", type="signal"),
    LayerToken(ordinal=1, name="In1.Cu", type="signal"),
    LayerToken(ordinal=2, name="In2.Cu", type="signal"),
    LayerToken(ordinal=31, name="B.Cu", type="signal"),
]
ALL_COPPER_LAYER_NAMES = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]


def _valid_keepout_settings() -> KeepoutSettings:
    return KeepoutSettings(
        tracks="not_allowed",
        vias="not_allowed",
        pads="not_allowed",
        copperpour="not_allowed",
        footprints="not_allowed",
    )


def build_board(
    *,
    barrier_layers: list[str] | None = ALL_COPPER_LAYER_NAMES,
    # Default width tracks MIN_BARRIER_WIDTH_MM (currently 12.6mm, PD3) plus
    # a 1mm margin per side, so a "fully correct" fixture stays correct if
    # that constant is ever retargeted again -- was a hardcoded (45.0, 55.0)
    # (10mm), which passed at the prior 8.0mm/PD2 figure but is now, itself,
    # narrower than the settled 12.6mm/PD3 requirement.
    barrier_x: tuple[float, float] = (
        50.0 - MIN_BARRIER_WIDTH_MM / 2.0 - 1.0,
        50.0 + MIN_BARRIER_WIDTH_MM / 2.0 + 1.0,
    ),
    barrier_y: tuple[float, float] = (0.0, 100.0),
    keepout_settings: KeepoutSettings | None = None,
    include_barrier: bool = True,
    hv_x: float = 20.0,
    selv_x: float = 80.0,
    extra_trace_items: list | None = None,
    extra_zones: list[Zone] | None = None,
    board_outline: list[Position] | None = None,
) -> Board:
    """Base fixture: 100x100mm board, HV footprint R1 at (hv_x, 50) on
    net 'ac_l', SELV footprint U1 at (selv_x, 50) on net 'gnd', one HV
    trace segment near R1 (so "copper items examined" is never zero), and
    -- unless include_barrier=False -- a keepout zone named
    BARRIER_ZONE_NAME spanning barrier_layers over the rectangle
    x in barrier_x, y in barrier_y."""
    board = Board()
    board.version = "20211014"
    board.generator = "pytest"
    board.layers = list(COPPER_LAYERS) + [LayerToken(ordinal=44, name="Edge.Cuts", type="user")]
    board.nets = [Net(number=0, name=""), Net(number=1, name="ac_l"), Net(number=2, name="gnd")]

    outline = board_outline or [
        Position(0, 0), Position(100, 0), Position(100, 100), Position(0, 100)
    ]
    board.graphicItems = [GrPoly(coordinates=outline, layer="Edge.Cuts", width=0.1)]

    zones: list[Zone] = []
    if include_barrier:
        zones.append(
            Zone(
                net=0,
                netName="",
                layers=barrier_layers or [],
                name=BARRIER_ZONE_NAME,
                hatch=Hatch(style="none", pitch=0.0),
                keepoutSettings=keepout_settings if keepout_settings is not None else _valid_keepout_settings(),
                polygons=[
                    ZonePolygon(
                        coordinates=[
                            Position(barrier_x[0], barrier_y[0]),
                            Position(barrier_x[1], barrier_y[0]),
                            Position(barrier_x[1], barrier_y[1]),
                            Position(barrier_x[0], barrier_y[1]),
                        ]
                    )
                ],
                tstamp="barrier-zone",
            )
        )
    zones.extend(extra_zones or [])
    board.zones = zones

    fp_hv = Footprint()
    fp_hv.entryName = "Test:HV"
    fp_hv.layer = "F.Cu"
    fp_hv.position = Position(hv_x, 50)
    fp_hv.properties = {"Reference": "R1"}
    fp_hv.pads = [
        Pad(
            number="1", type="smd", shape="rect", position=Position(0, 0), size=Position(1, 1),
            layers=["F.Cu"], net=Net(number=1, name="ac_l"),
        )
    ]

    fp_selv = Footprint()
    fp_selv.entryName = "Test:SELV"
    fp_selv.layer = "F.Cu"
    fp_selv.position = Position(selv_x, 50)
    fp_selv.properties = {"Reference": "U1"}
    fp_selv.pads = [
        Pad(
            number="1", type="smd", shape="rect", position=Position(0, 0), size=Position(1, 1),
            layers=["F.Cu"], net=Net(number=2, name="gnd"),
        )
    ]

    board.footprints = [fp_hv, fp_selv]

    base_segment = Segment(
        start=Position(hv_x - 10, 10), end=Position(hv_x + 10, 10),
        width=0.3, layer="F.Cu", net=1, tstamp="seg-hv-base",
    )
    board.traceItems = [base_segment] + (extra_trace_items or [])

    return board


def write_board(tmp_path: Path, board: Board, name: str = "board.kicad_pcb") -> Path:
    p = tmp_path / name
    board.to_file(str(p))
    return p


# ---------------------------------------------------------------------------
# TestMissingBarrier
# ---------------------------------------------------------------------------


class TestMissingBarrier:
    def test_no_keepout_zone_at_all(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(include_barrier=False))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        assert any(v.check == "missing" for v in report.violations)
        assert report.barrier_found is False
        # denominators still reported even though the barrier is missing
        assert report.hv_pads == 1
        assert report.selv_pads == 1
        assert report.copper_items_examined >= 1

    def test_keepout_present_but_wrong_name(self, tmp_path: Path) -> None:
        board = build_board(include_barrier=False)
        # A keepout zone that exists but isn't OUR barrier (e.g. a
        # courtyard-clearance keepout for some unrelated part).
        board.zones = [
            Zone(
                net=0, netName="", layers=ALL_COPPER_LAYER_NAMES, name="SOME_OTHER_KEEPOUT",
                hatch=Hatch(style="none", pitch=0.0), keepoutSettings=_valid_keepout_settings(),
                polygons=[ZonePolygon(coordinates=[Position(1, 1), Position(2, 1), Position(2, 2), Position(1, 2)])],
                tstamp="unrelated-keepout",
            )
        ]
        board_path = write_board(tmp_path, board)
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        assert any(v.check == "missing" for v in report.violations)
        assert report.keepout_zones_found_total == 1  # counted, just not treated as the barrier


# ---------------------------------------------------------------------------
# TestLayerSpan
# ---------------------------------------------------------------------------


class TestLayerSpan:
    def test_missing_inner_layers(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(barrier_layers=["F.Cu", "B.Cu"]))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        assert any(v.check == "layer-span" for v in report.violations)

    def test_wildcard_cu_layer_is_accepted(self, tmp_path: Path) -> None:
        """`*.Cu` is a valid KiCad shorthand for every copper layer -- must
        not be treated as a missing-layer violation."""
        board_path = write_board(tmp_path, build_board(barrier_layers=["*.Cu"]))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert not any(v.check == "layer-span" for v in report.violations)


# ---------------------------------------------------------------------------
# TestKeepoutSettings
# ---------------------------------------------------------------------------


class TestKeepoutSettings:
    def test_default_settings_permit_everything(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(keepout_settings=KeepoutSettings()))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        settings_violations = [v for v in report.violations if v.check == "keepout-settings"]
        assert len(settings_violations) == 5  # tracks, vias, pads, copperpour, footprints


# ---------------------------------------------------------------------------
# TestWidth
# ---------------------------------------------------------------------------


class TestWidth:
    def test_barrier_narrower_than_minimum(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(barrier_x=(49.0, 51.0)))  # 2mm, needs 12.6mm
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        assert any(v.check == "width" for v in report.violations)

    def test_barrier_exactly_at_minimum_plus_margin_passes_width_check(self, tmp_path: Path) -> None:
        half = MIN_BARRIER_WIDTH_MM / 2.0
        board_path = write_board(
            tmp_path, build_board(barrier_x=(50.0 - half - 0.5, 50.0 + half + 0.5))
        )
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert not any(v.check == "width" for v in report.violations)


# ---------------------------------------------------------------------------
# TestPartition
# ---------------------------------------------------------------------------


class TestPartition:
    def test_barrier_does_not_span_full_board_height(self, tmp_path: Path) -> None:
        """A barrier that stops short of the board edge doesn't separate
        anything -- copper can route around its end."""
        board_path = write_board(tmp_path, build_board(barrier_y=(10.0, 90.0)))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        assert any(v.check == "partition" for v in report.violations)


# ---------------------------------------------------------------------------
# TestIntrusion
# ---------------------------------------------------------------------------


class TestIntrusion:
    def test_segment_crosses_barrier(self, tmp_path: Path) -> None:
        crossing = Segment(
            start=Position(40, 50), end=Position(60, 50), width=0.3, layer="F.Cu", net=1,
            tstamp="seg-crossing",
        )
        board_path = write_board(tmp_path, build_board(extra_trace_items=[crossing]))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        intrusions = [v for v in report.violations if v.check == "intrusion"]
        assert any("seg-crossing" in v.detail for v in intrusions)

    def test_via_inside_barrier(self, tmp_path: Path) -> None:
        via = Via(
            position=Position(50, 50), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"], net=1,
            tstamp="via-crossing",
        )
        board_path = write_board(tmp_path, build_board(extra_trace_items=[via]))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        intrusions = [v for v in report.violations if v.check == "intrusion"]
        assert any("via-crossing" in v.detail for v in intrusions)

    def test_via_breaches_inner_layer_even_if_not_named(self, tmp_path: Path) -> None:
        """A through via's `layers` field names only the two outer layers,
        but its drill physically passes through every inner layer too.
        Confirm the gate still flags it against a barrier that spans ONLY
        an inner layer."""
        via = Via(
            position=Position(50, 50), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"], net=1,
            tstamp="via-inner-breach",
        )
        board_path = write_board(
            tmp_path, build_board(barrier_layers=["In1.Cu"], extra_trace_items=[via])
        )
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        # Both layer-span (In1.Cu alone doesn't cover all 4) AND intrusion
        # are expected here; assert the intrusion specifically fired.
        intrusions = [v for v in report.violations if v.check == "intrusion"]
        assert any("via-inner-breach" in v.detail for v in intrusions)

    def test_pad_inside_barrier(self, tmp_path: Path) -> None:
        board = build_board()
        extra_fp = Footprint()
        extra_fp.entryName = "Test:Stray"
        extra_fp.layer = "F.Cu"
        extra_fp.position = Position(50, 50)
        extra_fp.properties = {"Reference": "C99"}
        extra_fp.pads = [
            Pad(
                number="1", type="smd", shape="rect", position=Position(0, 0), size=Position(1, 1),
                layers=["F.Cu"], net=Net(number=1, name="ac_l"),
            )
        ]
        board.footprints = list(board.footprints) + [extra_fp]
        board_path = write_board(tmp_path, board)
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        intrusions = [v for v in report.violations if v.check == "intrusion"]
        assert any("C99" in v.detail for v in intrusions)

    def test_pad_body_overlaps_barrier_even_when_center_is_outside(self, tmp_path: Path) -> None:
        """A large pad whose CENTER sits just outside the keepout but whose
        physical body straddles the boundary must still be flagged -- a
        safety intrusion check must never under-approximate a pad's real
        extent by collapsing it to a single point."""
        board = build_board()  # barrier spans x=[45,55]
        extra_fp = Footprint()
        extra_fp.entryName = "Test:LargePad"
        extra_fp.layer = "F.Cu"
        # Center at x=43 (2mm outside the barrier's left edge at x=45), but
        # a 6mm-wide pad reaches to x=46 -- 1mm into the barrier.
        extra_fp.position = Position(43, 50)
        extra_fp.properties = {"Reference": "C98"}
        extra_fp.pads = [
            Pad(
                number="1", type="smd", shape="rect", position=Position(0, 0), size=Position(6, 2),
                layers=["F.Cu"], net=Net(number=1, name="ac_l"),
            )
        ]
        board.footprints = list(board.footprints) + [extra_fp]
        board_path = write_board(tmp_path, board)
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        intrusions = [v for v in report.violations if v.check == "intrusion"]
        assert any("C98" in v.detail for v in intrusions)

    def test_copper_pour_zone_crosses_barrier(self, tmp_path: Path) -> None:
        pour = Zone(
            net=1, netName="ac_l", layers=["F.Cu"], hatch=Hatch(style="none", pitch=0.0),
            polygons=[
                ZonePolygon(
                    coordinates=[Position(0, 0), Position(60, 0), Position(60, 30), Position(0, 30)]
                )
            ],
            tstamp="pour-crossing",
        )
        board_path = write_board(tmp_path, build_board(extra_zones=[pour]))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        intrusions = [v for v in report.violations if v.check == "intrusion"]
        assert any("pour-crossing" in v.detail for v in intrusions)


# ---------------------------------------------------------------------------
# TestFarSideCrossing
# ---------------------------------------------------------------------------


class TestFarSideCrossing:
    def test_selv_component_on_hv_side(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(selv_x=20.0, hv_x=10.0))
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"
        assert any(v.check == "far-side-crossing" for v in report.violations)


# ---------------------------------------------------------------------------
# TestPass
# ---------------------------------------------------------------------------


class TestPass:
    def test_fully_correct_barrier_passes(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "clean"
        assert report.violations == []
        assert report.barrier_found is True
        assert report.hv_pads == 1
        assert report.selv_pads == 1


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_board_file(self, tmp_path: Path) -> None:
        manifest_path = write_manifest(tmp_path)
        with pytest.raises(GateError):
            run(tmp_path / "does_not_exist.kicad_pcb", manifest_path)

    def test_missing_manifest_file(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        with pytest.raises(GateError):
            run(board_path, tmp_path / "does_not_exist.yaml")

    def test_empty_manifest_domains(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(tmp_path, "schema_version: 1\ndomains: {}\n")
        with pytest.raises(GateError):
            run(board_path, manifest_path)

    def test_zero_hv_pads_on_board(self, tmp_path: Path) -> None:
        """Manifest declares an HV net that touches nothing on this board."""
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(
            tmp_path,
            "schema_version: 1\ndomains:\n  HV:\n    nets: [\"nonexistent_hv_net\"]\n"
            "  SELV:\n    nets: [\"gnd\"]\n",
        )
        with pytest.raises(GateError, match="zero HV-domain-classified pads"):
            run(board_path, manifest_path)

    def test_zero_selv_pads_on_board(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(
            tmp_path,
            "schema_version: 1\ndomains:\n  HV:\n    nets: [\"ac_l\"]\n"
            "  SELV:\n    nets: [\"nonexistent_selv_net\"]\n",
        )
        with pytest.raises(GateError, match="zero SELV-domain-classified pads"):
            run(board_path, manifest_path)

    def test_zero_copper_items_on_board(self, tmp_path: Path) -> None:
        board = build_board()
        board.traceItems = []  # remove the one base segment; zones still present (the barrier itself
        # is a keepout, not counted as copper) -- must still fail closed since
        # there is no real copper to check an intrusion against.
        board_path = write_board(tmp_path, board)
        manifest_path = write_manifest(tmp_path)
        with pytest.raises(GateError, match="zero copper items"):
            run(board_path, manifest_path)

    def test_zero_footprints_on_board(self, tmp_path: Path) -> None:
        board = build_board()
        board.footprints = []
        board_path = write_board(tmp_path, board)
        manifest_path = write_manifest(tmp_path)
        with pytest.raises(GateError, match="zero footprints"):
            run(board_path, manifest_path)


# ---------------------------------------------------------------------------
# TestFailBeforePassAfter
# ---------------------------------------------------------------------------


class TestFailBeforePassAfter:
    """Explicit before/after demonstration for the gate itself (it is new
    and has no prior git history to diff against, so this stands in for
    the "prove it would have caught the bug" pattern used elsewhere in this
    repo's gate tests) -- built as two synthetic fixtures, never via
    ``git stash`` (forbidden in this plan; the stash ref is shared across
    worktrees on this project)."""

    def test_before_no_keepout_fails(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(include_barrier=False), name="before.kicad_pcb")
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "violation"

    def test_after_correct_keepout_passes(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(include_barrier=True), name="after.kicad_pcb")
        manifest_path = write_manifest(tmp_path)
        state, report = run(board_path, manifest_path)
        assert state == "clean"


# ---------------------------------------------------------------------------
# Sanity checks on the loaders themselves (not just run())
# ---------------------------------------------------------------------------


class TestLoaders:
    def test_load_manifest_rejects_overlapping_domains(self, tmp_path: Path) -> None:
        manifest_path = write_manifest(
            tmp_path,
            "schema_version: 1\ndomains:\n  HV:\n    nets: [\"shared\"]\n"
            "  SELV:\n    nets: [\"shared\"]\n",
        )
        with pytest.raises(GateError, match="BOTH HV and SELV"):
            load_manifest(manifest_path)

    def test_load_board_reports_copper_layers_in_ordinal_order(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        board = load_board(board_path)
        assert board.copper_layers_ordered == ALL_COPPER_LAYER_NAMES
