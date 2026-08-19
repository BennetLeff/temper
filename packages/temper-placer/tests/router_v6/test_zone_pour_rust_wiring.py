"""Wire-level tests for the Rust zone generator in ``_emit_zone_pours``.

The production emission path now computes every zone outline with
``temper_geometry.pour_outline_py`` (packages/temper-geometry/src/
zone_generator.rs) and emits hole-preserving outlines via
``emit_zone_outline_s_expr_py``.  These tests pin the three measured
defects the wiring closes -- creepage carve (12.6mm not 2.0mm), holes
preserved, honest island policy -- at the production seam, not only in
the Rust unit tests.

See docs/evidence/2026-08-15-rust-zone-pour-design.md and
docs/evidence/2026-08-16-zone-pour-rust-generator.md.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from temper_placer.router_v6._zone_pour_stitch import _emit_zone_pours
from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

NET_RE = re.compile(r'\(net_name "([^"]+)"\)')
POLYGON_RE = re.compile(r"\(polygon\n\s+\(pts")


def _zone_blocks(segments: list[str]) -> list[str]:
    return [s for s in segments if "(zone " in s]


def _polygon_count(block: str) -> int:
    return len(POLYGON_RE.findall(block))


def _rings(block: str) -> list[list[tuple[float, float]]]:
    """Parse every (polygon (pts ...)) ring out of one zone block."""
    rings: list[list[tuple[float, float]]] = []
    for m in POLYGON_RE.finditer(block):
        chunk = block[m.end() :]
        pts = [
            (float(x), float(y))
            for x, y in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", chunk.split("))")[0])
        ]
        rings.append(pts)
    return rings


def _hole_bbox(rings: list[list[tuple[float, float]]]) -> tuple[float, float] | None:
    """Bounding box width/height of the first hole ring, or None."""
    if len(rings) < 2:
        return None
    xs = [p[0] for p in rings[1]]
    ys = [p[1] for p in rings[1]]
    return (max(xs) - min(xs), max(ys) - min(ys))


def _pcb_with_pad(net: str, position: tuple[float, float], layer: str = "F.Cu"):
    """A minimal ParsedPCB-shaped fixture: one component with one pin on
    *layer* at *position* (rotation-quadrant/side defaults = the
    ``initial_rotation_quadrant``/``initial_side`` None path), plus an
    explicit large board outline so hull clipping does not collapse to
    the component's own bounds."""
    from temper_placer.core.netlist import Component, Pin

    comp = Component(
        ref="U1",
        footprint="0805",
        bounds=(2.0, 1.25),
        initial_position=position,
        pins=[
            Pin(
                name="1",
                number="1",
                position=(0.0, 0.0),
                net=net,
                width=2.0,
                height=2.0,
                layer=layer,
            )
        ],
    )
    board = SimpleNamespace(
        outline_polygon=((0.0, 0.0), (120.0, 0.0), (120.0, 120.0), (0.0, 120.0)),
        get_bounds_array=lambda: (0.0, 0.0, 120.0, 120.0),
    )
    return SimpleNamespace(components=[comp], tracks=[], vias=[], board=board)


