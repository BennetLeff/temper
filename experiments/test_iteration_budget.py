"""
Test suite for adaptive A* iteration budget calculation.

Following TDD (Red-Green-Refactor):
1. RED: Write tests that fail
2. GREEN: Implement minimum code to pass
3. REFACTOR: Clean up and optimize

Pure function tests - no mocks needed!
"""

import pytest
from typing import Protocol


class CongestionLevel:
    """Will be implemented in routing/iteration_budget.py"""

    pass


class RoutingContext:
    """Will be implemented in routing/iteration_budget.py"""

    pass


class IterationBudget:
    """Will be implemented in routing/iteration_budget.py"""

    pass


class CongestionDetector(Protocol):
    """Will be implemented in routing/congestion.py"""

    pass


# ============================================================================
# Phase 1: RoutingContext Tests (Pure Functions)
# ============================================================================


def test_routing_context_manhattan_distance_simple():
    """GIVEN route from (0,0) to (10,5), WHEN calculating distance, THEN returns 15mm"""
    from temper_placer.routing.iteration_budget import RoutingContext

    context = RoutingContext(
        net_name="+5V",
        start=(0.0, 0.0),
        end=(10.0, 5.0),
        allowed_layers=(0, 1, 2, 3),
        net_class="PowerTrace",
    )

    assert context.manhattan_distance() == 15.0


def test_routing_context_manhattan_distance_negative_coords():
    """GIVEN route with negative coordinates, WHEN calculating, THEN returns absolute distance"""
    from temper_placer.routing.iteration_budget import RoutingContext

    context = RoutingContext(
        net_name="SPI_CLK",
        start=(-5.0, -10.0),
        end=(5.0, 10.0),
        allowed_layers=(0, 1),
        net_class="Signal",
    )

    assert context.manhattan_distance() == 30.0


def test_routing_context_immutability():
    """GIVEN RoutingContext, WHEN trying to modify, THEN raises error (frozen dataclass)"""
    from temper_placer.routing.iteration_budget import RoutingContext

    context = RoutingContext(
        net_name="GND", start=(0.0, 0.0), end=(1.0, 1.0), allowed_layers=(0,), net_class="Ground"
    )

    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        context.net_name = "PGND"


# ============================================================================
# Phase 2: IterationBudget.calculate() Tests (Core Logic)
# ============================================================================


def test_iteration_budget_low_congestion_short_route():
    """GIVEN 10mm route in LOW congestion area, WHEN calculating, THEN returns ~10k iterations"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context = RoutingContext(
        net_name="USB_D+",
        start=(0.0, 0.0),
        end=(10.0, 0.0),
        allowed_layers=(0, 1),
        net_class="Signal",
    )

    budget = IterationBudget.calculate(
        context=context, congestion=CongestionLevel.LOW, base_iterations_per_cell=100
    )

    # Expected: 10mm * 100 * 1.0 (LOW) * 1.5 (2 layers) * 1.0 (short) * 1.2 = 1,800
    # Clamped to min 5,000
    assert budget.max_iterations >= 5_000
    assert budget.max_iterations <= 20_000
    assert budget.congestion_factor == 1.0
    assert "LOW" in budget.reason or "low" in budget.reason


def test_iteration_budget_extreme_congestion_scales_8x():
    """GIVEN EXTREME vs LOW congestion, WHEN calculating, THEN 8x higher budget"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context = RoutingContext(
        net_name="SPI_CLK",
        start=(0.0, 0.0),
        end=(50.0, 0.0),
        allowed_layers=(0, 1, 2, 3),
        net_class="Signal",
    )

    budget_low = IterationBudget.calculate(context, CongestionLevel.LOW)
    budget_extreme = IterationBudget.calculate(context, CongestionLevel.EXTREME)

    assert budget_extreme.congestion_factor == 8.0
    assert budget_low.congestion_factor == 1.0
    assert (
        budget_extreme.max_iterations >= budget_low.max_iterations * 6
    )  # At least 6x (accounting for clamping)


def test_iteration_budget_multi_layer_increases_budget():
    """GIVEN 4-layer vs 1-layer route, WHEN calculating, THEN 2.5x more iterations"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context_1_layer = RoutingContext(
        net_name="GND", start=(0.0, 0.0), end=(20.0, 0.0), allowed_layers=(0,), net_class="Ground"
    )

    context_4_layer = RoutingContext(
        net_name="+5V",
        start=(0.0, 0.0),
        end=(20.0, 0.0),
        allowed_layers=(0, 1, 2, 3),
        net_class="PowerTrace",
    )

    budget_1 = IterationBudget.calculate(context_1_layer, CongestionLevel.MEDIUM)
    budget_4 = IterationBudget.calculate(context_4_layer, CongestionLevel.MEDIUM)

    assert budget_4.layer_factor == 2.5
    assert budget_1.layer_factor == 1.0
    assert budget_4.max_iterations >= budget_1.max_iterations * 2.0


def test_iteration_budget_long_distance_exponential_scaling():
    """GIVEN 100mm+ route, WHEN calculating, THEN applies 1.5x distance factor"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context_long = RoutingContext(
        net_name="+5V",
        start=(0.0, 0.0),
        end=(100.0, 50.0),  # 150mm Manhattan
        allowed_layers=(0, 1, 2, 3),
        net_class="PowerTrace",
    )

    context_short = RoutingContext(
        net_name="+5V",
        start=(0.0, 0.0),
        end=(10.0, 5.0),  # 15mm Manhattan
        allowed_layers=(0, 1, 2, 3),
        net_class="PowerTrace",
    )

    budget_long = IterationBudget.calculate(context_long, CongestionLevel.MEDIUM)
    budget_short = IterationBudget.calculate(context_short, CongestionLevel.MEDIUM)

    assert budget_long.distance_factor == 1.5
    assert budget_short.distance_factor == 1.0


