"""Tests for the pad-vs-fixed-copper NoOverlap constraint (issue #523, R24).

Five groups, mapping to the R24 gates and the fail-capable requirement in
``temper_placer.placer.cp_sat.fixed_copper``:

1. ``TestGeneratorNotVacuous`` -- falsifier-driven: against the real board,
   the generator produces a non-empty obstacle list and per-ref pad lists.
2. ``TestItemBuilding`` -- frame normalization (traces/vias raw -> solver
   frame), net/layer filtering, the ``include_other_pads`` switch, and the
   degenerate-segment encoding.
3. ``TestFixedCopperSoundnessBMC`` -- the R24 item-2 BMC-exhaustive sweep of
   the encoded predicate (``encoded_overlap``) against the exact oracle
   (``exact_clearance_mm``), over pad sizes x item kinds x a relative-position
   grid covering touching/overlapping/clear at 0.9x/1.0x/1.1x margin x all
   four rotations, asserting encoded-clear => exact-clear (soundness, zero
   counterexamples) and encoded-overlap => exact-clearance within the
   documented slack bound.
4. ``TestPostSolveAudit`` -- the R24 item-3 audit function against passing,
   deliberately-broken, and missing-position placements.
5. ``TestFailCapableSolve`` -- solve-level: a placement whose pad sits on a
   different-net track must be rejected (infeasible, unsat core naming the
   fixed-copper assumption), a clear placement accepted.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io._kicad_types import TraceData
from temper_placer.placer.cp_sat._encoder_solve import solve_placement
from temper_placer.placer.cp_sat.fixed_copper import (
    COPPER_LAYERS,
    FixedCopperItem,
    PadRectLocal,
    _rectilinear_convex_edges,
    audit_fixed_copper,
    build_fixed_copper_items,
    build_free_component_pads,
    encoded_overlap,
    encoded_pad_world_rect,
    exact_clearance_mm,
    pad_world_rect,
    segment_slack_mm,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"

_MARGIN = 0.05
# The encoder embeds _GRID_HEADROOM_MM (0.02 mm) beyond the margin in every
# item's encoded box (see fixed_copper.py's module docstring soundness
# section -- integer-grid quantization can erode up to 1.5 units of the
# encoded margin otherwise). The test helpers below must mirror that so the
# BMC sweep evaluates the SAME predicate the encoder enforces.
_HEADROOM = 0.02


def _pad(center=(0.0, 0.0), half=(0.5, 0.5), net="NET_A", layers=None, number="1"):
    return PadRectLocal(
        number=number,
        net=net,
        layers=layers if layers is not None else frozenset({"F.Cu"}),
        center=center,
        half=half,
    )


def _segment_item(p0, p1, width=0.2, net="NET_B", layers=None):
    exp = width / 2 + _MARGIN + _HEADROOM
    return FixedCopperItem(
        kind="segment",
        net=net,
        layers=layers if layers is not None else frozenset({"F.Cu"}),
        rect=(
            min(p0[0], p1[0]) - exp,
            min(p0[1], p1[1]) - exp,
            max(p0[0], p1[0]) + exp,
            max(p0[1], p1[1]) + exp,
        ),
        exact={"p0": p0, "p1": p1, "width": width},
        slack_mm=segment_slack_mm(p0, p1, width, _MARGIN + _HEADROOM),
        margin_mm=_MARGIN,
        label="seg",
    )


def _via_item(center, diameter=0.8, net="NET_B", layers=None):
    pad = diameter / 2 + _MARGIN + _HEADROOM
    return FixedCopperItem(
        kind="via",
        net=net,
        layers=layers if layers is not None else frozenset({"F.Cu"}),
        rect=(center[0] - pad, center[1] - pad, center[0] + pad, center[1] + pad),
        exact={"center": center, "diameter": diameter},
        slack_mm=(math.sqrt(2.0) - 1.0) * pad,
        margin_mm=_MARGIN,
        label="via",
    )


def _pad_item(rect, net="NET_B", layers=None):
    exp = _MARGIN + _HEADROOM
    return FixedCopperItem(
        kind="pad",
        net=net,
        layers=layers if layers is not None else frozenset({"F.Cu"}),
        rect=(rect[0] - exp, rect[1] - exp, rect[2] + exp, rect[3] + exp),
        exact={"rect": rect},
        slack_mm=(math.sqrt(2.0) - 1.0) * exp,
        margin_mm=_MARGIN,
        label="pad",
    )


def _zone_item(polygon, net="NET_B", layers=None):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    exp = _MARGIN + _HEADROOM
    edges = _rectilinear_convex_edges(polygon, _MARGIN)
    return FixedCopperItem(
        kind="zone",
        net=net,
        layers=layers if layers is not None else frozenset({"F.Cu"}),
        rect=(min(xs) - exp, min(ys) - exp, max(xs) + exp, max(ys) + exp),
        exact={"polygon": list(polygon)},
        slack_mm=float("inf"),
        margin_mm=_MARGIN,
        label="zone",
        edges=edges,
    )


def _load_real_board():
    """Parse the production board, skipping when unavailable (run `make
    netlist` first) -- mirrors test_domain_clearance's fixture convention."""
    if not _PCB_PATH.exists():
        pytest.skip(f"production board {_PCB_PATH} not available")
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(_PCB_PATH)


