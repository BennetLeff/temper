"""Tests for force-directed position refinement.

This module tests the force simulation that refines initial positions
by applying attraction (adjacency) and repulsion (separation) forces.

Following TDD: these tests are written BEFORE implementation.
"""

from __future__ import annotations

import math
import pytest
import numpy as np

# These imports will fail until implementation exists
from temper_placer.core.board import Zone
from temper_placer.topological.graph import TopologicalGraph

# Imports that will be implemented
from temper_placer.topological.force_refinement import (
    apply_force_refinement,
    compute_adjacency_force,
    compute_separation_force,
    compute_boundary_force,
    _force_refine_numpy,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_zone() -> Zone:
    """A simple 100x100 zone at origin."""
    return Zone(
        name="TEST_ZONE",
        bounds=(0.0, 0.0, 100.0, 100.0),
    )


@pytest.fixture
def small_zone() -> Zone:
    """A small 50x50 zone."""
    return Zone(
        name="SMALL_ZONE",
        bounds=(0.0, 0.0, 50.0, 50.0),
    )


@pytest.fixture
def empty_graph() -> TopologicalGraph:
    """Empty topological graph."""
    return TopologicalGraph()


@pytest.fixture
def two_component_graph() -> TopologicalGraph:
    """Graph with two components, no constraints."""
    graph = TopologicalGraph()
    graph.add_component("C1")
    graph.add_component("C2")
    return graph


@pytest.fixture
def adjacent_graph() -> TopologicalGraph:
    """Graph with adjacency constraint."""
    graph = TopologicalGraph()
    graph.add_component("C1")
    graph.add_component("C2")
    graph.add_adjacency("C1", "C2", max_distance=10.0, constraint_id="adj_1")
    return graph


@pytest.fixture
def separated_graph() -> TopologicalGraph:
    """Graph with separation constraint."""
    graph = TopologicalGraph()
    graph.add_component("C1")
    graph.add_component("C2")
    graph.add_separation("C1", "C2", min_distance=30.0, constraint_id="sep_1")
    return graph


@pytest.fixture
def mixed_constraint_graph() -> TopologicalGraph:
    """Graph with both adjacency and separation."""
    graph = TopologicalGraph()
    graph.add_component("A")
    graph.add_component("B")
    graph.add_component("C")
    graph.add_component("D")

    # A-B should be close
    graph.add_adjacency("A", "B", max_distance=10.0, constraint_id="adj_1")

    # C-D should be far from A-B
    graph.add_separation("A", "C", min_distance=40.0, constraint_id="sep_1")
    graph.add_separation("B", "D", min_distance=40.0, constraint_id="sep_2")

    return graph


# =============================================================================
# Tests: compute_adjacency_force
# =============================================================================


class TestComputeAdjacencyForce:
    """Tests for adjacency (attraction) force computation."""

    def test_far_apart_attracts(self):
        """Components far apart experience attraction."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([50.0, 0.0])
        target_distance = 10.0

        force_a, force_b = compute_adjacency_force(pos_a, pos_b, target_distance)

        # A should be pulled toward B (positive x)
        assert force_a[0] > 0
        # B should be pulled toward A (negative x)
        assert force_b[0] < 0

    def test_at_target_distance_minimal_force(self):
        """Components at target distance have minimal force."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([10.0, 0.0])
        target_distance = 10.0

        force_a, force_b = compute_adjacency_force(pos_a, pos_b, target_distance)

        # Forces should be approximately zero
        assert abs(force_a[0]) < 0.1
        assert abs(force_b[0]) < 0.1

    def test_too_close_repels(self):
        """Components too close experience repulsion."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([5.0, 0.0])
        target_distance = 10.0

        force_a, force_b = compute_adjacency_force(pos_a, pos_b, target_distance)

        # A should be pushed away from B (negative x)
        assert force_a[0] < 0
        # B should be pushed away from A (positive x)
        assert force_b[0] > 0

    def test_force_magnitude_proportional_to_distance_error(self):
        """Force magnitude increases with distance from target."""
        pos_a = np.array([0.0, 0.0])
        target_distance = 10.0

        # Small error
        pos_b_close = np.array([15.0, 0.0])
        force_close, _ = compute_adjacency_force(pos_a, pos_b_close, target_distance)

        # Large error
        pos_b_far = np.array([50.0, 0.0])
        force_far, _ = compute_adjacency_force(pos_a, pos_b_far, target_distance)

        assert np.linalg.norm(force_far) > np.linalg.norm(force_close)

    def test_force_direction_2d(self):
        """Force direction is correct in 2D."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([30.0, 40.0])  # 50 units away at angle
        target_distance = 10.0

        force_a, force_b = compute_adjacency_force(pos_a, pos_b, target_distance)

        # Force should point toward B from A
        direction_to_b = pos_b - pos_a
        direction_to_b = direction_to_b / np.linalg.norm(direction_to_b)

        force_a_normalized = force_a / np.linalg.norm(force_a)

        # Should be approximately same direction
        assert np.dot(force_a_normalized, direction_to_b) > 0.99

    def test_symmetric_forces(self):
        """Forces on A and B are equal and opposite."""
        pos_a = np.array([10.0, 20.0])
        pos_b = np.array([50.0, 60.0])
        target_distance = 15.0

        force_a, force_b = compute_adjacency_force(pos_a, pos_b, target_distance)

        # Forces should be opposite
        np.testing.assert_array_almost_equal(force_a, -force_b)


# =============================================================================
# Tests: compute_separation_force
# =============================================================================


class TestComputeSeparationForce:
    """Tests for separation (repulsion) force computation."""

    def test_too_close_repels(self):
        """Components too close experience repulsion."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([10.0, 0.0])
        min_distance = 30.0

        force_a, force_b = compute_separation_force(pos_a, pos_b, min_distance)

        # A should be pushed away from B (negative x)
        assert force_a[0] < 0
        # B should be pushed away from A (positive x)
        assert force_b[0] > 0

    def test_far_enough_no_force(self):
        """Components already separated have no force."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([50.0, 0.0])
        min_distance = 30.0

        force_a, force_b = compute_separation_force(pos_a, pos_b, min_distance)

        # No force needed - already far enough
        assert abs(force_a[0]) < 0.01
        assert abs(force_b[0]) < 0.01

    def test_force_magnitude_increases_when_closer(self):
        """Force magnitude increases as components get closer."""
        pos_a = np.array([0.0, 0.0])
        min_distance = 30.0

        # Somewhat close
        pos_b_medium = np.array([20.0, 0.0])
        force_medium, _ = compute_separation_force(pos_a, pos_b_medium, min_distance)

        # Very close
        pos_b_close = np.array([5.0, 0.0])
        force_close, _ = compute_separation_force(pos_a, pos_b_close, min_distance)

        assert np.linalg.norm(force_close) > np.linalg.norm(force_medium)

    def test_exactly_at_minimum_minimal_force(self):
        """At exactly minimum distance, force is minimal."""
        pos_a = np.array([0.0, 0.0])
        pos_b = np.array([30.0, 0.0])
        min_distance = 30.0

        force_a, force_b = compute_separation_force(pos_a, pos_b, min_distance)

        # Should be approximately zero (or very small)
        assert np.linalg.norm(force_a) < 1.0

    def test_symmetric_forces(self):
        """Forces on A and B are equal and opposite."""
        pos_a = np.array([10.0, 20.0])
        pos_b = np.array([20.0, 30.0])
        min_distance = 50.0

        force_a, force_b = compute_separation_force(pos_a, pos_b, min_distance)

        np.testing.assert_array_almost_equal(force_a, -force_b)


# =============================================================================
# Tests: compute_boundary_force
# =============================================================================


class TestComputeBoundaryForce:
    """Tests for boundary containment force computation."""

    def test_inside_zone_no_force(self, simple_zone):
        """Component inside zone has no boundary force."""
        position = np.array([50.0, 50.0])  # Center of zone

        force = compute_boundary_force(position, simple_zone)

        assert abs(force[0]) < 0.01
        assert abs(force[1]) < 0.01

    def test_outside_left_pushes_right(self, simple_zone):
        """Component outside left boundary pushed right."""
        position = np.array([-10.0, 50.0])

        force = compute_boundary_force(position, simple_zone)

        # Should push right (positive x)
        assert force[0] > 0

    def test_outside_right_pushes_left(self, simple_zone):
        """Component outside right boundary pushed left."""
        position = np.array([110.0, 50.0])

        force = compute_boundary_force(position, simple_zone)

        # Should push left (negative x)
        assert force[0] < 0

    def test_outside_bottom_pushes_up(self, simple_zone):
        """Component outside bottom boundary pushed up."""
        position = np.array([50.0, -10.0])

        force = compute_boundary_force(position, simple_zone)

        # Should push up (positive y)
        assert force[1] > 0

    def test_outside_top_pushes_down(self, simple_zone):
        """Component outside top boundary pushed down."""
        position = np.array([50.0, 110.0])

        force = compute_boundary_force(position, simple_zone)

        # Should push down (negative y)
        assert force[1] < 0

    def test_corner_pushed_diagonally(self, simple_zone):
        """Component outside corner pushed diagonally."""
        position = np.array([-10.0, -10.0])  # Outside bottom-left

        force = compute_boundary_force(position, simple_zone)

        # Should push toward inside (positive x and y)
        assert force[0] > 0
        assert force[1] > 0

    def test_force_proportional_to_overshoot(self, simple_zone):
        """Force magnitude increases with distance outside boundary."""
        # Small overshoot
        pos_small = np.array([105.0, 50.0])
        force_small = compute_boundary_force(pos_small, simple_zone)

        # Large overshoot
        pos_large = np.array([150.0, 50.0])
        force_large = compute_boundary_force(pos_large, simple_zone)

        assert abs(force_large[0]) > abs(force_small[0])


# =============================================================================
# Tests: apply_force_refinement
# =============================================================================


class TestApplyForceRefinement:
    """Integration tests for force refinement."""

    def test_no_constraints_stable(self, simple_zone, two_component_graph):
        """No constraints means positions stay approximately stable."""
        positions = {
            "C1": (25.0, 25.0),
            "C2": (75.0, 75.0),
        }
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=two_component_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=50,
        )

        # Positions should not change much (no constraints to satisfy)
        assert abs(refined["C1"][0] - 25.0) < 10.0
        assert abs(refined["C2"][0] - 75.0) < 10.0

    def test_adjacency_pulls_together(self, simple_zone, adjacent_graph):
        """Adjacent components are pulled closer."""
        # Start far apart
        positions = {
            "C1": (10.0, 50.0),
            "C2": (90.0, 50.0),
        }
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=100,
        )

        # Calculate distance after refinement
        x1, y1 = refined["C1"]
        x2, y2 = refined["C2"]
        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

        # Should be closer to target (10mm) than initial (80mm)
        assert distance < 50.0  # Significant improvement

    def test_separation_pushes_apart(self, simple_zone, separated_graph):
        """Separated components are pushed apart."""
        # Start too close
        positions = {
            "C1": (45.0, 50.0),
            "C2": (55.0, 50.0),
        }
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=separated_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=100,
        )

        x1, y1 = refined["C1"]
        x2, y2 = refined["C2"]
        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

        # Should be pushed toward min_distance (30mm)
        assert distance > 20.0

    def test_boundary_containment(self, small_zone, two_component_graph):
        """Components outside boundary pushed back in."""
        # Start outside boundary
        positions = {
            "C1": (-20.0, 25.0),
            "C2": (70.0, 25.0),
        }
        zone_assignments = {"C1": "SMALL_ZONE", "C2": "SMALL_ZONE"}
        zones = {"SMALL_ZONE": small_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=two_component_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=100,
        )

        # Both should now be inside zone (0-50, 0-50)
        x1, y1 = refined["C1"]
        x2, y2 = refined["C2"]

        # Use small tolerance for floating-point precision
        tol = 1e-6
        assert -tol <= x1 <= 50.0 + tol, f"C1 x={x1} outside zone"
        assert -tol <= x2 <= 50.0 + tol, f"C2 x={x2} outside zone"

    def test_mixed_constraints(self, simple_zone, mixed_constraint_graph):
        """Mixed adjacency and separation constraints."""
        positions = {
            "A": (25.0, 25.0),
            "B": (75.0, 25.0),  # Far from A (but should be adjacent)
            "C": (30.0, 75.0),  # Close to A (but should be separated)
            "D": (70.0, 75.0),
        }
        zone_assignments = {k: "TEST_ZONE" for k in positions}
        zones = {"TEST_ZONE": simple_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=mixed_constraint_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=200,
        )

        # A-B should be closer (adjacency)
        dist_ab_before = math.sqrt((75 - 25) ** 2)  # 50
        x_a, y_a = refined["A"]
        x_b, y_b = refined["B"]
        dist_ab_after = math.sqrt((x_b - x_a) ** 2 + (y_b - y_a) ** 2)

        assert dist_ab_after < dist_ab_before * 0.8  # At least 20% closer

        # A-C should be farther (separation)
        x_c, y_c = refined["C"]
        dist_ac_after = math.sqrt((x_c - x_a) ** 2 + (y_c - y_a) ** 2)

        # Should have pushed apart
        assert dist_ac_after > 30.0

    def test_zero_iterations_returns_unchanged(self, simple_zone, adjacent_graph):
        """Zero iterations returns input unchanged."""
        positions = {
            "C1": (10.0, 50.0),
            "C2": (90.0, 50.0),
        }
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=0,
        )

        assert refined["C1"] == positions["C1"]
        assert refined["C2"] == positions["C2"]

    def test_learning_rate_effect(self, simple_zone, adjacent_graph):
        """Higher learning rate causes faster convergence."""
        positions = {
            "C1": (10.0, 50.0),
            "C2": (90.0, 50.0),
        }
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        # Low learning rate
        refined_slow = apply_force_refinement(
            positions=positions,
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=20,
            learning_rate=0.01,
        )

        # High learning rate
        refined_fast = apply_force_refinement(
            positions=dict(positions),
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=20,
            learning_rate=0.5,
        )

        # Calculate distances
        def dist(p1, p2):
            return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

        dist_slow = dist(refined_slow["C1"], refined_slow["C2"])
        dist_fast = dist(refined_fast["C1"], refined_fast["C2"])

        # Faster learning should converge more in same iterations
        # (get closer to target of 10mm)
        assert dist_fast < dist_slow

    def test_deterministic_output(self, simple_zone, adjacent_graph):
        """Same input produces identical output."""
        positions = {"C1": (10.0, 50.0), "C2": (90.0, 50.0)}
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined1 = apply_force_refinement(
            positions=dict(positions),
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=50,
        )

        refined2 = apply_force_refinement(
            positions=dict(positions),
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=50,
        )

        assert refined1["C1"] == pytest.approx(refined2["C1"], rel=1e-6)
        assert refined1["C2"] == pytest.approx(refined2["C2"], rel=1e-6)

    def test_empty_positions(self, simple_zone, empty_graph):
        """Empty positions returns empty result."""
        refined = apply_force_refinement(
            positions={},
            graph=empty_graph,
            zones={"TEST_ZONE": simple_zone},
            zone_assignments={},
            iterations=50,
        )

        assert refined == {}


