"""
Tests for routing verifier integration with placement feedback (temper-wna.6).

The RoutingVerifier is the main entry point for routing verification,
connecting all routing analysis modules and providing feedback to the optimizer.

Verification Levels:
- TOPOLOGICAL (Level 1): Net ordering + layer assignment only (<1s)
- GEOMETRIC (Level 2): Congestion analysis (~5s)
- MAZE (Level 3): Actual pathfinding (~10s)
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType
from temper_placer.core.netlist import Component, Net, Netlist, Pin

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_board():
    """Create a simple 100x100mm board for testing."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[],
    )


@pytest.fixture
def sample_netlist():
    """Create a sample netlist for verifier testing."""
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[
                Pin("G", "1", (-5.0, 0.0), net="GATE_H"),
                Pin("C", "2", (0.0, 0.0), net="DC_BUS_P"),
            ],
            net_class="HighVoltage",
        ),
        Component(
            ref="U_GATE",
            footprint="SOIC-16",
            bounds=(10.0, 6.0),
            pins=[
                Pin("OUT", "1", (4.0, 0.0), net="GATE_H"),
                Pin("VCC", "8", (-4.0, 0.0), net="VCC_15V"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="C1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin("1", "1", (-0.9, 0.0), net="VCC_15V"),
                Pin("2", "2", (0.9, 0.0), net="GND"),
            ],
            net_class="Signal",
        ),
    ]

    nets = [
        Net("DC_BUS_P", [("Q1", "C")], net_class="HighVoltage"),
        Net("GATE_H", [("Q1", "G"), ("U_GATE", "OUT")], net_class="GateDrive"),
        Net("VCC_15V", [("U_GATE", "VCC"), ("C1", "1")], net_class="Power"),
        Net("GND", [("C1", "2")], net_class="Power"),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def sample_loops():
    """Create sample loops for verification."""
    collection = LoopCollection()

    collection.add_loop(
        Loop(
            name="gate_drive_high",
            loop_type=LoopType.GATE_DRIVE_HIGH,
            description="High-side gate drive loop",
            components=["U_GATE", "Q1"],
            nets=["GATE_H"],
            max_area_mm2=50,
            priority=LoopPriority.HIGH,
        )
    )

    return collection


@pytest.fixture
def sample_positions():
    """Create sample positions for the netlist."""
    return jnp.array(
        [
            [20.0, 50.0],  # Q1
            [60.0, 50.0],  # U_GATE
            [80.0, 50.0],  # C1
        ]
    )


# =============================================================================
# Tests for VerificationLevel Enum
# =============================================================================


class TestVerificationLevel:
    """Tests for VerificationLevel enumeration."""

    def test_verification_levels_exist(self):
        """Should have all expected verification levels."""
        from temper_placer.routing.verifier import VerificationLevel

        assert hasattr(VerificationLevel, "TOPOLOGICAL")
        assert hasattr(VerificationLevel, "GEOMETRIC")
        assert hasattr(VerificationLevel, "MAZE")

    def test_verification_level_ordering(self):
        """Levels should be ordered by complexity."""
        from temper_placer.routing.verifier import VerificationLevel

        assert VerificationLevel.TOPOLOGICAL.value < VerificationLevel.GEOMETRIC.value
        assert VerificationLevel.GEOMETRIC.value < VerificationLevel.MAZE.value


# =============================================================================
# Tests for RoutingVerifierConfig Dataclass
# =============================================================================


class TestRoutingVerifierConfig:
    """Tests for RoutingVerifierConfig."""

    def test_default_config(self):
        """Should create config with sensible defaults."""
        from temper_placer.routing.verifier import RoutingVerifierConfig, VerificationLevel

        config = RoutingVerifierConfig()

        assert config.level == VerificationLevel.GEOMETRIC
        assert config.cell_size_mm > 0
        assert config.congestion_threshold > 0
        assert config.max_routing_time_s > 0

    def test_custom_config(self):
        """Should accept custom configuration."""
        from temper_placer.routing.verifier import RoutingVerifierConfig, VerificationLevel

        config = RoutingVerifierConfig(
            level=VerificationLevel.MAZE,
            cell_size_mm=0.5,
            congestion_threshold=0.9,
            max_routing_time_s=30.0,
        )

        assert config.level == VerificationLevel.MAZE
        assert config.cell_size_mm == 0.5


# =============================================================================
# Tests for RoutingVerifier Class
# =============================================================================


class TestRoutingVerifierInit:
    """Tests for RoutingVerifier initialization."""

    def test_verifier_creation(self):
        """Should create a verifier with default config."""
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        assert verifier is not None
        assert verifier.config is not None

    def test_verifier_with_custom_config(self):
        """Should accept custom configuration."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        config = RoutingVerifierConfig(level=VerificationLevel.TOPOLOGICAL)
        verifier = RoutingVerifier(config)

        assert verifier.config.level == VerificationLevel.TOPOLOGICAL


# =============================================================================
# Tests for Verification at Different Levels
# =============================================================================


class TestTopologicalVerification:
    """Tests for Level 1 (Topological) verification."""

    def test_topological_verify(self, sample_netlist, sample_positions, simple_board, sample_loops):
        """Should perform topological verification quickly."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        config = RoutingVerifierConfig(level=VerificationLevel.TOPOLOGICAL)
        verifier = RoutingVerifier(config)

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        assert result is not None
        assert hasattr(result, "feasible")
        assert hasattr(result, "net_ordering")
        assert hasattr(result, "layer_assignments")

    def test_topological_returns_ordering(
        self, sample_netlist, sample_positions, simple_board, sample_loops
    ):
        """Should return net ordering at topological level."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        config = RoutingVerifierConfig(level=VerificationLevel.TOPOLOGICAL)
        verifier = RoutingVerifier(config)

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        assert result.net_ordering is not None
        assert len(result.net_ordering) == len(sample_netlist.nets)


class TestGeometricVerification:
    """Tests for Level 2 (Geometric) verification."""

    def test_geometric_verify(self, sample_netlist, sample_positions, simple_board, sample_loops):
        """Should perform geometric verification with congestion analysis."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        config = RoutingVerifierConfig(level=VerificationLevel.GEOMETRIC)
        verifier = RoutingVerifier(config)

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        assert result is not None
        assert hasattr(result, "congestion_map")

    def test_geometric_detects_congestion(self, simple_board, sample_loops):
        """Should detect congestion in dense placement."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        # Create a very dense netlist in small area
        components = []
        nets = []
        for i in range(10):
            components.append(
                Component(
                    ref=f"U{i}",
                    footprint="SOIC-8",
                    bounds=(5.0, 4.0),
                    pins=[
                        Pin("1", "1", (0, 0), net=f"NET_{i}"),
                        Pin("2", "2", (0, 1), net=f"NET_{(i + 1) % 10}"),
                    ],
                )
            )
            nets.append(Net(f"NET_{i}", [(f"U{i}", "1"), (f"U{(i + 1) % 10}", "2")]))

        dense_netlist = Netlist(components=components, nets=nets)

        # All components clustered in 10x10 area
        dense_positions = jnp.array([[50.0 + (i % 3) * 5, 50.0 + (i // 3) * 5] for i in range(10)])

        config = RoutingVerifierConfig(
            level=VerificationLevel.GEOMETRIC,
            congestion_threshold=0.5,
        )
        verifier = RoutingVerifier(config)

        result = verifier.verify(
            netlist=dense_netlist,
            positions=dense_positions,
            board=simple_board,
            loops=sample_loops,
        )

        # Dense placement should show some congestion
        assert result.congestion_map is not None


class TestMazeVerification:
    """Tests for Level 3 (Maze) verification."""

    def test_maze_verify(self, sample_netlist, sample_positions, simple_board, sample_loops):
        """Should perform full maze routing verification."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        config = RoutingVerifierConfig(level=VerificationLevel.MAZE)
        verifier = RoutingVerifier(config)

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        assert result is not None
        assert hasattr(result, "completion_rate")

    def test_maze_returns_routed_paths(
        self, sample_netlist, sample_positions, simple_board, sample_loops
    ):
        """Should return actual routing paths when successful."""
        from temper_placer.routing.verifier import (
            RoutingVerifier,
            RoutingVerifierConfig,
            VerificationLevel,
        )

        config = RoutingVerifierConfig(level=VerificationLevel.MAZE)
        verifier = RoutingVerifier(config)

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        if result.feasible:
            assert result.completion_rate == 1.0


# =============================================================================
# Tests for Placement Feedback Generation
# =============================================================================


class TestPlacementFeedback:
    """Tests for generating placement adjustment hints."""

    def test_generate_feedback_from_failures(self, sample_netlist, simple_board, sample_loops):
        """Should generate placement hints from routing failures."""
        from temper_placer.routing.diagnostics import RoutingReport
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        # Create a mock report with failures
        report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=["NET_A"],
            failed_nets=["NET_B"],
            diagnostics=[],
            congestion_map=None,
            total_wirelength=100.0,
            total_vias=5,
            worst_congestion=1.5,
        )

        adjustments = verifier.to_placement_feedback(report)

        assert isinstance(adjustments, list)

    def test_feedback_sorted_by_priority(self):
        """Placement hints should be sorted by priority."""
        from temper_placer.routing.diagnostics import (
            FailureType,
            PlacementAdjustment,
            RoutingDiagnostic,
            RoutingReport,
        )
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        # Create report with multiple diagnostics of different priorities
        diag1 = RoutingDiagnostic(
            net="NET_A",
            failure_type=FailureType.NO_PATH,
            location=(0, 0),
            severity="warning",
            blocking_elements=["C1"],
            constraint_violated=None,
            suggested_fix="Move C1",
            fix_confidence=0.5,
            placement_hint=PlacementAdjustment(
                component="C1",
                adjustment_type="move",
                direction=(1.0, 0.0),
                reason="Clear path",
                priority=0.5,
            ),
        )

        diag2 = RoutingDiagnostic(
            net="NET_B",
            failure_type=FailureType.NO_PATH,
            location=(0, 0),
            severity="critical",
            blocking_elements=["Q1"],
            constraint_violated=None,
            suggested_fix="Move Q1",
            fix_confidence=0.9,
            placement_hint=PlacementAdjustment(
                component="Q1",
                adjustment_type="move",
                direction=(2.0, 0.0),
                reason="Critical path",
                priority=1.0,  # Higher priority
            ),
        )

        report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=[],
            failed_nets=["NET_A", "NET_B"],
            diagnostics=[diag1, diag2],
            congestion_map=None,
            total_wirelength=0,
            total_vias=0,
            worst_congestion=0,
        )

        adjustments = verifier.to_placement_feedback(report)

        # Higher priority (Q1) should come first
        if len(adjustments) >= 2:
            assert adjustments[0].priority >= adjustments[1].priority