# ---------------------------------------------------------------------------
# Group 1: the generator is not vacuous
# ---------------------------------------------------------------------------


class TestGeneratorNotVacuous:
    def test_real_board_produces_items_and_pads(self) -> None:
        pr = _load_real_board()
        free = {"K2", "K3", "C27"}
        pads = build_free_component_pads(pr.netlist, free)
        items = build_fixed_copper_items(pr, pr.netlist, free)
        assert set(pads) == free
        assert all(len(ps) >= 2 for ps in pads.values())
        assert len(items) > 1000, (
            "Falsifier fired: the production board's fixed-copper obstacle "
            "list collapsed -- the generator is inspecting nothing."
        )
        kinds = {i.kind for i in items}
        assert {"segment", "via", "zone", "pad"} <= kinds

    def test_k3_has_all_layer_tht_pads(self) -> None:
        pr = _load_real_board()
        pads = build_free_component_pads(pr.netlist, {"K3"})
        assert pads["K3"], "K3 has no pads -- the constraint would be vacuous"
        for pad in pads["K3"]:
            assert pad.layers == COPPER_LAYERS, (
                "K3 pads are THT and must be obstacles on ALL four copper layers"
            )


# ---------------------------------------------------------------------------
# Group 2: item building -- frames, filtering, switches
# ---------------------------------------------------------------------------


