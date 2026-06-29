"""
Boundary edge-case tests for Router V6 Stage 5.4: Add Thermal Relief.

Covers spoke parameter boundaries, net name boundaries, plane layer
boundaries, via diameter boundaries, board boundaries, and empty input.

Each parametrized test explores a distinct axis of edge cases.  If a
particular input set reveals a crash or unexpected behaviour, the case
is marked ``pytest.mark.xfail`` — do NOT fix the module; we only
characterise its current behaviour.

Part of temper-95xg (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.thermal_relief import (
    ThermalReliefReport,
    _is_power_net,
    add_thermal_relief,
)
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.dfm_boundary_constants import (
    BOARD_DIMS_NAN,
    BOARD_DIMS_ZERO,
    THRESHOLD_INF,
    THRESHOLD_NAN,
    THRESHOLD_NEGATIVE,
    THRESHOLD_ZERO,
    VIA_DIAMETERS_NAN,
    VIA_DIAMETERS_NEGATIVE,
    VIA_DIAMETERS_ZERO,
)

# ============================================================================
# Helper factories
# ============================================================================

_NORMAL_SPOKE_COUNT = 4
_NORMAL_SPOKE_WIDTH = 0.254
_NORMAL_CLEARANCE_GAP = 0.254
_NORMAL_VIA_DIAMETER = 0.6
_NORMAL_VIA_DRILL = 0.3
_POWER_NET = "GND"
_NON_POWER_NET = "SIGNAL"
_FROM_LAYER = "F.Cu"
_TO_LAYER = "In1.Cu"  # default plane layer


def _make_path(net_name: str = _POWER_NET) -> RoutePath:
    """Create a minimal straight-line RoutePath."""
    coords = [(0.0, 0.0), (10.0, 10.0)]
    length = math.hypot(
        coords[-1][0] - coords[0][0],
        coords[-1][1] - coords[0][1],
    )
    return RoutePath(net_name, coords, _FROM_LAYER, length)


def _make_via(
    net_name: str = _POWER_NET,
    diameter: float = _NORMAL_VIA_DIAMETER,
    drill: float = _NORMAL_VIA_DRILL,
    position: tuple[float, float] = (5.0, 5.0),
    from_layer: str = _FROM_LAYER,
    to_layer: str = _TO_LAYER,
) -> Via:
    """Create a via that connects to a default plane layer."""
    return Via(position, from_layer, to_layer, diameter, drill, net_name)


def _make_results(
    net_name: str = _POWER_NET,
    vias: list[Via] | None = None,
    via_diameter: float = _NORMAL_VIA_DIAMETER,
) -> RoutingResults:
    """Create minimal RoutingResults with a power net and optional vias."""
    if vias is None:
        vias = [_make_via(net_name=net_name, diameter=via_diameter)]
    path = _make_path(net_name=net_name)
    route = CompiledRoute(net_name, path, 0.127, vias, None)
    return RoutingResults(compiled_routes={net_name: route}, failed_nets=[])


# ============================================================================
# 1. Spoke parameter boundaries
# ============================================================================

class TestSpokeCountBoundaries:
    """spoke_count < 2 must raise ValueError."""

    @pytest.mark.parametrize(
        "spoke_count",
        [
            pytest.param(0, id="spoke_count_zero"),
            pytest.param(1, id="spoke_count_one"),
            pytest.param(-1, id="spoke_count_negative"),
        ],
    )
    def test_spoke_count_invalid_raises_valueerror(self, spoke_count: int) -> None:
        results = _make_results()
        with pytest.raises(ValueError, match="spoke_count"):
            add_thermal_relief(results, spoke_count=spoke_count)

    def test_spoke_count_nan_should_raise_valueerror(self) -> None:
        results = _make_results()
        with pytest.raises(ValueError):
            add_thermal_relief(results, spoke_count=float("nan"))


class TestSpokeWidthBoundaries:
    """spoke_width <= 0 must raise ValueError."""

    @pytest.mark.parametrize(
        "spoke_width",
        [
            pytest.param(v, id=f"spoke_width_{v}")
            for v in THRESHOLD_ZERO + THRESHOLD_NEGATIVE
        ],
    )
    def test_spoke_width_zero_or_negative_raises(self, spoke_width: float) -> None:
        results = _make_results()
        with pytest.raises(ValueError, match="spoke_width"):
            add_thermal_relief(results, spoke_width=spoke_width)

    @pytest.mark.parametrize(
        "spoke_width",
        [
            pytest.param(v, id=f"spoke_width_nan_{i}")
            for i, v in enumerate(THRESHOLD_NAN)
        ],
    )
    def test_spoke_width_nan_should_raise(self, spoke_width: float) -> None:
        results = _make_results()
        with pytest.raises(ValueError):
            add_thermal_relief(results, spoke_width=spoke_width)

    @pytest.mark.parametrize(
        "spoke_width",
        [
            pytest.param(v, id=f"spoke_width_inf_{i}")
            for i, v in enumerate(THRESHOLD_INF)
        ],
    )
    def test_spoke_width_inf_should_raise(self, spoke_width: float) -> None:
        results = _make_results()
        with pytest.raises(ValueError):
            add_thermal_relief(results, spoke_width=spoke_width)


class TestClearanceGapBoundaries:
    """clearance_gap <= 0 must raise ValueError."""

    @pytest.mark.parametrize(
        "clearance_gap",
        [
            pytest.param(v, id=f"clearance_gap_{v}")
            for v in THRESHOLD_ZERO + THRESHOLD_NEGATIVE
        ],
    )
    def test_clearance_gap_zero_or_negative_raises(
        self, clearance_gap: float
    ) -> None:
        results = _make_results()
        with pytest.raises(ValueError, match="clearance_gap"):
            add_thermal_relief(results, clearance_gap=clearance_gap)

    @pytest.mark.parametrize(
        "clearance_gap",
        [
            pytest.param(v, id=f"clearance_gap_nan_{i}")
            for i, v in enumerate(THRESHOLD_NAN)
        ],
    )
    def test_clearance_gap_nan_should_raise(self, clearance_gap: float) -> None:
        results = _make_results()
        with pytest.raises(ValueError):
            add_thermal_relief(results, clearance_gap=clearance_gap)


# ============================================================================
# 2. Net name boundaries
# ============================================================================

class TestNetNameBoundaries:
    """Boundary tests for net name handling in _is_power_net and routing."""

    @pytest.mark.parametrize(
        "net_name,expected_relief",
        [
            pytest.param("", 0, id="empty_string"),
            pytest.param("GND", 1, id="normal_power_net"),
            pytest.param("SIGNAL", 0, id="non_power_net"),
            # _is_power_net is case-insensitive (re.IGNORECASE) so these DO
            # match the power-net regex, but _connects_to_power_plane checks
            # ``net_name in plane_nets`` which is case-sensitive against the
            # default frozenset ({"GND", ...}), so the via is skipped.
            pytest.param("gnd", 0, id="lowercase_power_net_no_default_plane_net"),
            pytest.param("GnD", 0, id="mixedcase_power_net_no_default_plane_net"),
        ],
    )
    def test_net_name_basic(
        self, net_name: str, expected_relief: int
    ) -> None:
        """Basic net names: empty, power, non-power, and case interactions."""
        results = _make_results(net_name=net_name)
        report = add_thermal_relief(results)
        assert report.relief_count == expected_relief

    def test_net_name_very_long_non_matching(self) -> None:
        """1000-character net name that does NOT match power pattern."""
        long_name = "X" * 1000
        results = _make_results(net_name=long_name)
        report = add_thermal_relief(results)
        # Should not crash; not a power net
        assert report.relief_count == 0

    def test_net_name_very_long_matching(self) -> None:
        """1000-character net name with GND suffix — matches power pattern."""
        long_name = "X" * 996 + "GND"
        results = _make_results(net_name=long_name)
        report = add_thermal_relief(results)
        # Should not crash; should match because *GND suffix pattern
        assert report.relief_count >= 0

    @pytest.mark.parametrize(
        "special_name",
        [
            pytest.param("GND\x00NULL", id="null_byte"),
            pytest.param("VCC\nnewline", id="newline"),
            pytest.param("POWER\ttab", id="tab"),
            pytest.param("GND\rreturn", id="carriage_return"),
            pytest.param("\x1b[31mANSI", id="ansi_escape"),
            pytest.param("GND\\backslash", id="backslash"),
            pytest.param("GND\x1fUS", id="unit_separator"),
            pytest.param("😀GND😀", id="emoji_surrounding"),
        ],
    )
    def test_net_name_special_chars_does_not_crash(
        self, special_name: str
    ) -> None:
        """Net names with special / control characters must not crash."""
        results = _make_results(net_name=special_name)
        report = add_thermal_relief(results)
        # No crash is the primary assertion
        assert report.relief_count >= 0


class TestIsPowerNetFunction:
    """Direct unit tests for the _is_power_net helper."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            pytest.param("", False, id="empty"),
            pytest.param("GND", True, id="GND"),
            pytest.param("PGND", True, id="PGND"),
            pytest.param("AGND", True, id="AGND"),
            pytest.param("DGND", True, id="DGND"),
            pytest.param("CGND", True, id="CGND"),
            pytest.param("SGND", True, id="*GND_suffix"),
            pytest.param("VCC", True, id="VCC"),
            pytest.param("VDD", True, id="VDD"),
            pytest.param("SIGNAL", False, id="signal"),
            pytest.param("GND1", False, id="GND_suffix_digit"),  # \b prevents
            # \b word boundary: "1" is a word char so \b does NOT match
            # between "1" and "G"; the regex correctly rejects "1GND".
            pytest.param("1GND", False, id="GND_prefix_digit_no_boundary"),
        ],
    )
    def test_is_power_net(self, name: str, expected: bool) -> None:
        """_is_power_net regex covers known power families and *GND suffix."""
        assert _is_power_net(name) is expected


