"""Tests for BottleneckMap dataclass and load_bottleneck_map loader.

@req(2026-06-23-004, R3)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from temper_placer.deterministic.bottleneck_map import (
    BottleneckMap,
    load_bottleneck_map,
)
from temper_placer.deterministic.state import BoardState


def _map(**overrides) -> BottleneckMap:
    """Build a BottleneckMap with sensible defaults for tests."""
    defaults: dict = {
        "cell_size_mm": 5.0,
        "width": 4,
        "height": 4,
        "origin_xy": (0.0, 0.0),
        "scores": tuple(0.1 for _ in range(16)),
    }
    defaults.update(overrides)
    return BottleneckMap(**defaults)


class TestScoreAt:
    """Coverage for the O(1) cell-indexed lookup."""

    def test_score_at_cell_origin(self) -> None:
        scores = [0.0] * 4
        scores[0] = 0.9
        m = BottleneckMap(
            cell_size_mm=1.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=tuple(scores),
        )
        assert m.score_at(0.0, 0.0) == 0.9

    def test_score_at_floor_rounding(self) -> None:
        # column 1 = x in [5, 10), so x=7.0 must floor to col 1
        scores = [0.0] * 4
        scores[1] = 0.4
        m = BottleneckMap(
            cell_size_mm=5.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=tuple(scores),
        )
        assert m.score_at(7.0, 0.0) == 0.4
        # x=10.0 lands exactly on the boundary; flooring to col 2 is OOB
        assert m.score_at(10.0, 0.0) == 0.0

    def test_score_out_of_bounds_returns_zero(self) -> None:
        m = _map(width=10, height=10, scores=tuple(0.5 for _ in range(100)))
        assert m.score_at(999.0, 999.0) == 0.0
        # Negative coordinates are also OOB and clamp to 0
        assert m.score_at(-5.0, -5.0) == 0.0

    def test_score_at_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        m = _map()
        with pytest.raises(FrozenInstanceError):
            m.cell_size_mm = 1.0  # type: ignore[misc]


class TestLoadBottleneckMap:
    """Coverage for the loader's preference order and miss behavior."""

    def test_load_prefers_board_state_attribute(
        self, tmp_path: Path
    ) -> None:
        map_a = _map(scores=tuple(0.2 for _ in range(16)))
        map_b = _map(scores=tuple(0.8 for _ in range(16)))
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text(json.dumps(_serialise(map_b)))

        state = Mock(spec=BoardState)
        state.bottleneck_analysis = map_a

        result = load_bottleneck_map(state, sidecar_path=sidecar)
        assert result is map_a

    def test_load_falls_back_to_sidecar(self, tmp_path: Path) -> None:
        sidecar_map = _map(scores=tuple(0.3 for _ in range(16)))
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text(json.dumps(_serialise(sidecar_map)))

        state = Mock(spec=BoardState)
        state.bottleneck_analysis = None

        result = load_bottleneck_map(state, sidecar_path=sidecar)
        assert result == sidecar_map

    def test_load_returns_none_on_miss(self, tmp_path: Path) -> None:
        state = Mock(spec=BoardState)
        state.bottleneck_analysis = None

        result = load_bottleneck_map(state, sidecar_path=tmp_path / "missing.json")
        assert result is None

    def test_load_returns_none_when_attr_wrong_type(self, tmp_path: Path) -> None:
        # When the in-state attribute is a different (legacy) type, we
        # should not crash; we should treat it as a miss and return None.
        state = Mock(spec=BoardState)
        state.bottleneck_analysis = object()  # not a BottleneckMap

        result = load_bottleneck_map(state, sidecar_path=tmp_path / "missing.json")
        assert result is None

    def test_load_handles_malformed_sidecar(self, tmp_path: Path) -> None:
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text("{not valid json")

        state = Mock(spec=BoardState)
        state.bottleneck_analysis = None

        result = load_bottleneck_map(state, sidecar_path=sidecar)
        assert result is None

    def test_load_handles_incomplete_sidecar(self, tmp_path: Path) -> None:
        # Missing required fields => None, not exception
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text(json.dumps({"cell_size_mm": 1.0}))

        state = Mock(spec=BoardState)
        state.bottleneck_analysis = None

        result = load_bottleneck_map(state, sidecar_path=sidecar)
        assert result is None

    def test_load_clamps_out_of_range_scores(self, tmp_path: Path) -> None:
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text(
            json.dumps(
                {
                    "cell_size_mm": 1.0,
                    "width": 2,
                    "height": 1,
                    "origin_xy": [0.0, 0.0],
                    "scores": [1.5, -0.5],
                }
            )
        )
        state = Mock(spec=BoardState)
        state.bottleneck_analysis = None

        result = load_bottleneck_map(state, sidecar_path=sidecar)
        assert result is not None
        assert result.score_at(0.0, 0.0) == 1.0
        assert result.score_at(1.0, 0.0) == 0.0


def _serialise(m: BottleneckMap) -> dict:
    return {
        "cell_size_mm": m.cell_size_mm,
        "width": m.width,
        "height": m.height,
        "origin_xy": list(m.origin_xy),
        "scores": list(m.scores),
    }
