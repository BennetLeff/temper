"""Tests for corner envelope sweep."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.spice.corner_sweep import (
    AxisDef,
    generate_corner_grid,
    load_corner_def,
)

SAMPLE_CORNERS_YAML = """
mode: corners
axes:
  Vbus:
    unit: V
    min: 300
    max: 400
    num_points: 3
    spice_param: VDC
  Tj:
    unit: degC
    min: 25
    max: 150
    num_points: 3
    spice_param: TJ
    sets_temp: true
parallel:
  max_workers: 1
"""


@pytest.fixture
def corner_config(tmp_path: Path) -> Path:
    p = tmp_path / "corners.yaml"
    p.write_text(SAMPLE_CORNERS_YAML)
    return p


class TestLoadCornerDef:
    def test_loads_axes(self, corner_config: Path) -> None:
        mode, axes, workers = load_corner_def(corner_config)
        assert mode == "corners"
        assert len(axes) == 2
        assert axes[0].name == "Vbus"
        assert axes[1].name == "Tj"
        assert workers == 1

    def test_axis_values(self, corner_config: Path) -> None:
        _, axes, _ = load_corner_def(corner_config)
        vbus_axis = axes[0]
        assert vbus_axis.values == pytest.approx([300.0, 350.0, 400.0])

    def test_sets_temp_flag(self, corner_config: Path) -> None:
        _, axes, _ = load_corner_def(corner_config)
        assert not axes[0].sets_temp
        assert axes[1].sets_temp


class TestGenerateCornerGrid:
    @pytest.fixture
    def sample_axes(self) -> list[AxisDef]:
        return [
            AxisDef(
                name="Vbus",
                unit="V",
                min_val=300,
                max_val=400,
                num_points=2,
                spice_param="VDC",
            ),
            AxisDef(
                name="Tj",
                unit="degC",
                min_val=25,
                max_val=150,
                num_points=2,
                spice_param="TJ",
                sets_temp=True,
            ),
        ]

    def test_corners_only_4_corners(
        self, sample_axes: list[AxisDef]
    ) -> None:
        grid = generate_corner_grid(sample_axes, "corners")
        assert len(grid) == 4

    def test_full_factorial_4_corners_with_2_points(
        self, sample_axes: list[AxisDef]
    ) -> None:
        grid = generate_corner_grid(sample_axes, "full")
        assert len(grid) == 4

    def test_corner_parameter_values(
        self, sample_axes: list[AxisDef]
    ) -> None:
        grid = generate_corner_grid(sample_axes, "corners")
        vbus_vals = {c["Vbus"] for c in grid}
        assert vbus_vals == {300.0, 400.0}
        tj_vals = {c["Tj"] for c in grid}
        assert tj_vals == {25.0, 150.0}

    def test_single_axis_produces_two_corners(self) -> None:
        axes = [
            AxisDef(
                name="Vbus",
                unit="V",
                min_val=300,
                max_val=400,
                num_points=5,
                spice_param="VDC",
            ),
        ]
        grid = generate_corner_grid(axes, "corners")
        assert len(grid) == 2

    def test_full_mode_single_axis_produces_n_points(self) -> None:
        axes = [
            AxisDef(
                name="Vbus",
                unit="V",
                min_val=300,
                max_val=400,
                num_points=5,
                spice_param="VDC",
            ),
        ]
        grid = generate_corner_grid(axes, "full")
        assert len(grid) == 5


@pytest.mark.skip(reason="requires ngspice; tested in integration")
class TestRunCornerSweep:
    def test_sweep_returns_results(self) -> None:
        pass