class TestItemBuilding:
    def _pr(self, traces=None, vias=None, zones=None, origin=(0.0, 0.0)):
        board = Board(width=100.0, height=100.0, origin=origin, zones=zones or [])
        netlist = Netlist(
            components=[
                Component(
                    ref="U1",
                    footprint="t",
                    bounds=(2.0, 2.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="NET_A",
                              width=1.0, height=1.0, shape="rect", layer="F.Cu")],
                    initial_position=(10.0, 10.0),
                    initial_rotation=0,
                )
            ],
            nets=[Net(name="NET_A", pins=[("U1", "1")])],
        )
        return SimpleNamespace(traces=traces or [], vias=vias or [], board=board), netlist

    def test_traces_are_origin_normalized(self) -> None:
        """The parser leaves traces in raw board coordinates; the solver
        frame is origin-subtracted. Items must be normalized."""
        tr = TraceData(start=(25.0, 25.0), end=(25.0, 35.0), width=0.2, layer="F.Cu", net="NET_B")
        pr, netlist = self._pr(traces=[tr], origin=(20.0, 20.0))
        items = build_fixed_copper_items(pr, netlist, {"U1"})
        [item] = [i for i in items if i.kind == "segment"]
        # Raw (25,25)-(25,35) minus origin (20,20) -> (5,5)-(5,15), width 0.2.
        assert item.exact["p0"] == (5.0, 5.0)
        assert item.exact["p1"] == (5.0, 15.0)
        expected = (5.0 - 0.1 - _MARGIN - _HEADROOM, 5.0 - 0.1 - _MARGIN - _HEADROOM,
                    5.0 + 0.1 + _MARGIN + _HEADROOM, 15.0 + 0.1 + _MARGIN + _HEADROOM)
        assert item.rect == pytest.approx(expected, abs=1e-9)

    def test_same_net_trace_is_not_an_obstacle_for_the_pad_net(self) -> None:
        """A pad on NET_A must not be blocked by NET_A copper (its own
        future connection). The per-pair net filter lives at encode time, so
        the item is still built but the audit skips it."""
        tr = TraceData(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="F.Cu", net="NET_A")
        pr, netlist = self._pr(traces=[tr])
        pads = build_free_component_pads(netlist, {"U1"})
        items = build_fixed_copper_items(pr, netlist, {"U1"})
        violations = audit_fixed_copper(pads, items, {"U1": (10.0, 10.0)}, {"U1": 0})
        assert violations == [], (
            "U1's own-net trace was treated as an obstacle -- the same-net "
            "skip rule is broken (a pad landing on its own net's copper is "
            "the intended connection, not a short)."
        )

    def test_layer_filter_drops_non_copper_and_disjoint_layers(self) -> None:
        pr, netlist = self._pr(
            traces=[TraceData(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="B.Cu", net="NET_B")]
        )
        # U1's pad is F.Cu-only; the B.Cu trace shares no layer -> not an
        # obstacle for it.
        items = build_fixed_copper_items(pr, netlist, {"U1"})
        assert len(items) == 1 and items[0].kind == "segment"
        pads = build_free_component_pads(netlist, {"U1"})
        violations = audit_fixed_copper(pads, items, {"U1": (0.0, 0.0)}, {"U1": 0})
        assert violations == []

    def test_include_other_pads_switch(self) -> None:
        """With include_other_pads=True a pinned component's pad is an
        obstacle; with False it is not."""
        other = Component(
            ref="U2",
            footprint="t",
            bounds=(2.0, 2.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="NET_C",
                      width=1.0, height=1.0, shape="rect", layer="F.Cu")],
            initial_position=(5.0, 5.0),
            initial_rotation=0,
        )
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])
        netlist = Netlist(
            components=[
                Component(ref="U1", footprint="t", bounds=(2.0, 2.0),
                          pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="NET_A",
                                    width=1.0, height=1.0, shape="rect", layer="F.Cu")],
                          initial_position=(10.0, 10.0), initial_rotation=0),
                other,
            ],
            nets=[Net(name="NET_A", pins=[("U1", "1")]), Net(name="NET_C", pins=[("U2", "1")])],
        )
        pr = SimpleNamespace(traces=[], vias=[], board=board)
        with_pads = build_fixed_copper_items(pr, netlist, {"U1"}, include_other_pads=True)
        without = build_fixed_copper_items(pr, netlist, {"U1"}, include_other_pads=False)
        assert sum(1 for i in with_pads if i.kind == "pad") == 1
        assert sum(1 for i in without if i.kind == "pad") == 0

    def test_degenerate_segment_is_encoded_as_disc(self) -> None:
        tr = TraceData(start=(3.0, 3.0), end=(3.0, 3.0), width=0.4, layer="F.Cu", net="NET_B")
        pr, netlist = self._pr(traces=[tr])
        items = build_fixed_copper_items(pr, netlist, {"U1"})
        [item] = items
        # Zero-length segment -> box of the endpoint expanded by w/2 + m + headroom.
        assert item.rect == pytest.approx(
            (3.0 - 0.2 - _MARGIN - _HEADROOM, 3.0 - 0.2 - _MARGIN - _HEADROOM,
             3.0 + 0.2 + _MARGIN + _HEADROOM, 3.0 + 0.2 + _MARGIN + _HEADROOM),
            abs=1e-9,
        )
        # The exact oracle treats it as a disc centred at the endpoint.
        assert exact_clearance_mm((3.0 - 0.35, 3.0 - 0.35, 3.0 + 0.35, 3.0 + 0.35), item) == 0.0


