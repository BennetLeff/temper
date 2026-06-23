"""
Tests for U4: DRC fence invariant on PhasedComponentAssignmentStage.

Covers:
- Invariant declared when sidecar loaded
- Invariant absent when no sidecar
- Invariant flags components placed in CRITICAL cells
- Components in free cells / MEDIUM / HIGH cells are not flagged
"""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest

from temper_placer.deterministic.channels import ChannelMap
from temper_placer.deterministic.stages.phased_component_assignment import (
    CRITICAL_BOTTLENECK_INVARIANT,
    PhasedComponentAssignmentStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import PlacementConstraints


def _make_cmap(bottlenecks: list[dict], *, cell_size_um: int = 1000) -> ChannelMap:
    grid = [[0.0] * 4 for _ in range(4)]
    return ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": float(cell_size_um),
            "grid": grid,
            "bottlenecks": bottlenecks,
        }
    )


def _stage_with(channel_map: ChannelMap | None) -> PhasedComponentAssignmentStage:
    return PhasedComponentAssignmentStage(
        constraints=PlacementConstraints(),
        slot_spacing=10.0,
        channel_map=channel_map,
    )


class TestInvariantDeclaration:
    def test_invariant_declared_when_sidecar_loaded(self):
        cmap = _make_cmap(
            [
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ]
        )
        stage = _stage_with(cmap)
        invariant_names = [iv.check_name for iv in stage.invariants]
        assert CRITICAL_BOTTLENECK_INVARIANT in invariant_names

    def test_invariant_absent_when_no_sidecar(self):
        stage = _stage_with(None)
        assert CRITICAL_BOTTLENECK_INVARIANT not in [
            iv.check_name for iv in stage.invariants
        ]

    def test_invariant_absent_for_empty_map(self):
        stage = _stage_with(ChannelMap.empty())
        assert CRITICAL_BOTTLENECK_INVARIANT not in [
            iv.check_name for iv in stage.invariants
        ]


class TestViolationDetection:
    def test_invariant_flags_component_in_critical_cell(self, caplog):
        cmap = _make_cmap(
            [
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ]
        )
        stage = _stage_with(cmap)
        placements = {"U1": (1.5, 1.5)}  # gx=1, gy=1 -> CRITICAL

        with caplog.at_level(logging.WARNING):
            violations = stage.find_critical_bottleneck_violations(placements)

        assert len(violations) == 1
        v = violations[0]
        assert v["ref"] == "U1"
        assert v["x"] == 1
        assert v["y"] == 1
        assert v["layer"] == "F.Cu"
        assert v["severity"] == "CRITICAL"

    def test_invariant_passes_component_in_free_cell(self):
        cmap = _make_cmap(
            [
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ]
        )
        stage = _stage_with(cmap)
        # U1 in cell (0, 0); U2 in cell (3, 3). Both free.
        placements = {"U1": (0.5, 0.5), "U2": (3.5, 3.5)}
        violations = stage.find_critical_bottleneck_violations(placements)
        assert violations == []

    def test_invariant_passes_component_in_medium_bottleneck(self):
        cmap = _make_cmap(
            [
                # MEDIUM and HIGH cells must not trigger the fence.
                {"x": 0, "y": 0, "layer": "F.Cu", "severity": "MEDIUM", "score": 0.5},
                {"x": 1, "y": 0, "layer": "F.Cu", "severity": "HIGH", "score": 0.9},
            ]
        )
        stage = _stage_with(cmap)
        placements = {
            "U1": (0.5, 0.5),  # MEDIUM cell
            "U2": (1.5, 0.5),  # HIGH cell
        }
        violations = stage.find_critical_bottleneck_violations(placements)
        assert violations == []

    def test_invariant_soft_launch_logs_warning_only(self, caplog):
        """U4 only adds the WARNING-only path; U6 adds the hard-fail flip."""
        cmap = _make_cmap(
            [
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ]
        )
        stage = _stage_with(cmap)
        placements = {"U1": (1.5, 1.5)}
        with caplog.at_level(logging.WARNING):
            violations = stage._check_critical_bottlenecks(placements)
        assert len(violations) == 1
        assert any("CRITICAL" in r.message for r in caplog.records)
        # And the run does not raise.
        assert violations[0]["ref"] == "U1"

    def test_invariant_out_of_grid_not_flagged(self):
        cmap = _make_cmap(
            [
                # CRITICAL cell at gx=1, gy=1
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ]
        )
        stage = _stage_with(cmap)
        # Slot far outside the 4x4 grid (which spans 0..4mm in both axes)
        placements = {"U1": (50.0, 50.0)}
        violations = stage.find_critical_bottleneck_violations(placements)
        assert violations == []
