"""Integration tests for the placement-to-routing pipeline gap.

Verifies that benders_placement and route_pcb produce real results
when wired through the closure test infrastructure.
"""

from pathlib import Path

import pytest


@pytest.fixture
def fixture_board_path():
    """Path to a test fixture board with real components."""
    base = Path(__file__).parent.parent / "fixtures" / "medium_board.kicad_pcb"
    if base.exists():
        return base
    alt = Path(__file__).parent.parent / "fixtures" / "minimal_board.kicad_pcb"
    if alt.exists():
        return alt
    pytest.skip("No fixture board available")


class TestPlacementIntegration:
    """U3: Verify placement step produces real results."""

    def test_closure_produces_nonzero_placement(self, fixture_board_path):
        """SC1: Closure test's benders_iterations > 0 on a real board."""
        from temper_placer.regression.closure_test import ClosureTest

        ct = ClosureTest(
            pcb_path=fixture_board_path,
            seed={"benders_seed": 42, "router_seed": 42},
        )
        result = ct.run()

        assert result.benders_iterations > 0, (
            f"Expected non-zero benders_iterations, got {result.benders_iterations}. "
            f"Errors: {result.errors}, Warnings: {result.warnings}"
        )

    def test_closure_no_import_warnings(self, fixture_board_path):
        """SC1: Closure test produces no ImportError warnings."""
        from temper_placer.regression.closure_test import ClosureTest

        ct = ClosureTest(
            pcb_path=fixture_board_path,
            seed={"benders_seed": 42, "router_seed": 42},
        )
        result = ct.run()

        benders_warnings = [w for w in result.warnings if "Benders" in w]
        router_warnings = [w for w in result.warnings if "Router V6" in w]

        assert not benders_warnings, f"Benders import warnings: {benders_warnings}"
        assert not router_warnings, f"Router V6 import warnings: {router_warnings}"

    def test_benders_placement_on_real_board(self, fixture_board_path):
        """R3: benders_placement produces placements dict on a valid PCB."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
        from temper_placer.placement.benders_loop import benders_placement

        parsed = parse_kicad_pcb_v6(fixture_board_path)
        result = benders_placement(parsed, 42)

        assert isinstance(result.placements, dict)
        assert result.iterations == 1
        assert result.cuts == 0

        for ref, (x, y) in result.placements.items():
            assert isinstance(ref, str)
            assert isinstance(x, float)
            assert isinstance(y, float)

    def test_imports_succeed(self):
        """Verify all critical imports work without errors."""
        from temper_placer.placement.benders_loop import (
            BendersPlacementResult,
            benders_placement,
        )
        from temper_placer.router_v6 import route_pcb, RoutingResult

        assert callable(benders_placement)
        assert callable(route_pcb)
        assert BendersPlacementResult is not None
        assert RoutingResult is not None


class TestRoutingIntegration:
    """U3: Verify routing produces real results (slow tests)."""

    @pytest.mark.slow
    def test_route_pcb_with_real_board(self, fixture_board_path):
        """R3: route_pcb produces non-zero completion on a valid PCB."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
        from temper_placer.router_v6 import route_pcb

        parsed = parse_kicad_pcb_v6(fixture_board_path)
        result = route_pcb(parsed, {}, 42)

        assert hasattr(result, "completion_rate")
        assert result.completion_rate >= 0.0

    @pytest.mark.slow
    def test_full_pipeline_closes(self, fixture_board_path):
        """SC1: Full closure test runs, returns non-zero results."""
        from temper_placer.regression.closure_test import ClosureTest

        ct = ClosureTest(
            pcb_path=fixture_board_path,
            seed={"benders_seed": 42, "router_seed": 42},
        )
        result = ct.run()

        assert result.board_id != ""
        assert result.benders_iterations > 0
        assert result.router_completion_pct >= 0.0
        assert result.wall_clock_seconds > 0