# ---------------------------------------------------------------------------
# Group 3: R24 item 2 -- BMC-exhaustive soundness sweep
# ---------------------------------------------------------------------------


class TestFixedCopperSoundnessBMC:
    """BMC-exhaustive validation (R24 item 2).

    Falsifier: if this sweep finds ANY (pad size, item, offset, rotation)
    combination where the encoded predicate reports "clear" but the exact
    oracle reports a clearance below the margin, the soundness proof in
    ``fixed_copper.py``'s module docstring is false and this test must fail.
    The second sweep bounds the conservatism: encoded-overlap cases must not
    exceed the documented per-kind slack.
    """

    _PAD_SIZES = [
        (0.0, 0.0),  # degenerate point pad (clamped in the encoder)
        (1.0, 1.0),
        (3.0, 2.0),  # elongated
    ]
    _ROTS = (0, 1, 2, 3)

    def _cases(self):
        """(pad, item) pairs covering every item kind with exact geometry."""
        items = [
            _segment_item((0.0, 0.0), (4.0, 0.0), width=0.3),          # horizontal
            _segment_item((0.0, 0.0), (0.0, 4.0), width=0.3),          # vertical
            _segment_item((0.0, 0.0), (4.0, 3.0), width=0.5),          # diagonal
            _segment_item((2.0, 2.0), (2.0, 2.0), width=0.5),          # degenerate
            _via_item((2.0, 2.0), diameter=0.8),
            _pad_item((1.0, 1.0, 3.0, 3.0)),
            _zone_item([(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)]),  # L
        ]
        for (w, h), item, rot in itertools.product(self._PAD_SIZES, items, self._ROTS):
            half = (w / 2, h / 2)
            yield _pad(half=half), item, rot

    def test_soundness_zero_counterexamples(self) -> None:
        checked = 0
        counterexamples = []
        # The exact oracle computes distance with float arithmetic; a pad
        # edge EXACTLY at the margin boundary (clearance == margin, which is
        # allowed) can compute to margin - ~1e-16 (e.g. 0.45 - 0.4 =
        # 0.04999999999999993). The soundness claim is clearance >= margin;
        # assert with a tolerance far below the 0.01mm model grid so a real
        # violation (>= 0.01mm below margin) still fails loudly while a
        # float-eps boundary touch is not miscounted.
        eps = 1e-9
        # Window centred on the item, covering touching/overlapping/clear at
        # 0.9x/1.0x/1.1x margin and well beyond.
        steps = [x * 0.05 for x in range(-60, 61)]  # -3.0..+3.0 mm, 0.05 mm steps
        for pad, item, rot in self._cases():
            for dx, dy in itertools.product(steps, steps):
                center = (float(dx), float(dy))
                # ENCODED predicate: the pad rect exactly as the CP-SAT
                # encoder represents it (half-extents clamped to 0.01 mm,
                # mirroring _pad_rotation_tables_with). The exact oracle
                # below measures the pad's TRUE geometry. Evaluating the
                # encoded predicate against the raw (unclamped) rect would
                # let a degenerate point pad sit at exactly the margin
                # distance and wrongly report a counterexample the real
                # encoder rejects (see encoded_pad_world_rect docstring).
                erect = encoded_pad_world_rect(pad, center, rot)
                if encoded_overlap(erect, item):
                    continue  # covered by the slack sweep
                checked += 1
                rect = pad_world_rect(pad, center, rot)
                if exact_clearance_mm(rect, item) < item.margin_mm - eps:
                    counterexamples.append((pad, item, rot, center))
                    if len(counterexamples) >= 5:
                        break
            if len(counterexamples) >= 5:
                break
        assert checked > 100_000, "sweep collapsed to a trivial size -- not exhaustive enough"
        assert counterexamples == [], (
            f"Soundness FALSIFIED: {len(counterexamples)} case(s) where the encoded "
            f"predicate claimed 'clear' but the exact oracle measured a clearance "
            f"below the {_MARGIN}mm margin. First: {counterexamples[:2]}"
        )

    def test_conservatism_within_documented_slack(self) -> None:
        """Encoded-overlap cases that the exact geometry still accepts must
        have a true clearance no more than the documented slack ABOVE the
        margin (the bbox corner overhang). Genuine shorts (exact clearance
        below the margin) are correct rejections, not conservatism, and are
        not counted. Zones are excluded -- documented as a future
        tightening."""
        steps = [x * 0.05 for x in range(-60, 61)]
        worst = {}  # kind -> max excess observed
        violations = []
        for pad, item, rot in self._cases():
            if item.kind == "zone":
                continue
            for dx, dy in itertools.product(steps, steps):
                center = (float(dx), float(dy))
                erect = encoded_pad_world_rect(pad, center, rot)
                if not encoded_overlap(erect, item):
                    continue
                rect = pad_world_rect(pad, center, rot)
                exact = exact_clearance_mm(rect, item)
                if exact < item.margin_mm:
                    continue  # genuine short -- correct rejection
                excess = exact - item.margin_mm
                worst[item.kind] = max(worst.get(item.kind, 0.0), excess)
                tol = 1e-9
                if excess > item.slack_mm + tol:
                    violations.append((item.kind, excess, item.slack_mm, pad, item, rot, center))
                    if len(violations) >= 5:
                        break
            if len(violations) >= 5:
                break
        assert violations == [], (
            f"Conservatism bound violated: {len(violations)} case(s) where the "
            f"observed excess clearance exceeded the documented slack. "
            f"First: {violations[:2]}"
        )
        # The sweep must actually exercise the corner region (excess > 0) for
        # at least the segment/via/pad kinds, or the bound check is vacuous.
        assert any(w > 1e-6 for w in worst.values()), (
            "Slack sweep never exercised a bbox corner -- vacuous conservatism check"
        )

    def test_sweep_is_not_trivially_all_clear_or_all_overlapping(self) -> None:
        pad = _pad(half=(0.5, 0.5))
        item = _segment_item((0.0, 0.0), (4.0, 0.0), width=0.3)
        outcomes = {
            encoded_overlap(pad_world_rect(pad, (float(dx), 0.0), 0), item)
            for dx in range(-20, 21)
        }
        assert outcomes == {True, False}, (
            "BMC sweep is vacuous -- encoded_overlap never varies across offsets"
        )