def test_iteration_budget_clamped_to_max_1m():
    """GIVEN extreme parameters, WHEN calculating, THEN clamps to 1M max"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context = RoutingContext(
        net_name="EXTREME_NET",
        start=(0.0, 0.0),
        end=(200.0, 200.0),  # 400mm
        allowed_layers=(0, 1, 2, 3),
        net_class="Signal",
    )

    budget = IterationBudget.calculate(
        context=context,
        congestion=CongestionLevel.EXTREME,
        base_iterations_per_cell=1000,  # Very high base
    )

    assert budget.max_iterations <= 1_000_000


def test_iteration_budget_clamped_to_min_5k():
    """GIVEN very short route, WHEN calculating, THEN clamps to 5k min"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context = RoutingContext(
        net_name="SHORT",
        start=(0.0, 0.0),
        end=(1.0, 0.0),  # 1mm
        allowed_layers=(0,),
        net_class="Signal",
    )

    budget = IterationBudget.calculate(context, CongestionLevel.LOW, base_iterations_per_cell=10)

    assert budget.max_iterations >= 5_000


def test_iteration_budget_reason_contains_key_info():
    """GIVEN any calculation, WHEN generating reason, THEN includes distance, congestion, layers"""
    from temper_placer.routing.iteration_budget import (
        RoutingContext,
        IterationBudget,
        CongestionLevel,
    )

    context = RoutingContext(
        net_name="+3V3",
        start=(0.0, 0.0),
        end=(50.0, 30.0),
        allowed_layers=(0, 1, 2),
        net_class="PowerTrace",
    )

    budget = IterationBudget.calculate(context, CongestionLevel.HIGH)

    assert "dist" in budget.reason or "distance" in budget.reason
    assert "congestion" in budget.reason or "HIGH" in budget.reason or "high" in budget.reason
    assert "layer" in budget.reason or "3" in budget.reason
    assert str(budget.max_iterations) in budget.reason


# ============================================================================
# Phase 3: CongestionDetector Tests
# ============================================================================


def test_grid_congestion_detector_empty_grid_returns_low():
    """GIVEN empty grid, WHEN detecting congestion, THEN returns LOW"""
    from temper_placer.routing.adaptive_congestion import GridBasedCongestionDetector
    from temper_placer.routing.iteration_budget import CongestionLevel
    from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
    from temper_placer.core.units import Millimeters

    # Create empty grid (100mm x 100mm, 0.1mm cell size)
    grid = ClearanceGrid(width_mm=100.0, height_mm=100.0, cell_size_mm=0.1)
    detector = GridBasedCongestionDetector(grid=grid)

    congestion = detector.detect_congestion(
        point=(Millimeters(50.0), Millimeters(50.0)), radius=Millimeters(5.0)
    )

    assert congestion == CongestionLevel.LOW


def test_grid_congestion_detector_high_occupancy_returns_high():
    """GIVEN 70% blocked cells in area, WHEN detecting, THEN returns HIGH"""
    # This test will need actual grid blocking - may need to be integration test
    # For now, test the threshold logic with mock
    pytest.skip("Requires integration with real ClearanceGrid - will test in integration phase")


def test_component_detector_near_qfn_returns_extreme():
    """GIVEN point 3mm from U_MCU (QFN-56), WHEN detecting, THEN returns EXTREME"""
    from temper_placer.routing.adaptive_congestion import ComponentBasedCongestionDetector
    from temper_placer.routing.iteration_budget import CongestionLevel
    from temper_placer.core.units import Millimeters

    # Mock netlist with component positions
    class MockNetlist:
        def get_component_position(self, ref):
            if ref == "U_MCU":
                return (Millimeters(50.0), Millimeters(50.0))
            return None

    detector = ComponentBasedCongestionDetector(
        netlist=MockNetlist(), fine_pitch_components=frozenset({"U_MCU"})
    )

    # Point 3mm away from U_MCU
    congestion = detector.detect_congestion(
        point=(Millimeters(53.0), Millimeters(50.0)), radius=Millimeters(5.0)
    )

    assert congestion == CongestionLevel.EXTREME


def test_component_detector_far_from_components_returns_low():
    """GIVEN point 50mm from any component, WHEN detecting, THEN returns LOW"""
    from temper_placer.routing.adaptive_congestion import ComponentBasedCongestionDetector
    from temper_placer.routing.iteration_budget import CongestionLevel
    from temper_placer.core.units import Millimeters

    class MockNetlist:
        def get_component_position(self, ref):
            if ref == "U_MCU":
                return (Millimeters(0.0), Millimeters(0.0))
            return None

    detector = ComponentBasedCongestionDetector(
        netlist=MockNetlist(), fine_pitch_components=frozenset({"U_MCU"})
    )

    congestion = detector.detect_congestion(
        point=(Millimeters(100.0), Millimeters(100.0)), radius=Millimeters(5.0)
    )

    assert congestion == CongestionLevel.LOW


# ============================================================================
# Phase 4: Integration Tests (to be moved to validate_astar_improvements.py)
# ============================================================================


def test_real_board_spi_clk_calculation():
    """GIVEN real SPI_CLK route context, WHEN calculating budget, THEN reasonable value"""
    # This will be moved to integration tests
    pytest.skip("Integration test - run after implementation")


def test_real_board_v5_calculation():
    """GIVEN real +5V route context, WHEN calculating budget, THEN reasonable value"""
    pytest.skip("Integration test - run after implementation")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
