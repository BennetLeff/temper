"""Tests for heuristics.pipeline module.

Tests the HeuristicPipeline orchestrator:
- Heuristic registration and sorting
- Pipeline execution order
- Conflict resolution integration
- Random fill for remaining components
- Conversion to PlacementState
"""


import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.heuristics import create_default_pipeline
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.heuristics.conflict import ResolutionStrategy
from temper_placer.heuristics.pipeline import (
    HeuristicPipeline,
    PipelineResult,
)
from temper_placer.io.config_loader import PlacementConstraints


class MockHeuristic(Heuristic):
    """Mock heuristic for testing pipeline behavior."""

    def __init__(
        self,
        name: str,
        priority: HeuristicPriority,
        placements: dict[str, ComponentPlacement] | None = None,
        record_execution: list[str] | None = None,
    ):
        self._name = name
        self._priority = priority
        self._placements = placements or {}
        self._record_execution = record_execution  # Shared list to track execution order

    @property
    def name(self):
        return self._name

    @property
    def priority(self):
        return self._priority

    def apply(self, _context: PlacementContext) -> HeuristicResult:
        if self._record_execution is not None:
            self._record_execution.append(self._name)

        return HeuristicResult(
            placements=self._placements,
            success=True,
            message=f"Applied {self._name}",
        )


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_basic_result(self):
        """Test basic result creation."""
        placements = {"U1": ComponentPlacement(ref="U1", position=(50.0, 50.0))}
        state = PlacementState(
            positions=jnp.zeros((1, 2)),
            rotation_logits=jnp.zeros((1, 4)),
        )
        result = PipelineResult(
            placements=placements,
            state=state,
            conflicts=["conflict1"],
            heuristic_stats={"test": {"placed": 1}},
            unplaced=["R1"],
        )
        assert "U1" in result.placements
        assert len(result.conflicts) == 1
        assert "R1" in result.unplaced