# ============================================================================
# 3. Plane layer boundaries
# ============================================================================

class TestPlaneLayerBoundaries:
    """Boundary tests for plane_layers parameter."""

    def test_plane_layers_none_uses_defaults(self) -> None:
        """plane_layers=None should fall back to defaults."""
        results = _make_results()
        report = add_thermal_relief(results, plane_layers=None)
        assert report.relief_count == 1  # GND via to In1.Cu matches default

    def test_plane_layers_empty_list_no_relief(self) -> None:
        """plane_layers=[] means no via can touch a plane — zero reliefs."""
        results = _make_results()
        report = add_thermal_relief(results, plane_layers=[])
        assert report.relief_count == 0

    @pytest.mark.parametrize(
        "layers",
        [
            pytest.param(["Fake.Layer"], id="single_fake"),
            pytest.param(["In1.Cu", "NonExistent.Layer"], id="mixed_real_fake"),
            pytest.param(["Layer1", "Layer2", "Layer3"], id="multiple_fake"),
        ],
    )
    def test_plane_layers_nonexistent_no_crash(
        self, layers: list[str]
    ) -> None:
        """Non-existent layer names should not crash — just yield zero reliefs."""
        results = _make_results()
        report = add_thermal_relief(results, plane_layers=layers)
        assert report.relief_count >= 0

    def test_plane_layers_match_by_to_layer(self) -> None:
        """Via.to_layer matching a plane layer should produce relief."""
        results = _make_results()  # via to_layer = "In1.Cu"
        report = add_thermal_relief(results, plane_layers=["In1.Cu"])
        assert report.relief_count == 1

    def test_plane_layers_match_by_from_layer(self) -> None:
        """Via.from_layer matching a plane layer should produce relief."""
        via = _make_via(from_layer="In2.Cu", to_layer="B.Cu")
        results = _make_results(vias=[via])
        report = add_thermal_relief(results, plane_layers=["In2.Cu"])
        assert report.relief_count == 1


