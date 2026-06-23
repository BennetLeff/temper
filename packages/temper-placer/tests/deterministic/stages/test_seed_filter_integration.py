"""Tests for the bottleneck-map seed filter integration in
``PhasedComponentAssignmentStage._place_optimize``.

@req(2026-06-23-004, R2)
@req(2026-06-23-004, K4)
@req(2026-06-23-004, R3)  # silent-disable when map is missing
@req(2026-06-23-004, R6)  # structured log line keys
"""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest

from temper_placer.deterministic.bottleneck_map import BottleneckMap
from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import (
    PlacementConstraints,
    SeedFilterConfig,
)


def _make_map(scores: list[float], cell: float = 1.0) -> BottleneckMap:
    side = 2
    return BottleneckMap(
        cell_size_mm=cell,
        width=side,
        height=side,
        origin_xy=(0.0, 0.0),
        scores=tuple(scores),
    )


def _make_state(bottleneck_map: BottleneckMap | None = None) -> BoardState:
    netlist = Mock()
    netlist.components = [
        Mock(ref="C1", bounds=(2, 2), pins=[]),
        Mock(ref="C2", bounds=(2, 2), pins=[]),
    ]
    netlist.nets = []
    zone_slots = frozenset(
        [
            (
                "Signal",
                (
                    (0.5, 0.5),
                    (1.5, 0.5),
                    (0.5, 1.5),
                    (1.5, 1.5),
                ),
            )
        ]
    )
    return BoardState(
        netlist=netlist,
        component_zone_map=frozenset([("C1", "Signal"), ("C2", "Signal")]),
        zone_slots=zone_slots,
        bottleneck_analysis=bottleneck_map,
    )


class TestFilterBehavior:
    def test_filter_disabled_passes_pool_through(self, caplog: pytest.LogCaptureFixture) -> None:
        """``seed_filter.enabled=False`` -> no filtering, no log line."""
        constraints = PlacementConstraints()
        constraints.seed_filter = SeedFilterConfig(
            enabled=False, threshold=0.7, hv_threshold=0.5
        )
        stage = PhasedComponentAssignmentStage(constraints)
        # Manually wire a high-congestion map (would normally drop slots)
        stage._bottleneck_map = _make_map([0.9, 0.9, 0.9, 0.9])
        slots = [(0.5, 0.5), (1.5, 0.5), (0.5, 1.5), (1.5, 1.5)]
        comp_by_ref = {"C1": Mock(ref="C1", bounds=(2, 2), pins=[])}
        with caplog.at_level(logging.INFO, logger="temper_placer.deterministic.stages.phased_component_assignment"):
            result = stage._apply_bottleneck_filter("C1", list(slots), comp_by_ref)
        assert result == slots
        # No seed_filter log line should be emitted when disabled.
        assert not any("event=seed_filter" in rec.message for rec in caplog.records)

    def test_filter_missing_map_silent_disable(self, caplog: pytest.LogCaptureFixture) -> None:
        """``seed_filter.enabled=True`` but no BottleneckMap -> silent pass-through."""
        constraints = PlacementConstraints()
        # Defaults: enabled=True
        stage = PhasedComponentAssignmentStage(constraints)
        assert stage._bottleneck_map is None
        slots = [(0.5, 0.5), (1.5, 0.5), (0.5, 1.5), (1.5, 1.5)]
        comp_by_ref = {"C1": Mock(ref="C1", bounds=(2, 2), pins=[])}
        with caplog.at_level(logging.INFO):
            result = stage._apply_bottleneck_filter("C1", list(slots), comp_by_ref)
        assert result == slots
        # No log line on silent-disable (per R3).
        assert not any("event=seed_filter" in rec.message for rec in caplog.records)

    def test_filter_rejects_high_congestion_slots(self) -> None:
        """A 0.9 cell is rejected; a 0.5 cell is accepted."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints)
        # (0,0) cell is 0.9; (1,0) is 0.5
        stage._bottleneck_map = _make_map([0.9, 0.5, 0.1, 0.1])
        slots = [(0.5, 0.5), (1.5, 0.5), (0.5, 1.5), (1.5, 1.5)]
        comp_by_ref = {"C1": Mock(ref="C1", bounds=(2, 2), pins=[])}
        result = stage._apply_bottleneck_filter("C1", list(slots), comp_by_ref)
        # (0.5, 0.5) is in the 0.9 cell and must be rejected
        assert (0.5, 0.5) not in result
        assert (1.5, 0.5) in result
        assert (0.5, 1.5) in result
        assert (1.5, 1.5) in result

    def test_empty_pool_falls_back_with_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Aggressive threshold rejects all -> fall back with warning."""
        constraints = PlacementConstraints()
        constraints.seed_filter = SeedFilterConfig(
            enabled=True, threshold=0.01, hv_threshold=0.01
        )
        stage = PhasedComponentAssignmentStage(constraints)
        stage._bottleneck_map = _make_map([0.9, 0.8, 0.7, 0.6])
        slots = [(0.5, 0.5), (1.5, 0.5), (0.5, 1.5), (1.5, 1.5)]
        comp_by_ref = {"C1": Mock(ref="C1", bounds=(2, 2), pins=[])}
        with caplog.at_level(logging.DEBUG):
            result = stage._apply_bottleneck_filter("C1", list(slots), comp_by_ref)
        # All slots restored; warning emitted.
        assert sorted(result) == sorted(slots)
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("falling back" in m for m in warning_msgs)
        # The follow-up INFO log line should report fallback_used=True
        info_msgs = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("fallback_used=True" in m for m in info_msgs)