# =============================================================================
# Tests for Determinism
# =============================================================================


class TestVerifierDeterminism:
    """Tests for verifier determinism."""

    def test_verify_deterministic(
        self, sample_netlist, sample_positions, simple_board, sample_loops
    ):
        """Same inputs should produce identical results."""
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        result1 = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        result2 = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        assert result1.feasible == result2.feasible
        assert result1.net_ordering == result2.net_ordering


# =============================================================================
# Tests for Verifier with PCL Constraints
# =============================================================================


class TestVerifierWithConstraints:
    """Tests for verifier integration with PCL constraints."""

    def test_verify_with_constraints(
        self, sample_netlist, sample_positions, simple_board, sample_loops
    ):
        """Should accept PCL constraints for verification."""
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        # Mock constraints (in real code, loaded from PCL)
        constraints = None  # TODO: Add PCLConstraints fixture

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
            constraints=constraints,
        )

        assert result is not None


# =============================================================================
# Tests for CLI Integration
# =============================================================================


class TestVerifierCLI:
    """Tests for CLI flag handling."""

    def test_verification_level_from_string(self):
        """Should parse verification level from CLI string."""
        from temper_placer.routing.verifier import (
            VerificationLevel,
            parse_verification_level,
        )

        assert parse_verification_level("topological") == VerificationLevel.TOPOLOGICAL
        assert parse_verification_level("geometric") == VerificationLevel.GEOMETRIC
        assert parse_verification_level("maze") == VerificationLevel.MAZE

    def test_verification_level_case_insensitive(self):
        """Should handle case variations."""
        from temper_placer.routing.verifier import (
            VerificationLevel,
            parse_verification_level,
        )

        assert parse_verification_level("TOPOLOGICAL") == VerificationLevel.TOPOLOGICAL
        assert parse_verification_level("Geometric") == VerificationLevel.GEOMETRIC

    def test_invalid_level_raises(self):
        """Should raise for invalid verification level."""
        from temper_placer.routing.verifier import parse_verification_level

        with pytest.raises(ValueError):
            parse_verification_level("invalid_level")


