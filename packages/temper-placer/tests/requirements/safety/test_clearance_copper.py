"""Unit tests for the copper-to-copper clearance/creepage measurement.

REQ-SAFE-01's checker used to measure the straight line between component
*origins*. Copper extends outward from an origin, so that figure is an upper
bound on true copper-to-copper separation -- optimistic, in the unsafe
direction, on every pair it ever reported. These tests pin the corrected
behaviour: shape-aware, rotation-aware, exact.

Every expected number below is derived by hand from the pad geometry in the
test itself, so a test that agrees with the implementation is agreeing with
arithmetic, not with itself.
"""

from __future__ import annotations

import logging
import math

import pytest

from tests.requirements.validators.clearance import (
    CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND,
    CREEPAGE_MODEL_UNBROKEN_SURFACE,
    InsulationType,
    VoltageDomain,
    check_creepage_path,
    check_domain_clearance,
    format_clearance_report,
    verify_iec60335_compliance,
)

HV = "N_HV"
LV = "N_LV"

_NETS = {
    HV: {"domain": VoltageDomain.DC_BUS},
    LV: {"domain": VoltageDomain.LV_CONTROL},
}


def _pad(net, offset, width, height, shape, number="1", roundrect_ratio=0.25, pad_rot=0.0):
    return {
        "number": number,
        "net": net,
        "offset": offset,
        "width": width,
        "height": height,
        "shape": shape,
        "roundrect_ratio": roundrect_ratio,
        "pad_rotation_deg": pad_rot,
    }


def _comp(ref, position, pads, rotation_deg=0.0):
    return {
        "ref": ref,
        "position": position,
        "rotation_deg": rotation_deg,
        "nets": sorted({p["net"] for p in pads if p["net"]}),
        "pads": pads,
    }


def _placement(components, cutouts=None):
    out = {"components": components, "nets": _NETS}
    if cutouts is not None:
        out["board"] = {"surface_cutouts": cutouts}
    return out


def _measure(components, cutouts=None, min_mm=1000.0):
    """Run a clearance check guaranteed to violate, and return the measurement."""
    result = check_domain_clearance(
        _placement(components, cutouts),
        VoltageDomain.DC_BUS,
        VoltageDomain.LV_CONTROL,
        min_mm=min_mm,
    )
    assert len(result.violations) == 1, result.violations
    return result.violations[0]


# =============================================================================
# The defect itself: origin distance vs copper distance
# =============================================================================


class TestOriginVsCopper:
    def test_copper_distance_is_far_smaller_than_origin_distance(self):
        """The regression this whole change exists to prevent.

        Two 8x8mm rect pads at +/-2.5mm from their own origins (this is R30's
        real ``lib:LitzPad_15A`` geometry) sit 20mm apart origin-to-origin.
        Each part's copper reaches 2.5 + 4.0 = 6.5mm toward the other, so the
        true gap is 20 - 6.5 - 6.5 = 7.0mm. The old checker reported 20mm --
        13mm of margin that does not exist.
        """
        a = _comp("A", (0.0, 0.0), [_pad(HV, (2.5, 0.0), 8.0, 8.0, "rect")])
        b = _comp("B", (20.0, 0.0), [_pad(LV, (-2.5, 0.0), 8.0, 8.0, "rect")])

        origin_distance = math.dist((0.0, 0.0), (20.0, 0.0))
        assert origin_distance == pytest.approx(20.0)

        v = _measure([a, b])
        assert v.measured_mm == pytest.approx(7.0, abs=1e-9)
        assert v.geometry_model == "copper"
        # The margin the old model invented, quantified.
        assert origin_distance - v.measured_mm == pytest.approx(13.0, abs=1e-9)

    def test_pair_that_passes_on_origins_and_fails_on_copper(self):
        """Same geometry, a 10mm requirement: origin distance clears it by
        10mm; real copper misses it by 3mm. A checker measuring origins
        reports nothing at all here."""
        a = _comp("A", (0.0, 0.0), [_pad(HV, (2.5, 0.0), 8.0, 8.0, "rect")])
        b = _comp("B", (20.0, 0.0), [_pad(LV, (-2.5, 0.0), 8.0, 8.0, "rect")])
        result = check_domain_clearance(
            _placement([a, b]), VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, min_mm=10.0
        )
        assert not result.passed
        assert result.violations[0].measured_mm == pytest.approx(7.0, abs=1e-9)

    def test_missing_pad_geometry_falls_back_to_origins_and_says_so(self, caplog):
        """The fallback is allowed (synthetic placements carry no pads) but
        must never be silent: it is the old, optimistic model."""
        a = {"ref": "A", "position": (0.0, 0.0), "nets": [HV]}
        b = {"ref": "B", "position": (5.0, 0.0), "nets": [LV]}
        with caplog.at_level(logging.WARNING):
            v = _measure([a, b])
        assert v.geometry_model == "origin"
        assert v.measured_mm == pytest.approx(5.0)
        assert "ORIGIN-TO-ORIGIN" in v.message
        assert any("optimistic" in r.getMessage() for r in caplog.records)


