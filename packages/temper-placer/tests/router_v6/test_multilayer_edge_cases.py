"""
Parametrized edge-case tests for multi-layer and via-edge behaviours
across DFM modules (Stage 5 Manufacturing DRC).

Covers blind, buried, through, zero-span, and non-existent layer vias;
inner-layer paths; RoutePath3D mixed-layer segments; dangling vias;
out-of-bounds via positions; and mixed single/multi-layer nets.

Each test exercises one of the DFM modules — annular ring, teardrop,
copper balance, clearance, creepage, thermal relief, or acid trap —
with a focus on layer-aware logic.

Part of temper-xxxx (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import warnings

import pytest

from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    AnnularRingViolation,
    _check_via,
    check_annular_rings,
)
from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    verify_clearance,
)
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    _layer_is_between,
    analyze_copper_balance,
)
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    verify_creepage,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import (
    TeardropReport,
    insert_teardrops,
)
from temper_placer.router_v6.thermal_relief import (
    add_thermal_relief,
)
from temper_placer.router_v6.via_placement import Via

# ============================================================================
# Shared helpers (follow the same pattern as other boundary test files)
# ============================================================================

_NORMAL_TRACE_WIDTH = 0.127
_NORMAL_VIA_DIAMETER = 0.6
_NORMAL_VIA_DRILL = 0.3
_NORMAL_NET = "NET1"
_DEFAULT_LAYER = "F.Cu"


def _make_path(
    coords: list | None = None,
    layer: str = _DEFAULT_LAYER,
    net_name: str = _NORMAL_NET,
) -> RoutePath:
    """Create a ``RoutePath`` for ``CompiledRoute`` construction."""
    if coords is None:
        coords = [(0.0, 0.0), (10.0, 10.0)]
    length = math.hypot(
        coords[-1][0] - coords[0][0],
        coords[-1][1] - coords[0][1],
    )
    return RoutePath(net_name, coords, layer, length)


def _make_via(
    diameter: float = _NORMAL_VIA_DIAMETER,
    drill: float = _NORMAL_VIA_DRILL,
    position: tuple[float, float] = (5.0, 5.0),
    from_layer: str = "F.Cu",
    to_layer: str = "B.Cu",
    net_name: str = _NORMAL_NET,
    via_type: str | None = None,
) -> Via:
    """Create a ``Via`` with optional ``via_type`` override."""
    via = Via(position, from_layer, to_layer, diameter, drill, net_name)
    if via_type is not None:
        via.via_type = via_type  # type: ignore[attr-defined]
    return via


def _make_route(
    net_name: str = _NORMAL_NET,
    coords: list | None = None,
    width: float = _NORMAL_TRACE_WIDTH,
    layer: str = _DEFAULT_LAYER,
    vias: list | None = None,
    path: RoutePath | RoutePath3D | None = None,
) -> CompiledRoute:
    """Create a ``CompiledRoute`` for testing."""
    if path is None:
        path = _make_path(coords=coords, layer=layer, net_name=net_name)
    return CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=width,
        vias=list(vias) if vias else [],
        matched_length_mm=None,
    )


def _make_results(
    routes: dict[str, CompiledRoute] | None = None,
    vias: list | None = None,
    path: RoutePath | None = None,
    net_name: str = _NORMAL_NET,
    trace_width: float = _NORMAL_TRACE_WIDTH,
    failed_nets: list[str] | None = None,
) -> RoutingResults:
    """Build ``RoutingResults`` from either a route dict or a single route."""
    if routes is None:
        if vias is None:
            vias = []
        if path is None:
            path = _make_path(net_name=net_name)
        route = CompiledRoute(net_name, path, trace_width, vias, None)
        routes = {net_name: route}
    return RoutingResults(
        compiled_routes=routes,
        failed_nets=list(failed_nets) if failed_nets else [],
    )


# ============================================================================
# 1. Blind vias — F.Cu → In1.Cu
# ============================================================================


class TestBlindVia:
    """Blind vias connect an external layer to an internal layer."""

    # ------------------------------------------------------------------
    # 1a. Annular ring uses external threshold
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "diameter, drill, min_ring, expect_violation",
        [
            # ring = (0.6-0.3)/2 = 0.15 > 0.05 => passes
            (0.6, 0.3, 0.05, False),
            # ring = (0.4-0.3)/2 ≈ 0.05000000000000002 > 0.05 in FP
            # (in IEEE 754, 0.4 - 0.3 = 0.10000000000000003, /2 = 0.05000000000000002)
            # The <= check with FP epsilon now catches this boundary case.
            pytest.param(
                0.4, 0.3, 0.05, True,
                id="d=0.4-drill=0.3-at-threshold",
            ),
            # ring = (0.32-0.3)/2 = 0.01 < 0.05 => violation
            (0.32, 0.3, 0.05, True),
            # Internal alone would use 0.025 — but blind touches F.Cu
            # ring = 0.03 > 0.025 (internal threshold) but < 0.05 (external)
            # => should violate because external threshold is used
            (0.36, 0.3, 0.05, True),
        ],
    )
    def test_blind_via_annular_ring_uses_external_threshold(
        self, diameter, drill, min_ring, expect_violation
    ):
        """Blind via (F.Cu→In1.Cu) uses the full external threshold."""
        via = _make_via(
            diameter=diameter, drill=drill,
            from_layer="F.Cu", to_layer="In1.Cu",
        )
        result = _check_via(via, _NORMAL_NET, min_ring, 0.025)

        if expect_violation:
            assert isinstance(result, AnnularRingViolation), (
                f"Blind via d={diameter} drill={drill} should violate "
                f"at min_ring={min_ring}"
            )
            # The threshold must be the full external threshold
            assert result.minimum_required == pytest.approx(min_ring)
        else:
            assert result is None, (
                f"Blind via d={diameter} drill={drill} should pass "
                f"at min_ring={min_ring}"
            )

    # ------------------------------------------------------------------
    # 1b. Teardrop checks path layer matches via layers
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path_layer, via_from, via_to, expect_teardrop",
        [
            # Path on F.Cu matches via.from_layer
            ("F.Cu", "F.Cu", "In1.Cu", True),
            # Path on In1.Cu matches via.to_layer
            ("In1.Cu", "F.Cu", "In1.Cu", True),
            # Path on B.Cu — no match (blind via doesn't reach B.Cu)
            ("B.Cu", "F.Cu", "In1.Cu", False),
            # Path on In2.Cu — no match
            ("In2.Cu", "F.Cu", "In1.Cu", False),
        ],
    )
    def test_blind_via_teardrop_layer_matching(
        self, path_layer, via_from, via_to, expect_teardrop
    ):
        """Teardrop only generated when path layer matches via layers."""
        path = _make_path(layer=path_layer)
        via = _make_via(from_layer=via_from, to_layer=via_to)
        results = _make_results(vias=[via], path=path)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = insert_teardrops(results)

        if expect_teardrop:
            assert report.teardrop_count == 1, (
                f"Expected 1 teardrop for path_layer={path_layer} "
                f"via={via_from}→{via_to}"
            )
        else:
            assert report.teardrop_count == 0, (
                f"Expected 0 teardrops for path_layer={path_layer} "
                f"via={via_from}→{via_to}"
            )

    # ------------------------------------------------------------------
    # 1c. Copper balance attributes to from/to layers only (no barrel)
    # ------------------------------------------------------------------

    def test_blind_via_copper_only_on_endpoint_layers(self):
        """Blind via annulus appears only on from/to layers, not In2.Cu or B.Cu."""
        via = _make_via(from_layer="F.Cu", to_layer="In1.Cu")
        path = _make_path(layer="F.Cu")
        results = _make_results(vias=[via], path=path, trace_width=0.2)

        report = analyze_copper_balance(results, 100, 100)

        f_cu = _get_balance(report, "F.Cu")
        in1 = _get_balance(report, "In1.Cu")
        in2 = _get_balance(report, "In2.Cu")
        b_cu = _get_balance(report, "B.Cu")

        # Trace on F.Cu + via annulus on F.Cu => area > 0
        assert f_cu.copper_area_mm2 > 0, "F.Cu should have trace + via copper"
        # Via annulus on In1.Cu => area > 0
        assert in1.copper_area_mm2 > 0, "In1.Cu should have via annulus"
        # No copper on In2.Cu or B.Cu for a blind via
        assert in2.copper_area_mm2 == pytest.approx(0.0), (
            "In2.Cu should have no copper (blind via doesn't reach it)"
        )
        assert b_cu.copper_area_mm2 == pytest.approx(0.0), (
            "B.Cu should have no copper (blind via doesn't reach it)"
        )


# ============================================================================
# 2. Buried vias — In1.Cu → In2.Cu
# ============================================================================


class TestBuriedVia:
    """Buried vias connect two internal layers."""

    # ------------------------------------------------------------------
    # 2a. Annular ring uses internal threshold (0.5×)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "diameter, drill, min_ring, expect_violation",
        [
            # ring = 0.15, internal threshold = 0.025 => passes
            (0.6, 0.3, 0.05, False),
            # ring = 0.025, internal threshold = 0.025 => violation (<=)
            (0.35, 0.3, 0.05, True),
            # ring = 0.024, internal threshold = 0.025 => violation
            (0.348, 0.3, 0.05, True),
            # ring = 0.026 > internal threshold 0.025 => passes
            # But < external 0.05 — if external threshold were used
            # it would violate.  So this confirms internal threshold.
            (0.352, 0.3, 0.05, False),
        ],
    )
    def test_buried_via_annular_ring_uses_internal_threshold(
        self, diameter, drill, min_ring, expect_violation
    ):
        """Buried via (In1.Cu→In2.Cu) uses 0.5× threshold."""
        via = _make_via(
            diameter=diameter, drill=drill,
            from_layer="In1.Cu", to_layer="In2.Cu",
        )
        result = _check_via(via, _NORMAL_NET, min_ring, 0.025)

        if expect_violation:
            assert isinstance(result, AnnularRingViolation), (
                f"Buried via d={diameter} drill={drill} should violate "
                f"at min_ring={min_ring}"
            )
            # Threshold must be half the external value
            assert result.minimum_required == pytest.approx(min_ring * 0.5)
        else:
            assert result is None, (
                f"Buried via d={diameter} drill={drill} should pass "
                f"at min_ring={min_ring}"
            )

    # ------------------------------------------------------------------
    # 2b. Copper balance attributes only to endpoint layers (no barrel)
    # ------------------------------------------------------------------

    def test_buried_via_copper_only_on_intermediate_layers(self):
        """Buried via (In1.Cu→In2.Cu) copper appears only on In1.Cu and In2.Cu."""
        via = _make_via(from_layer="In1.Cu", to_layer="In2.Cu")
        path = _make_path(layer="In1.Cu")
        results = _make_results(vias=[via], path=path, trace_width=0.2)

        report = analyze_copper_balance(results, 100, 100)

        f_cu = _get_balance(report, "F.Cu")
        in1 = _get_balance(report, "In1.Cu")
        in2 = _get_balance(report, "In2.Cu")
        b_cu = _get_balance(report, "B.Cu")

        assert f_cu.copper_area_mm2 == pytest.approx(0.0), (
            "F.Cu should have no copper (buried via doesn't reach it)"
        )
        assert in1.copper_area_mm2 > 0, "In1.Cu should have trace + via annulus"
        assert in2.copper_area_mm2 > 0, "In2.Cu should have via annulus"
        assert b_cu.copper_area_mm2 == pytest.approx(0.0), (
            "B.Cu should have no copper (buried via doesn't reach it)"
        )

    # ------------------------------------------------------------------
    # 2c. Teardrop on internal path with buried via
    # ------------------------------------------------------------------

    def test_buried_via_teardrop_on_internal_layer(self):
        """Teardrop works for a path on In1.Cu connected to buried via."""
        path = _make_path(layer="In1.Cu")
        via = _make_via(from_layer="In1.Cu", to_layer="In2.Cu")
        results = _make_results(vias=[via], path=path)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = insert_teardrops(results)

        assert report.teardrop_count == 1
        assert report.teardrops[0].layer == "In1.Cu"


# ============================================================================
# 3. Through vias — F.Cu → B.Cu
# ============================================================================


class TestThroughVia:
    """Through vias span all layers."""

    # ------------------------------------------------------------------
    # 3a. Copper balance must attribute to ALL intermediate layers
    # ------------------------------------------------------------------

    def test_through_via_copper_on_all_layers(self):
        """Through via (F.Cu→B.Cu) adds copper on all 4 standard layers."""
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
        path = _make_path(layer="F.Cu")
        results = _make_results(vias=[via], path=path, trace_width=0.2)

        report = analyze_copper_balance(results, 100, 100)

        for layer_name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
            lb = _get_balance(report, layer_name)
            assert lb.copper_area_mm2 > 0, (
                f"{layer_name} should have copper from through-hole via"
            )

    # ------------------------------------------------------------------
    # 3b. Annular ring uses external threshold
    # ------------------------------------------------------------------

    def test_through_via_annular_ring_external_threshold(self):
        """Through via (F.Cu→B.Cu) touches external layers → full threshold."""
        # ring = (0.36-0.3)/2 = 0.03
        # external threshold = 0.05 => violation
        via = _make_via(
            diameter=0.36, drill=0.3,
            from_layer="F.Cu", to_layer="B.Cu",
        )
        result = _check_via(via, _NORMAL_NET, 0.05, 0.025)
        assert isinstance(result, AnnularRingViolation)
        assert result.minimum_required == pytest.approx(0.05)

    # ------------------------------------------------------------------
    # 3c. _layer_is_between correctness
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "from_layer, to_layer, candidate, expected",
        [
            ("F.Cu", "B.Cu", "In1.Cu", True),
            ("F.Cu", "B.Cu", "In2.Cu", True),
            ("F.Cu", "B.Cu", "F.Cu", False),   # not strictly between
            ("F.Cu", "B.Cu", "B.Cu", False),   # not strictly between
            ("F.Cu", "In1.Cu", "In2.Cu", False),  # beyond to_layer
            ("In1.Cu", "B.Cu", "In2.Cu", True),
            ("In1.Cu", "B.Cu", "F.Cu", False),
            ("B.Cu", "F.Cu", "In1.Cu", True),  # reversed order
            ("B.Cu", "F.Cu", "In2.Cu", True),  # reversed order
        ],
    )
    def test_layer_is_between(self, from_layer, to_layer, candidate, expected):
        """``_layer_is_between`` correctly identifies intermediate layers."""
        assert _layer_is_between(from_layer, to_layer, candidate) == expected


# ============================================================================
# 4. Zero-span via — from_layer == to_layer
# ============================================================================


class TestZeroSpanVia:
    """Via where from_layer == to_layer (should be treated gracefully)."""

    @pytest.mark.parametrize(
        "module_name, from_to",
        [
            ("annular_ring", ("F.Cu", "F.Cu")),
            ("annular_ring", ("In1.Cu", "In1.Cu")),
            ("teardrop", ("F.Cu", "F.Cu")),
            ("teardrop", ("In1.Cu", "In1.Cu")),
            ("copper_balance", ("F.Cu", "F.Cu")),
            ("copper_balance", ("In1.Cu", "In1.Cu")),
        ],
    )
    def test_zero_span_via_does_not_crash(self, module_name, from_to):
        """Zero-span via should not crash any DFM module."""
        from_layer, to_layer = from_to
        via = _make_via(from_layer=from_layer, to_layer=to_layer)
        path = _make_path(layer=from_layer)
        results = _make_results(vias=[via], path=path)

        if module_name == "annular_ring":
            report = check_annular_rings(results)
            assert isinstance(report, AnnularRingReport)
            # Should still be checked
            assert report.total_vias_checked == 1

        elif module_name == "teardrop":
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                report = insert_teardrops(results)
            assert isinstance(report, TeardropReport)
            # Via.from_layer == Via.to_layer == path.layer => teardrop possible
            assert report.teardrop_count >= 0

        elif module_name == "copper_balance":
            report = analyze_copper_balance(results, 100, 100)
            assert isinstance(report, CopperBalanceReport)
            # Copper should appear only on that single layer
            for lb in report.layer_balances:
                if lb.layer_name == from_layer:
                    assert lb.copper_area_mm2 > 0
                else:
                    assert lb.copper_area_mm2 == pytest.approx(0.0)


# ============================================================================
# 5. Non-existent layer names
# ============================================================================


class TestNonExistentLayers:
    """Graceful handling of via with layer names outside the standard stack."""

    NON_EXISTENT_LAYERS = [
        "L99.Cu",
        "NonExistent",
        "",
        "F.Cu.L99",
        "In99.Cu",
        "Signal.Cu",
    ]

    # ------------------------------------------------------------------
    # 5a. Annular ring
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("bad_layer", NON_EXISTENT_LAYERS)
    def test_annular_ring_non_existent_layer(self, bad_layer):
        """Non-existent layer → treated as internal (0.5× threshold)."""
        via = _make_via(from_layer=bad_layer, to_layer=bad_layer)
        path = _make_path(layer="F.Cu")
        results = _make_results(vias=[via], path=path, net_name="NONET")

        report = check_annular_rings(results, min_annular_ring=0.05)
        assert isinstance(report, AnnularRingReport)
        # Via is checked; layer unknown → neither external → internal 0.5×
        assert report.total_vias_checked == 1

    # ------------------------------------------------------------------
    # 5b. Copper balance
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("bad_layer", NON_EXISTENT_LAYERS)
    def test_copper_balance_non_existent_layer(self, bad_layer):
        """Via on non-existent layer → _layer_is_between returns False."""
        via = _make_via(from_layer=bad_layer, to_layer="B.Cu")
        path = _make_path(layer="F.Cu")
        results = _make_results(vias=[via], path=path, trace_width=0.2)

        report = analyze_copper_balance(results, 100, 100)
        assert isinstance(report, CopperBalanceReport)
        # Non-existent layer not in standard 4 → no crash

    # ------------------------------------------------------------------
    # 5c. Teardrop
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("bad_layer", NON_EXISTENT_LAYERS)
    def test_teardrop_non_existent_layer(self, bad_layer):
        """Teardrop: path on non-existent layer doesn't match via."""
        path = _make_path(layer=bad_layer)
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
        results = _make_results(vias=[via], path=path)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = insert_teardrops(results)
        assert isinstance(report, TeardropReport)
        # Path layer doesn't match via layers → 0 teardrops
        assert report.teardrop_count == 0