class TestRustGeneratorIsWiredIntoEmission:
    def test_emitted_zones_are_hole_capable(self):
        """The emitted s-expression carries one (polygon ...) element per
        ring -- exterior first, holes after -- the KiCad format that the
        old single-ring emitter could not express (the 167
        isolated_copper islands root cause)."""
        # A +170V_BUS pad sits INSIDE the AC_L cluster's hull; its
        # creepage halo (12.6mm radius + 1mm half-extent) carves an
        # interior HOLE rather than a boundary bite.
        pcb = _pcb_with_pad("+170V_BUS", (50.0, 50.0))
        segments: list[str] = []
        _emit_zone_pours(
            {"ac_l": [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]},
            segments,
            {"ac_l": 1, "+170V_BUS": 2},
            pcb=pcb,
        )
        blocks = _zone_blocks(segments)
        assert blocks, "expected at least one zone for ac_l"
        # The HV pad's creepage halo is far inside the compact hull, so
        # the carve must produce an interior hole -- i.e. at least one
        # zone carries >= 2 polygons.
        assert any(_polygon_count(b) >= 2 for b in blocks), (
            "expected a hole-carrying zone (interior HV pad at 12.6mm creepage); "
            "got polygon counts: " + str([_polygon_count(b) for b in blocks])
        )

    def test_carve_is_creepage_not_clearance(self):
        """The carve distance is 12.6mm (PD3 creepage), not 2.0mm
        (clearance) -- measured as the difference between a 2.00mm
        violation and a 12.58mm pass on the real board."""
        creepage = default_creepage_table()
        # ACMains-vs-LV in the generated creepage table: 12.6mm.
        assert creepage.required("ACMains", "Power", "Pad") == 12.6

        # A +3V3 (Power) pad at (50, 50) sits inside a diamond-shaped ac_l
        # hull (pads at N/E/S/W).  Carved at 12.6mm the halo (13.6mm
        # radius) cuts a hole ~27mm across; at 2.0mm the hole would be
        # ~6mm.  The emitted hole's bounding box distinguishes the two
        # unambiguously.  ac_l is continuity-exempt (ACMains) so its pour
        # is a single unclustered hull, and KeepAll keeps the piece with
        # the hole.
        pcb = _pcb_with_pad("+3V3", (50.0, 50.0))
        segments: list[str] = []
        _emit_zone_pours(
            {"ac_l": [(50.0, 30.0), (70.0, 50.0), (50.0, 70.0), (30.0, 50.0)]},
            segments,
            {"ac_l": 1, "+3V3": 2},
            pcb=pcb,
        )
        blocks = _zone_blocks(segments)
        assert blocks, "expected an ac_l zone"
        hole_sizes = [_hole_bbox(_rings(b)) for b in blocks]
        assert any(
            sz is not None and sz[0] > 20.0 and sz[1] > 20.0 for sz in hole_sizes
        ), (
            "expected a creepage-sized hole (~27mm bbox, 12.6mm halo x2 + 2mm "
            "pad), got hole bboxes: " + str(hole_sizes)
        )
        # A clearance-sized hole (~6mm bbox at 2.0mm carve) must NOT be
        # present anywhere.
        assert not any(
            sz is not None and 4.0 < sz[0] < 10.0 and 4.0 < sz[1] < 10.0
            for sz in hole_sizes
        ), "found a clearance-sized (2.0mm) carve hole -- creepage not applied"

    def test_ntc_no_fails_honestly_at_pd3(self):
        """power_in.ntc-no's single hull spans the densest region of the
        board; carved at 12.6mm creepage it covers 0/4 pads, so PadsOnly
        must drop every piece -- the honest 'pour infeasible' answer
        instead of 47+ misleading islands."""
        # ntc-no's own pads are all within 12.6mm of an LV (+3V3, Power)
        # obstacle here -- the HV-vs-LV PD3 creepage halo (12.6mm) -- so
        # every carved piece is padless and gets dropped.  The +3V3 pad
        # is declared on every copper layer ("*.Cu", a through-hole pad)
        # so the carve applies on every layer the pour emits to -- on a
        # layer where the obstacle was absent the pour would rightly
        # survive, which is not the failure mode under test.
        pcb = _pcb_with_pad("+3V3", (50.0, 50.0), layer="*.Cu")
        # ntc-no pads clustered around the HV pad, inside its 12.6mm halo.
        positions = [
            (46.0, 46.0),
            (54.0, 46.0),
            (46.0, 54.0),
            (54.0, 54.0),
        ]
        segments: list[str] = []
        _emit_zone_pours(
            {"power_in.ntc-no": positions},
            segments,
            {"power_in.ntc-no": 1, "+170V_BUS": 2},
            pcb=pcb,
        )
        # No zone at all: the carve left nothing that contains an own pad.
        assert _zone_blocks(segments) == []

    def test_own_net_pads_are_not_carved_against(self):
        """A pad of the net being poured never appears in the obstacle
        list -- same-net copper is the pour's own, not foreign."""
        pcb = _pcb_with_pad("ac_l", (50.0, 50.0))
        segments: list[str] = []
        _emit_zone_pours(
            {"ac_l": [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]},
            segments,
            {"ac_l": 1},
            pcb=pcb,
        )
        blocks = _zone_blocks(segments)
        assert blocks, "expected ac_l zone despite its own pad inside the hull"
        # A same-net pad does NOT carve a hole: the zone is a single ring.
        assert all(_polygon_count(b) == 1 for b in blocks), (
            "same-net pad must not appear as an obstacle; "
            "polygon counts: " + str([_polygon_count(b) for b in blocks])
        )


