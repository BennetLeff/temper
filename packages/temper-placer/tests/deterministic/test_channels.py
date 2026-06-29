"""
Tests for the channel sidecar loader (U1).

Covers:
- Valid sidecar parse
- Missing file (degraded to empty)
- Malformed JSON (raises ChannelSidecarError)
- Unknown severity (raises ChannelSidecarError)
- Unknown schema hash (raises ChannelSidecarError)
- Penalty shape: free cell, CRITICAL + full-free, out-of-grid, full-occupied
- Cell-boundary floor semantics
- Empty map always returns 0.0
"""

from __future__ import annotations

import json
import math

import pytest

from temper_placer.deterministic.channels import (
    ALLOWED_SCHEMA_HASHES,
    ALLOWED_SEVERITIES,
    SEVERITY_WEIGHTS,
    Bottleneck,
    ChannelMap,
    ChannelSidecarError,
    routability_penalty,
)


def _make_sidecar(
    *,
    grid: list[list[float]] | None = None,
    cell_size_um: float = 1000.0,
    bottlenecks: list[dict] | None = None,
    schema_hash: str = "temper.channels.v1",
) -> dict:
    if grid is None:
        grid = [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
    return {
        "temper_schema_hash": schema_hash,
        "cell_size_um": cell_size_um,
        "grid": grid,
        "bottlenecks": bottlenecks or [],
    }


class TestLoadValidSidecar:
    def test_load_valid_sidecar(self, tmp_path):
        sidecar = _make_sidecar(
            grid=[
                [0.1, 0.2, 0.3],
                [0.4, 0.5, 0.6],
                [0.7, 0.8, 0.9],
            ],
            cell_size_um=500.0,
            bottlenecks=[
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "HIGH", "score": 0.9},
            ],
        )
        path = tmp_path / "placement.channels.json"
        path.write_text(json.dumps(sidecar))

        cmap = ChannelMap.load_from_sidecar(path)

        assert isinstance(cmap, ChannelMap)
        assert isinstance(cmap.grid, tuple)
        assert all(isinstance(row, tuple) for row in cmap.grid)
        assert cmap.cell_size_um == 500.0
        assert cmap.width == 3
        assert cmap.height == 3
        assert cmap.grid[0][0] == 0.1
        assert cmap.grid[2][2] == 0.9
        assert cmap.schema_hash == "temper.channels.v1"
        assert len(cmap.bottlenecks) == 1
        bn = next(iter(cmap.bottlenecks))
        assert isinstance(bn, Bottleneck)
        assert bn.x == 1
        assert bn.y == 1
        assert bn.severity == "HIGH"
        assert bn.score == 0.9


class TestLoadFailures:
    def test_load_missing_file(self, tmp_path):
        ChannelMap.empty()
        # ChannelMap.load_from_sidecar raises on missing; the pipeline wrapper
        # is responsible for catching and degrading. Verify the raise here.
        with pytest.raises(ChannelSidecarError) as exc:
            ChannelMap.load_from_sidecar(tmp_path / "does-not-exist.json")
        assert "not found" in str(exc.value)

    def test_load_malformed_json(self, tmp_path):
        path = tmp_path / "placement.channels.json"
        path.write_text("{ not valid json")
        with pytest.raises(ChannelSidecarError) as exc:
            ChannelMap.load_from_sidecar(path)
        msg = str(exc.value)
        assert str(path) in msg
        assert "malformed" in msg.lower()

    def test_load_unknown_severity(self, tmp_path):
        sidecar = _make_sidecar(
            bottlenecks=[
                {"x": 0, "y": 0, "layer": "F.Cu", "severity": "GIGA", "score": 1.0},
            ],
        )
        path = tmp_path / "placement.channels.json"
        path.write_text(json.dumps(sidecar))
        with pytest.raises(ChannelSidecarError) as exc:
            ChannelMap.load_from_sidecar(path)
        assert "GIGA" in str(exc.value)
        assert "severity" in str(exc.value).lower()

    def test_load_unknown_schema_hash(self, tmp_path):
        sidecar = _make_sidecar(schema_hash="temper.channels.v999")
        path = tmp_path / "placement.channels.json"
        path.write_text(json.dumps(sidecar))
        with pytest.raises(ChannelSidecarError) as exc:
            ChannelMap.load_from_sidecar(path)
        assert "temper_schema_hash" in str(exc.value)
        assert "temper.channels.v999" in str(exc.value)


class TestSeverityWeightConstants:
    def test_severity_weights_match_spec(self):
        assert SEVERITY_WEIGHTS["LOW"] == 0.05
        assert SEVERITY_WEIGHTS["MEDIUM"] == 0.15
        assert SEVERITY_WEIGHTS["HIGH"] == 0.4
        assert SEVERITY_WEIGHTS["CRITICAL"] == 1.0

    def test_allowed_severities_match_keys(self):
        assert set(SEVERITY_WEIGHTS) == set(ALLOWED_SEVERITIES)

    def test_allowed_schema_hashes_non_empty(self):
        assert "temper.channels.v1" in ALLOWED_SCHEMA_HASHES