class TestHeuristicPipeline:
    """Tests for HeuristicPipeline class."""

    @pytest.fixture
    def test_board(self):
        """Create a simple 100x100 board."""
        return Board(width=100.0, height=100.0, origin=(0.0, 0.0))

    @pytest.fixture
    def test_components(self):
        """Create test components."""
        return [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5.0, 4.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="R1",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="C1",
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
        ]

    @pytest.fixture
    def test_netlist(self, test_components):
        """Create test netlist."""
        nets = [Net("NET1", [("U1", "1"), ("R1", "1"), ("C1", "1")])]
        return Netlist(components=test_components, nets=nets)

    @pytest.fixture
    def test_constraints(self):
        """Create test constraints."""
        return PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=5.0,
        )

    def test_empty_pipeline_runs(self, test_board, test_netlist, test_constraints, rng_key):
        """Empty pipeline runs without error (uses random fill)."""
        pipeline = HeuristicPipeline()

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        assert isinstance(result, PipelineResult)
        assert result.state is not None
        # Random fill should place all components
        assert len(result.unplaced) == 0

    def test_register_heuristic(self):
        """Can register heuristics."""
        pipeline = HeuristicPipeline()
        heuristic = MockHeuristic("test", HeuristicPriority.STYLE)

        pipeline.register(heuristic)

        registered = pipeline.get_registered_heuristics()
        assert len(registered) == 1
        assert registered[0] == ("test", HeuristicPriority.STYLE)

    def test_register_all(self):
        """Can register multiple heuristics at once."""
        pipeline = HeuristicPipeline()
        h1: Heuristic = MockHeuristic("h1", HeuristicPriority.HARD)
        h2: Heuristic = MockHeuristic("h2", HeuristicPriority.STYLE)

        pipeline.register_all([h1, h2])

        registered = pipeline.get_registered_heuristics()
        assert len(registered) == 2

    def test_clear_heuristics(self):
        """Can clear all registered heuristics."""
        pipeline = HeuristicPipeline()
        pipeline.register(MockHeuristic("test", HeuristicPriority.STYLE))

        pipeline.clear()

        assert len(pipeline.get_registered_heuristics()) == 0

    def test_heuristics_executed_in_priority_order(
        self, test_board, test_netlist, test_constraints, rng_key
    ):
        """Heuristics are executed in priority order (lowest first)."""
        pipeline = HeuristicPipeline()
        execution_order = []

        # Register in random order
        pipeline.register(
            MockHeuristic("style", HeuristicPriority.STYLE, record_execution=execution_order)
        )
        pipeline.register(
            MockHeuristic("hard", HeuristicPriority.HARD, record_execution=execution_order)
        )
        pipeline.register(
            MockHeuristic("org", HeuristicPriority.ORGANIZATIONAL, record_execution=execution_order)
        )

        pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        # Should be executed in priority order: HARD(0) -> ORGANIZATIONAL(2) -> STYLE(3)
        assert execution_order == ["hard", "org", "style"]

    def test_heuristic_placements_applied(
        self, test_board, test_netlist, test_constraints, rng_key
    ):
        """Placements from heuristics are applied to result."""
        pipeline = HeuristicPipeline()

        placement = ComponentPlacement(
            ref="U1",
            position=(50.0, 50.0),
            rotation=1,
            confidence=0.95,
            placed_by="test_heuristic",
        )

        heuristic = MockHeuristic(
            "test",
            HeuristicPriority.STRUCTURAL,
            placements={"U1": placement},
        )
        pipeline.register(heuristic)

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        assert "U1" in result.placements
        assert result.placements["U1"].position == (50.0, 50.0)
        assert result.placements["U1"].rotation == 1

    def test_heuristic_stats_recorded(self, test_board, test_netlist, test_constraints, rng_key):
        """Stats are recorded for each heuristic."""
        pipeline = HeuristicPipeline()

        heuristic = MockHeuristic("test", HeuristicPriority.STRUCTURAL)
        pipeline.register(heuristic)

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        assert "test" in result.heuristic_stats
        assert "placed" in result.heuristic_stats["test"]
        assert "priority" in result.heuristic_stats["test"]

    def test_random_fill_for_unplaced(self, test_board, test_netlist, test_constraints, rng_key):
        """Random fill places components not placed by heuristics."""
        pipeline = HeuristicPipeline()

        # Heuristic that only places U1
        placement = ComponentPlacement(ref="U1", position=(50.0, 50.0))
        heuristic = MockHeuristic(
            "partial",
            HeuristicPriority.STRUCTURAL,
            placements={"U1": placement},
        )
        pipeline.register(heuristic)

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        # All components should be placed (U1 by heuristic, others by fill)
        assert "U1" in result.placements
        assert "R1" in result.placements
        assert "C1" in result.placements
        assert "random_fill" in result.heuristic_stats

    def test_state_has_correct_shape(self, test_board, test_netlist, test_constraints, rng_key):
        """Resulting PlacementState has correct shape."""
        pipeline = HeuristicPipeline()

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        assert result.state.positions.shape == (3, 2)  # 3 components, x/y
        assert result.state.rotation_logits.shape == (3, 4)  # 3 components, 4 rotations

    def test_state_positions_match_placements(
        self, test_board, test_netlist, test_constraints, rng_key
    ):
        """State positions match placements dictionary."""
        pipeline = HeuristicPipeline()

        placement = ComponentPlacement(ref="U1", position=(30.0, 40.0))
        heuristic = MockHeuristic(
            "test",
            HeuristicPriority.STRUCTURAL,
            placements={"U1": placement},
        )
        pipeline.register(heuristic)

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        # Get U1's index in netlist
        u1_idx = test_netlist.get_component_index("U1")
        pos = result.state.positions[u1_idx]

        assert float(pos[0]) == pytest.approx(30.0, abs=0.1)
        assert float(pos[1]) == pytest.approx(40.0, abs=0.1)

    def test_rotation_logits_favor_chosen_rotation(
        self, test_board, test_netlist, test_constraints, rng_key
    ):
        """Rotation logits strongly favor the chosen rotation."""
        pipeline = HeuristicPipeline()

        placement = ComponentPlacement(ref="U1", position=(50.0, 50.0), rotation=2)
        heuristic = MockHeuristic(
            "test",
            HeuristicPriority.STRUCTURAL,
            placements={"U1": placement},
        )
        pipeline.register(heuristic)

        result = pipeline.run(
            board=test_board,
            netlist=test_netlist,
            constraints=test_constraints,
            key=rng_key,
        )

        u1_idx = test_netlist.get_component_index("U1")
        logits = result.state.rotation_logits[u1_idx]

        # Rotation 2 should have highest logit
        assert jnp.argmax(logits) == 2

    def test_conflict_strategy_configurable(self):
        """Conflict resolution strategy is configurable."""
        pipeline = HeuristicPipeline(
            conflict_strategy=ResolutionStrategy.REJECT,
            min_spacing_mm=1.0,
        )

        assert pipeline.conflict_strategy == ResolutionStrategy.REJECT
        assert pipeline.min_spacing_mm == 1.0