# =============================================================================
# Shape correctness -- all four KiCad pad shapes
# =============================================================================


class TestPadShapes:
    """One 10mm origin separation, one 4x2mm pad per side, four shapes.

    Each shape's half-extent along the X axis (the separation axis) differs,
    and so must the reported gap. Hand-derivation per case is in the test.
    """

    @pytest.mark.parametrize(
        "shape,expected_gap,why",
        [
            # rect 4x2: half-extent on X is 2.0 -> 10 - 2 - 2 = 6.0
            ("rect", 6.0, "sharp corners, half-width 2.0 each side"),
            # oval 4x2: r = min(4,2)/2 = 1.0, core 2x0 -> half-extent on X is
            # 1.0 + 1.0 = 2.0, identical to rect ON THIS AXIS -> 6.0
            ("oval", 6.0, "stadium: core half-width 1.0 + corner r 1.0 = 2.0"),
            # roundrect 4x2 @0.25: r = 0.25*2 = 0.5, core 3x1 -> half-extent
            # on X is 1.5 + 0.5 = 2.0 -> 6.0 (the r terms cancel on-axis)
            ("roundrect", 6.0, "corner r cancels on-axis: 1.5 + 0.5 = 2.0"),
            # circle 4x4 (width==height forced below): r = 2.0 -> 6.0
            ("circle", 6.0, "radius 2.0 each side"),
        ],
    )
    def test_on_axis_half_extent_per_shape(self, shape, expected_gap, why):
        h = 4.0 if shape == "circle" else 2.0
        a = _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 4.0, h, shape)])
        b = _comp("B", (10.0, 0.0), [_pad(LV, (0.0, 0.0), 4.0, h, shape)])
        v = _measure([a, b])
        assert v.measured_mm == pytest.approx(expected_gap, abs=1e-9), why

    @pytest.mark.parametrize(
        "shape,expected_gap",
        [
            # Separation along Y now, where the shapes genuinely differ.
            # rect 4x2: half-height 1.0 -> 10 - 1 - 1 = 8.0
            ("rect", 8.0),
            # oval 4x2: core 2x0, r=1.0 -> half-height 0 + 1.0 = 1.0 -> 8.0
            ("oval", 8.0),
            # roundrect 4x2 @0.25: core 3x1, r=0.5 -> 1.0 + ... on-axis the
            # r cancels: core half-height 0.5 + 0.5 = 1.0 -> 8.0
            ("roundrect", 8.0),
        ],
    )
    def test_short_axis_half_extent_per_shape(self, shape, expected_gap):
        a = _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 4.0, 2.0, shape)])
        b = _comp("B", (0.0, 10.0), [_pad(LV, (0.0, 0.0), 4.0, 2.0, shape)])
        v = _measure([a, b])
        assert v.measured_mm == pytest.approx(expected_gap, abs=1e-9)

    def test_rect_corner_reaches_further_than_a_circle_of_the_same_size(self):
        """The specific error the pre-#388 ``max(w,h)/2`` circle model made:
        a square's corner lies outside its inscribed circle.

        Two 8x8 rect pads offset diagonally by (10, 10): the corner-to-corner
        gap is ``hypot(10,10) - hypot(4,4) - hypot(4,4)`` = 14.142 - 5.657 -
        5.657 = 2.828mm. A circle model of radius 4.0 would have said
        14.142 - 4 - 4 = 6.142mm -- 3.3mm of margin that is not there.
        """
        a = _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 8.0, 8.0, "rect")])
        b = _comp("B", (10.0, 10.0), [_pad(LV, (0.0, 0.0), 8.0, 8.0, "rect")])
        v = _measure([a, b])
        expected = math.hypot(10.0, 10.0) - 2 * math.hypot(4.0, 4.0)
        assert v.measured_mm == pytest.approx(expected, abs=1e-9)
        assert v.measured_mm == pytest.approx(2.828, abs=1e-3)

    def test_overlapping_copper_reports_zero_not_negative(self):
        a = _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 8.0, 8.0, "rect")])
        b = _comp("B", (2.0, 0.0), [_pad(LV, (0.0, 0.0), 8.0, 8.0, "rect")])
        v = _measure([a, b])
        assert v.measured_mm == 0.0