class TestZoneToZoneCreepageIsCarved:
    """Zone-vs-zone was the one obstacle class the carve never covered.

    The reason recorded in ``pair_clearance_keepout``'s docstring was that
    KiCad resolves zone overlap by priority at fill time. Re-measured
    2026-08-19: the filler enforces zone-to-zone CLEARANCE and never
    CREEPAGE, so that reason holds only for clearance-governed pairs. On
    the committed board all 45 under-separated cross-net same-layer pour
    pairs are clearance-governed (0.5/2.0/3.0mm, creepage 0.0), but 13
    creepage-governed pairs also share layers -- HighVoltageTank vs
    HighVoltage, 10.0mm creepage against a 2.0mm clearance -- and they pass
    by 0.3561mm that no code puts there.

    These two tests are the pair that matters: the carve must bite on a
    creepage-governed pair, and must NOT bite on a clearance-governed one
    (removing copper the filler is already correct about is a real cost).
    """

    @staticmethod
    def _pcb_with_pads(pads: dict[str, list[tuple[float, float]]], layer: str = "F.Cu"):
        from temper_placer.core.netlist import Component, Pin

        components = []
        for idx, (net, positions) in enumerate(sorted(pads.items())):
            for jdx, pos in enumerate(positions):
                components.append(
                    Component(
                        ref=f"U{idx}_{jdx}",
                        footprint="0805",
                        bounds=(2.0, 1.25),
                        initial_position=pos,
                        pins=[
                            Pin(
                                name="1",
                                number="1",
                                position=(0.0, 0.0),
                                net=net,
                                width=1.0,
                                height=1.0,
                                layer=layer,
                            )
                        ],
                    )
                )
        board = SimpleNamespace(
            outline_polygon=((0.0, 0.0), (140.0, 0.0), (140.0, 140.0), (0.0, 140.0)),
            get_bounds_array=lambda: (0.0, 0.0, 140.0, 140.0),
        )
        return SimpleNamespace(components=components, tracks=[], vias=[], board=board)

    @staticmethod
    def _min_gap(segments: list[str], net_a: str, net_b: str, layer: str = "F.Cu") -> float:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        def _union(net: str):
            polys = []
            for block in _zone_blocks(segments):
                m = NET_RE.search(block)
                if not m or m.group(1) != net:
                    continue
                if f'(layer "{layer}")' not in block:
                    continue
                rings = _rings(block)
                if not rings or len(rings[0]) < 3:
                    continue
                poly = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3])
                polys.append(poly if poly.is_valid else poly.buffer(0))
            return unary_union(polys) if polys else None

        ua, ub = _union(net_a), _union(net_b)
        assert ua is not None and not ua.is_empty, f"no {net_a} pour emitted"
        assert ub is not None and not ub.is_empty, f"no {net_b} pour emitted"
        return ua.distance(ub)

    # Two squares whose hulls sit ~5mm apart -- closer than the 10.0mm
    # HighVoltageTank-vs-HighVoltage creepage figure, and closer than the
    # 2.0mm HighVoltage-vs-HighVoltage clearance figure is wide.
    _A = [(30.0, 30.0), (45.0, 30.0), (45.0, 45.0), (30.0, 45.0)]
    _B = [(50.0, 30.0), (65.0, 30.0), (65.0, 45.0), (50.0, 45.0)]

    def test_a_creepage_governed_pair_is_pushed_apart(self):
        """`tank.c_tank1-p2` is HighVoltageTank, `w1_1` is HighVoltage:
        clearance 2.0mm, creepage 10.0mm. Nothing but the outline can hold
        the 10.0mm, because the filler never checks creepage."""
        from temper_placer.router_v6.zone_pour_clearance import default_table
        from temper_placer.router_v6.zone_pour_creepage import (
            default_creepage_table as _creep,
        )

        assert default_table().required("HighVoltageTank", "HighVoltage", "Zone") == 2.0
        assert _creep().required("HighVoltageTank", "HighVoltage", "Zone") == 10.0

        pads = {"tank.c_tank1-p2": self._A, "w1_1": self._B}
        segments: list[str] = []
        _emit_zone_pours(
            pads,
            segments,
            {"tank.c_tank1-p2": 1, "w1_1": 2},
            pcb=self._pcb_with_pads(pads),
        )
        gap = self._min_gap(segments, "tank.c_tank1-p2", "w1_1")
        assert gap >= 10.0 - 1e-6, (
            f"creepage-governed pour pair emitted {gap:.4f}mm apart, needs 10.0mm"
        )

    def test_a_clearance_governed_pair_is_left_to_the_filler(self):
        """`+170V_BUS` and `hb-gnd` are both HighVoltage: 2.0mm clearance,
        0.0mm creepage. KiCad's filler clips the lower-priority pour back
        off the higher-priority one, so carving here would only destroy
        copper. The outlines must be left overlapping/touching."""
        from temper_placer.router_v6.zone_pour_creepage import (
            default_creepage_table as _creep,
        )

        assert _creep().required("HighVoltage", "HighVoltage", "Zone") == 0.0

        pads = {"+170V_BUS": self._A, "hb-gnd": self._B}
        segments: list[str] = []
        _emit_zone_pours(
            pads,
            segments,
            {"+170V_BUS": 1, "hb-gnd": 2},
            pcb=self._pcb_with_pads(pads),
        )
        gap = self._min_gap(segments, "+170V_BUS", "hb-gnd")
        assert gap < 10.0, (
            f"a clearance-governed pair was carved apart to {gap:.4f}mm -- the "
            "carve must not remove copper the filler already governs"
        )
