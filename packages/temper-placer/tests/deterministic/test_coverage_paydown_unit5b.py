"""
Coverage paydown unit5b — deterministic module entries still uncovered.

Targets:
- Stage base class properties (declared_reads, declared_writes, invariants,
  is_active, last_modified_regions, name, run) — 7 entries
- Stage .name properties for stages lacking coverage — ~10 entries
- ClearanceGrid public methods (occupancy_grid, export_stats,
  export_visualization) — 3 FAIL entries
- ClearanceGridStage.name — 1 FAIL entry
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid, ClearanceGridStage


# ============================================================================
# Concrete Stage subclass for testing base class properties
# ============================================================================


class _ConcreteStage(Stage):
    """Minimal concrete Stage with all default base-class behaviour."""

    @property
    def name(self) -> str:
        return "concrete_test"

    def run(self, state: BoardState) -> BoardState:
        return state


class _CustomStage(Stage):
    """Stage that overrides all base-class properties."""

    @property
    def name(self) -> str:
        return "custom"

    @property
    def invariants(self):
        return ("inv1", "inv2")

    @property
    def last_modified_regions(self):
        return [(0.0, 0.0, 10.0, 10.0)]

    @property
    def declared_writes(self):
        return ("write1",)

    @property
    def declared_reads(self):
        return ("read1",)

    @property
    def is_active(self) -> bool:
        return False

    def run(self, state: BoardState) -> BoardState:
        return state


# ============================================================================
# Stage base class tests
# ============================================================================


class TestStageBaseProperties:
    """Cover Stage.declared_reads, .declared_writes, .invariants, .is_active,
    .last_modified_regions, .name, .run."""

    def test_default_declared_reads(self):
        """Stage.declared_reads defaults to empty tuple."""
        stage = _ConcreteStage()
        assert stage.declared_reads == ()

    def test_default_declared_writes(self):
        """Stage.declared_writes defaults to empty tuple."""
        stage = _ConcreteStage()
        assert stage.declared_writes == ()

    def test_default_invariants(self):
        """Stage.invariants defaults to empty tuple."""
        stage = _ConcreteStage()
        assert stage.invariants == ()

    def test_default_is_active(self):
        """Stage.is_active defaults to True."""
        stage = _ConcreteStage()
        assert stage.is_active is True

    def test_default_last_modified_regions(self):
        """Stage.last_modified_regions defaults to None."""
        stage = _ConcreteStage()
        assert stage.last_modified_regions is None

    def test_concrete_name(self):
        """Stage.name returns the overridden value."""
        stage = _ConcreteStage()
        assert stage.name == "concrete_test"

    def test_run_passthrough(self):
        """Stage.run with a passthrough returns state unchanged."""
        stage = _ConcreteStage()
        board = Board(width=100.0, height=100.0)
        state = BoardState(board=board)
        result = stage.run(state)
        assert result is state

    def test_custom_invariants(self):
        """Stage.invariants can be overridden."""
        stage = _CustomStage()
        assert stage.invariants == ("inv1", "inv2")

    def test_custom_last_modified_regions(self):
        """Stage.last_modified_regions can be overridden."""
        stage = _CustomStage()
        assert stage.last_modified_regions == [(0.0, 0.0, 10.0, 10.0)]

    def test_custom_declared_writes(self):
        """Stage.declared_writes can be overridden."""
        stage = _CustomStage()
        assert stage.declared_writes == ("write1",)

    def test_custom_declared_reads(self):
        """Stage.declared_reads can be overridden."""
        stage = _CustomStage()
        assert stage.declared_reads == ("read1",)

    def test_custom_is_active(self):
        """Stage.is_active can be overridden to False."""
        stage = _CustomStage()
        assert stage.is_active is False


# ============================================================================
# Stage .name property tests (stages lacking coverage for .name)
# ============================================================================


class TestStageNames:
    """Cover .name properties for stages that are still on the allowlist."""

    def test_config_attach_stage_name(self):
        from temper_placer.deterministic.stages.config_attach import (
            ConfigAttachStage,
        )
        stage = ConfigAttachStage(config={})
        assert stage.name == "config_attach"

    def test_courtyard_check_stage_name(self):
        from temper_placer.deterministic.stages.courtyard_check import (
            CourtyardCheckStage,
        )
        stage = CourtyardCheckStage(courtyards={})
        assert stage.name == "courtyard_check"

    def test_drc_sweep_stage_name(self):
        from temper_placer.deterministic.stages.drc_sweep import (
            DRCSweepStage,
        )
        stage = DRCSweepStage()
        assert stage.name == "drc_sweep"

    def test_track_deduplication_stage_name(self):
        from temper_placer.deterministic.stages.drc_sweep import (
            TrackDeduplicationStage,
        )
        stage = TrackDeduplicationStage()
        assert stage.name == "track_deduplication"

    def test_drc_validation_stage_name(self):
        from temper_placer.deterministic.stages.drc_validation import (
            DRCValidationStage,
        )
        stage = DRCValidationStage()
        assert stage.name == "drc_validation"

    def test_drc_oracle_setup_stage_name(self):
        from temper_placer.deterministic.stages.setup import (
            DRCOracleSetupStage,
        )
        stage = DRCOracleSetupStage()
        assert stage.name == "drc_oracle_setup"

    def test_routing_channel_aware_slot_stage_name(self):
        from temper_placer.deterministic.stages.zone_aware_slot_generation import (
            RoutingChannelAwareSlotStage,
        )
        stage = RoutingChannelAwareSlotStage()
        assert stage.name == "routing_channel_aware_slot_generation"

    def test_clearance_grid_stage_name(self):
        """FAIL entry: ClearanceGridStage.name."""
        stage = ClearanceGridStage()
        assert stage.name == "clearance_grid"

    def test_via_deduplication_stage_name(self):
        from temper_placer.deterministic.stages.via_validation import (
            ViaDeduplicationStage,
        )
        stage = ViaDeduplicationStage()
        assert stage.name == "via_deduplication"

    def test_via_validation_stage_name(self):
        from temper_placer.deterministic.stages.via_validation import (
            ViaValidationStage,
        )
        stage = ViaValidationStage()
        assert stage.name == "via_validation"

    def test_short_circuit_detection_stage_name(self):
        from temper_placer.deterministic.stages.drc_sweep import (
            ShortCircuitDetectionStage,
        )
        stage = ShortCircuitDetectionStage()
        assert stage.name == "short_circuit_detection"

    def test_fine_pitch_escape_stage_name(self):
        from temper_placer.deterministic.stages.fine_pitch_escape import (
            FinePitchEscapeStage,
        )
        stage = FinePitchEscapeStage()
        assert stage.name == "fine_pitch_escape"

    def test_placement_validation_stage_name(self):
        from temper_placer.deterministic.stages.placement_validation import (
            PlacementValidationStage,
        )
        stage = PlacementValidationStage()
        assert stage.name == "placement_validation"


# ============================================================================
# ClearanceGrid public methods (FAIL entries)
# ============================================================================


class TestClearanceGridPublicMethods:
    """Cover ClearanceGrid.occupancy_grid, .export_stats, .export_visualization."""

    @pytest.fixture
    def grid(self):
        """A small 2-layer 50x50mm clearance grid."""
        return ClearanceGrid(width_mm=50.0, height_mm=50.0, cell_size_mm=1.0)

    def test_occupancy_grid_shape(self, grid):
        """ClearanceGrid.occupancy_grid returns a 3D ndarray."""
        og = grid.occupancy_grid
        import numpy as np
        assert isinstance(og, np.ndarray)
        assert og.ndim == 3
        # Default layer_count=2, height=50 cells, width=50 cells
        assert og.shape == (2, 50, 50)

    def test_export_stats_returns_dict(self, grid):
        """ClearanceGrid.export_stats returns a dictionary with expected keys."""
        stats = grid.export_stats()
        assert isinstance(stats, dict)
        assert "dimensions" in stats
        assert "layer_count" in stats
        assert "nets_registered" in stats
        assert stats["dimensions"]["width_mm"] == 50.0
        assert stats["dimensions"]["height_mm"] == 50.0
        assert stats["dimensions"]["cell_size_mm"] == 1.0

    def test_export_visualization_creates_file(self, grid, tmp_path):
        """ClearanceGrid.export_visualization writes a PNG file."""
        outpath = tmp_path / "grid_viz.png"
        grid.export_visualization(str(outpath), layer=0)
        # If matplotlib is available, the file should exist.
        # If not, the function prints a warning and returns.
        try:
            import matplotlib  # noqa: F401
            assert outpath.is_file(), f"Expected {outpath} to exist with matplotlib installed"
        except ImportError:
            # matplotlib not available — the function will print a warning and skip
            pass

    def test_export_visualization_bad_layer(self, grid, tmp_path):
        """ClearanceGrid.export_visualization with out-of-range layer returns early."""
        outpath = tmp_path / "grid_bad.png"
        # layer 99 is out of range for default 2-layer grid; should return early
        grid.export_visualization(str(outpath), layer=99)
        # Should not crash

    def test_export_stats_with_blocked_cells(self, grid):
        """export_stats includes blocking info when cells are blocked."""
        grid.block_circle(center=(25, 25), radius_mm=0.5, clearance_mm=0.3)
        stats = grid.export_stats()
        assert "blocking" in stats
        # At least layer 0 should have some blocked count
        assert "F_Cu" in stats["blocking"] or len(stats["blocking"]) > 0

    def test_occupancy_grid_after_blocking(self, grid):
        """Occupancy grid still has correct shape after blocking cells."""
        grid.block_circle(center=(25, 25), radius_mm=1.0, clearance_mm=0.0)
        og = grid.occupancy_grid
        import numpy as np
        assert og.shape == (2, 50, 50)
        assert og.dtype == np.int32


# ============================================================================
# Additional Stage .run methods that can work with minimal state
# ============================================================================


class TestMinimalStageRuns:
    """Cover .run() methods that accept minimal/empty state."""

    def test_drc_sweep_stage_run_empty_state(self):
        """DRCSweepStage.run with empty state returns state unchanged."""
        from temper_placer.deterministic.stages.drc_sweep import (
            DRCSweepStage,
        )
        stage = DRCSweepStage()
        board = Board(width=100.0, height=100.0)
        state = BoardState(board=board)
        result = stage.run(state)
        assert result is state  # no oracle -> no-op

    def test_via_deduplication_stage_run_empty_state(self):
        """ViaDeduplicationStage.run with empty state returns state unchanged."""
        from temper_placer.deterministic.stages.via_validation import (
            ViaDeduplicationStage,
        )
        stage = ViaDeduplicationStage()
        board = Board(width=100.0, height=100.0)
        state = BoardState(board=board)
        result = stage.run(state)
        # Run should not raise; state unchanged (no vias to dedup)
        assert isinstance(result, BoardState)

    def test_via_validation_stage_run_empty_state(self):
        """ViaValidationStage.run with empty state returns state unchanged."""
        from temper_placer.deterministic.stages.via_validation import (
            ViaValidationStage,
        )
        stage = ViaValidationStage()
        board = Board(width=100.0, height=100.0)
        state = BoardState(board=board)
        result = stage.run(state)
        # No vias or routes — early return
        assert result is state

    def test_short_circuit_detection_stage_run_empty_state(self):
        """ShortCircuitDetectionStage.run with empty state returns state unchanged."""
        from temper_placer.deterministic.stages.drc_sweep import (
            ShortCircuitDetectionStage,
        )
        stage = ShortCircuitDetectionStage()
        board = Board(width=100.0, height=100.0)
        state = BoardState(board=board)
        result = stage.run(state)
        assert isinstance(result, BoardState)

    def test_config_attach_stage_run_with_config(self):
        """ConfigAttachStage.run attaches config to state."""
        from temper_placer.deterministic.stages.config_attach import (
            ConfigAttachStage,
        )
        stage = ConfigAttachStage(config={"key": "value"})
        board = Board(width=100.0, height=100.0)
        state = BoardState(board=board)
        result = stage.run(state)
        assert result is not state  # new state with config
        assert result.config == {"key": "value"}
