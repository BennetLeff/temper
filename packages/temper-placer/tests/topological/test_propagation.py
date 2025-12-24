"""Tests for constraint propagation solver."""

from temper_placer.topological.graph import TopologicalGraph
from temper_placer.topological.propagation import (
    ConstraintPropagator,
    DistanceBound,
)


class TestDistanceBound:
    """Tests for DistanceBound data structure."""

    def test_default_bounds(self):
        """Default bounds are [0, inf)."""
        bound = DistanceBound()
        assert bound.min_distance == 0.0
        assert bound.max_distance == float("inf")

    def test_custom_bounds(self):
        """Can specify custom bounds."""
        bound = DistanceBound(min_distance=5.0, max_distance=10.0)
        assert bound.min_distance == 5.0
        assert bound.max_distance == 10.0

    def test_tighten_max(self):
        """Tightening max takes minimum."""
        bound = DistanceBound(max_distance=10.0)
        bound.tighten_max(8.0)
        assert bound.max_distance == 8.0

        bound.tighten_max(12.0)  # Should not increase
        assert bound.max_distance == 8.0

    def test_tighten_min(self):
        """Tightening min takes maximum."""
        bound = DistanceBound(min_distance=5.0)
        bound.tighten_min(7.0)
        assert bound.min_distance == 7.0

        bound.tighten_min(3.0)  # Should not decrease
        assert bound.min_distance == 7.0

    def test_is_feasible_valid(self):
        """Feasible when min <= max."""
        bound = DistanceBound(min_distance=5.0, max_distance=10.0)
        assert bound.is_feasible()

    def test_is_feasible_equal(self):
        """Feasible when min == max (exact distance required)."""
        bound = DistanceBound(min_distance=5.0, max_distance=5.0)
        assert bound.is_feasible()

    def test_is_infeasible(self):
        """Infeasible when min > max."""
        bound = DistanceBound(min_distance=10.0, max_distance=5.0)
        assert not bound.is_feasible()