class TestCreateDefaultPipeline:
    """Tests for create_default_pipeline factory function."""

    def test_creates_pipeline(self):
        """Factory creates a HeuristicPipeline instance."""
        pipeline = create_default_pipeline()
        assert isinstance(pipeline, HeuristicPipeline)

    def test_default_conflict_strategy(self):
        """Default pipeline uses NUDGE strategy."""
        pipeline = create_default_pipeline()
        assert pipeline.conflict_strategy == ResolutionStrategy.NUDGE

    def test_default_min_spacing(self):
        """Default pipeline has 0.5mm min spacing."""
        pipeline = create_default_pipeline()
        assert pipeline.min_spacing_mm == 0.5


class TestPipelineWithEmptyBoard:
    """Tests for pipeline behavior with edge cases."""

    @pytest.fixture
    def empty_netlist(self):
        """Create an empty netlist."""
        return Netlist(components=[], nets=[])

    def test_empty_netlist_works(self, simple_board, empty_netlist, rng_key):
        """Pipeline handles empty netlist gracefully."""
        pipeline = HeuristicPipeline()
        constraints = PlacementConstraints()

        result = pipeline.run(
            board=simple_board,
            netlist=empty_netlist,
            constraints=constraints,
            key=rng_key,
        )

        assert result.state.positions.shape == (0, 2)
        assert len(result.placements) == 0
        assert len(result.unplaced) == 0

    def test_single_component(self, simple_board, rng_key):
        """Pipeline handles single component."""
        component = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
        )
        netlist = Netlist(components=[component], nets=[])
        constraints = PlacementConstraints()

        pipeline = HeuristicPipeline()
        result = pipeline.run(
            board=simple_board,
            netlist=netlist,
            constraints=constraints,
            key=rng_key,
        )

        assert len(result.placements) == 1
        assert "U1" in result.placements


class TestPipelineConflictResolution:
    """Tests for conflict resolution within pipeline."""

    @pytest.fixture
    def test_board(self):
        """Board large enough to allow nudging."""
        return Board(width=80.0, height=80.0, origin=(0.0, 0.0))

    @pytest.fixture
    def two_components(self):
        """Two components that could overlap."""
        return [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(10.0, 8.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
            Component(
                ref="U2",
                footprint="SOIC-8",
                bounds=(10.0, 8.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ),
        ]

    @pytest.fixture
    def two_comp_netlist(self, two_components):
        """Netlist with two components."""
        return Netlist(components=two_components, nets=[])

    def test_conflicting_placements_resolved(self, test_board, two_comp_netlist, rng_key):
        """Conflicting placements from heuristics are resolved."""
        pipeline = HeuristicPipeline(
            conflict_strategy=ResolutionStrategy.NUDGE,
            min_spacing_mm=0.5,
        )

        # Two heuristics placing components at same spot (center of board)
        placement1 = ComponentPlacement(ref="U1", position=(40.0, 40.0))
        placement2 = ComponentPlacement(ref="U2", position=(40.0, 40.0))

        h1 = MockHeuristic("h1", HeuristicPriority.STRUCTURAL, {"U1": placement1})
        h2 = MockHeuristic("h2", HeuristicPriority.ORGANIZATIONAL, {"U2": placement2})

        pipeline.register(h1)
        pipeline.register(h2)

        constraints = PlacementConstraints(board_margin_mm=3.0)
        result = pipeline.run(
            board=test_board,
            netlist=two_comp_netlist,
            constraints=constraints,
            key=rng_key,
        )

        # Both should be placed (conflict resolved by nudge)
        assert "U1" in result.placements
        assert "U2" in result.placements

        # Positions should be different (U2 was nudged)
        pos1 = result.placements["U1"].position
        pos2 = result.placements["U2"].position
        assert pos1 != pos2