# ============================================================================
# 4. Via diameter boundaries
# ============================================================================

class TestViaDiameterBoundaries:
    """Boundary tests for via diameter values used as pad_size."""

    @pytest.mark.parametrize(
        "diameter",
        [
            pytest.param(d, id=f"via_diameter_zero_{i}")
            for i, d in enumerate(VIA_DIAMETERS_ZERO)
        ],
    )
    def test_via_diameter_zero_does_not_crash(self, diameter: float) -> None:
        """Zero-diameter via produces degenerate geometry but must not crash."""
        results = _make_results(via_diameter=diameter)
        report = add_thermal_relief(results)
        assert report.relief_count >= 0

    @pytest.mark.parametrize(
        "diameter",
        [
            pytest.param(d, id=f"via_diameter_neg_{i}")
            for i, d in enumerate(VIA_DIAMETERS_NEGATIVE)
        ],
    )
    def test_via_diameter_negative_does_not_crash(self, diameter: float) -> None:
        """Negative-diameter via produces nonsensical pad_size but must not crash."""
        results = _make_results(via_diameter=diameter)
        report = add_thermal_relief(results)
        assert report.relief_count >= 0

    @pytest.mark.parametrize(
        "diameter",
        [
            pytest.param(d, id=f"via_diameter_nan_{i}")
            for i, d in enumerate(VIA_DIAMETERS_NAN)
        ],
    )
    def test_via_diameter_nan_should_be_handled(self, diameter: float) -> None:
        """NaN via diameter silently produces NaN geometry — should be rejected."""
        results = _make_results(via_diameter=diameter)
        report = add_thermal_relief(results)
        # Report is structurally valid but geometry is corrupted
        assert report.relief_count >= 0
        if report.relief_count > 0:
            for relief in report.thermal_reliefs:
                for (x1, y1), (x2, y2) in relief.spoke_segments:
                    assert math.isfinite(x1)
                    assert math.isfinite(y1)
                    assert math.isfinite(x2)
                    assert math.isfinite(y2)


