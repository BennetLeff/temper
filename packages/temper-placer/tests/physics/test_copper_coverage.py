"""
Tests for copper_coverage_grid and thermal plausibility checks (issue #137).

Covers:
- Grid shape matches fdm_config dimensions
- Cells over the plane area (minus keepouts) read HIGH
- Cells inside a keepout read LOW/zero
- Real copper grid yields physically sane T_j (< 300 deg-C)
- Zero-copper (pure-FR4) triggers the sanity floor (UNMEASURED / abort)
- between-arm saturation detected when scores are degenerate
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.core.board import Board, LayerStackup, MountingHole
from temper_placer.physics.copper_coverage import (
    SANITY_CEILING_C,
    check_thermal_plausibility,
    copper_coverage_grid,
)
from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mini_board(width: float = 100.0, height: float = 100.0) -> Board:
    """Mini board with the standard 4-layer Temper stackup."""
    return Board(
        width=width,
        height=height,
        origin=(0.0, 0.0),
        layer_stackup=LayerStackup.default_4layer(),
    )


def _mini_board_with_keepout() -> Board:
    """Board with a keepout zone blocking a corner."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=LayerStackup.default_4layer(),
        keepouts=[(0.0, 0.0, 20.0, 20.0)],  # bottom-left 20x20mm blocked
    )