# =============================================================================
# Tests: NumPy Backend (_force_refine_numpy)
# =============================================================================


class TestForceRefineNumpy:
    """Tests for NumPy implementation of force refinement."""

    def test_basic_operation(self):
        """NumPy backend runs without error."""
        positions = np.array([[10.0, 50.0], [90.0, 50.0]])
        adjacencies = [(0, 1, 10.0)]  # (i, j, target_distance)
        separations = []
        zone_bounds = np.array(
            [
                [0.0, 0.0, 100.0, 100.0],
                [0.0, 0.0, 100.0, 100.0],
            ]
        )

        result = _force_refine_numpy(
            positions=positions,
            adjacencies=adjacencies,
            separations=separations,
            zone_bounds=zone_bounds,
            iterations=50,
            lr=0.1,
        )

        assert result.shape == (2, 2)

    def test_output_type(self):
        """Output is numpy array."""
        positions = np.array([[50.0, 50.0]])

        result = _force_refine_numpy(
            positions=positions,
            adjacencies=[],
            separations=[],
            zone_bounds=np.array([[0.0, 0.0, 100.0, 100.0]]),
            iterations=10,
            lr=0.1,
        )

        assert isinstance(result, np.ndarray)

    def test_convergence_energy_decreases(self):
        """Total constraint violation decreases over iterations."""
        # Start with violated constraints
        positions = np.array([[10.0, 50.0], [90.0, 50.0]])
        adjacencies = [(0, 1, 10.0)]  # Want 10mm, have 80mm

        zone_bounds = np.array(
            [
                [0.0, 0.0, 100.0, 100.0],
                [0.0, 0.0, 100.0, 100.0],
            ]
        )

        # Run few iterations
        result_early = _force_refine_numpy(
            positions=positions.copy(),
            adjacencies=adjacencies,
            separations=[],
            zone_bounds=zone_bounds,
            iterations=10,
            lr=0.1,
        )

        # Run many iterations
        result_late = _force_refine_numpy(
            positions=positions.copy(),
            adjacencies=adjacencies,
            separations=[],
            zone_bounds=zone_bounds,
            iterations=100,
            lr=0.1,
        )

        # Calculate distance errors
        dist_early = np.linalg.norm(result_early[1] - result_early[0])
        dist_late = np.linalg.norm(result_late[1] - result_late[0])

        # Later should be closer to target (10mm)
        error_early = abs(dist_early - 10.0)
        error_late = abs(dist_late - 10.0)

        assert error_late < error_early

    def test_handles_many_components(self):
        """Can handle many components without error."""
        n = 100
        positions = np.random.rand(n, 2) * 100

        # Create some random adjacencies
        adjacencies = [(i, (i + 1) % n, 10.0) for i in range(0, n, 5)]

        zone_bounds = np.tile([0.0, 0.0, 100.0, 100.0], (n, 1))

        result = _force_refine_numpy(
            positions=positions,
            adjacencies=adjacencies,
            separations=[],
            zone_bounds=zone_bounds,
            iterations=10,
            lr=0.1,
        )

        assert result.shape == (n, 2)


