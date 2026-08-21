"""
Coverage paydown v3 — deterministic modules (InstrumentedStage,
BottleneckMap, load_bottleneck_map, load_guard_config, etc.).

Tests functions still on the coverage allowlist that existing suites
(differential, PBT, oracle) don't exercise directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from shapely.geometry import Polygon

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState


# ============================================================================
# BoardState helpers
# ============================================================================


@pytest.fixture
def fixture_state() -> BoardState:
    """Minimal BoardState with board + netlist for stage tests."""
    comps = [
        Component(
            ref="U1",
            footprint="SOIC8",
            bounds=(5, 4),
            pins=[Pin("1", "1", (0, 0), net="VCC")],
        ),
    ]
    nets = [Net("VCC", [("U1", "1")], net_class="Power")]
    return BoardState(
        board=Board(width=100.0, height=100.0),
        netlist=Netlist(components=comps, nets=nets),
    )


# ============================================================================
# BottleneckMap.score_at and load_bottleneck_map
# ============================================================================


class TestBottleneckMapScoreAt:
    def test_score_at_out_of_bounds_returns_zero(self):
        from temper_placer.deterministic.bottleneck_map import BottleneckMap

        bm = BottleneckMap(
            cell_size_mm=1.0,
            width=10,
            height=10,
            origin_xy=(0.0, 0.0),
            scores=tuple(0.5 for _ in range(100)),
        )
        result = bm.score_at(999.0, 999.0)
        assert result == 0.0

    def test_score_at_origin(self):
        from temper_placer.deterministic.bottleneck_map import BottleneckMap

        scores = [0.0] * 4
        scores[0] = 0.8
        bm = BottleneckMap(
            cell_size_mm=1.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=tuple(scores),
        )
        result = bm.score_at(0.0, 0.0)
        assert result == 0.8

    def test_score_at_negative_coords(self):
        from temper_placer.deterministic.bottleneck_map import BottleneckMap

        bm = BottleneckMap(
            cell_size_mm=5.0,
            width=4,
            height=4,
            origin_xy=(0.0, 0.0),
            scores=tuple(0.3 for _ in range(16)),
        )
        assert bm.score_at(-5.0, -5.0) == 0.0


class TestLoadBottleneckMap:
    def test_load_from_state_attribute(self, fixture_state):
        from temper_placer.deterministic.bottleneck_map import (
            BottleneckMap,
            load_bottleneck_map,
        )
        from dataclasses import replace

        bm = BottleneckMap(
            cell_size_mm=1.0,
            width=5,
            height=5,
            origin_xy=(0.0, 0.0),
            scores=tuple(0.1 for _ in range(25)),
        )
        state = replace(fixture_state, bottleneck_analysis=bm)
        result = load_bottleneck_map(state)
        assert result is bm

    def test_load_from_sidecar_file(self, fixture_state, tmp_path: Path):
        from temper_placer.deterministic.bottleneck_map import (
            load_bottleneck_map,
        )

        payload = {
            "cell_size_mm": 5.0,
            "width": 4,
            "height": 4,
            "scores": [0.1] * 16,
            "origin_xy": [0.0, 0.0],
        }
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text(json.dumps(payload))

        result = load_bottleneck_map(fixture_state, sidecar_path=sidecar)
        assert result is not None
        assert result.cell_size_mm == 5.0
        assert result.width == 4
        assert result.height == 4

    def test_load_missing_sidecar_returns_none(self, fixture_state):
        from temper_placer.deterministic.bottleneck_map import (
            load_bottleneck_map,
        )

        result = load_bottleneck_map(
            fixture_state, sidecar_path="/nonexistent/path.json"
        )
        assert result is None

    def test_load_no_sources_returns_none(self, fixture_state):
        from temper_placer.deterministic.bottleneck_map import (
            load_bottleneck_map,
        )

        result = load_bottleneck_map(fixture_state)
        assert result is None


# ============================================================================
# InstrumentedStage.run
# ============================================================================


class _DummyStage:
    """Minimal stage-like object that InstrumentedStage can wrap."""

    def run(self, state: BoardState) -> BoardState:
        return state


class TestInstrumentedStageRun:
    def test_run_with_no_tracked_nets(self, fixture_state):
        from temper_placer.deterministic.instrumentation import InstrumentedStage

        stage = InstrumentedStage(_DummyStage())
        result = stage.run(fixture_state)
        assert result is fixture_state

    def test_run_with_tracked_nets(self, fixture_state):
        from temper_placer.deterministic.instrumentation import InstrumentedStage

        stage = InstrumentedStage(_DummyStage(), track_nets=["VCC"])
        result = stage.run(fixture_state)
        assert isinstance(result, BoardState)


# ============================================================================
# load_guard_config
# ============================================================================


class TestLoadGuardConfig:
    def test_load_none_returns_defaults(self):
        from temper_placer.deterministic.stages.hv_lv_partition import (
            load_guard_config,
        )

        cfg = load_guard_config(None)
        assert cfg.enabled is True

    def test_load_empty_returns_defaults(self):
        from temper_placer.deterministic.stages.hv_lv_partition import (
            load_guard_config,
        )

        cfg = load_guard_config({})
        assert cfg.enabled is True

    def test_load_with_block_configured(self):
        from temper_placer.deterministic.stages.hv_lv_partition import (
            load_guard_config,
        )

        cfg = load_guard_config(
            {"hv_lv_guard_strip": {"enabled": False, "width_mm": 6.0}}
        )
        assert cfg.enabled is False
        assert cfg.width_mm == 6.0

    def test_load_invalid_block_logs_and_defaults(self, caplog):
        from temper_placer.deterministic.stages.hv_lv_partition import (
            load_guard_config,
        )

        with caplog.at_level("WARNING"):
            cfg = load_guard_config({"hv_lv_guard_strip": "not-a-mapping"})
        assert cfg.enabled is True
        assert "not a mapping" in caplog.text


# ============================================================================
# guard_strip
# ============================================================================


class TestComputeGuardStrip:
    def test_zero_width_returns_outline_as_lv(self):
        from temper_placer.deterministic.geometry.guard_strip import (
            compute_guard_strip,
        )

        outline = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        hv, lv, corridor = compute_guard_strip(outline, 0.0)
        assert hv.is_empty
        assert not lv.is_empty
        assert corridor.is_empty
        assert lv.equals(outline)

    def test_small_width_returns_ring(self):
        from temper_placer.deterministic.geometry.guard_strip import (
            compute_guard_strip,
        )

        outline = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        hv, lv, corridor = compute_guard_strip(outline, 10.0)
        assert not hv.is_empty
        assert not lv.is_empty
        assert not corridor.is_empty

    def test_large_width_empties_lv(self):
        from temper_placer.deterministic.geometry.guard_strip import (
            compute_guard_strip,
        )

        outline = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        hv, lv, corridor = compute_guard_strip(outline, 60.0)  # > half min side
        assert not hv.is_empty
        assert lv.is_empty

    def test_rejects_non_polygon(self):
        from temper_placer.deterministic.geometry.guard_strip import (
            compute_guard_strip,
        )

        with pytest.raises(ValueError, match="must be a shapely Polygon"):
            compute_guard_strip("not a polygon", 10.0)  # type: ignore[arg-type]


# ============================================================================
# BoardState methods (additional coverage beyond existing paydown)
# ============================================================================


class TestBoardStateAdditional:
    def test_is_route_locked_with_multiple_locks(self, fixture_state):
        state = fixture_state.with_locked_routes({"VCC", "GND"})
        assert state.is_route_locked("VCC") is True
        assert state.is_route_locked("GND") is True
        assert state.is_route_locked("UNLOCKED") is False

    def test_with_config_preserves_other_fields(self, fixture_state):
        config = {"key": "val"}
        state = fixture_state.with_config(config)
        assert state.board is fixture_state.board
        assert state.netlist is fixture_state.netlist

    def test_with_config_none(self, fixture_state):
        state = fixture_state.with_config(None)
        assert state.config is None

    def test_with_config_none_preserves_board(self, fixture_state):
        state = fixture_state.with_config(None)
        assert state.config is None
        assert state.board is fixture_state.board