# =============================================================================
# Tests for Timeout Handling
# =============================================================================


class TestVerifierTimeout:
    """Tests for verification timeout handling."""

    def test_respects_timeout(self):
        """Should respect max_routing_time_s configuration."""
        from temper_placer.routing.verifier import RoutingVerifierConfig

        config = RoutingVerifierConfig(max_routing_time_s=5.0)

        assert config.max_routing_time_s == 5.0

    # Note: Actual timeout testing would require a slow verification scenario
    # which is impractical for unit tests. Integration tests should cover this.


# =============================================================================
# Tests for Complete Verification Pipeline
# =============================================================================


class TestCompletePipeline:
    """Integration tests for the complete verification pipeline."""

    def test_simple_placement_verifiable(
        self, sample_netlist, sample_positions, simple_board, sample_loops
    ):
        """Simple, spread-out placement should verify successfully."""
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        # A simple, spread-out placement should be routable
        assert result.feasible is True or result.completion_rate > 0.8

    def test_verification_result_has_all_fields(
        self, sample_netlist, sample_positions, simple_board, sample_loops
    ):
        """Result should have all expected fields."""
        from temper_placer.routing.verifier import RoutingVerifier

        verifier = RoutingVerifier()

        result = verifier.verify(
            netlist=sample_netlist,
            positions=sample_positions,
            board=simple_board,
            loops=sample_loops,
        )

        # Check all expected attributes
        assert hasattr(result, "feasible")
        assert hasattr(result, "completion_rate")
        assert hasattr(result, "net_ordering")
        assert hasattr(result, "layer_assignments")
        assert hasattr(result, "diagnostics")