# =============================================================================
# Tests: JAX Backend (Optional)
# =============================================================================


class TestForceRefineJax:
    """Tests for JAX implementation (optional backend)."""

    @pytest.fixture
    def jax_available(self):
        """Check if JAX is available."""
        try:
            import jax  # noqa

            return True
        except ImportError:
            return False

    def test_jax_backend_produces_valid_output(self, jax_available, simple_zone, adjacent_graph):
        """JAX backend produces valid positions."""
        if not jax_available:
            pytest.skip("JAX not available")

        positions = {"C1": (10.0, 50.0), "C2": (90.0, 50.0)}
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined = apply_force_refinement(
            positions=positions,
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=50,
            backend="jax",
        )

        assert len(refined) == 2
        assert "C1" in refined
        assert "C2" in refined

    def test_backends_produce_similar_results(self, jax_available, simple_zone, adjacent_graph):
        """NumPy and JAX backends produce similar results."""
        if not jax_available:
            pytest.skip("JAX not available")

        positions = {"C1": (10.0, 50.0), "C2": (90.0, 50.0)}
        zone_assignments = {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        zones = {"TEST_ZONE": simple_zone}

        refined_numpy = apply_force_refinement(
            positions=dict(positions),
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=50,
            learning_rate=0.1,
            backend="numpy",
        )

        refined_jax = apply_force_refinement(
            positions=dict(positions),
            graph=adjacent_graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=50,
            learning_rate=0.1,
            backend="jax",
        )

        # Results should be similar (within tolerance)
        for ref in ["C1", "C2"]:
            x_np, y_np = refined_numpy[ref]
            x_jax, y_jax = refined_jax[ref]

            assert x_np == pytest.approx(x_jax, abs=5.0)  # Within 5mm
            assert y_np == pytest.approx(y_jax, abs=5.0)


# =============================================================================
# Tests: Performance
# =============================================================================


class TestPerformance:
    """Performance tests for force refinement."""

    @pytest.mark.slow
    def test_100_components_reasonable_time(self, simple_zone):
        """100 components completes in reasonable time."""
        import time

        n = 100
        graph = TopologicalGraph()
        for i in range(n):
            graph.add_component(f"C{i}")

        # Add some adjacencies
        for i in range(0, n - 1, 2):
            graph.add_adjacency(f"C{i}", f"C{i + 1}", 10.0, f"adj_{i}")

        positions = {f"C{i}": (float(i % 10) * 10, float(i // 10) * 10) for i in range(n)}
        zone_assignments = {f"C{i}": "TEST_ZONE" for i in range(n)}
        zones = {"TEST_ZONE": simple_zone}

        start = time.time()

        apply_force_refinement(
            positions=positions,
            graph=graph,
            zones=zones,
            zone_assignments=zone_assignments,
            iterations=100,
        )

        elapsed = time.time() - start

        # Should complete in under 1 second
        assert elapsed < 1.0, f"Took {elapsed:.2f}s, expected < 1.0s"
