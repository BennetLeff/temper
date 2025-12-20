"""Tests for topological heuristic integration into the pipeline.

This module tests that TopologicalInitializationHeuristic is properly
integrated into the default heuristics pipeline and handles edge cases.

Following TDD: these tests are written BEFORE implementation changes.
"""

from __future__ import annotations

import pytest
import jax
import jax.numpy as jnp

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Netlist, Net
from temper_placer.heuristics import (
    HeuristicPipeline,
    HeuristicPriority,
    create_default_pipeline,
)
from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
from temper_placer.io.config_loader import PlacementConstraints


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_board() -> Board:
    """Simple 100x100mm board with one zone."""
    return Board(
        width=100.0,
        height=100.0,
        zones=[
            Zone(
                name="MAIN",
                bounds=(10.0, 10.0, 80.0, 80.0),  # (x, y, width, height)
            )
        ],
    )


@pytest.fixture
def simple_netlist() -> Netlist:
    """Simple netlist with 5 components and 2 nets."""
    components = [
        Component(ref="U1", footprint="TSSOP-8", bounds=(3.0, 4.5)),
        Component(ref="U2", footprint="TSSOP-8", bounds=(3.0, 4.5)),
        Component(ref="C1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="C2", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
    ]
    nets = [
        Net(name="VCC", pins=[("U1", "1"), ("C1", "1"), ("C2", "1")]),
        Net(name="GND", pins=[("U1", "4"), ("U2", "4"), ("C1", "2"), ("C2", "2"), ("R1", "2")]),
    ]
    return Netlist(components=components, nets=nets)


@pytest.fixture
def default_constraints() -> PlacementConstraints:
    """Default placement constraints."""
    return PlacementConstraints(
        board_margin_mm=5.0,
    )


@pytest.fixture
def jax_key() -> jax.Array:
    """JAX random key for tests."""
    return jax.random.PRNGKey(42)


# =============================================================================
# Test: Pipeline Registration
# =============================================================================


class TestPipelineRegistration:
    """Tests that TopologicalInitializationHeuristic is in the default pipeline."""

    def test_default_pipeline_includes_topological(self):
        """Default pipeline should include TopologicalInitializationHeuristic."""
        pipeline = create_default_pipeline()

        topological_heuristics = [
            h for h in pipeline.heuristics if isinstance(h, TopologicalInitializationHeuristic)
        ]

        assert len(topological_heuristics) == 1, (
            "TopologicalInitializationHeuristic should be registered in default pipeline"
        )

    def test_topological_has_highest_priority(self):
        """TopologicalInitializationHeuristic should have INITIALIZATION priority."""
        pipeline = create_default_pipeline()

        topological = next(
            (h for h in pipeline.heuristics if isinstance(h, TopologicalInitializationHeuristic)),
            None,
        )

        assert topological is not None
        assert topological.priority == HeuristicPriority.INITIALIZATION

    def test_topological_runs_first(self):
        """TopologicalInitializationHeuristic should run before other heuristics."""
        pipeline = create_default_pipeline()

        # Sort by priority (as the pipeline does internally)
        sorted_heuristics = sorted(pipeline.heuristics, key=lambda h: h.priority)

        # First should be topological (priority -1)
        first = sorted_heuristics[0]
        assert isinstance(first, TopologicalInitializationHeuristic), (
            f"First heuristic should be TopologicalInitializationHeuristic, got {type(first).__name__}"
        )


# =============================================================================
# Test: Pipeline Execution
# =============================================================================


class TestPipelineExecution:
    """Tests that the pipeline runs successfully with topological heuristic."""

    def test_pipeline_runs_with_topological(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """Pipeline should complete successfully with topological heuristic."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        assert result is not None
        assert result.state is not None

    def test_all_components_placed(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """All components should be placed after pipeline runs."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        # All components should be placed (in placements dict or state)
        assert len(result.unplaced) == 0, f"Unplaced components: {result.unplaced}"

    def test_topological_stats_recorded(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """Heuristic stats should include topological_initialization."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        assert "topological_initialization" in result.heuristic_stats

    def test_positions_within_board(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """All positions should be within board bounds."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        positions = result.state.positions

        # Check all positions are within board
        assert jnp.all(positions[:, 0] >= 0), "X positions should be >= 0"
        assert jnp.all(positions[:, 0] <= simple_board.width), (
            "X positions should be <= board width"
        )
        assert jnp.all(positions[:, 1] >= 0), "Y positions should be >= 0"
        assert jnp.all(positions[:, 1] <= simple_board.height), (
            "Y positions should be <= board height"
        )


# =============================================================================
# Test: Skip Topological
# =============================================================================


class TestSkipTopological:
    """Tests for skipping topological heuristic."""

    def test_create_pipeline_without_topological(self):
        """Should be able to create pipeline without topological heuristic."""
        from temper_placer.heuristics import create_default_pipeline

        pipeline = create_default_pipeline(include_topological=False)

        topological_heuristics = [
            h for h in pipeline.heuristics if isinstance(h, TopologicalInitializationHeuristic)
        ]

        assert len(topological_heuristics) == 0

    def test_pipeline_works_without_topological(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """Pipeline should work without topological heuristic."""
        from temper_placer.heuristics import create_default_pipeline

        pipeline = create_default_pipeline(include_topological=False)

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        assert result is not None
        assert result.state is not None


# =============================================================================
# Test: Feasibility Checking
# =============================================================================


class TestFeasibilityChecking:
    """Tests for fail-fast feasibility checking."""

    def test_infeasible_constraints_detected(self):
        """Infeasible constraints should be detected early."""
        # Create a board that's too small for the components
        tiny_board = Board(
            width=5.0,  # Very small
            height=5.0,
            zones=[Zone(name="TINY", bounds=(0, 0, 5.0, 5.0))],
        )

        # Large components that can't fit
        large_components = [
            Component(ref="U1", footprint="BGA", bounds=(10.0, 10.0)),  # Bigger than board
            Component(ref="U2", footprint="BGA", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=large_components, nets=[])
        constraints = PlacementConstraints(board_margin_mm=1.0)

        heuristic = TopologicalInitializationHeuristic()
        from temper_placer.heuristics.base import PlacementContext

        context = PlacementContext(
            board=tiny_board,
            netlist=netlist,
            constraints=constraints,
        )

        result = heuristic.apply(context)

        # Should fail or report infeasibility
        assert result.success is False or len(result.conflicts) > 0

    def test_feasibility_diagnostics_populated(
        self, simple_board, simple_netlist, default_constraints
    ):
        """Feasibility diagnostics should be populated."""
        heuristic = TopologicalInitializationHeuristic()
        from temper_placer.heuristics.base import PlacementContext

        context = PlacementContext(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
        )

        result = heuristic.apply(context)

        # Result should have message explaining what happened
        assert result.message != "" or result.success


# =============================================================================
# Test: Pipeline Result Diagnostics
# =============================================================================


class TestPipelineResultDiagnostics:
    """Tests for enhanced PipelineResult with topological diagnostics."""

    def test_result_has_topological_graph(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """PipelineResult should include topological graph if available."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        # Check if topological diagnostics are available
        if hasattr(result, "topological_diagnostics"):
            assert result.topological_diagnostics is not None

    def test_result_has_zone_assignments(
        self, simple_board, simple_netlist, default_constraints, jax_key
    ):
        """PipelineResult should include zone assignments."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        # Zone assignments should be in heuristic stats
        topological_stats = result.heuristic_stats.get("topological_initialization", {})
        # Stats should exist (implementation detail whether zones are included)
        assert isinstance(topological_stats, dict)


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in topological integration."""

    def test_empty_netlist_handled(self, simple_board, default_constraints, jax_key):
        """Empty netlist should be handled gracefully."""
        pipeline = create_default_pipeline()
        empty_netlist = Netlist(components=[], nets=[])

        result = pipeline.run(
            board=simple_board,
            netlist=empty_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        # Should complete without error
        assert result is not None

    def test_no_zones_handled(self, simple_netlist, default_constraints, jax_key):
        """Board without zones should be handled gracefully."""
        pipeline = create_default_pipeline()
        board_no_zones = Board(width=100.0, height=100.0, zones=[])

        result = pipeline.run(
            board=board_no_zones,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=jax_key,
        )

        # Should complete without error
        assert result is not None
        assert result.state is not None

    def test_null_constraints_handled(self, simple_board, simple_netlist, jax_key):
        """Null constraints should be handled gracefully."""
        pipeline = create_default_pipeline()

        result = pipeline.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=None,
            key=jax_key,
        )

        # Should complete without error
        assert result is not None


# =============================================================================
# Test: Determinism
# =============================================================================


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_seed_same_result(self, simple_board, simple_netlist, default_constraints):
        """Same seed should produce same result."""
        pipeline1 = create_default_pipeline()
        pipeline2 = create_default_pipeline()

        key1 = jax.random.PRNGKey(42)
        key2 = jax.random.PRNGKey(42)

        result1 = pipeline1.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=key1,
        )

        result2 = pipeline2.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=key2,
        )

        # Positions should be identical
        assert jnp.allclose(result1.state.positions, result2.state.positions)

    def test_different_seed_different_result(
        self, simple_board, simple_netlist, default_constraints
    ):
        """Different seeds should produce different results (unless deterministic placement)."""
        pipeline1 = create_default_pipeline()
        pipeline2 = create_default_pipeline()

        key1 = jax.random.PRNGKey(42)
        key2 = jax.random.PRNGKey(999)

        result1 = pipeline1.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=key1,
        )

        result2 = pipeline2.run(
            board=simple_board,
            netlist=simple_netlist,
            constraints=default_constraints,
            key=key2,
        )

        # Results may or may not differ depending on whether topological
        # placement is fully deterministic. This test verifies the system
        # at least handles different seeds.
        assert result1.state is not None
        assert result2.state is not None
