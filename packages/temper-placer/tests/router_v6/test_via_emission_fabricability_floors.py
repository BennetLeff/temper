"""Two ``router_v6`` paths emit vias as raw s-expression TEXT, bypassing
the Rust ``Via::new`` constructor where the board's fabricability floors
are otherwise enforced. These tests hold each of them to the floors the
repo ALREADY declares -- and pin those floors to their declaring source,
so neither the code nor the constants can drift apart silently.

* ``_zone_pour_stitch._stitch_pads_to_each_other`` -- annular ring.
  Its via pad/drill pair comes from the netclass table with a
  ``0.8``/``0.4`` fallback on a lookup MISS. That fallback is a 0.20mm
  ring against a declared 0.254mm floor. On today's board the only
  ``_CONTINUITY_EXEMPT_NETS`` member resolves to ``HighVoltage``
  (1.2/0.6, a 0.30mm ring), so the sub-floor pair was latent, not live
  -- ``test_the_fallback_pair_is_genuinely_sub_floor`` is the
  anti-vacuity proof that it is nonetheless real, and
  ``test_a_netclass_lookup_miss_still_emits_a_fabricable_via`` drives the
  path that reaches it.

* ``_ground_plane._find_via_drop_point`` -- copper-to-board-edge
  clearance. It tested the bare ``board_polygon.contains(footprint)``, a
  0.0mm margin, while the SAME module holds its pour 1.0mm off the edge.
  Measured on the committed board: 2 of the 66 emitted gnd drop vias sat
  0.094mm and 0.170mm from the outline -- both live
  ``copper_edge_clearance`` errors against the board's declared 0.5mm
  rule, not latent ones.

Neither fix changes a declared threshold. Both make a code path honour a
number the board already publishes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from temper_placer.router_v6 import _ground_plane as gp
from temper_placer.router_v6 import _zone_pour_stitch as zps

REPO_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
PROJECT_FILE = REPO_ROOT / "pcb" / "temper.kicad_pro"

_VIA_AT = re.compile(
    r"\(via \(at ([-\d.]+) ([-\d.]+)\).*?\(size ([\d.]+)\) \(drill ([\d.]+)\)"
)


def _board_rules() -> dict:
    """The board's own declared DRC rules -- the SSOT both fixes defer to."""
    data = json.loads(PROJECT_FILE.read_text())
    return data["board"]["design_settings"]["rules"]


# ---------------------------------------------------------------------------
# The floors are the board's, not this module's
# ---------------------------------------------------------------------------


def test_annular_floor_matches_the_board_project_file():
    """``_MIN_ANNULAR_RING_MM`` is a re-declaration of the board's own
    ``min_via_annular_width``, not an independent number. If the board
    ever changes it, this fails rather than silently enforcing a stale
    figure."""
    assert pytest.approx(
        _board_rules()["min_via_annular_width"]
    ) == zps._MIN_ANNULAR_RING_MM


def test_edge_clearance_floor_matches_the_board_project_file():
    """Same contract for ``COPPER_EDGE_CLEARANCE_MM`` vs the board's
    ``min_copper_edge_clearance``."""
    assert pytest.approx(
        _board_rules()["min_copper_edge_clearance"]
    ) == gp.COPPER_EDGE_CLEARANCE_MM


def test_edge_clearance_is_distinct_from_the_pour_margin():
    """Anti-conflation: the module's own conservative pour shrink
    (1.0mm) and the board's hard DRC rule (0.5mm) are different numbers
    serving different purposes. The fix must not have collapsed one into
    the other."""
    assert pytest.approx(1.0) == gp.BOARD_EDGE_MARGIN_MM
    assert gp.COPPER_EDGE_CLEARANCE_MM < gp.BOARD_EDGE_MARGIN_MM


# ---------------------------------------------------------------------------
# F50a -- annular ring on the stitch via path
# ---------------------------------------------------------------------------