class TestZonePolygonExactBMC:
    """R24 item-2 for the polygon-exact zone encoding: the encoded predicate
    (per-edge half-plane separation) must agree EXACTLY with the shapely
    polygon oracle for convex rectilinear zones -- no false clears (sound)
    and no false overlaps (exact, not conservative). The non-convex case
    falls back to the bbox (sound superset), tested separately.
    """

    # Convex axis-aligned polygons (clockwise and counter-clockwise).
    _CONVEX = [
        # unit square, CCW
        [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        # rectangle, CW
        [(0.0, 0.0), (0.0, 3.0), (5.0, 3.0), (5.0, 0.0)],
        # 8-gon: axis-aligned rectangle with subdivided edges (all turns
        # same direction -- genuinely convex with >4 vertices)
        [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (4.0, 2.0), (4.0, 4.0), (2.0, 4.0), (0.0, 4.0), (0.0, 2.0)],
    ]
    # Non-convex rectilinear (L-shape) -> bbox fallback (edges is None).
    _NONCONVEX = [
        [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)],
    ]
    _PAD_HALVES = [(0.0, 0.0), (0.5, 0.5), (1.5, 1.0)]
    _ROTS = (0, 1, 2, 3)

    def test_convex_rectilinear_zones_are_exact(self) -> None:
        steps = [x * 0.25 for x in range(-20, 41)]  # -5.0..+10.0 mm
        checked = 0
        mismatches = []
        for poly in self._CONVEX:
            item = _zone_item(poly)
            assert item.edges is not None, f"convex polygon got no edges: {poly}"
            for (w, h), rot in itertools.product(self._PAD_HALVES, self._ROTS):
                pad = _pad(half=(w, h))
                for dx, dy in itertools.product(steps, steps):
                    center = (float(dx), float(dy))
                    rect = pad_world_rect(pad, center, rot)
                    encoded = encoded_overlap(rect, item)
                    exact = exact_clearance_mm(rect, item) < item.margin_mm
                    checked += 1
                    if encoded != exact:
                        mismatches.append((poly, (w, h), rot, center, encoded, exact))
                        if len(mismatches) >= 5:
                            break
                if len(mismatches) >= 5:
                    break
            if len(mismatches) >= 5:
                break
        assert checked > 50_000, f"sweep collapsed: {checked}"
        assert mismatches == [], (
            f"Zone polygon-exact encoding FALSIFIED: {len(mismatches)} case(s) "
            f"where encoded != exact oracle. First: {mismatches[:2]}"
        )

    def test_nonconvex_falls_back_to_bbox_still_sound(self) -> None:
        steps = [x * 0.25 for x in range(-20, 41)]
        checked = 0
        unsound = []
        for poly in self._NONCONVEX:
            item = _zone_item(poly)
            assert item.edges is None, "non-convex polygon must keep bbox fallback"
            for (w, h), rot in itertools.product(self._PAD_HALVES, self._ROTS):
                pad = _pad(half=(w, h))
                for dx, dy in itertools.product(steps, steps):
                    center = (float(dx), float(dy))
                    rect = pad_world_rect(pad, center, rot)
                    if not encoded_overlap(rect, item):
                        checked += 1
                        exact = exact_clearance_mm(rect, item)
                        if exact < item.margin_mm:
                            unsound.append((poly, (w, h), rot, center, exact))
                            if len(unsound) >= 5:
                                break
                if len(unsound) >= 5:
                    break
            if len(unsound) >= 5:
                break
        assert checked > 5_000, "non-convex bbox sweep collapsed"
        assert unsound == [], (
            f"bbox fallback UNSOUND: {len(unsound)} encoded-clear but exact-below-margin"
        )

    def test_edges_helper_classifies_convex_vs_not(self) -> None:
        assert _rectilinear_convex_edges([(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)], 0.05) is not None
        assert _rectilinear_convex_edges([(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)], 0.05) is None
        # diagonal edge -> bbox fallback
        assert _rectilinear_convex_edges([(0.0, 0.0), (4.0, 1.0), (4.0, 4.0), (0.0, 4.0)], 0.05) is None