class TestObservability:
    def test_observability_emits_required_keys(self, caplog: pytest.LogCaptureFixture) -> None:
        """All R6 keys present in the structured log line, fallback_used=False."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints)
        stage._bottleneck_map = _make_map([0.1, 0.2, 0.3, 0.4])
        slots = [(0.5, 0.5), (1.5, 0.5), (0.5, 1.5), (1.5, 1.5)]
        comp_by_ref = {"C1": Mock(ref="C1", bounds=(2, 2), pins=[])}
        with caplog.at_level(logging.INFO):
            stage._apply_bottleneck_filter("C1", list(slots), comp_by_ref)

        seed_filter_records = [
            r for r in caplog.records if "event=seed_filter" in r.message
        ]
        assert len(seed_filter_records) == 1
        msg = seed_filter_records[0].message
        for key in (
            "candidates_total",
            "candidates_accepted",
            "candidates_rejected",
            "avg_bottleneck_score_accepted",
            "threshold",
            "hv_threshold",
            "fallback_used",
        ):
            assert key in msg, f"Missing required key: {key}"
        assert "event=seed_filter" in msg
        assert "fallback_used=False" in msg

    def test_observability_fallback_used_true(self, caplog: pytest.LogCaptureFixture) -> None:
        """Aggressive threshold triggers fallback_used=True on the INFO line."""
        constraints = PlacementConstraints()
        constraints.seed_filter = SeedFilterConfig(
            enabled=True, threshold=0.01, hv_threshold=0.01
        )
        stage = PhasedComponentAssignmentStage(constraints)
        stage._bottleneck_map = _make_map([0.9, 0.8, 0.7, 0.6])
        slots = [(0.5, 0.5), (1.5, 0.5), (0.5, 1.5), (1.5, 1.5)]
        comp_by_ref = {"C1": Mock(ref="C1", bounds=(2, 2), pins=[])}
        with caplog.at_level(logging.INFO):
            stage._apply_bottleneck_filter("C1", list(slots), comp_by_ref)
        seed_filter_records = [
            r for r in caplog.records if "event=seed_filter" in r.message
        ]
        assert len(seed_filter_records) == 1
        assert "fallback_used=True" in seed_filter_records[0].message


class TestIntegration:
    def test_integration_fallback_matches_unfiltered_path(self) -> None:
        """Run twice on a board with no bottleneck data; placements match."""
        constraints_a = PlacementConstraints()
        constraints_a.seed_filter = SeedFilterConfig(
            enabled=True, threshold=0.7, hv_threshold=0.5
        )
        constraints_b = PlacementConstraints()
        constraints_b.seed_filter = SeedFilterConfig(
            enabled=False, threshold=0.7, hv_threshold=0.5
        )
        # Same state: no bottleneck data on either.
        state = _make_state(bottleneck_map=None)
        stage_a = PhasedComponentAssignmentStage(constraints_a)
        stage_b = PhasedComponentAssignmentStage(constraints_b)
        result_a = stage_a.run(state)
        result_b = stage_b.run(state)
        # Placements are equivalent (frozen sets of (ref, pos)).
        assert dict(result_a.placements) == dict(result_b.placements)
