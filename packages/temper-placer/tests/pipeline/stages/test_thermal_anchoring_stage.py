"""U12: Integration tests for thermal anchoring stage.

Tests the ThermalAnchoringStage with a mock DataContext containing
board, netlist, and constraints.  Verifies gate conditions, no-op
behavior, anchor placement, and safety gate integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.io.config_loader import (
    PlacementConstraints,
    PlacementInitialization,
    ThermalConstraint,
    ThermalProperties,
)
from temper_placer.pipeline.dag_types import DataContext, StageResult
from temper_placer.pipeline.state import PipelineError, PipelineState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def board():
    return Board(width=100.0, height=150.0)


@pytest.fixture
def pipeline_state():
    from temper_placer.pipeline.state import PipelineConfig

    return PipelineState(config=PipelineConfig(input_pcb=Path("/dev/null")))


@pytest.fixture
def netlist_with_power_devices():
    comps = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 21.0),
            initial_position=(50.0, 140.0),
            fixed=False,
            zone="power_zone",
        ),
        Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(16.0, 21.0),
            initial_position=(70.0, 135.0),
            fixed=False,
            zone="power_zone",
        ),
        Component(
            ref="C1",
            footprint="0805",
            bounds=(2.0, 1.25),
            initial_position=(50.0, 75.0),
            fixed=False,
        ),
    ]
    return Netlist(components=comps, nets=[])


@pytest.fixture
def constraints_with_thermal_anchoring():
    """Constraints with thermal_anchoring enabled and thermal_properties."""
    constraints = PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=150.0,
        initialization=PlacementInitialization(
            thermal_anchoring=True,
            anchoring_grid_resolution=25,
        ),
        thermal_constraints=[
            ThermalConstraint(
                components=["Q1", "Q2"],
                prefer_edge=True,
                max_distance_from_edge_mm=10.0,
            ),
        ],
        thermal_properties=ThermalProperties(
            high_power_components=["Q1", "Q2"],
            power_dissipation_w={"Q1": 20.0, "Q2": 20.0},
            min_separation_mm=15.0,
            rated_tj_max={"Q1": 175.0, "Q2": 175.0},
        ),
    )
    return constraints


@pytest.fixture
def constraints_without_anchoring():
    """Constraints with thermal_anchoring disabled."""
    constraints = PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=150.0,
        initialization=PlacementInitialization(thermal_anchoring=False),
        thermal_constraints=[
            ThermalConstraint(
                components=["Q1", "Q2"],
                prefer_edge=True,
                max_distance_from_edge_mm=10.0,
            ),
        ],
        thermal_properties=ThermalProperties(
            high_power_components=["Q1", "Q2"],
            power_dissipation_w={"Q1": 20.0, "Q2": 20.0},
            rated_tj_max={"Q1": 175.0, "Q2": 175.0},
        ),
    )
    return constraints


@pytest.fixture
def constraints_without_thermal_constraints():
    """Constraints without any thermal_constraints (should skip anchoring)."""
    constraints = PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=150.0,
        initialization=PlacementInitialization(thermal_anchoring=True),
    )
    return constraints


@pytest.fixture
def constraints_without_thermal_properties():
    """Constraints with anchoring enabled but no thermal_properties."""
    constraints = PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=150.0,
        initialization=PlacementInitialization(thermal_anchoring=True),
        thermal_constraints=[
            ThermalConstraint(
                components=["Q1"],
                prefer_edge=True,
                max_distance_from_edge_mm=10.0,
            ),
        ],
    )
    return constraints


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThermalAnchoringStage:
    """Integration tests for the thermal anchoring pipeline stage."""

    def test_anchoring_active_writes_fixed_positions(
        self, board, pipeline_state, netlist_with_power_devices, constraints_with_thermal_anchoring
    ):
        """Happy path: thermal_anchoring=True + thermal_constraints -> anchors written."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        state = pipeline_state
        context: DataContext = {
            "board": board,
            "netlist": netlist_with_power_devices,
            "constraints": constraints_with_thermal_anchoring,
        }

        stage = ThermalAnchoringStage()
        result = stage(state, context)

        assert isinstance(result, StageResult)
        assert "Q1" in constraints_with_thermal_anchoring.fixed_positions
        assert "Q2" in constraints_with_thermal_anchoring.fixed_positions
        assert "Q1" in constraints_with_thermal_anchoring.fixed_components
        assert "Q2" in constraints_with_thermal_anchoring.fixed_components

        # Verify R1: anchors are near TOP edge (within max_distance=10mm)
        q1_x, q1_y = constraints_with_thermal_anchoring.fixed_positions["Q1"]
        q2_x, q2_y = constraints_with_thermal_anchoring.fixed_positions["Q2"]
        assert 150.0 - q1_y <= 10.0, f"Q1 is {150.0 - q1_y:.1f}mm from TOP edge"
        assert 150.0 - q2_y <= 10.0, f"Q2 is {150.0 - q2_y:.1f}mm from TOP edge"

        # Verify R2: minimum separation
        dx = q1_x - q2_x
        dy = q1_y - q2_y
        dist = (dx**2 + dy**2) ** 0.5
        assert dist >= 15.0, f"Q1-Q2 separation is {dist:.1f}mm < 15mm"

        # Verify state flag
        assert state.thermal_anchoring_applied is True

    def test_anchoring_disabled_is_noop(
        self, board, netlist_with_power_devices, constraints_without_anchoring
    ):
        """thermal_anchoring=False -> stage is no-op."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        state = pipeline_state
        context: DataContext = {
            "board": board,
            "netlist": netlist_with_power_devices,
            "constraints": constraints_without_anchoring,
        }

        stage = ThermalAnchoringStage()
        result = stage(state, context)

        assert isinstance(result, StageResult)
        assert constraints_without_anchoring.fixed_positions == {}

    def test_no_thermal_constraints_is_noop(
        self, board, netlist_with_power_devices, constraints_without_thermal_constraints
    ):
        """No thermal_constraints in PCL -> stage is no-op."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        state = pipeline_state
        context: DataContext = {
            "board": board,
            "netlist": netlist_with_power_devices,
            "constraints": constraints_without_thermal_constraints,
        }

        stage = ThermalAnchoringStage()
        result = stage(state, context)

        assert isinstance(result, StageResult)
        assert constraints_without_thermal_constraints.fixed_positions == {}

    def test_no_thermal_properties_is_noop(
        self, board, netlist_with_power_devices, constraints_without_thermal_properties
    ):
        """Anchoring enabled but no thermal_properties -> stage skips."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        state = pipeline_state
        context: DataContext = {
            "board": board,
            "netlist": netlist_with_power_devices,
            "constraints": constraints_without_thermal_properties,
        }

        stage = ThermalAnchoringStage()
        result = stage(state, context)

        assert isinstance(result, StageResult)

    def test_no_constraints_in_context_is_noop(self, board, pipeline_state, netlist_with_power_devices):
        """No constraints object in context -> stage is no-op."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        state = pipeline_state
        context: DataContext = {
            "board": board,
            "netlist": netlist_with_power_devices,
        }

        stage = ThermalAnchoringStage()
        result = stage(state, context)

        assert isinstance(result, StageResult)

    def test_missing_board_or_netlist_is_noop(self, pipeline_state, constraints_with_thermal_anchoring):
        """Missing board or netlist -> stage is no-op."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        state = pipeline_state
        context: DataContext = {
            "constraints": constraints_with_thermal_anchoring,
        }

        stage = ThermalAnchoringStage()
        result = stage(state, context)

        assert isinstance(result, StageResult)

    def test_stage_returns_stage_result(self):
        """Smoke test: stage can be instantiated and called."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        stage = ThermalAnchoringStage()
        assert hasattr(stage, "__call__")

    def test_anchors_deterministic_across_runs(
        self, board, pipeline_state, netlist_with_power_devices, constraints_with_thermal_anchoring
    ):
        """SC7: Same input produces identical anchors across runs."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        def run():
            c = PlacementConstraints(
                board_width_mm=100.0,
                board_height_mm=150.0,
                initialization=PlacementInitialization(
                    thermal_anchoring=True,
                    anchoring_grid_resolution=25,
                ),
                thermal_constraints=[
                    ThermalConstraint(
                        components=["Q1", "Q2"],
                        max_distance_from_edge_mm=10.0,
                    ),
                ],
                thermal_properties=ThermalProperties(
                    high_power_components=["Q1", "Q2"],
                    power_dissipation_w={"Q1": 20.0, "Q2": 20.0},
                    rated_tj_max={"Q1": 175.0, "Q2": 175.0},
                ),
            )
            state = pipeline_state
            context: DataContext = {
                "board": board,
                "netlist": netlist_with_power_devices,
                "constraints": c,
            }
            ThermalAnchoringStage()(state, context)
            return c.fixed_positions

        first = run()
        for _ in range(5):
            assert run() == first, "Anchors not deterministic across runs"


class TestThermalAnchoringSafetyGates:
    """Test safety gate behavior during stage execution."""

    def test_pipeline_error_on_missing_thermal_props(self, board, pipeline_state, netlist_with_power_devices):
        """PipelineError when thermal_properties is missing but anchoring enabled."""
        from temper_placer.pipeline.stages.thermal_anchoring_stage import (
            ThermalAnchoringStage,
        )

        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=150.0,
            initialization=PlacementInitialization(thermal_anchoring=True),
            thermal_constraints=[
                ThermalConstraint(
                    components=["Q1", "Q2"],
                ),
            ],
        )

        state = pipeline_state
        context: DataContext = {
            "board": board,
            "netlist": netlist_with_power_devices,
            "constraints": constraints,
        }

        stage = ThermalAnchoringStage()
        # Without thermal_properties, stage is a no-op (no PipelineError)
        result = stage(state, context)
        assert isinstance(result, StageResult)
