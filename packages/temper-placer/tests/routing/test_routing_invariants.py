"""
Tests for routing invariant checks.
"""

import pytest
import jax.numpy as jnp
from temper_placer.routing.maze_router import GridCell, MazeRouter, RoutePath
from temper_placer.routing.routing_invariants import (
    InvariantViolation,
    RoutingInvariantError,
    validate_path_connectivity,
    validate_endpoints,
    validate_no_blocked_cells,
    validate_within_bounds,
    validate_route_result,
    validate_no_overlaps,
    format_violations,
)


class TestValidatePathConnectivity:
    """Tests for path connectivity validation."""
    
    def test_empty_path(self):
        """Empty path should pass."""
        assert validate_path_connectivity([]) == []
    
    def test_single_cell(self):
        """Single cell path should pass."""
        path = [GridCell(5, 5, 0)]
        assert validate_path_connectivity(path) == []
    
    def test_valid_horizontal_path(self):
        """Horizontal path should pass."""
        path = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        assert validate_path_connectivity(path) == []
    
    def test_valid_vertical_path(self):
        """Vertical path should pass."""
        path = [GridCell(0, 0, 0), GridCell(0, 1, 0), GridCell(0, 2, 0)]
        assert validate_path_connectivity(path) == []
    
    def test_valid_layer_change(self):
        """Layer transition should pass."""
        path = [GridCell(5, 5, 0), GridCell(5, 5, 1), GridCell(5, 6, 1)]
        assert validate_path_connectivity(path) == []
    
    def test_valid_complex_path(self):
        """Complex path with turns should pass."""
        path = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),
            GridCell(1, 1, 0),
            GridCell(1, 1, 1),  # via
            GridCell(2, 1, 1),
        ]
        assert validate_path_connectivity(path) == []
    
    def test_invalid_diagonal(self):
        """Diagonal move should fail."""
        path = [GridCell(0, 0, 0), GridCell(1, 1, 0)]
        violations = validate_path_connectivity(path)
        assert len(violations) == 1
        assert violations[0].invariant == "path_connectivity"
    
    def test_invalid_gap(self):
        """Gap in path should fail."""
        path = [GridCell(0, 0, 0), GridCell(3, 0, 0)]
        violations = validate_path_connectivity(path)
        assert len(violations) == 1
    
    def test_invalid_double_move(self):
        """Moving in two dimensions at once should fail."""
        path = [GridCell(0, 0, 0), GridCell(1, 0, 1)]  # x and layer
        violations = validate_path_connectivity(path)
        assert len(violations) == 1


class TestValidateEndpoints:
    """Tests for endpoint validation."""
    
    def test_valid_endpoints(self):
        """Correct endpoints should pass."""
        path = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        assert validate_endpoints(path, (0, 0), (2, 0)) == []
    
    def test_empty_path(self):
        """Empty path should fail."""
        violations = validate_endpoints([], (0, 0), (5, 5))
        assert len(violations) == 1
    
    def test_wrong_start(self):
        """Wrong start should fail."""
        path = [GridCell(1, 0, 0), GridCell(2, 0, 0)]
        violations = validate_endpoints(path, (0, 0), (2, 0))
        assert len(violations) == 1
        assert "starts" in violations[0].message
    
    def test_wrong_end(self):
        """Wrong end should fail."""
        path = [GridCell(0, 0, 0), GridCell(1, 0, 0)]
        violations = validate_endpoints(path, (0, 0), (5, 0))
        assert len(violations) == 1
        assert "ends" in violations[0].message
    
    def test_different_layers_ok(self):
        """Endpoints on different layers should still pass (x,y match)."""
        path = [GridCell(0, 0, 0), GridCell(0, 0, 1), GridCell(1, 0, 1)]
        assert validate_endpoints(path, (0, 0), (1, 0)) == []