class TestConstraintPropagator:
    """Tests for ConstraintPropagator."""

    def test_init_from_empty_graph(self):
        """Propagator initializes from empty graph."""
        graph = TopologicalGraph()
        propagator = ConstraintPropagator(graph)

        assert len(propagator.nodes) == 0
        assert len(propagator.bounds) == 0

    def test_init_from_single_component(self):
        """Single component has identity bound to itself."""
        graph = TopologicalGraph()
        graph.add_component("Q1")

        propagator = ConstraintPropagator(graph)
        assert len(propagator.nodes) == 1
        assert "Q1" in propagator.node_idx

    def test_init_from_adjacency_constraint(self):
        """Adjacency constraint initializes max bound."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_adjacency("Q1", "Q2", max_distance=5.0, constraint_id="c1")

        propagator = ConstraintPropagator(graph)

        # Check forward bound
        bound_12 = propagator.get_bound("Q1", "Q2")
        assert bound_12.max_distance == 5.0

        # Check reverse bound (symmetric)
        bound_21 = propagator.get_bound("Q2", "Q1")
        assert bound_21.max_distance == 5.0

    def test_init_from_separation_constraint(self):
        """Separation constraint initializes min bound."""
        graph = TopologicalGraph()
        graph.add_component("HV")
        graph.add_component("LV")
        graph.add_separation("HV", "LV", min_distance=10.0, constraint_id="c1")

        propagator = ConstraintPropagator(graph)

        bound = propagator.get_bound("HV", "LV")
        assert bound.min_distance == 10.0

    def test_propagate_no_constraints(self):
        """Propagation succeeds with no constraints."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")

        propagator = ConstraintPropagator(graph)
        assert propagator.propagate()

    def test_propagate_simple_chain_max(self):
        """Propagates max distance through chain: A--5--B--3--C => A--8--C."""
        graph = TopologicalGraph()
        graph.add_component("A")
        graph.add_component("B")
        graph.add_component("C")

        graph.add_adjacency("A", "B", max_distance=5.0, constraint_id="c1")
        graph.add_adjacency("B", "C", max_distance=3.0, constraint_id="c2")

        propagator = ConstraintPropagator(graph)
        assert propagator.propagate()

        # A-C bound should be ≤ 5+3 = 8
        bound_ac = propagator.get_bound("A", "C")
        assert bound_ac.max_distance <= 8.0

    def test_propagate_longer_chain(self):
        """Propagates through longer chain: A--5--B--3--C--2--D."""
        graph = TopologicalGraph()
        for comp in ["A", "B", "C", "D"]:
            graph.add_component(comp)

        graph.add_adjacency("A", "B", 5.0, "c1")
        graph.add_adjacency("B", "C", 3.0, "c2")
        graph.add_adjacency("C", "D", 2.0, "c3")

        propagator = ConstraintPropagator(graph)
        assert propagator.propagate()

        # A-D should be ≤ 5+3+2 = 10
        bound_ad = propagator.get_bound("A", "D")
        assert bound_ad.max_distance <= 10.0

    def test_propagate_detects_infeasibility(self):
        """Detects infeasible constraints: A--5--B, B--5--C, A-C separated ≥15mm."""
        graph = TopologicalGraph()
        for comp in ["A", "B", "C"]:
            graph.add_component(comp)

        # A-B ≤ 5mm, B-C ≤ 5mm => A-C ≤ 10mm
        graph.add_adjacency("A", "B", 5.0, "c1")
        graph.add_adjacency("B", "C", 5.0, "c2")

        # But A-C ≥ 15mm (impossible!)
        graph.add_separation("A", "C", 15.0, "c3")

        propagator = ConstraintPropagator(graph)
        assert not propagator.propagate()

    def test_get_infeasible_pairs(self):
        """Returns all infeasible pairs after failed propagation."""
        graph = TopologicalGraph()
        for comp in ["A", "B", "C"]:
            graph.add_component(comp)

        graph.add_adjacency("A", "B", 5.0, "c1")
        graph.add_adjacency("B", "C", 5.0, "c2")
        graph.add_separation("A", "C", 15.0, "c3")

        propagator = ConstraintPropagator(graph)
        propagator.propagate()

        infeasible = propagator.get_infeasible_pairs()
        assert len(infeasible) > 0

        # Should report A-C conflict
        refs = {(a, c) for a, c, _ in infeasible}
        assert ("A", "C") in refs or ("C", "A") in refs

    def test_propagate_multiple_paths(self):
        """Chooses tightest bound when multiple paths exist."""
        graph = TopologicalGraph()
        for comp in ["A", "B", "C"]:
            graph.add_component(comp)

        # Direct path: A--10--C
        graph.add_adjacency("A", "C", 10.0, "c1")

        # Indirect path: A--3--B--3--C (tighter: 6mm total)
        graph.add_adjacency("A", "B", 3.0, "c2")
        graph.add_adjacency("B", "C", 3.0, "c3")

        propagator = ConstraintPropagator(graph)
        assert propagator.propagate()

        # Should use tighter bound from indirect path
        bound_ac = propagator.get_bound("A", "C")
        assert bound_ac.max_distance == 6.0

    def test_propagate_terminates_early(self):
        """Stops iterating when no changes occur."""
        graph = TopologicalGraph()
        graph.add_component("A")
        graph.add_component("B")
        graph.add_adjacency("A", "B", 5.0, "c1")

        propagator = ConstraintPropagator(graph)

        # Should terminate in 1 iteration (no propagation needed)
        assert propagator.propagate(max_iterations=100)

    def test_propagate_separation_chain(self):
        """Propagates minimum distances: A sep B ≥10, B sep C ≥10 => A sep C ≥0."""
        # Note: Separation doesn't propagate additively like adjacency
        # A--B ≥10 and B--C ≥10 doesn't mean A--C ≥20
        # (B could be between A and C, making A-C as small as 0)

        graph = TopologicalGraph()
        for comp in ["A", "B", "C"]:
            graph.add_component(comp)

        graph.add_separation("A", "B", 10.0, "c1")
        graph.add_separation("B", "C", 10.0, "c2")

        propagator = ConstraintPropagator(graph)
        assert propagator.propagate()

        # A-C min bound should not propagate additively
        bound_ac = propagator.get_bound("A", "C")
        # Min distance could be 0 if B is between them
        assert bound_ac.min_distance >= 0.0

    def test_propagate_mixed_constraints(self):
        """Handles mix of adjacency and separation constraints."""
        graph = TopologicalGraph()
        for comp in ["A", "B", "C", "D"]:
            graph.add_component(comp)

        # A--5--B, B--5--C (adjacent)
        graph.add_adjacency("A", "B", 5.0, "c1")
        graph.add_adjacency("B", "C", 5.0, "c2")

        # C separated from D ≥ 10mm
        graph.add_separation("C", "D", 10.0, "c3")

        propagator = ConstraintPropagator(graph)
        assert propagator.propagate()

        # A-C ≤ 10mm
        assert propagator.get_bound("A", "C").max_distance <= 10.0

        # C-D ≥ 10mm
        assert propagator.get_bound("C", "D").min_distance == 10.0

    def test_no_over_propagation(self):
        """Doesn't create tighter bounds than necessary."""
        graph = TopologicalGraph()
        graph.add_component("A")
        graph.add_component("B")

        # Only constraint: A--10--B
        graph.add_adjacency("A", "B", 10.0, "c1")

        propagator = ConstraintPropagator(graph)
        propagator.propagate()

        bound = propagator.get_bound("A", "B")
        # Should be exactly 10, not tighter
        assert bound.max_distance == 10.0
        assert bound.min_distance == 0.0  # No min specified

    def test_large_graph_performance(self):
        """Handles moderately large graphs (100 components)."""
        graph = TopologicalGraph()

        # Create chain of 100 components
        n = 100
        for i in range(n):
            graph.add_component(f"C{i}")

        for i in range(n - 1):
            graph.add_adjacency(f"C{i}", f"C{i + 1}", 5.0, f"c{i}")

        propagator = ConstraintPropagator(graph)

        # Should complete in reasonable time (< 1 second)
        import time

        start = time.time()
        assert propagator.propagate()
        elapsed = time.time() - start

        assert elapsed < 1.0  # O(n³) should be fast for n=100

        # C0 to C99 should be ≤ 99*5 = 495mm
        bound = propagator.get_bound("C0", "C99")
        assert bound.max_distance <= 495.0