# ---------------------------------------------------------------------------
# Group 4: R24 item 3 -- post-solve audit
# ---------------------------------------------------------------------------


class TestPostSolveAudit:
    def test_clean_placement_has_no_violations(self) -> None:
        pads = {"U1": [_pad(center=(0.0, 0.0), half=(0.5, 0.5))]}
        item = _segment_item((0.0, 0.0), (4.0, 0.0), width=0.3)  # y in [-0.2, 0.2]
        # Pad at (2, 3): rect y in [2.5, 3.5], clears the segment by ~2.3mm.
        violations = audit_fixed_copper(pads, [item], {"U1": (2.0, 3.0)}, {"U1": 0})
        assert violations == []

    def test_broken_placement_is_caught(self) -> None:
        """The audit must not trust the solver: a resolved placement that
        actually overlaps a different-net track must be flagged."""
        pads = {"U1": [_pad(center=(0.0, 0.0), half=(0.5, 0.5))]}
        item = _segment_item((0.0, 0.0), (4.0, 0.0), width=0.3)
        # Pad centred on the track -> real short.
        violations = audit_fixed_copper(pads, [item], {"U1": (2.0, 0.0)}, {"U1": 0})
        assert len(violations) == 1
        v = violations[0]
        assert v.ref == "U1"
        assert v.item_kind == "segment"
        assert v.actual_mm == 0.0

    def test_missing_resolved_position_is_flagged_not_silently_skipped(self) -> None:
        pads = {"U1": [_pad(center=(0.0, 0.0))]}
        violations = audit_fixed_copper(pads, [], {}, {})
        assert len(violations) == 1
        assert "missing resolved position" in violations[0].reason

    def test_same_net_item_is_ignored(self) -> None:
        pads = {"U1": [_pad(center=(0.0, 0.0), half=(0.5, 0.5), net="NET_A")]}
        item = _segment_item((0.0, 0.0), (4.0, 0.0), width=0.3, net="NET_A")
        violations = audit_fixed_copper(pads, [item], {"U1": (2.0, 0.0)}, {"U1": 0})
        assert violations == []

    def test_disjoint_layers_are_ignored(self) -> None:
        pads = {"U1": [_pad(center=(0.0, 0.0), half=(0.5, 0.5), layers=frozenset({"F.Cu"}))]}
        item = _segment_item((0.0, 0.0), (4.0, 0.0), width=0.3, layers=frozenset({"B.Cu"}))
        violations = audit_fixed_copper(pads, [item], {"U1": (2.0, 0.0)}, {"U1": 0})
        assert violations == []