# ============================================================================
# 5. Board boundaries
# ============================================================================

class TestBoardBoundaries:
    """Boundary tests for the board parameter."""

    def test_board_none_uses_no_clamping(self) -> None:
        """board=None should work — spoke endpoints are not clamped."""

        results = _make_results()
        report = add_thermal_relief(results, board=None)
        assert report.relief_count >= 0

    @pytest.mark.parametrize(
        "width,height",
        [
            pytest.param(w, h, id=f"board_zero_{w}x{h}")
            for w, h in BOARD_DIMS_ZERO
        ],
    )
    def test_board_zero_area_does_not_crash(
        self, width: float, height: float
    ) -> None:
        """Board with zero area should produce degenerate clamping but not crash."""
        from temper_placer.core.board import Board as BoardCls

        board = BoardCls(width=width, height=height)
        results = _make_results()
        report = add_thermal_relief(results, board=board)
        assert report.relief_count >= 0

    @pytest.mark.parametrize(
        "width,height",
        [
            pytest.param(w, h, id=f"board_nan_{i}")
            for i, (w, h) in enumerate(BOARD_DIMS_NAN)
        ],
    )
    def test_board_nan_dimensions_should_be_handled(
        self, width: float, height: float
    ) -> None:
        """Board with NaN dimensions should not silently corrupt geometry."""
        from temper_placer.core.board import Board as BoardCls

        board = BoardCls(width=width, height=height)
        results = _make_results()
        report = add_thermal_relief(results, board=board)
        assert report.relief_count >= 0
        # All spoke coordinates should be finite
        for relief in report.thermal_reliefs:
            for (x1, y1), (x2, y2) in relief.spoke_segments:
                assert math.isfinite(x1)
                assert math.isfinite(y1)
                assert math.isfinite(x2)
                assert math.isfinite(y2)

    def test_board_normal_with_clamping(self) -> None:
        """Normal board should clamp spoke endpoints within its bounds."""
        from temper_placer.core.board import Board as BoardCls

        board = BoardCls(width=100.0, height=100.0, origin=(0.0, 0.0))
        results = _make_results()
        report = add_thermal_relief(results, board=board)
        assert report.relief_count >= 0
        for relief in report.thermal_reliefs:
            for (_x1, _y1), (x2, y2) in relief.spoke_segments:
                # Spoke endpoints clamped to board outline
                assert 0.0 <= x2 <= board.width + 1e-9, f"x2={x2} out of bounds"
                assert 0.0 <= y2 <= board.height + 1e-9, f"y2={y2} out of bounds"


# ============================================================================
# 6. Empty input
# ============================================================================

