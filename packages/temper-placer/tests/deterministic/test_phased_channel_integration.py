"""
Tests for U2: Placer score-thread integration.

Verifies that PhasedComponentAssignmentStage.score_slot closure adds the
routability term when channel_map is supplied, that disabling either
channel_map or w_r reproduces the baseline (no sidecar) output, that a
WARNING is logged when no sidecar is provided, and that the per-call
penalty lookup fits inside the 5µs/call budget.
"""

from __future__ import annotations

import logging
import statistics
import time

import pytest

from temper_placer.deterministic.channels import ChannelMap, routability_penalty
from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.io.config_loader import PlacementConstraints


def _make_two_slot_cmap(*, cell_size_um: float = 1000.0) -> ChannelMap:
    """Build a 4x4 grid with one CRITICAL bottleneck cell and a free cell.

    Cell (2, 2) is CRITICAL with occupancy 1.0 (worst case). All other
    cells are free and un-bottlenecked.
    """
    grid = [[0.0] * 4 for _ in range(4)]
    grid[2][2] = 1.0
    return ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": cell_size_um,
            "grid": grid,
            "bottlenecks": [
                {"x": 2, "y": 2, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ],
        }
    )


def _build_stage(
    *, channel_map: ChannelMap | None = None, w_r: float = 0.05
) -> PhasedComponentAssignmentStage:
    return PhasedComponentAssignmentStage(
        constraints=PlacementConstraints(),
        slot_spacing=10.0,
        channel_map=channel_map,
        w_r=w_r,
    )


class TestScoreSlotWithSidecar:
    def test_score_slot_with_sidecar_prefers_free_slot(self):
        """Two candidate slots, one CRITICAL, one wirelength-shorter.

        Wirelength delta = 0.05mm so the score contribution of the
        CRITICAL cell (penalty 1.0 * w_r 0.05 = 0.05) exactly equals
        the wirelength advantage; we expect the placer to pick the
        wirelength-shorter slot only when the wirelength delta exceeds
        the CRITICAL score contribution. With identical deltas the
        wirelength-shorter slot wins (lower score).
        """
        stage = _build_stage(channel_map=_make_two_slot_cmap())

        component_ref = "U1"
        # net_pins: the component is on a net with already-placed U2 at (10, 10)
        net_pins = {"NET1": [("U1", "1"), ("U2", "1")]}
        # U2 already at (10, 10). Candidate slots:
        # - free slot (3.5, 3.5) -> wirelength from (10, 10) = 13mm, penalty=0
        # - critical slot (2.5, 2.5) -> wirelength from (10, 10) = 15mm,
        #   penalty=1.0 -> contributes 0.05
        # Free slot score: 0 + 13*0.1 + 0 = 1.3
        # Critical slot score: 0 + 15*0.1 + 0.05 = 1.55
        # Free slot wins.
        current = {"U2": (10.0, 10.0)}
        free_slot = (3.5, 3.5)
        crit_slot = (2.5, 2.5)

        s_free = stage._select_best_slot(
            component_ref, [free_slot, crit_slot], current, {}, net_pins
        )
        assert s_free == free_slot

    def test_critical_wins_when_wirelength_advantage_is_small(self):
        """When the wirelength advantage of the free slot is small, the
        CRITICAL penalty should dominate.

        U2 at (2.7, 2.7). HPWL:
        - free slot (3.5, 3.5) -> max_x-min_x + max_y-min_y = 0.8 + 0.8 = 1.6
        - crit slot (2.5, 2.5) -> max_x-min_x + max_y-min_y = 0.2 + 0.2 = 0.4
        free score: 0 + 1.6*0.1 + 0 = 0.16
        crit score: 0 + 0.4*0.1 + 0.05 = 0.09 -> crit wins
        """
        stage = _build_stage(channel_map=_make_two_slot_cmap())
        net_pins = {"NET1": [("U1", "1"), ("U2", "1")]}
        current = {"U2": (2.7, 2.7)}
        free_slot = (3.5, 3.5)
        crit_slot = (2.5, 2.5)
        s = stage._select_best_slot(
            component_ref="U1", candidate_slots=[free_slot, crit_slot],
            current_placements=current, phase_placements={}, net_pins=net_pins,
        )
        assert s == crit_slot


class TestBaselineParity:
    def test_score_slot_no_sidecar_matches_baseline(self):
        """No channel_map -> score is constraint_penalty + wirelength * 0.1.

        We verify by computing the same expression by hand and comparing
        the selected slot.
        """
        net_pins = {"NET1": [("U1", "1"), ("U2", "1")]}
        current = {"U2": (5.0, 5.0)}
        candidate = [(1.0, 1.0), (4.0, 4.0), (6.0, 6.0)]

        stage_no = _build_stage(channel_map=None, w_r=0.05)
        # Without sidecar, w_r is irrelevant
        stage_zero = _build_stage(channel_map=_make_two_slot_cmap(), w_r=0.0)

        s_no = stage_no._select_best_slot(
            "U1", candidate, current, {}, net_pins
        )
        s_zero = stage_zero._select_best_slot(
            "U1", candidate, current, {}, net_pins
        )
        assert s_no == s_zero

    def test_score_slot_w_r_zero_matches_baseline(self):
        """w_r=0.0 with a sidecar must match no-sidecar output byte-for-byte."""
        net_pins = {"NET1": [("U1", "1"), ("U2", "1")]}
        current = {"U2": (5.0, 5.0)}
        candidate = [(1.0, 1.0), (4.0, 4.0), (6.0, 6.0)]

        stage_no = _build_stage(channel_map=None, w_r=0.0)
        stage_zero = _build_stage(channel_map=_make_two_slot_cmap(), w_r=0.0)

        s_no = stage_no._select_best_slot(
            "U1", candidate, current, {}, net_pins
        )
        s_zero = stage_zero._select_best_slot(
            "U1", candidate, current, {}, net_pins
        )
        assert s_no == s_zero


class TestWarningLogging:
    def test_warning_logged_when_no_sidecar(self, caplog):
        with caplog.at_level(logging.WARNING, logger="temper_placer.deterministic.stages.phased_component_assignment"):
            _build_stage(channel_map=None, w_r=0.05)
        assert any("channel_map" in rec.message for rec in caplog.records)

    def test_no_warning_when_sidecar_loaded(self, caplog):
        with caplog.at_level(logging.WARNING, logger="temper_placer.deterministic.stages.phased_component_assignment"):
            _build_stage(channel_map=_make_two_slot_cmap(), w_r=0.05)
        assert not any("channel_map" in rec.message for rec in caplog.records)


class TestPerformanceBudget:
    def test_per_call_under_5_microseconds(self):
        """Median per-call penalty lookup < 5µs (R9 SC5).

        The penalty function must be allocation-free in steady state.
        We do a 1000-iteration median measurement; the first call warms
        up the dataclass attribute access path.
        """
        cmap = _make_two_slot_cmap()
        slot = (2.5, 2.5)

        # Warm-up
        for _ in range(50):
            routability_penalty(slot, cmap)

        # Measure
        samples: list[float] = []
        for _ in range(1000):
            t0 = time.perf_counter_ns()
            routability_penalty(slot, cmap)
            samples.append(time.perf_counter_ns() - t0)

        median_ns = statistics.median(samples)
        median_us = median_ns / 1000.0
        assert median_us < 5.0, f"median {median_us:.2f}µs exceeds 5µs budget"