# =============================================================================
# Rotation
# =============================================================================


class TestRotation:
    def test_rotated_footprint_moves_its_pads(self):
        """A pad 3mm along the component's local +X, on a component rotated
        90 degrees, ends up 3mm along world +Y -- so it no longer approaches
        the neighbour sitting on the world +X axis.

        Unrotated: A's pad is at x=+3 with half-width 0.5, B's pad at x=10
        with half-width 0.5 -> gap 10 - 3.5 - 0.5 = 6.0.
        Rotated 90: A's pad is at (0, 3); distance from (0,3) to (10,0) is
        hypot(10,3) = 10.440; the pads are axis-aligned rectangles so the
        exact gap is larger than 6.0 and must be reported as such.
        """
        pads_a = [_pad(HV, (3.0, 0.0), 1.0, 1.0, "rect")]
        b = _comp("B", (10.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")])

        flat = _measure([_comp("A", (0.0, 0.0), pads_a, rotation_deg=0.0), b])
        assert flat.measured_mm == pytest.approx(6.0, abs=1e-9)

        turned = _measure([_comp("A", (0.0, 0.0), pads_a, rotation_deg=90.0), b])
        assert turned.measured_mm > flat.measured_mm
        # Pad A centre is now (0,3), pad B centre (10,0); both 1x1 axis-aligned
        # in their own frames but A is rotated 90 (still axis-aligned).
        # Closest points: A's corner (0.5, 2.5), B's corner (9.5, 0.5).
        assert turned.measured_mm == pytest.approx(math.hypot(9.0, 2.0), abs=1e-9)

    def test_pad_intrinsic_rotation_is_honoured_on_top_of_the_footprint(self):
        """KiCad pads may carry their own ``(at x y angle)``. A 4x1 pad
        rotated 90 degrees about its own centre presents its 1mm side, not
        its 4mm side, to a neighbour on the X axis.

        Unrotated: 10 - 2.0 - 0.5 = 7.5. Pad-rotated 90: 10 - 0.5 - 0.5 = 9.0.
        """
        b = _comp("B", (10.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")])

        flat = _measure([_comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 4.0, 1.0, "rect")]), b])
        assert flat.measured_mm == pytest.approx(7.5, abs=1e-9)

        turned = _measure(
            [
                _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 4.0, 1.0, "rect", pad_rot=90.0)]),
                b,
            ]
        )
        assert turned.measured_mm == pytest.approx(9.0, abs=1e-9)

    def test_rotation_by_45_degrees_is_exact_not_snapped(self):
        """Rotation is not quantized to quadrants. A 2x2 rect rotated 45
        degrees presents a corner: its half-extent on X becomes
        ``hypot(1,1)`` = 1.414, not 1.0, so the gap shrinks by 0.414mm.
        """
        b = _comp("B", (10.0, 0.0), [_pad(LV, (0.0, 0.0), 2.0, 2.0, "rect")])
        flat = _measure([_comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 2.0, 2.0, "rect")]), b])
        tilt = _measure(
            [_comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 2.0, 2.0, "rect")], rotation_deg=45.0), b]
        )
        assert flat.measured_mm == pytest.approx(8.0, abs=1e-9)
        assert tilt.measured_mm == pytest.approx(9.0 - math.sqrt(2.0), abs=1e-9)


# =============================================================================
# Pad-level domain restriction
# =============================================================================