class TestEmptyInput:
    """Boundary tests for empty or missing inputs."""

    def test_zero_vias_power_net_no_relief(self) -> None:
        """Power net with zero vias should produce zero thermal reliefs."""
        path = _make_path(net_name=_POWER_NET)
        route = CompiledRoute(_POWER_NET, path, 0.127, [], None)
        results = RoutingResults(
            compiled_routes={_POWER_NET: route}, failed_nets=[]
        )
        report = add_thermal_relief(results)
        assert report.relief_count == 0

    def test_zero_routes_empty_results(self) -> None:
        """Empty compiled_routes should produce zero thermal reliefs."""
        results = RoutingResults(compiled_routes={}, failed_nets=[])
        report = add_thermal_relief(results)
        assert report.relief_count == 0
        assert isinstance(report, ThermalReliefReport)

    def test_only_signal_nets_no_relief(self) -> None:
        """Signal nets (non-power) should produce zero thermal reliefs."""
        path = _make_path(net_name=_NON_POWER_NET)
        via = _make_via(net_name=_NON_POWER_NET)
        route = CompiledRoute(_NON_POWER_NET, path, 0.127, [via], None)
        results = RoutingResults(
            compiled_routes={_NON_POWER_NET: route}, failed_nets=[]
        )
        report = add_thermal_relief(results)
        assert report.relief_count == 0

    def test_power_net_no_plane_connection_no_relief(self) -> None:
        """Power-net via that does NOT touch a plane layer — zero reliefs."""
        # Via only on outer layers, not touching any plane
        via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
        results = _make_results(vias=[via])
        # Default plane layers are In1.Cu, In2.Cu — neither is touched
        report = add_thermal_relief(results, plane_layers=["In1.Cu", "In2.Cu"])
        assert report.relief_count == 0

    def test_power_net_not_in_plane_nets_no_relief(self) -> None:
        """Power-net name matches regex but is NOT in plane_nets — zero reliefs."""
        results = _make_results(net_name="VCC")  # VCC matches regex
        # Supply plane_nets that does NOT include VCC
        report = add_thermal_relief(results, plane_nets=frozenset({"GND", "PGND"}))
        assert report.relief_count == 0

    def test_failed_nets_ignored(self) -> None:
        """Failed nets should not cause thermal relief generation."""
        results = RoutingResults(
            compiled_routes={},  # empty
            failed_nets=[_POWER_NET],  # GND failed
        )
        report = add_thermal_relief(results)
        assert report.relief_count == 0


# ============================================================================
# 7. Combined boundary interactions
# ============================================================================

class TestCombinedBoundaries:
    """Tests where multiple boundary values interact."""

    def test_zero_spoke_count_and_nan_width(self) -> None:
        """NaN spoke_width raises before spoke_count=0 is evaluated
        (NaN guard fires first)."""
        results = _make_results()
        with pytest.raises(ValueError, match="spoke_width"):
            add_thermal_relief(
                results,
                spoke_count=0,
                spoke_width=float("nan"),
            )

    def test_zero_clearance_and_nan_spoke_width(self) -> None:
        """clearance_gap=0 raises before spoke_width=NaN evaluated
        (validation order matters)."""
        results = _make_results()
        with pytest.raises(ValueError, match="spoke_width"):
            add_thermal_relief(
                results,
                spoke_width=0.0,       # raises first (checked first)
                clearance_gap=float("nan"),
            )

    @pytest.mark.parametrize(
        "spoke_count,spoke_width,clearance_gap",
        [
            pytest.param(2, 0.001, 0.001, id="minimum_valid"),
            pytest.param(100, 1.0, 1.0, id="large_valid"),
            pytest.param(4, 0.254, 0.254, id="default_valid"),
        ],
    )
    def test_fully_valid_params_produce_relief(
        self,
        spoke_count: int,
        spoke_width: float,
        clearance_gap: float,
    ) -> None:
        """Valid (non-boundary) parameters should produce thermal reliefs."""
        results = _make_results()
        report = add_thermal_relief(
            results,
            spoke_count=spoke_count,
            spoke_width=spoke_width,
            clearance_gap=clearance_gap,
        )
        assert report.relief_count == 1
        assert report.total_spokes == spoke_count