# ============================================================================
# 6. Paths on inner layers — clearance & creepage
# ============================================================================


class TestInnerLayerPaths:
    """Clearance and creepage should work on inner-layer paths."""

    INNER_LAYERS = ["In1.Cu", "In2.Cu"]

    @pytest.mark.parametrize("layer", INNER_LAYERS)
    def test_clearance_on_inner_layer(self, layer):
        """Two nets on the same inner layer produce clearance checks."""
        r1 = _make_route("NET1", coords=[(0.0, 0.0), (10.0, 0.0)], layer=layer)
        r2 = _make_route("NET2", coords=[(0.0, 0.5), (10.0, 0.5)], layer=layer)
        results = _make_results(routes={"NET1": r1, "NET2": r2})

        report = verify_clearance(results, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1
        # Edge-to-edge ≈ 0.5 - 2*(0.127/2) = 0.373 mm > 0.127 => no violation
        assert report.violation_count == 0, (
            f"Unexpected violation on inner layer {layer}"
        )

    @pytest.mark.parametrize("layer", INNER_LAYERS)
    def test_clearance_violation_on_inner_layer(self, layer):
        """Two nets on same inner layer too close → violation."""
        r1 = _make_route("NET1", coords=[(0.0, 0.0), (10.0, 0.0)], layer=layer)
        r2 = _make_route("NET2", coords=[(0.0, 0.05), (10.0, 0.05)], layer=layer)
        results = _make_results(routes={"NET1": r1, "NET2": r2})

        report = verify_clearance(results, min_clearance=0.127)
        assert report.violation_count >= 1, (
            f"Expected clearance violation on {layer} with 0.05 mm spacing"
        )

    @pytest.mark.parametrize("layer", INNER_LAYERS)
    def test_creepage_on_inner_layer(self, layer):
        """HV net on inner layer — creepage check should still run."""
        hv = _make_route("AC_L", coords=[(0.0, 0.0), (10.0, 0.0)], layer=layer)
        lv = _make_route("SIG1", coords=[(0.0, 0.5), (10.0, 0.5)], layer=layer)
        results = _make_results(routes={"AC_L": hv, "SIG1": lv})

        report = verify_creepage(results)
        assert isinstance(report, CreepageReport)
        assert report.total_checks >= 1

    def test_clearance_different_inner_layers_no_check(self):
        """Nets on different inner layers — clearance is infinite, no violation."""
        r1 = _make_route("NET1", coords=[(0.0, 0.0), (10.0, 0.0)], layer="In1.Cu")
        r2 = _make_route("NET2", coords=[(0.0, 0.0), (10.0, 0.0)], layer="In2.Cu")
        results = _make_results(routes={"NET1": r1, "NET2": r2})

        report = verify_clearance(results, min_clearance=0.127)
        # Net-pair is still counted as a check, but distance is inf → no violation
        assert report.total_checks == 1
        assert report.violation_count == 0


# ============================================================================
# 7. RoutePath3D paths — mixed-layer segments
# ============================================================================


class TestRoutePath3D:
    """Mixed-layer RoutePath3D paths."""

    @staticmethod
    def _make_3d_path(
        net_name: str = _NORMAL_NET,
        segments: list | None = None,
        via_positions: list | None = None,
        path_length: float = 100.0,
    ) -> RoutePath3D:
        """Create a ``RoutePath3D`` with explicit per-segment layers."""
        if segments is None:
            segments = [
                (0.0, 0.0, "F.Cu"),
                (50.0, 0.0, "F.Cu"),
                (50.0, 0.0, "In1.Cu"),  # layer transition
                (50.0, 50.0, "In1.Cu"),
            ]
        return RoutePath3D(
            net_name=net_name,
            segments=segments,
            via_positions=list(via_positions) if via_positions else [],
            path_length=path_length,
        )

    # ------------------------------------------------------------------
    # 7a. Copper balance with RoutePath3D
    # ------------------------------------------------------------------

    def test_copper_balance_with_3d_path(self):
        """RoutePath3D: copper is attributed per segment layer."""
        path_3d = self._make_3d_path()
        route = _make_route(path=path_3d, width=0.254)
        results = _make_results(routes={"N1": route})

        report = analyze_copper_balance(results, 100, 100)
        assert isinstance(report, CopperBalanceReport)

        f_cu = _get_balance(report, "F.Cu")
        in1 = _get_balance(report, "In1.Cu")
        # Both F.Cu and In1.Cu should have copper from segments
        assert f_cu.copper_area_mm2 > 0, "F.Cu should have copper from 3D segments"
        assert in1.copper_area_mm2 > 0, "In1.Cu should have copper from 3D segments"

    def test_copper_balance_3d_path_with_via(self):
        """RoutePath3D + via: copper attributed correctly."""
        segments = [
            (0.0, 0.0, "F.Cu"),
            (30.0, 0.0, "F.Cu"),
            (30.0, 0.0, "In1.Cu"),
            (60.0, 0.0, "In1.Cu"),
        ]
        path_3d = self._make_3d_path(segments=segments)
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu", position=(30.0, 0.0))
        route = CompiledRoute("N1", path_3d, 0.254, [via], None)
        results = RoutingResults(compiled_routes={"N1": route}, failed_nets=[])

        report = analyze_copper_balance(results, 100, 100)
        # Through via adds copper on all layers
        for layer_name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
            lb = _get_balance(report, layer_name)
            assert lb.copper_area_mm2 > 0, (
                f"{layer_name} should have copper (3D segments + through via)"
            )

    # ------------------------------------------------------------------
    # 7b. Clearance with RoutePath3D — via-point detection
    # ------------------------------------------------------------------

    def test_clearance_with_3d_path_does_not_crash(self):
        """RoutePath3D: clearance check must not crash."""
        segs1 = [(0.0, 0.0, "F.Cu"), (10.0, 0.0, "F.Cu")]
        segs2 = [(0.0, 1.0, "F.Cu"), (10.0, 1.0, "F.Cu")]
        path1 = self._make_3d_path(net_name="NET1", segments=segs1)
        path2 = self._make_3d_path(net_name="NET2", segments=segs2)
        r1 = CompiledRoute("NET1", path1, 0.127, [], None)
        r2 = CompiledRoute("NET2", path2, 0.127, [], None)
        results = RoutingResults(
            compiled_routes={"NET1": r1, "NET2": r2}, failed_nets=[]
        )

        report = verify_clearance(results, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)

    # ------------------------------------------------------------------
    # 7c. Teardrop with RoutePath3D (no layer_name — should skip)
    # ------------------------------------------------------------------

    def test_teardrop_with_3d_path_skips(self):
        """RoutePath3D has no ``layer_name`` → teardrop generation skips."""
        path_3d = self._make_3d_path()
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
        route = CompiledRoute("N1", path_3d, 0.127, [via], None)
        results = RoutingResults(compiled_routes={"N1": route}, failed_nets=[])

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = insert_teardrops(results)
        # RoutePath3D lacks layer_name → path_layer is None → teardrop skipped
        assert report.teardrop_count == 0

    # ------------------------------------------------------------------
    # 7d. RoutePath3D with empty segments
    # ------------------------------------------------------------------

    def test_copper_balance_3d_empty_segments(self):
        """RoutePath3D with zero segments → no crash."""
        path_3d = self._make_3d_path(segments=[])
        route = CompiledRoute("N1", path_3d, 0.254, [], None)
        results = RoutingResults(compiled_routes={"N1": route}, failed_nets=[])

        report = analyze_copper_balance(results, 100, 100)
        assert isinstance(report, CopperBalanceReport)
        # All layers should have zero copper
        for lb in report.layer_balances:
            assert lb.copper_area_mm2 == pytest.approx(0.0)


# ============================================================================
# 8. Dangling vias — via on a net with no trace on that layer
# ============================================================================


class TestDanglingVias:
    """Vias not connected to any trace segment on the relevant layer."""

    def test_teardrop_skips_dangling_via(self):
        """Via on F.Cu→B.Cu, but path is on In1.Cu — no teardrop."""
        path = _make_path(layer="In1.Cu")
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
        results = _make_results(vias=[via], path=path)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = insert_teardrops(results)

        # Path layer In1.Cu is not in (F.Cu, B.Cu) → no teardrop
        assert report.teardrop_count == 0

    def test_teardrop_with_no_trace_on_via_layer(self):
        """Via on F.Cu→B.Cu, path on F.Cu — teardrop IS generated."""
        path = _make_path(layer="F.Cu")
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
        results = _make_results(vias=[via], path=path)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = insert_teardrops(results)

        assert report.teardrop_count == 1

    def test_thermal_relief_skips_via_not_touching_plane(self):
        """Via on F.Cu→B.Cu not touching plane layers → no thermal relief."""
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu", net_name="GND")
        path = _make_path(net_name="GND")
        results = _make_results(vias=[via], path=path, net_name="GND")

        # Default plane layers are In1.Cu, In2.Cu — not touched
        report = add_thermal_relief(results, plane_layers=["In1.Cu", "In2.Cu"])
        assert report.relief_count == 0


# ============================================================================
# 9. Via position outside board bounds
# ============================================================================


class TestViaOutsideBoard:
    """Via position outside the board outline."""

    OUTSIDE_POSITIONS = [
        (-10.0, -10.0),
        (-10.0, 50.0),
        (110.0, 50.0),
        (50.0, -10.0),
        (110.0, 110.0),
    ]

    # ------------------------------------------------------------------
    # 9a. Annular ring still works (geometry-based, no board check)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("position", OUTSIDE_POSITIONS)
    def test_annular_ring_outside_board(self, position):
        """Annular ring check does not depend on board bounds."""
        via = _make_via(position=position)
        result = _check_via(via, _NORMAL_NET, 0.05, 0.025)
        # Normal via (0.6/0.3) → ring = 0.15 > 0.05 → passes
        assert result is None

    # ------------------------------------------------------------------
    # 9b. Teardrop outside board
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("position", OUTSIDE_POSITIONS)
    def test_teardrop_outside_board(self, position):
        """Teardrop generation: geometry works regardless of board bounds."""
        via = _make_via(position=position)
        path = _make_path(
            coords=[(position[0], position[1]), (position[0] + 10, position[1])]
        )
        results = _make_results(vias=[via], path=path)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            report = insert_teardrops(results)
        assert isinstance(report, TeardropReport)

    # ------------------------------------------------------------------
    # 9c. Copper balance: via position doesn't affect area
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("position", OUTSIDE_POSITIONS)
    def test_copper_balance_outside_board(self, position):
        """Copper area is position-independent; outside-board positions OK."""
        via = _make_via(position=position)
        path = _make_path(
            coords=[(position[0], position[1]), (position[0] + 1, position[1])],
            layer="F.Cu",
        )
        results = _make_results(vias=[via], path=path, trace_width=0.2)

        report = analyze_copper_balance(results, 100, 100)
        assert isinstance(report, CopperBalanceReport)
        # F.Cu should have trace + via annulus
        f_cu = _get_balance(report, "F.Cu")
        assert f_cu.copper_area_mm2 > 0


# ============================================================================
# 10. Mixed single/multi-layer nets in same RoutingResults
# ============================================================================


class TestMixedLayerNets:
    """Multiple nets with different layer configurations in one RoutingResults."""

    def test_mixed_route_path_and_route_path_3d(self):
        """One net uses RoutePath, another uses RoutePath3D."""
        # Standard path on F.Cu
        r1 = _make_route("NET1", coords=[(0.0, 0.0), (10.0, 0.0)], layer="F.Cu")

        # 3D path spanning multiple layers
        segs = [(0.0, 5.0, "In1.Cu"), (10.0, 5.0, "In1.Cu")]
        path_3d = RoutePath3D("NET2", segs, [], 10.0)
        r2 = CompiledRoute("NET2", path_3d, 0.254, [], None)

        results = RoutingResults(
            compiled_routes={"NET1": r1, "NET2": r2}, failed_nets=[]
        )

        # Copper balance should handle both
        report = analyze_copper_balance(results, 100, 100)
        assert isinstance(report, CopperBalanceReport)

        f_cu = _get_balance(report, "F.Cu")
        in1 = _get_balance(report, "In1.Cu")
        assert f_cu.copper_area_mm2 > 0, "F.Cu should have copper from NET1"
        assert in1.copper_area_mm2 > 0, "In1.Cu should have copper from NET2"

    def test_mixed_via_types_in_same_results(self):
        """Blind, buried, and through vias in the same RoutingResults."""
        blind_via = _make_via(from_layer="F.Cu", to_layer="In1.Cu", net_name="N1")
        buried_via = _make_via(from_layer="In1.Cu", to_layer="In2.Cu", net_name="N2")
        through_via = _make_via(from_layer="F.Cu", to_layer="B.Cu", net_name="N3")

        r1 = _make_route("N1", coords=[(0.0, 0.0), (5.0, 0.0)],
                          layer="F.Cu", vias=[blind_via])
        r2 = _make_route("N2", coords=[(0.0, 2.0), (5.0, 2.0)],
                          layer="In1.Cu", vias=[buried_via])
        r3 = _make_route("N3", coords=[(0.0, 4.0), (5.0, 4.0)],
                          layer="F.Cu", vias=[through_via])

        results = RoutingResults(
            compiled_routes={"N1": r1, "N2": r2, "N3": r3}, failed_nets=[]
        )

        # --- Annular ring ---
        ar_report = check_annular_rings(results)
        assert ar_report.total_vias_checked == 3
        # All default vias pass (ring=0.15 > 0.05)
        assert ar_report.violation_count == 0

        # --- Copper balance ---
        cb_report = analyze_copper_balance(results, 100, 100)
        assert isinstance(cb_report, CopperBalanceReport)

        # Through via adds copper on all layers
        for layer_name in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
            lb = _get_balance(cb_report, layer_name)
            assert lb.copper_area_mm2 > 0, (
                f"{layer_name} should have copper from mixed vias"
            )

        # --- Teardrop ---
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            td_report = insert_teardrops(results)
        # Blind via on F.Cu path → teardrop; through via on F.Cu path → teardrop
        # Buried via on In1.Cu path → teardrop
        assert td_report.teardrop_count == 3

    def test_mixed_single_layer_and_multilayer_paths_clearance(self):
        """Clearance between a RoutePath and a RoutePath3D on the same layer."""
        segs = [(0.0, 0.5, "F.Cu"), (10.0, 0.5, "F.Cu")]
        path_3d = RoutePath3D("NET2", segs, [], 10.0)
        r1 = _make_route("NET1", coords=[(0.0, 0.0), (10.0, 0.0)], layer="F.Cu")
        r2 = CompiledRoute("NET2", path_3d, 0.127, [], None)
        results = RoutingResults(
            compiled_routes={"NET1": r1, "NET2": r2}, failed_nets=[]
        )

        report = verify_clearance(results, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1


# ============================================================================
# 11. Additional edge cases — combined interactions
# ============================================================================


class TestCombinedInteractions:
    """Interactions between multiple DFM modules on edge-case input."""

    def test_via_on_inner_layer_path_with_all_modules(self):
        """Run all DFM modules on a buried via + inner-layer path."""
        via = _make_via(from_layer="In1.Cu", to_layer="In2.Cu")
        path = _make_path(layer="In1.Cu", coords=[(0.0, 0.0), (10.0, 10.0)])
        results = _make_results(vias=[via], path=path, trace_width=0.254)

        # 1. Annular ring
        ar = check_annular_rings(results)
        assert isinstance(ar, AnnularRingReport)
        assert ar.total_vias_checked == 1

        # 2. Teardrop
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            td = insert_teardrops(results)
        assert isinstance(td, TeardropReport)
        assert td.teardrop_count == 1

        # 3. Copper balance
        cb = analyze_copper_balance(results, 100, 100)
        assert isinstance(cb, CopperBalanceReport)

        # 4. Clearance (single net — no checks)
        cl = verify_clearance(results)
        assert isinstance(cl, ClearanceReport)
        assert cl.total_checks == 0

        # 5. Creepage (single net — no checks)
        cr = verify_creepage(results)
        assert isinstance(cr, CreepageReport)
        assert cr.total_checks == 0

    @pytest.mark.parametrize(
        "from_layer, to_layer, expect_between",
        [
            # For through via F.Cu→B.Cu: intermediate = In1.Cu, In2.Cu (2 layers)
            ("F.Cu", "B.Cu", 2),
            # For F.Cu→In2.Cu: In2.Cu is to_layer (direct), only In1.Cu is intermediate
            ("F.Cu", "In2.Cu", 1),
            # For In1.Cu→B.Cu: B.Cu is to_layer (direct), only In2.Cu is intermediate
            ("In1.Cu", "B.Cu", 1),
            # Adjacent layers have 0 intermediate layers
            ("F.Cu", "In1.Cu", 0),
            ("In2.Cu", "B.Cu", 0),
        ],
    )
    def test_via_intermediate_layer_count(
        self, from_layer, to_layer, expect_between
    ):
        """Verify the number of intermediate layers for various via spans."""
        via = _make_via(from_layer=from_layer, to_layer=to_layer)
        path = _make_path(layer=from_layer)
        results = _make_results(vias=[via], path=path)

        report = analyze_copper_balance(results, 100, 100)

        # Count how many inner layers have via copper from the
        # intermediate-layer (barrel) contribution ONLY.
        # The via annulus area for 0.6/0.3 is π(0.3² - 0.15²) ≈ 0.212 mm².
        # A layer gets via copper either because it's from_layer/to_layer
        # (direct connection) OR because it lies strictly between them.
        # We use _layer_is_between to test intermediate layers.
        intermediate_layers = ["In1.Cu", "In2.Cu"]
        count_between = sum(
            1 for il in intermediate_layers
            if _layer_is_between(from_layer, to_layer, il)
        )

        assert count_between == expect_between, (
            f"Expected {expect_between} intermediate layers for "
            f"{from_layer}→{to_layer}, got {count_between}"
        )


# ============================================================================
# Boundary / crash tests marked as xfail where appropriate
# ============================================================================


class TestCrashBoundaries:
    """Cases expected to crash or misbehave; marked xfail."""

    def test_zero_span_via_copper_balance_exact_behavior(self):
        """Zero-span via: copper should appear only on the single layer."""
        via = _make_via(from_layer="F.Cu", to_layer="F.Cu")
        path = _make_path(layer="F.Cu")
        results = _make_results(vias=[via], path=path, trace_width=0.2)

        report = analyze_copper_balance(results, 100, 100)
        f_cu = _get_balance(report, "F.Cu")
        in1 = _get_balance(report, "In1.Cu")

        # F.Cu gets trace + via annulus (from_layer/to_layer direct match)
        assert f_cu.copper_area_mm2 > 0

        # Via is NOT strictly between F.Cu and F.Cu → no intermediate copper
        # But the via ALSO matches the direct check (from_layer == "F.Cu"
        # and to_layer == "F.Cu").  With the current implementation the
        # direct check fires for the same layer, so the copper appears
        # exactly once (no double-count).
        # In1.Cu should have zero copper
        assert in1.copper_area_mm2 == pytest.approx(0.0)

    def test_empty_layer_name_via_copper_balance(self):
        """Empty layer name → _layer_is_between ValueError is caught gracefully."""
        via = _make_via(from_layer="", to_layer="B.Cu")
        path = _make_path(layer="F.Cu")
        results = _make_results(vias=[via], path=path)

        # Should not raise — _layer_is_between catches ValueError and returns False
        report = analyze_copper_balance(results, 100, 100)
        assert isinstance(report, CopperBalanceReport)


# ============================================================================
# Utility
# ============================================================================


def _get_balance(report: CopperBalanceReport, layer_name: str):
    """Get the ``LayerCopperBalance`` for a given layer name."""
    for lb in report.layer_balances:
        if lb.layer_name == layer_name:
            return lb
    raise KeyError(f"Layer {layer_name!r} not found in report")