# ---------------------------------------------------------------------------
# Group 5: fail-capable solve-level test
# ---------------------------------------------------------------------------


class TestFailCapableSolve:
    """A placement whose pad sits on a different-net track must be rejected
    by the solver (infeasible), and a clear placement accepted."""

    @staticmethod
    def _synthetic():
        pins = [
            Pin(name="1", number="1", position=(0.0, 0.0), net="NET_A",
                width=1.0, height=1.0, shape="rect", layer="all", is_pth=True)
        ]
        comp = Component(ref="U1", footprint="t", bounds=(2.0, 2.0), pins=pins,
                         initial_position=(6.0, 8.0), initial_rotation=0)
        netlist = Netlist(components=[comp], nets=[Net(name="NET_A", pins=[("U1", "1")])])
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])
        tr = TraceData(start=(5.0, 5.0), end=(7.0, 5.0), width=0.2, layer="F.Cu", net="NET_B")
        parse_result = SimpleNamespace(traces=[tr], vias=[], board=board)
        fc = {"parse_result": parse_result, "free_refs": {"U1"}, "margin_mm": _MARGIN}
        return netlist, board, fc

    def test_bad_placement_is_rejected(self) -> None:
        netlist, board, fc = self._synthetic()
        # Pad centred at (6,5) sits on the NET_B track (y=5, w=0.2).
        result = solve_placement(
            netlist=netlist, board=board, timeout_ms=10_000,
            fixed_positions={"U1": (6.0, 5.0, 0)}, fixed_copper=fc,
        )
        assert result.status == "infeasible"
        names = [u.get("name", "?") for u in result.unsat_core]
        assert any(n.startswith("fixed_copper_") for n in names), (
            f"bad placement rejected but the unsat core {names} does not name "
            "the fixed-copper assumption -- can't tell which constraint binds"
        )

    def test_good_placement_is_accepted(self) -> None:
        netlist, board, fc = self._synthetic()
        # Pad centred at (6,8) clears the track at y=5.
        result = solve_placement(
            netlist=netlist, board=board, timeout_ms=10_000,
            fixed_positions={"U1": (6.0, 8.0, 0)}, fixed_copper=fc,
        )
        assert result.status in ("optimal", "feasible")
        assert result.positions.get("U1") == (6.0, 8.0)