def _mini_board_with_mounting_hole() -> Board:
    """Board with a mounting hole near a corner."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=LayerStackup.default_4layer(),
        mounting_holes=[
            MountingHole(position=(10.0, 10.0), diameter=3.2, keepout_radius=5.0),
        ],
    )


def _mini_fdm_config(
    height_cells: int = 20, width_cells: int = 20, cell_size_mm: float = 5.0,
) -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=cell_size_mm,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=5000,
    )


# ---------------------------------------------------------------------------
# Grid shape tests
# ---------------------------------------------------------------------------


class TestGridShape:
    """Copper coverage grid is aligned to the FDM grid."""

    def test_grid_shape_matches_fdm_config(self):
        """Grid dimensions equal (height_cells, width_cells)."""
        board = _mini_board(100, 100)
        fdm_config = _mini_fdm_config(height_cells=20, width_cells=30)
        grid = copper_coverage_grid(board, fdm_config)
        assert grid.shape == (20, 30)

    def test_grid_dtype_float64(self):
        """Grid is float64 with values in [0, 1]."""
        board = _mini_board(100, 100)
        fdm_config = _mini_fdm_config()
        grid = copper_coverage_grid(board, fdm_config)
        assert grid.dtype == np.float64
        assert np.all(grid >= 0.0)
        assert np.all(grid <= 1.0)


# ---------------------------------------------------------------------------
# Plane coverage tests
# ---------------------------------------------------------------------------


class TestPlaneCoverage:
    """Plane layers contribute solid coverage over board area."""

    def test_solid_plane_coverage_inside_board(self):
        """Cells well inside the board have non-zero copper from planes."""
        board = _mini_board(100, 100)
        fdm_config = _mini_fdm_config(cell_size_mm=2.0, height_cells=50, width_cells=50)
        grid = copper_coverage_grid(board, fdm_config)

        # Expected: (In1 1oz + In2 1oz) / (2+1+1+1) = 0.40 at placement time
        center_val = grid[25, 25]
        assert center_val > 0.35, (
            f"Expected > 0.35 in board centre, got {center_val:.4f}"
        )

    def test_placement_time_fraction_around_04(self):
        """At placement time (no traces), fraction ~ 0.40 for 4-layer stackup."""
        board = _mini_board(100, 100)
        fdm_config = _mini_fdm_config(cell_size_mm=2.0, height_cells=50, width_cells=50)
        grid = copper_coverage_grid(board, fdm_config)
        mean_val = float(np.mean(grid[5:45, 5:45]))  # exclude boundaries
        # With two 1oz planes out of 5oz total, mean ~ 0.40
        assert 0.30 < mean_val < 0.50, (
            f"Expected ~0.40 at placement time, got {mean_val:.4f}"
        )

    def test_outside_board_is_zero(self):
        """Cells outside the board rectangle have zero copper."""
        board = _mini_board(50, 50)  # half the FDM grid
        fdm_config = _mini_fdm_config(cell_size_mm=1.0, height_cells=100, width_cells=100)
        grid = copper_coverage_grid(board, fdm_config)

        # Top-right corner (beyond 50x50mm = 50 cells at 1mm): should be outside
        assert grid[75, 75] == 0.0

        # Cell near origin should be inside
        assert grid[10, 10] > 0.0


# ---------------------------------------------------------------------------
# Keepout tests
# ---------------------------------------------------------------------------


class TestKeepouts:
    """Keepouts and mounting holes reduce copper coverage."""

    def test_cell_inside_keepout_is_zero(self):
        """A cell inside a keepout rectangle should have zero coverage."""
        board = _mini_board_with_keepout()
        fdm_config = _mini_fdm_config(cell_size_mm=5.0, height_cells=20, width_cells=20)
        grid = copper_coverage_grid(board, fdm_config)

        # Cell at (2.5, 2.5) -> row 0, col 0 is inside keepout (0,0,20,20)
        val_inside = grid[0, 0]
        assert val_inside == 0.0, (
            f"Cell inside keepout should be 0, got {val_inside:.4f}"
        )

        # Cell at (60, 60) -> row 12, col 12 is outside keepout
        val_outside = grid[12, 12]
        assert val_outside > 0.0, (
            f"Cell outside keepout should have copper, got {val_outside:.4f}"
        )

    def test_cell_inside_mounting_hole_keepout_is_zero(self):
        """Cells inside mounting-hole keepout zone have zero coverage."""
        board = _mini_board_with_mounting_hole()
        fdm_config = _mini_fdm_config(cell_size_mm=1.0, height_cells=100, width_cells=100)
        grid = copper_coverage_grid(board, fdm_config)

        # Hole at (10, 10), keepout radius 5mm. Cell centre at (10, 10) is inside
        val_at_hole = grid[10, 10]
        assert val_at_hole == 0.0, (
            f"Cell at mounting hole should be 0, got {val_at_hole:.4f}"
        )

        # Cell far from hole should have copper
        val_far = grid[50, 50]
        assert val_far > 0.0

    def test_no_plane_layers_has_zero_at_placement_time(self):
        """A 4-layer board with no plane layers has zero at placement time."""
        from temper_placer.core.board import Layer
        board = Board(
            width=100.0,
            height=100.0,
            layer_stackup=LayerStackup(
                layers=(
                    Layer("F.Cu", "signal", copper_weight=1.0, is_routable=True),
                    Layer("In1.Cu", "signal", copper_weight=1.0, is_routable=False),
                    Layer("In2.Cu", "signal", copper_weight=1.0, is_routable=False),
                    Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
                ),
                thickness=1.6,
            ),
        )
        fdm_config = _mini_fdm_config()
        grid = copper_coverage_grid(board, fdm_config)
        # No plane layers -> zero everywhere at placement time
        expected_zero = np.zeros_like(grid)
        assert np.array_equal(grid, expected_zero)


# ---------------------------------------------------------------------------
# Physical plausibility: real copper grid
# ---------------------------------------------------------------------------


class TestPhysicalPlausibility:
    """With a real copper grid, device T_j is physically sane."""

    def test_real_grid_produces_sane_temperature(self):
        """A representative device at rated power stays < 300 deg-C."""
        board = _mini_board(100, 100)
        fdm_config = _mini_fdm_config(cell_size_mm=2.0, height_cells=50, width_cells=50)
        grid = copper_coverage_grid(board, fdm_config)

        devices = {"Q1": (50.0, 20.0), "Q2": (30.0, 20.0)}
        power_map = {"Q1": 30.0, "Q2": 15.0}

        result = solve_thermal_fdm(
            config=fdm_config,
            devices=devices,
            power_map=power_map,
            copper_grid=grid,
        )

        assert result.is_usable, f"Expected usable field, got {result.status}"
        field = np.asarray(result.field.grid, dtype=np.float64)
        peak = float(np.max(field))
        assert peak < 300.0, (
            f"Real copper grid peak {peak:.1f} C should be < 300 C "
            f"(physically sane); was the copper grid applied?"
        )
        # With real copper, peak should be > ambient (heating is real)
        assert peak > fdm_config.ambient_C + 1.0, (
            f"No heating detected with copper grid; peak={peak:.1f} C"
        )


# ---------------------------------------------------------------------------
# Fail-closed: zero-copper (#137 garbage) triggers sanity floor
# ---------------------------------------------------------------------------


class TestFailClosedZeroCopper:
    """Feeding zero-copper (the #137 garbage) makes the sanity floor trip."""

    def test_zero_copper_triggers_ceiling(self):
        """Pure-FR4 (zero copper) hits the sanity ceiling."""
        # Narrow grid to contain the heat: a 10x10mm board with 20x20 cells
        fdm_config = _mini_fdm_config(cell_size_mm=0.5, height_cells=20, width_cells=20)
        copper_grid = np.zeros((20, 20), dtype=np.float64)

        # Place a single device in the middle at moderate power
        devices = {"Q1": (5.0, 2.0)}
        power_map = {"Q1": 30.0}

        result = solve_thermal_fdm(
            config=fdm_config,
            devices=devices,
            power_map=power_map,
            copper_grid=copper_grid,
        )

        assert result.is_usable, "FDM should solve even with zero copper"
        field = np.asarray(result.field.grid, dtype=np.float64)
        peak = float(np.max(field))

        # The #137 garbage produces ~189,000 C. Sanity ceiling is 400 C.
        # Pure FR4 should produce wildly high temperatures at 30W on
        # a small board.
        assert peak > SANITY_CEILING_C, (
            f"Pure-FR4 peak {peak:.1f} C should exceed sanity ceiling "
            f"{SANITY_CEILING_C} C; this proves the guard catches #137"
        )

    def test_plausibility_check_rejects_high_field(self):
        """check_thermal_plausibility rejects fields above ceiling."""
        hot_field = np.full((10, 10), 500.0, dtype=np.float64)
        plausible, reason = check_thermal_plausibility(hot_field, ambient_C=40.0)
        assert not plausible
        assert "exceeds sanity ceiling" in reason

    def test_plausibility_check_accepts_normal_field(self):
        """check_thermal_plausibility accepts sane fields."""
        normal_field = np.full((10, 10), 80.0, dtype=np.float64)
        plausible, _ = check_thermal_plausibility(normal_field, ambient_C=40.0)
        assert plausible

    def test_plausibility_check_rejects_none(self):
        """check_thermal_plausibility rejects None field."""
        plausible, reason = check_thermal_plausibility(None)
        assert not plausible
        assert "None" in reason


# ---------------------------------------------------------------------------
# Between-arm saturation (#137 guard)
# ---------------------------------------------------------------------------


class TestBetweenArmSaturation:
    """Cross-arm saturation detection catches degenerate fields."""

    def _make_result(self, no_field_vals, cheap_vals, physics_vals):
        """Create a HelpsBatteryResult with given per-arm thermal scores."""
        from temper_placer.validation.helps_battery import HelpsBatteryResult
        from temper_placer.validation.prereg.schema import (
            CheapBaseline,
            CostBudget,
            FieldPreregistration,
            KillCriterion,
            ParametricRange,
            PassBar,
            StructuralBoundingCase,
        )
        from temper_placer.validation.prereg.schema import BecauseThreshold

        prereg = FieldPreregistration(
            field_name="thermal",
            independent_instrument="test",
            cheap_baseline=CheapBaseline(
                name="test",
                description="test baseline",
                metric="thermal_score",
                target_value=0.0,
                because="test prereg",
            ),
            parametric_ranges=[
                ParametricRange(
                    parameter="heatspread",
                    min=5.0,
                    max=40.0,
                    because="Cover range",
                ),
            ],
            structural_bounding_cases=[
                StructuralBoundingCase(
                    case_name="single_igbt",
                    description="Min config",
                    because="Required",
                ),
            ],
            pass_bar=PassBar(
                margin_gain=BecauseThreshold(name="X", value=0.1, because="min gain"),
                beat_cheap_baseline_by=BecauseThreshold(
                    name="Y", value=0.05, because="min margin",
                ),
                across_perturbations=BecauseThreshold(
                    name="N", value=2.0, because="stats",
                ),
            ),
            kill_criterion=KillCriterion(
                description="Any pass-bar violation kills",
                because="Safety",
            ),
            cost_budget=CostBudget(
                max_total_battery_seconds=100.0,
                max_rounds_budget=20,
                field_convergence_round_limit=5,
                thermal_grid_cells_max=10000,
                target_solve_time_ms_per_field=5000.0,
            ),
        )

        return HelpsBatteryResult(
            field_name="thermal",
            baseline_name="test",
            n_perturbations=len(no_field_vals),
            prereg=prereg,
            no_field_margins={"thermal_score": no_field_vals},
            cheap_margins={"thermal_score": cheap_vals},
            physics_margins={"thermal_score": physics_vals},
        )

    def test_all_identical_zero_detected(self, caplog):
        """All arms with thermal_score == 0.0 -> saturation warning logged."""
        import logging as _logging
        from temper_placer.validation.results.battery_run import (
            _check_between_arm_saturation,
        )

        caplog.set_level(_logging.WARNING)
        result = self._make_result([0.0, 0.0], [0.0, 0.0], [0.0, 0.0])
        _check_between_arm_saturation(result)
        assert "BETWEEN-ARM SATURATION" in caplog.text

    def test_all_identical_one_detected(self, caplog):
        """All arms with thermal_score == 1.0 -> saturation warning logged."""
        import logging as _logging
        from temper_placer.validation.results.battery_run import (
            _check_between_arm_saturation,
        )

        caplog.set_level(_logging.WARNING)
        result = self._make_result([1.0, 1.0], [1.0, 1.0], [1.0, 1.0])
        _check_between_arm_saturation(result)
        assert "BETWEEN-ARM SATURATION" in caplog.text

    def test_diverging_arms_no_warning(self, caplog):
        """Diverging scores -> no saturation warning."""
        import logging as _logging
        from temper_placer.validation.results.battery_run import (
            _check_between_arm_saturation,
        )

        caplog.set_level(_logging.WARNING)
        result = self._make_result([0.3, 0.4], [0.5, 0.6], [0.7, 0.8])
        _check_between_arm_saturation(result)
        assert "BETWEEN-ARM SATURATION" not in caplog.text

    def test_empty_arms_no_warning(self, caplog):
        """Empty margins -> no warning."""
        import logging as _logging
        from temper_placer.validation.helps_battery import HelpsBatteryResult
        from temper_placer.validation.prereg.schema import (
            CheapBaseline,
            CostBudget,
            FieldPreregistration,
            KillCriterion,
            ParametricRange,
            PassBar,
            StructuralBoundingCase,
        )
        from temper_placer.validation.prereg.schema import BecauseThreshold
        from temper_placer.validation.results.battery_run import (
            _check_between_arm_saturation,
        )

        caplog.set_level(_logging.WARNING)
        result = HelpsBatteryResult(
            field_name="thermal",
            baseline_name="test",
            n_perturbations=0,
            prereg=FieldPreregistration(
                field_name="thermal",
                independent_instrument="test",
                cheap_baseline=CheapBaseline(
                    name="test", description="d", metric="thermal_score",
                    target_value=0.0, because="test",
                ),
                parametric_ranges=[
                    ParametricRange(
                        parameter="h", min=5.0, max=40.0, because="Cover",
                    ),
                ],
                structural_bounding_cases=[
                    StructuralBoundingCase(
                        case_name="s", description="d", because="b",
                    ),
                ],
                pass_bar=PassBar(
                    margin_gain=BecauseThreshold(name="X", value=0.1, because="min gain"),
                    beat_cheap_baseline_by=BecauseThreshold(
                        name="Y", value=0.05, because="min margin",
                    ),
                    across_perturbations=BecauseThreshold(
                        name="N", value=2.0, because="sanity guard test",
                    ),
                ),
                kill_criterion=KillCriterion(
                    description="test", because="test",
                ),
                cost_budget=CostBudget(
                    max_total_battery_seconds=100.0,
                    max_rounds_budget=20,
                    field_convergence_round_limit=5,
                    thermal_grid_cells_max=10000,
                    target_solve_time_ms_per_field=5000.0,
                ),
            ),
        )
        _check_between_arm_saturation(result)
        assert "BETWEEN-ARM SATURATION" not in caplog.text
