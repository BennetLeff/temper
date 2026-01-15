"""
Tests for Benders Loop Orchestration.

The loop coordinates the Master Problem (ILP), Subproblem (Max-Flow),
and cut generation to find a provably routable placement.
"""

import pytest
from temper_placer.placement.benders_loop import (
    BendersOptimizer,
    BendersResult,
    BendersStatus,
)


class TestBendersOptimizer:
    """Test suite for Benders loop orchestration."""

    @pytest.fixture
    def simple_input_json(self, tmp_path):
        """Create a simple test input JSON file."""
        import json

        data = {
            "board": {"width_mm": 100, "height_mm": 100},
            "coordinate_system": "center",
            "hv_nets": [],
            "components": [
                {
                    "ref": "U1",
                    "width_mm": 10.0,
                    "height_mm": 5.0,
                    "center_x_mm": 20.0,
                    "center_y_mm": 50.0,
                    "classification": "FREE",
                    "hv_nets": [],
                },
                {
                    "ref": "U2",
                    "width_mm": 10.0,
                    "height_mm": 5.0,
                    "center_x_mm": 40.0,
                    "center_y_mm": 50.0,
                    "classification": "FREE",
                    "hv_nets": [],
                },
                {
                    "ref": "U3",
                    "width_mm": 10.0,
                    "height_mm": 5.0,
                    "center_x_mm": 60.0,
                    "center_y_mm": 50.0,
                    "classification": "FREE",
                    "hv_nets": [],
                },
            ],
        }

        json_file = tmp_path / "test_input.json"
        with open(json_file, "w") as f:
            json.dump(data, f)

        return str(json_file)

    def test_optimizer_creation(self, simple_input_json):
        """Test creating a Benders optimizer."""
        optimizer = BendersOptimizer(
            component_data_json=simple_input_json, max_iterations=10
        )

        assert optimizer.max_iterations == 10
        assert optimizer.current_iteration == 0

    def test_run_without_routability_check(self, simple_input_json):
        """Test running optimizer without routability checking (Master only)."""
        optimizer = BendersOptimizer(
            component_data_json=simple_input_json,
            max_iterations=1,
            check_routability=False,
        )

        result = optimizer.optimize()

        assert result.status in (BendersStatus.OPTIMAL, BendersStatus.FEASIBLE)
        assert result.iterations == 1
        assert len(result.final_positions) > 0
        assert result.total_movement >= 0

    def test_iteration_tracking(self, simple_input_json):
        """Test that iterations are tracked correctly."""
        optimizer = BendersOptimizer(
            component_data_json=simple_input_json, max_iterations=5
        )

        # Mock routability check to always return infeasible
        # This forces max iterations
        def mock_infeasible(*args, **kwargs):
            class MockResult:
                is_feasible = False
                min_cut_edges = [
                    (("F.Cu", (30.0, 45.0)), ("F.Cu", (30.0, 55.0)), 0),
                ]

            return MockResult()

        optimizer._check_routability = mock_infeasible

        result = optimizer.optimize()

        assert result.iterations == 5
        assert result.status == BendersStatus.MAX_ITERATIONS

    def test_infeasible_master_problem(self):
        """Test handling of infeasible Master Problem."""
        # Create conflicting constraints
        import json
        import tempfile

        data = {
            "board": {"width_mm": 20, "height_mm": 20},  # Very small board
            "coordinate_system": "center",
            "hv_nets": [],
            "components": [
                {
                    "ref": "U1",
                    "width_mm": 15.0,
                    "height_mm": 15.0,  # Too large for board
                    "center_x_mm": 10.0,
                    "center_y_mm": 10.0,
                    "classification": "FREE",
                    "hv_nets": [],
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            json_file = f.name

        optimizer = BendersOptimizer(json_file, max_iterations=1)
        result = optimizer.optimize()

        assert result.status == BendersStatus.INFEASIBLE

    def test_convergence_on_routable_placement(self):
        """Test that optimizer converges when placement is routable."""
        # This is a mock test - actual test would require Max-Flow integration
        pass

    def test_result_data_structure(self, simple_input_json):
        """Test BendersResult contains all required data."""
        optimizer = BendersOptimizer(
            simple_input_json, max_iterations=1, check_routability=False
        )
        result = optimizer.optimize()

        assert hasattr(result, "status")
        assert hasattr(result, "iterations")
        assert hasattr(result, "final_positions")
        assert hasattr(result, "total_movement")
        assert hasattr(result, "cuts_added")
        assert hasattr(result, "solve_time_sec")

        assert isinstance(result.status, BendersStatus)
        assert isinstance(result.iterations, int)
        assert isinstance(result.final_positions, dict)
        assert isinstance(result.total_movement, float)
        assert isinstance(result.cuts_added, list)
        assert isinstance(result.solve_time_sec, float)


class TestBendersStatus:
    """Test BendersStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert hasattr(BendersStatus, "OPTIMAL")
        assert hasattr(BendersStatus, "FEASIBLE")
        assert hasattr(BendersStatus, "INFEASIBLE")
        assert hasattr(BendersStatus, "MAX_ITERATIONS")
        assert hasattr(BendersStatus, "ERROR")


class TestCutManagement:
    """Test cut addition and tracking."""

    def test_cuts_are_tracked(self, simple_input_json):
        """Test that added cuts are tracked."""
        optimizer = BendersOptimizer(simple_input_json, max_iterations=1)

        # Mock to add a cut manually
        from temper_placer.placement.benders_cut_generator import (
            RoutabilityCut,
            CutType,
        )

        cut = RoutabilityCut(CutType.HORIZONTAL, ("U1", "U2"), 5.0, iteration=0)
        optimizer._add_cut(cut)

        assert len(optimizer.cuts_history) == 1
        assert optimizer.cuts_history[0] == cut

    def test_cuts_applied_to_master(self):
        """Test that cuts are applied to the Master Problem."""
        # Mock test - requires Master Problem integration
        pass


class TestIntegrationWithComponents:
    """Integration tests with real components."""

    def test_with_temper_data(self):
        """Test with actual Temper board data."""
        # This would use the real benders_input.json
        pass

    def test_power_stage_bottleneck_resolution(self):
        """Test resolving power stage routing bottleneck."""
        # Realistic scenario: Q1, Q2 too close causing congestion
        pass