class TestDomainRestriction:
    def test_only_pads_on_the_relevant_net_count_as_that_domains_copper(self):
        """A DC_BUS component's GND pad is not DC_BUS copper.

        A carries an HV pad at local x=-3 and an LV pad at local x=+3 (the
        one nearest B). Measuring the DC_BUS<->LV_CONTROL boundary must use
        A's *HV* pad, giving 10 - (-3 offset -> 3 away) ... concretely:
        HV pad centre at x=-3 half-width 0.5 -> nearest edge x=-2.5;
        B's LV pad at x=10 half-width 0.5 -> nearest edge 9.5; gap 12.0.
        Using A's nearer LV pad instead would wrongly report 6.0.
        """
        a = _comp(
            "A",
            (0.0, 0.0),
            [
                _pad(HV, (-3.0, 0.0), 1.0, 1.0, "rect", number="1"),
                _pad(LV, (3.0, 0.0), 1.0, 1.0, "rect", number="2"),
            ],
        )
        b = _comp("B", (10.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")])
        result = check_domain_clearance(
            _placement([a, b]), VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, min_mm=1000.0
        )
        # A straddles the boundary itself, so it is also reported intra --
        # correct, and checked separately in TestIntraFootprint.
        inter = [v for v in result.violations if v.pair_kind == "inter"]
        assert len(inter) == 1
        v = inter[0]
        assert v.measured_mm == pytest.approx(12.0, abs=1e-9)
        assert "A.1" in v.closest_pads and "B.1" in v.closest_pads


# =============================================================================
# Intra-footprint crossings
# =============================================================================


class TestIntraFootprint:
    def _straddler(self, gap_mm):
        """One part whose own pads straddle HV<->SELV, at a chosen gap.

        Two 1x1 rect pads whose centres are ``gap + 1.0`` apart give exactly
        ``gap`` mm of copper separation.
        """
        d = (gap_mm + 1.0) / 2.0
        return _comp(
            "U1",
            (50.0, 50.0),
            [
                _pad(HV, (-d, 0.0), 1.0, 1.0, "rect", number="1"),
                _pad(LV, (d, 0.0), 1.0, 1.0, "rect", number="2"),
            ],
        )

    def test_a_single_part_straddling_the_barrier_is_reported(self):
        """``_domain_boundary_pairs`` pairs only distinct components, so this
        part was invisible to the checker at every possible placement. Five
        such parts exist on the real board (C6, K2, K3, U3, U7)."""
        result = check_domain_clearance(
            _placement([self._straddler(3.0)]),
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=6.0,
        )
        assert not result.passed
        v = result.violations[0]
        assert v.pair_kind == "intra"
        assert v.ref_a == v.ref_b == "U1"
        assert v.measured_mm == pytest.approx(3.0, abs=1e-9)
        assert "within U1" in v.message

    def test_a_straddling_part_with_adequate_separation_passes(self):
        result = check_domain_clearance(
            _placement([self._straddler(7.0)]),
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=6.0,
        )
        assert result.passed

    def test_intra_pairs_are_not_generated_for_same_domain_boundaries(self):
        """The one same-domain matrix row is LV<->LV FUNCTIONAL. Applying it
        inside a footprint would flag the manufacturer's fixed pad pitch on
        essentially every multi-pad SELV part -- 41 further records across 33
        parts on the real board, none of them a barrier crossing and none of
        them actionable. See ``_intra_component_boundary_components``.
        """
        part = _comp(
            "U2",
            (50.0, 50.0),
            [
                _pad(LV, (-0.2, 0.0), 0.3, 0.3, "rect", number="1"),
                _pad("N_LV2", (0.2, 0.0), 0.3, 0.3, "rect", number="2"),
            ],
        )
        placement = {
            "components": [part],
            "nets": {
                LV: {"domain": VoltageDomain.LV_CONTROL},
                "N_LV2": {"domain": VoltageDomain.LV_CONTROL},
            },
        }
        result = check_domain_clearance(
            placement, VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, min_mm=0.5
        )
        assert result.passed
        assert result.stats["pairs_intra"] == 0

    def test_intra_pair_does_not_leak_into_the_cp_sat_pairing_function(self):
        """``placer.cp_sat.domain_clearance`` builds one SeparatedConstraint
        per pair from ``_domain_boundary_pairs``; a self-pair there would
        become a nonsensical ``SeparatedConstraint(a=X, b=X)``. Intra-footprint
        crossings are therefore enumerated separately, and that separation is
        pinned here.
        """
        from temper_placer.requirements.validators.clearance import (
            _domain_boundary_pairs,
            _nets_domain_map,
        )

        placement = _placement([self._straddler(3.0)])
        pairs = _domain_boundary_pairs(
            placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            _nets_domain_map(placement),
        )
        assert pairs == []


# =============================================================================
# Creepage is a different metric from clearance
# =============================================================================


class TestCreepageVsClearance:
    def _pair(self):
        return [
            _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 1.0, 1.0, "rect")]),
            _comp("B", (5.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
        ]

    def test_unbroken_surface_creepage_is_exact_and_tagged_as_such(self):
        """With no cutout the surface geodesic between two coplanar points IS
        the straight line, so creepage equals clearance *exactly* -- and says
        so, rather than being silently identical."""
        result = check_creepage_path(
            _placement(self._pair(), cutouts=[]),
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=8.0,
        )
        v = result.violations[0]
        assert v.metric == "creepage"
        assert v.creepage_model == CREEPAGE_MODEL_UNBROKEN_SURFACE
        assert v.measured_mm == pytest.approx(4.0, abs=1e-9)

    def test_clearance_carries_no_creepage_model(self):
        result = check_domain_clearance(
            _placement(self._pair(), cutouts=[]),
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=8.0,
        )
        assert result.violations[0].creepage_model is None

    def test_a_board_cutout_switches_creepage_to_a_loud_conservative_model(self, caplog):
        """Slot-aware surface pathing is not implemented. The moment the board
        declares a cutout, the reported creepage stops being exact and becomes
        an explicit lower bound -- tagged on the violation AND logged, never
        silently reported as if it were the real surface path.
        """
        slot = [[(2.0, -1.0), (3.0, -1.0), (3.0, 1.0), (2.0, 1.0)]]
        with caplog.at_level(logging.WARNING):
            result = check_creepage_path(
                _placement(self._pair(), cutouts=slot),
                VoltageDomain.DC_BUS,
                VoltageDomain.LV_CONTROL,
                min_mm=8.0,
            )
        v = result.violations[0]
        assert v.creepage_model == CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND
        assert result.stats["board_cutouts"] == 1
        assert any("slot-aware surface pathing" in r.getMessage() for r in caplog.records)

    def test_a_board_cutout_does_not_change_the_clearance_model(self, caplog):
        """Clearance is a straight line through air; a milled slot does not
        lengthen it. Only creepage is affected."""
        slot = [[(2.0, -1.0), (3.0, -1.0), (3.0, 1.0), (2.0, 1.0)]]
        with caplog.at_level(logging.WARNING):
            result = check_domain_clearance(
                _placement(self._pair(), cutouts=slot),
                VoltageDomain.DC_BUS,
                VoltageDomain.LV_CONTROL,
                min_mm=8.0,
            )
        assert result.violations[0].creepage_model is None
        assert not any("slot-aware" in r.getMessage() for r in caplog.records)

    def test_reported_creepage_is_never_below_reported_clearance(self):
        """The physical invariant: a surface path cannot be shorter than the
        straight line between the same two points."""
        for cutouts in ([], [[(2.0, -1.0), (3.0, -1.0), (3.0, 1.0), (2.0, 1.0)]]):
            placement = _placement(self._pair(), cutouts=cutouts)
            clr = check_domain_clearance(
                placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, min_mm=1000.0
            )
            crp = check_creepage_path(
                placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, min_mm=1000.0
            )
            assert crp.violations[0].measured_mm >= clr.violations[0].measured_mm


# =============================================================================
# Reporting
# =============================================================================


class TestReport:
    def test_report_is_sorted_worst_first_and_names_the_copper(self):
        components = [
            _comp("HV1", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 1.0, 1.0, "rect")]),
            _comp("LV1", (2.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
            _comp("LV2", (5.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
        ]
        result = verify_iec60335_compliance(
            _placement(components),
            {HV: VoltageDomain.DC_BUS, LV: VoltageDomain.LV_CONTROL},
        )
        report = result.report()
        shortfalls = [
            v.shortfall_mm for v in sorted(result.violations, key=lambda v: -v.shortfall_mm)
        ]
        assert shortfalls == sorted(shortfalls, reverse=True)
        # The worst pair (HV1<->LV1, 1.0mm of copper) must be on the first row.
        first_row = report.splitlines()[3]
        assert "HV1<->LV1" in first_row
        assert "HV1.1(N_HV) <-> LV1.1(N_LV)" in report
        for column in ("boundary", "metric", "meas", "req", "short"):
            assert column in report

    def test_report_of_a_clean_result(self):
        assert "No clearance/creepage violations." in format_clearance_report(
            verify_iec60335_compliance({"components": [], "nets": {}}, {})
        )

    def test_shortfall_is_required_minus_measured(self):
        v = _measure(
            [
                _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 1.0, 1.0, "rect")]),
                _comp("B", (5.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
            ],
            min_mm=6.0,
        )
        assert v.measured_mm == pytest.approx(4.0)
        assert v.shortfall_mm == pytest.approx(2.0)


# =============================================================================
# Pruning must not change any answer
# =============================================================================


class TestPruningSoundness:
    def test_the_cheap_lower_bound_never_prunes_a_real_violation(self):
        """``lower_bound`` = origin distance minus both copper reaches is used
        to skip pairs. If it were ever an over-estimate a violation would be
        silently dropped, so it is checked directly against the exact
        measurement over a sweep of separations straddling the threshold.
        """
        from temper_placer.requirements.validators.clearance import _CopperModel

        for sep in [x / 4.0 for x in range(20, 80)]:
            components = [
                _comp("A", (0.0, 0.0), [_pad(HV, (2.5, 0.0), 8.0, 8.0, "rect")]),
                _comp("B", (sep, 0.0), [_pad(LV, (-2.5, 0.0), 8.0, 8.0, "rect")]),
            ]
            placement = _placement(components)
            model = _CopperModel(placement)
            bound = model.lower_bound("A", "B")
            exact, kind, _ = model.copper_distance(
                "A",
                VoltageDomain.DC_BUS,
                "B",
                VoltageDomain.LV_CONTROL,
                {HV: VoltageDomain.DC_BUS, LV: VoltageDomain.LV_CONTROL},
            )
            assert kind == "copper"
            assert bound <= exact + 1e-9, f"unsound bound at sep={sep}"


# =============================================================================
# Against the real board: the two independently-known isolator figures
# =============================================================================


class TestRealBoardIsolatorFigures:
    """PR #388's pad-geometry model reports T1 = 9.100mm and K1 = 8.000mm for
    the two declared isolators on ``pcb/temper.kicad_pcb``. Those two numbers
    are the external check on this module's geometry: if it disagrees with
    them, its geometry is wrong, not the board's.

    K1's exact geometry is still why distances here are computed exactly
    (``pad_pair_distance``) rather than by polygonising arcs -- a polygon
    approximation could manufacture or hide a sub-millimeter violation. Its
    margin against the enforced requirement has moved twice since: first
    docs/evidence/2026-07-30-creepage-requirement-reconciliation.md
    corrected the REINFORCED DC_BUS<->LV_CONTROL creepage requirement from
    8.0mm to 10.0mm (the 300V-vs-400V Table 16 row question), then
    docs/evidence/2026-07-30-pollution-degree-determination.md corrected it
    again to 12.6mm (PD3, the then-governing default). K1's copper gap is
    exactly 8.000mm and does not itself change with either correction.

    UPDATE 2026-07-30 (PD2 adoption, this change): the project owner has
    since selected the PD2 8.0mm reinforced-creepage target for production
    (docs/evidence/2026-07-30-pd2-enclosure-decision.md), conditional on the
    sealed-compartment prerequisite recorded there and in
    HIGH_VOLTAGE_CLEARANCE_SPEC.md Sec 3.2.1; PD3/12.6mm remains the
    documented fallback if that prerequisite is not met. Against the
    currently-enforced 8.0mm figure, K1's exact 8.000mm gap is now a MATCH,
    not a shortfall -- see
    ``test_k1_is_a_genuine_creepage_violation_after_the_400v_correction``
    below, which re-measures this directly rather than assuming it.
    """

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "ref,pad_a,pad_b,expected_mm",
        [("T1", "1", "4", 9.100), ("K1", "13", "A1", 8.000)],
    )
    def test_isolator_pad_gap(self, ref, pad_a, pad_b, expected_mm):
        from temper_placer.core.pad_geometry import pad_pair_distance
        from temper_placer.requirements.validators.clearance import _component_pads

        from ._real_board_fixture import RealBoardUnavailable, load_real_board_placement

        try:
            placement, _domains, _stats = load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

        by_ref = {c["ref"]: c for c in placement["components"]}
        assert ref in by_ref, f"{ref} not present in the classified placement"
        pads = {p.number: p for p in _component_pads(by_ref[ref])}

        def spec(p):
            return (p.width, p.height, p.shape, p.cx, p.cy, p.rotation_rad, p.roundrect_ratio)

        gap = pad_pair_distance(spec(pads[pad_a]), spec(pads[pad_b]))
        assert gap == pytest.approx(expected_mm, abs=1e-6)

    @pytest.mark.slow
    def test_k1_is_a_genuine_creepage_violation_after_the_400v_correction(self):
        """K1's intra-footprint copper gap (8.000mm, exact -- see
        ``test_isolator_pad_gap``) does not move. What changed, twice, is
        the requirement it is measured against: REINFORCED DC_BUS<->LV_CONTROL
        creepage was 12.6mm as of 2026-07-30 (corrected from 10.0mm -- see
        docs/evidence/2026-07-30-pollution-degree-determination.md: IEC
        60335-2-6 cl. 29.2 Addition makes Pollution Degree 3 the default
        for this appliance class and no enclosure/sealing argument earned
        the PD2 exception on this design's own mechanical documents as they
        stood then; IEC 60335-1 Table 17 row iv, Material Group IIIa/IIIb,
        PD3, gives 6.3mm basic / 12.6mm reinforced). At that 12.6mm figure
        K1's intra-footprint gap fell exactly 4.6mm short, and a second,
        genuine inter-component violation also appeared: K1 (DC_BUS, via
        w1_2) sits 11.530mm from R78 (LV_CONTROL, +3V3) -- below 12.6mm,
        though above the prior 10.0mm minimum.

        UPDATE 2026-07-30 (PD2 adoption, this change): the project owner has
        since selected the PD2 8.0mm reinforced-creepage target for
        production (docs/evidence/2026-07-30-pd2-enclosure-decision.md),
        conditional on the sealed-compartment prerequisite recorded there
        and in HIGH_VOLTAGE_CLEARANCE_SPEC.md Sec 3.2.1; PD3/12.6mm remains
        the documented fallback if that prerequisite is not met. Against the
        currently-enforced 8.0mm figure, NEITHER of K1's two 12.6mm-era
        findings is a violation any more: the 8.000mm intra-footprint gap is
        an exact match (8.000 >= 8.0), and the 11.530mm inter-component
        distance clears with margin. This is re-measured directly below, not
        assumed -- if the sealed-compartment prerequisite is not met and the
        PD3 fallback governs instead, both findings above return exactly as
        documented. This test fails if the exact-geometry model
        (``pad_pair_distance``) stops being exact, which would perturb the
        8.000mm figure away from its exact value and make this assertion
        fragile in the wrong direction.
        """
        from ._real_board_fixture import RealBoardUnavailable, load_real_board_placement

        try:
            placement, domains, _stats = load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

        result = verify_iec60335_compliance(placement, domains)
        k1 = [v for v in result.violations if v.ref_a == "K1" or v.ref_b == "K1"]
        assert k1 == [], (
            "expected K1 to clear at the currently-enforced 8.0mm PD2 "
            f"target (exact 8.000mm intra-footprint gap; see "
            f"test_isolator_pad_gap); still violating: {k1}"
        )

    @pytest.mark.slow
    def test_the_seven_known_intra_footprint_blockers_are_now_visible(self):
        """C6, K2, K3, U3 and U7 each have their own pads on opposite sides of
        the mains<->SELV barrier, and were already visible under the old
        (incorrect, 300V-row) 8.0mm REINFORCED creepage requirement. K1
        (8.000mm) and T1 (9.100mm) joined them once the requirement became
        10.0mm (see
        docs/evidence/2026-07-30-creepage-requirement-reconciliation.md),
        and all seven remained violations once the requirement rose further
        to 12.6mm (PD3, see
        docs/evidence/2026-07-30-pollution-degree-determination.md): each
        one "passed" only because the requirement it was checked against was
        too lenient, not because it actually cleared the standard. No
        placement can fix any of these seven -- they are pad-to-pad gaps
        within a single footprint.

        UPDATE 2026-07-30 (PD2 adoption, this change): the project owner has
        since selected the PD2 8.0mm reinforced-creepage target for
        production (docs/evidence/2026-07-30-pd2-enclosure-decision.md),
        conditional on the sealed-compartment prerequisite recorded there
        and in HIGH_VOLTAGE_CLEARANCE_SPEC.md Sec 3.2.1; PD3/12.6mm remains
        the documented fallback if that prerequisite is not met. Re-measured
        directly against the now-enforced 8.0mm figure (not assumed from the
        12.6mm-era list above): C6 (8.000mm), K1 (8.000mm), U7 (8.100mm), U3
        (8.560mm), and T1 (9.100mm) now clear the 8.0mm minimum exactly or
        with margin and are no longer REQ-SAFE-01 violations -- this is the
        intended, structural effect of the PD2 decision, not a test
        weakening. K2 and K3 (3.559mm each) remained genuine blockers by a
        wide margin (~4.4mm short) regardless of pollution degree: they also
        fail the pollution-degree-INDEPENDENT 6.0mm clearance minimum, so no
        pollution-degree change could ever clear them.

        UPDATE 2026-08-01 (RT314012 swap landed, this change): K2 was
        swapped to the TE Schrack RT314012 (PR #524) and K3 to the same
        part at the #517-re-solved position (69.72, 29.0) rot 90 (this
        change, docs/evidence/2026-08-01-k3-relay-swap-resolved.md). The
        RT314012's 12.76mm coil-to-contact gap clears the 8.0mm bar (and
        the 6.0mm PD-independent minimum) with margin, so **K2 and K3 are
        no longer intra-footprint blockers** -- the real board now reports
        zero intra-footprint REQ-SAFE-01 violations. This assertion change
        records the fix, not a weakening: a regression that silently
        re-introduces any intra-footprint blocker is still caught by
        ``intra == set()`` below. If the sealed-compartment prerequisite is
        not met and the PD3 fallback governs instead, C6/K1/T1/U3/U7 return
        to the violation set as documented above (K2/K3 do not -- they are
        cleared structurally by the part swap, independent of pollution
        degree).
        """
        from ._real_board_fixture import RealBoardUnavailable, load_real_board_placement

        try:
            placement, domains, _stats = load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

        result = verify_iec60335_compliance(placement, domains)
        intra = {v.ref_a for v in result.violations if v.pair_kind == "intra"}

        # K2/K3: cleared structurally by the RT314012 swap (12.76mm internal
        # coil-to-contact gap, measured from the footprint geometry) -- they
        # were 3.559mm each on the outgoing G5LE-1, ~4.4mm short of the
        # 8.0mm bar and below the PD-independent 6.0mm minimum. No longer
        # blockers; any reappearance here is a regression to catch.
        assert "K2" not in intra, "K2 should clear on the RT314012 (12.76mm measured)"
        assert "K3" not in intra, "K3 should clear on the RT314012 (12.76mm measured)"
        assert all(
            v.insulation_type in (InsulationType.BASIC, InsulationType.REINFORCED)
            for v in result.violations
            if v.pair_kind == "intra"
        )

        # C6, K1, T1, U3, U7: cleared by the PD2 8.0mm target (were
        # violations only at PD3's stricter 12.6mm). Asserted absent, not
        # merely unmentioned, so a regression that silently re-adds any of
        # them to `intra` is caught here.
        assert "C6" not in intra, "C6 should clear at the 8.0mm PD2 target (8.000mm measured)"
        assert "K1" not in intra, "K1 should clear at the 8.0mm PD2 target (8.000mm measured)"
        assert "T1" not in intra, "T1 should clear at the 8.0mm PD2 target (9.100mm measured)"
        assert "U3" not in intra, "U3 should clear at the 8.0mm PD2 target (8.560mm measured)"
        assert "U7" not in intra, "U7 should clear at the 8.0mm PD2 target (8.100mm measured)"

        assert intra == set(), (
            f"expected zero intra-footprint blockers after the K2/K3 RT314012 "
            f"swap, got {intra}"
        )