class TestValidateNoBlockedCells:
    """Tests for blocked cell validation."""
    
    def test_empty_path(self):
        """Empty path should pass."""
        occupancy = jnp.zeros((10, 10, 1), dtype=jnp.int32)
        assert validate_no_blocked_cells([], occupancy) == []
    
    def test_valid_path_no_blocks(self):
        """Path on unblocked cells should pass."""
        occupancy = jnp.zeros((10, 10, 1), dtype=jnp.int32)
        path = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        assert validate_no_blocked_cells(path, occupancy) == []
    
    def test_path_through_blocked(self):
        """Path through blocked cell should fail."""
        occupancy = jnp.zeros((10, 10, 1), dtype=jnp.int32)
        occupancy = occupancy.at[1, 0, 0].set(-1)  # Block cell
        path = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        violations = validate_no_blocked_cells(path, occupancy)
        assert len(violations) == 1
        assert violations[0].location == (1, 0, 0)


class TestValidateWithinBounds:
    """Tests for bounds validation."""
    
    def test_valid_path(self):
        """Path within bounds should pass."""
        path = [GridCell(5, 5, 0), GridCell(6, 5, 0)]
        assert validate_within_bounds(path, (10, 10), 2) == []
    
    def test_out_of_bounds_x(self):
        """X out of bounds should fail."""
        path = [GridCell(10, 5, 0)]  # x=10 is out for grid_size=(10,10)
        violations = validate_within_bounds(path, (10, 10), 2)
        assert len(violations) == 1
    
    def test_out_of_bounds_layer(self):
        """Layer out of bounds should fail."""
        path = [GridCell(5, 5, 2)]  # layer=2 is out for num_layers=2
        violations = validate_within_bounds(path, (10, 10), 2)
        assert len(violations) == 1


class TestValidateRouteResult:
    """Tests for comprehensive route validation."""
    
    def test_valid_route(self):
        """Valid route should pass all checks."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        path = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        result = RoutePath(net="TEST", cells=path, length=2.0, via_count=0, success=True)
        
        violations = validate_route_result(result, router)
        assert violations == []
    
    def test_failed_route_skipped(self):
        """Failed routes should not be validated."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        result = RoutePath(net="TEST", cells=[], length=0.0, via_count=0, success=False)
        
        violations = validate_route_result(result, router)
        assert violations == []


class TestValidateNoOverlaps:
    """Tests for overlap detection."""
    
    def test_no_overlaps(self):
        """Non-overlapping routes should pass."""
        routes = {
            "NET_A": RoutePath("NET_A", [GridCell(0, 0, 0), GridCell(1, 0, 0)], 1.0, 0, True),
            "NET_B": RoutePath("NET_B", [GridCell(0, 1, 0), GridCell(1, 1, 0)], 1.0, 0, True),
        }
        assert validate_no_overlaps(routes) == []
    
    def test_detected_overlap(self):
        """Overlapping routes should be detected."""
        routes = {
            "NET_A": RoutePath("NET_A", [GridCell(0, 0, 0), GridCell(1, 0, 0)], 1.0, 0, True),
            "NET_B": RoutePath("NET_B", [GridCell(1, 0, 0), GridCell(2, 0, 0)], 1.0, 0, True),
        }
        overlaps = validate_no_overlaps(routes)
        assert len(overlaps) == 1
        assert overlaps[0] == ("NET_A", "NET_B", (1, 0, 0))
    
    def test_failed_routes_skipped(self):
        """Failed routes should not contribute to overlap detection."""
        routes = {
            "NET_A": RoutePath("NET_A", [GridCell(0, 0, 0)], 0.0, 0, True),
            "NET_B": RoutePath("NET_B", [GridCell(0, 0, 0)], 0.0, 0, False),  # Failed
        }
        assert validate_no_overlaps(routes) == []


class TestFormatViolations:
    """Tests for violation formatting."""
    
    def test_empty_violations(self):
        """No violations should show success."""
        result = format_violations([])
        assert "✓" in result
    
    def test_with_violations(self):
        """Violations should be formatted."""
        violations = [
            InvariantViolation(
                invariant="path_connectivity",
                message="Gap at step 5",
                net="NET_A",
            )
        ]
        result = format_violations(violations)
        assert "✗" in result
        assert "NET_A" in result
        assert "path_connectivity" in result


class TestRoutingInvariantError:
    """Tests for the exception class."""
    
    def test_exception_message(self):
        """Exception should include violations."""
        try:
            raise RoutingInvariantError(["error1", "error2"])
        except RoutingInvariantError as e:
            assert len(e.violations) == 2
            assert "error1" in str(e)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