class TestPenaltyShape:
    def test_penalty_in_grid_free(self):
        # 3x3 grid, 1mm cells, no bottlenecks. Slot at (0.5, 0.5) is cell (0,0).
        grid = [[0.0] * 3 for _ in range(3)]
        cmap = ChannelMap._from_payload(_make_sidecar(grid=grid, cell_size_um=1000.0))
        assert routability_penalty((0.5, 0.5), cmap) == 0.0

    def test_penalty_critical_full_free(self):
        # CRITICAL bottleneck, occupancy 0.0 -> severity_weight * (0.5 + 0.5 * 0) = 0.5
        grid = [[0.0] * 3 for _ in range(3)]
        cmap = ChannelMap._from_payload(
            _make_sidecar(
                grid=grid,
                cell_size_um=1000.0,
                bottlenecks=[
                    {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
                ],
            )
        )
        penalty = routability_penalty((1.5, 1.5), cmap)
        assert math.isclose(penalty, 0.5, rel_tol=1e-9)

    def test_penalty_out_of_grid(self):
        grid = [[0.0] * 3 for _ in range(3)]
        cmap = ChannelMap._from_payload(_make_sidecar(grid=grid, cell_size_um=1000.0))
        # gx < 0
        assert routability_penalty((-0.5, 0.5), cmap) == 0.0
        # gx >= width (grid covers mm 0..3; 3.5 lands at gx=3 which is out-of-grid)
        assert routability_penalty((3.5, 0.5), cmap) == 0.0
        # gy < 0
        assert routability_penalty((0.5, -0.5), cmap) == 0.0
        # gy >= height
        assert routability_penalty((0.5, 3.5), cmap) == 0.0

    def test_penalty_fully_occupied_returns_max(self):
        # CRITICAL + occupancy 1.0 -> 1.0 * (0.5 + 0.5 * 1) = 1.0
        grid = [[1.0] * 3 for _ in range(3)]
        cmap = ChannelMap._from_payload(
            _make_sidecar(
                grid=grid,
                cell_size_um=1000.0,
                bottlenecks=[
                    {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
                ],
            )
        )
        assert routability_penalty((1.5, 1.5), cmap) == 1.0

    def test_penalty_at_cell_boundary_consistent(self):
        # Two slots 1µm apart straddling a cell boundary must land in
        # distinct cells and produce different penalties when the cells
        # differ in severity.
        # cell_size_um = 1000; cell boundary is at x = 1.0mm = 1000µm.
        grid = [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        cmap = ChannelMap._from_payload(
            _make_sidecar(
                grid=grid,
                cell_size_um=1000.0,
                bottlenecks=[
                    {"x": 0, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
                ],
            )
        )
        # Slot at x = 0.9995mm -> gx = 0 (CRITICAL penalty)
        p_before = routability_penalty((0.9995, 1.5), cmap)
        # Slot at x = 1.0005mm -> gx = 1 (free)
        p_after = routability_penalty((1.0005, 1.5), cmap)
        assert p_before > p_after
        assert math.isclose(p_before, 0.5, rel_tol=1e-9)
        assert p_after == 0.0

    def test_empty_map_returns_zero(self):
        cmap = ChannelMap.empty()
        for slot in [(0.0, 0.0), (5.0, 5.0), (100.0, 100.0), (-1.0, -1.0)]:
            assert routability_penalty(slot, cmap) == 0.0

    def test_severity_monotonicity(self):
        grid = [[0.5] * 3 for _ in range(3)]
        penalties = {}
        for sev in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            cmap = ChannelMap._from_payload(
                _make_sidecar(
                    grid=grid,
                    cell_size_um=1000.0,
                    bottlenecks=[
                        {"x": 1, "y": 1, "layer": "F.Cu", "severity": sev, "score": 1.0},
                    ],
                )
            )
            penalties[sev] = routability_penalty((1.5, 1.5), cmap)
        assert penalties["LOW"] <= penalties["MEDIUM"] <= penalties["HIGH"] <= penalties["CRITICAL"]

    def test_occupancy_monotonicity(self):
        # Holding severity fixed at CRITICAL, penalty is non-decreasing in occupancy.
        last = -1.0
        for occ in (0.0, 0.25, 0.5, 0.75, 1.0):
            grid = [[occ] * 3 for _ in range(3)]
            cmap = ChannelMap._from_payload(
                _make_sidecar(
                    grid=grid,
                    cell_size_um=1000.0,
                    bottlenecks=[
                        {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
                    ],
                )
            )
            p = routability_penalty((1.5, 1.5), cmap)
            assert p >= last
            last = p


class TestEmptyMapShape:
    def test_empty_map_dimensions(self):
        cmap = ChannelMap.empty()
        assert cmap.width == 0
        assert cmap.height == 0
        assert cmap.cell_size_um == 0
        assert cmap.bottlenecks == frozenset()
        assert cmap.has_grid() is False