class TestAnnularRingClamp:
    def test_the_fallback_pair_is_genuinely_sub_floor(self):
        """ANTI-VACUITY. The clamp below would prove nothing if the
        literal it guards were already compliant. The ``0.8``/``0.4``
        netclass-miss fallback in ``_stitch_pads_to_each_other`` is a
        0.20mm ring; the floor is 0.254mm."""
        fallback_ring = (0.8 - 0.4) / 2.0
        assert fallback_ring == pytest.approx(0.20)
        assert fallback_ring < zps._MIN_ANNULAR_RING_MM

    def test_sub_floor_pad_is_enlarged_to_the_target_ring(self):
        clamped = zps._annular_ring_clamped_pad(0.8, 0.4)
        assert clamped == pytest.approx(0.4 + 2 * zps._ANNULAR_RING_TARGET_MM)
        assert (clamped - 0.4) / 2.0 >= zps._MIN_ANNULAR_RING_MM

    def test_a_compliant_pair_is_returned_untouched(self):
        """``HighVoltage``'s real 1.2/0.6 pair -- a 0.30mm ring -- must
        pass through byte-identical, so the clamp cannot perturb the
        board's existing via geometry."""
        assert zps._annular_ring_clamped_pad(1.2, 0.6) == pytest.approx(1.2)

    def test_the_clamp_never_touches_the_drill(self):
        """The correction is pad geometry only. This is what keeps it
        independent of the separate open question about which of the
        board's two hole-size numbers is the real drill floor: the clamp
        takes the drill as an input and returns only a pad."""
        for drill in (0.2, 0.3, 0.4, 0.5, 0.6):
            pad = zps._annular_ring_clamped_pad(0.05, drill)
            # The drill is never scaled up to meet any hole-size rule --
            # only the pad grows around whatever drill it was handed.
            assert pad == pytest.approx(drill + 2 * zps._ANNULAR_RING_TARGET_MM)

    @pytest.mark.parametrize("drill", [0.2, 0.3, 0.4, 0.5, 0.6, 0.8])
    @pytest.mark.parametrize("pad_excess", [0.0, 0.05, 0.2, 0.4, 0.507, 0.6, 1.0])
    def test_output_always_clears_the_floor(self, drill, pad_excess):
        """Total function: no (pad, drill) input produces a sub-floor
        ring on the output, including the exact 2 x 0.254 boundary."""
        pad = zps._annular_ring_clamped_pad(drill + pad_excess, drill)
        assert (pad - drill) / 2.0 >= zps._MIN_ANNULAR_RING_MM

    def test_every_live_netclass_survives_the_clamp_unchanged(self):
        """Cross-check against the real table: all 13 classes already sit
        at a 0.30mm ring, so the clamp is a no-op on every one of them.
        A regression in either the table or the clamp shows up here."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        assert TEMPER_NET_CLASSES, "empty netclass table -- test would prove nothing"
        for name, rules in TEMPER_NET_CLASSES.items():
            assert zps._annular_ring_clamped_pad(
                rules.via_diameter, rules.via_drill
            ) == pytest.approx(rules.via_diameter), name


class TestStitchViaEmission:
    """End-to-end through the real emitter, not just the helper."""

    @staticmethod
    def _emit() -> list[str]:
        net = next(iter(zps._CONTINUITY_EXEMPT_NETS))
        # The SMD pad position is the only one that gets a via at all
        # (THT pads already have a plated hole -- see the module's own
        # `needs_via` gate), so it must be in the fixture.
        smd = [
            pos for n, pos in zps._CONTINUITY_EXEMPT_NET_SMD_PAD_POSITIONS if n == net
        ]
        assert smd, "fixture net has no SMD pad -- no via would be emitted"
        verified = zps._CONTINUITY_EXEMPT_NET_VERIFIED_EDGES[net]
        positions = list(dict.fromkeys([p for edge in verified for p in edge]))
        for pos in smd:
            assert pos in positions, "SMD pad missing from the verified edge set"

        segments: list[str] = []
        zps._stitch_pads_to_each_other(
            {net: positions}, segments, {net: 7}, tstamp_counter=[0]
        )
        return [s for s in segments if "(via " in s]

    def test_emits_at_least_one_via(self):
        assert self._emit(), "no via emitted -- the floor tests would be vacuous"

    def test_every_emitted_via_clears_the_annular_floor(self):
        for via in self._emit():
            m = _VIA_AT.search(via)
            assert m, via
            size, drill = float(m.group(3)), float(m.group(4))
            assert (size - drill) / 2.0 >= zps._MIN_ANNULAR_RING_MM, via

    def test_a_netclass_lookup_miss_still_emits_a_fabricable_via(self, monkeypatch):
        """THE REGRESSION GUARD. The sub-floor pair is only reachable via
        the netclass-lookup miss, which today's board never hits because
        its one continuity-exempt net is assigned to ``HighVoltage``. It
        becomes reachable the moment a continuity-exempt net is added
        WITHOUT a netclass assignment. Simulate exactly that.
        """
        from temper_placer.core import design_rules

        net = next(iter(zps._CONTINUITY_EXEMPT_NETS))
        # Drop the assignment -> `rules` is None -> the 0.8/0.4 fallback.
        assignments = dict(design_rules.TEMPER_NET_ASSIGNMENTS)
        assignments.pop(net, None)
        monkeypatch.setattr(design_rules, "TEMPER_NET_ASSIGNMENTS", assignments)

        vias = self._emit()
        assert vias, "the miss path emitted nothing -- guard would be vacuous"
        for via in vias:
            m = _VIA_AT.search(via)
            assert m, via
            size, drill = float(m.group(3)), float(m.group(4))
            # Pre-fix this was 0.8/0.4 -- a 0.20mm ring, unfabricable.
            assert (size - drill) / 2.0 >= zps._MIN_ANNULAR_RING_MM, via
            assert drill == pytest.approx(0.4), "drill must be left alone"
            assert size == pytest.approx(0.4 + 2 * zps._ANNULAR_RING_TARGET_MM)


# ---------------------------------------------------------------------------
# F50b -- board-edge clearance on the gnd drop-via path
# ---------------------------------------------------------------------------


class TestViaDropPointEdgeClearance:
    # A 20x20 square board; a gnd pad 0.6mm in from the left edge, so a
    # 0.5mm-radius via disc centred on it clears the outline by 0.1mm --
    # inside the board (the pre-fix test passes) but far below the
    # board's 0.5mm copper_edge_clearance rule.
    BOARD = Polygon([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)])
    VIA_RADIUS = gp.VIA_SIZE_MM / 2.0
    NEAR_EDGE_PAD = (0.6, 10.0)

    def _drop(self, pad, **kw):
        kw.setdefault("existing_holes", [])
        kw.setdefault("via_radius_mm", self.VIA_RADIUS)
        kw.setdefault("keepout", None)
        kw.setdefault("other_copper", None)
        kw.setdefault("board_polygon", self.BOARD)
        return gp._find_via_drop_point(pad, **kw)

    def test_the_fixture_pad_is_genuinely_inside_the_board(self):
        """ANTI-VACUITY. The pre-fix check -- bare ``contains`` -- accepts
        this point. If it did not, the tests below would prove nothing
        about the margin and everything about the outline."""
        disc = Point(self.NEAR_EDGE_PAD).buffer(self.VIA_RADIUS, quad_segs=12)
        assert self.BOARD.contains(disc)
        gap = self.BOARD.exterior.distance(Point(self.NEAR_EDGE_PAD)) - self.VIA_RADIUS
        assert gap == pytest.approx(0.1)
        assert gap < gp.COPPER_EDGE_CLEARANCE_MM

    def test_pad_centre_is_rejected_and_the_ring_search_relocates_it(self):
        point, needs_stub = self._drop(self.NEAR_EDGE_PAD)
        assert point is not None, "expected the ring search to find a clear point"
        assert needs_stub is True, "a relocated via must be joined by a stub"
        assert point != self.NEAR_EDGE_PAD
        gap = self.BOARD.exterior.distance(Point(point)) - self.VIA_RADIUS
        assert gap >= gp.COPPER_EDGE_CLEARANCE_MM - 1e-9

    def test_the_require_pour_false_fallback_also_honours_the_margin(self):
        """The register located the leak specifically here: with a
        ``pour_region`` given, pass 1 required containment in the pour
        (itself inset from the edge), which masked the missing margin.
        Pass 2 drops that test entirely. Force pass 2 by giving a
        ``pour_region`` that contains nothing near the pad."""
        far_away_pour = Polygon(
            [(15.0, 15.0), (19.0, 15.0), (19.0, 19.0), (15.0, 19.0)]
        )
        point, _ = self._drop(self.NEAR_EDGE_PAD, pour_region=far_away_pour)
        assert point is not None
        assert not far_away_pour.contains(
            Point(point).buffer(self.VIA_RADIUS, quad_segs=12)
        ), "fixture failed to force the require_pour=False fallback"
        gap = self.BOARD.exterior.distance(Point(point)) - self.VIA_RADIUS
        assert gap >= gp.COPPER_EDGE_CLEARANCE_MM - 1e-9

    def test_no_pour_region_at_all_honours_the_margin(self):
        point, _ = self._drop(self.NEAR_EDGE_PAD, pour_region=None)
        assert point is not None
        gap = self.BOARD.exterior.distance(Point(point)) - self.VIA_RADIUS
        assert gap >= gp.COPPER_EDGE_CLEARANCE_MM - 1e-9

    def test_a_pad_in_the_corner_is_relocated_inward_not_emitted_in_place(self):
        """A corner pad is still serviceable -- the ring search walks it
        inward. What must NOT happen is emission at the original,
        edge-violating point."""
        corner_pad = (0.05, 0.05)
        point, needs_stub = self._drop(corner_pad)
        assert point is not None and needs_stub is True
        assert point != corner_pad
        gap = self.BOARD.exterior.distance(Point(point)) - self.VIA_RADIUS
        assert gap >= gp.COPPER_EDGE_CLEARANCE_MM - 1e-9

    def test_fails_closed_when_no_compliant_point_exists(self):
        """When the ring search finds nothing compliant, the function
        must return ``None`` so the caller SKIPS the via -- the module's
        own documented fail-closed discipline. Emitting a known-violating
        via is never the fallback.

        A 1.8mm-wide strip admits a 0.5mm-radius disc (bare ``contains``
        succeeds -- the pre-fix check) but cannot admit one held 0.5mm
        off both edges, which would need 2.0mm.
        """
        strip = Polygon([(0.0, 0.0), (1.8, 0.0), (1.8, 20.0), (0.0, 20.0)])
        pad = (0.9, 10.0)
        # Anti-vacuity: the pre-fix check accepts this point outright.
        assert strip.contains(Point(pad).buffer(self.VIA_RADIUS, quad_segs=12))

        point, needs_stub = self._drop(pad, board_polygon=strip)
        assert point is None
        assert needs_stub is False

    def test_a_via_well_inside_the_board_is_unaffected(self):
        """The margin must not perturb the overwhelming majority of drop
        points, which are nowhere near an edge."""
        centre = (10.0, 10.0)
        assert self._drop(centre) == (centre, False)


@pytest.mark.skipif(
    not PRODUCTION_BOARD.is_file(), reason="production board not present"
)
def test_no_emitted_gnd_drop_via_violates_edge_clearance_on_the_real_board():
    """The measurement, on the committed board, that makes this a real
    fix rather than a hypothetical one.

    Pre-fix (margin 0.0): 66 vias emitted, 2 of them 0.094mm and 0.170mm
    from the outline -- live ``copper_edge_clearance`` errors.
    Post-fix (margin 0.5): 65 vias emitted, 0 violations. One of the two
    was relocated by the ring search to a 0.770mm gap; the other had no
    compliant point and is skipped (fail-closed). Board-wide pad
    connectivity is byte-identical across the two runs -- measured
    separately via ``pad_connectivity_audit``: gnd 5/88 connected in
    both, 70 broken / 60 connected / 9 zone-dependent nets in both.

    Never writes to the board -- reads it only.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.routing_space import _get_board_polygon

    blocks, result = gp.generate_ground_plane_blocks(
        PRODUCTION_BOARD, tstamp_counter=[0]
    )
    outline = _get_board_polygon(parse_kicad_pcb_v6(PRODUCTION_BOARD)).exterior

    vias = [b for b in blocks if _VIA_AT.search(b)]
    assert vias, "no drop vias emitted -- this test would prove nothing"

    offenders = []
    for block in vias:
        m = _VIA_AT.search(block)
        x, y, size = float(m.group(1)), float(m.group(2)), float(m.group(3))
        gap = outline.distance(Point(x, y)) - size / 2.0
        if gap < gp.COPPER_EDGE_CLEARANCE_MM - 1e-9:
            offenders.append(((x, y), gap))
        # The gnd plane's own via template is 1.0/0.4 -- already a 0.30mm
        # ring. Assert it, so this path cannot regress below the annular
        # floor either.
        drill = float(m.group(4))
        assert (size - drill) / 2.0 >= zps._MIN_ANNULAR_RING_MM

    assert not offenders, (
        f"{len(offenders)} of {len(vias)} emitted gnd drop vias sit closer than "
        f"{gp.COPPER_EDGE_CLEARANCE_MM}mm to the board outline: {offenders}"
    )
    assert result.drop_via_count == len(vias)
    # Blast radius, pinned: the margin costs exactly one via relative to
    # the 66 the pre-fix code emitted, and that one was itself illegal.
    assert len(vias) == 65
