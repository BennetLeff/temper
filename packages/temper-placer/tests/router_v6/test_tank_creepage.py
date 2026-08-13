"""
Tests for router_v6.tank_creepage: the pairwise HV<->HV tank-node
creepage keepout.

See docs/evidence/2026-08-12-router-tank-creepage.md.
"""

import numpy as np

from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from temper_placer.router_v6.tank_creepage import (
    TANK_CREEPAGE_MM,
    TANK_NET_CLASS,
    apply_tank_creepage_keepout,
    needs_tank_creepage_check,
    release_tank_creepage_keepout,
    tank_pad_positions,
)


def _grid(layer: str = "F.Cu", cells: int = 400, cell_size: float = 0.1) -> OccupancyGrid:
    """A blank, fully-free occupancy grid, origin at (0, 0)."""
    return OccupancyGrid(
        layer_name=layer,
        grid=np.zeros((cells, cells), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=cell_size,
        width_cells=cells,
        height_cells=cells,
    )


def _design_rules() -> DesignRules:
    return DesignRules(
        net_classes={
            "HighVoltageTank": NetClassRules(
                name="HighVoltageTank",
                clearance_mm=2.0,
                trace_width_mm=3.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
                safety_category="HV",
                creepage_mm=10.0,
            ),
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                clearance_mm=2.0,
                trace_width_mm=3.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
                safety_category="HV",
                creepage_mm=6.0,
            ),
            "Signal": NetClassRules(
                name="Signal",
                clearance_mm=0.15,
                trace_width_mm=0.2,
                via_diameter_mm=0.6,
                via_drill_mm=0.3,
                safety_category="LV",
                creepage_mm=0.0,
            ),
        },
        net_class_assignments={
            "tank.c_tank1-p2": "HighVoltageTank",
            "discharge.k_dis1-nc": "HighVoltage",
            "signal.foo": "Signal",
        },
    )


class TestClassification:
    def test_tank_net_itself_does_not_need_the_check(self):
        dr = _design_rules()
        assert needs_tank_creepage_check("tank.c_tank1-p2", dr) is False

    def test_other_hv_net_needs_the_check(self):
        dr = _design_rules()
        assert needs_tank_creepage_check("discharge.k_dis1-nc", dr) is True

    def test_lv_signal_net_does_not_need_the_check(self):
        dr = _design_rules()
        assert needs_tank_creepage_check("signal.foo", dr) is False

    def test_unclassed_default_net_does_not_need_the_check(self):
        dr = _design_rules()
        assert needs_tank_creepage_check("totally_unknown_net", dr) is False


class TestTankPadPositions:
    def test_collects_pads_for_the_tank_class_only(self):
        dr = _design_rules()
        pad_centers = {
            "tank.c_tank1-p2": [(10.0, 10.0, 0.75, "F.Cu")],
            "discharge.k_dis1-nc": [(50.0, 50.0, 0.5, "F.Cu")],
        }
        pads = tank_pad_positions(pad_centers, dr)
        assert pads == [(10.0, 10.0, 0.75, "F.Cu")]

    def test_empty_when_no_tank_pads_present(self):
        dr = _design_rules()
        pads = tank_pad_positions({"discharge.k_dis1-nc": [(1.0, 1.0, 0.5, "F.Cu")]}, dr)
        assert pads == []


class TestKeepoutApplyRelease:
    def test_blocks_cells_within_pad_radius_plus_creepage(self):
        grid = _grid()
        grids = {"F.Cu": grid}
        # Pad at (20, 20)mm, radius 0.75mm -> keepout radius 0.75+10.0=10.75mm
        pads = [(20.0, 20.0, 0.75, "F.Cu")]
        changed = apply_tank_creepage_keepout(grids, pads, creepage_mm=TANK_CREEPAGE_MM)
        assert changed  # something was blocked

        # A point 5mm from the pad centre must be blocked (well inside 10.75mm)
        gx, gy = grid.world_to_grid(25.0, 20.0)
        assert grid.grid[gy, gx] != 0

        # A point 15mm away must NOT be blocked (outside 10.75mm)
        gx_far, gy_far = grid.world_to_grid(35.0, 20.0)
        assert grid.grid[gy_far, gx_far] == 0

    def test_release_restores_exactly_the_changed_cells_to_free(self):
        grid = _grid()
        grids = {"F.Cu": grid}
        pads = [(20.0, 20.0, 0.75, "F.Cu")]
        changed = apply_tank_creepage_keepout(grids, pads)
        assert any(grid.grid[gy, gx] != 0 for _g, gy, gx in changed)

        release_tank_creepage_keepout(changed)

        for _g, gy, gx in changed:
            assert grid.grid[gy, gx] == 0
        assert grid.free_cell_count == grid.width_cells * grid.height_cells

    def test_never_overwrites_a_cell_already_carrying_real_copper(self):
        """A cell already occupied by a real net (positive net_id) must be
        left untouched by the keepout -- ripup logic elsewhere identifies
        blockers by their real net_id and must never see a borrowed one."""
        grid = _grid()
        # Simulate a committed via/track from a real net (net_id=7) directly
        # under where the keepout would otherwise land.
        gx0, gy0 = grid.world_to_grid(20.0, 20.0)
        grid.grid[gy0, gx0] = 7
        grids = {"F.Cu": grid}
        pads = [(20.0, 20.0, 0.75, "F.Cu")]

        changed = apply_tank_creepage_keepout(grids, pads)

        assert grid.grid[gy0, gx0] == 7  # untouched
        assert (grid, gy0, gx0) not in changed

    def test_never_overwrites_a_permanent_static_obstacle(self):
        grid = _grid()
        gx0, gy0 = grid.world_to_grid(20.0, 20.0)
        grid.grid[gy0, gx0] = -1  # permanent static obstacle
        grids = {"F.Cu": grid}
        pads = [(20.0, 20.0, 0.75, "F.Cu")]

        changed = apply_tank_creepage_keepout(grids, pads)

        assert grid.grid[gy0, gx0] == -1
        assert (grid, gy0, gx0) not in changed

    def test_only_touches_the_pad_s_own_layer(self):
        f_grid = _grid("F.Cu")
        b_grid = _grid("B.Cu")
        grids = {"F.Cu": f_grid, "B.Cu": b_grid}
        pads = [(20.0, 20.0, 0.75, "F.Cu")]

        apply_tank_creepage_keepout(grids, pads)

        assert b_grid.free_cell_count == b_grid.width_cells * b_grid.height_cells

    def test_missing_layer_in_grids_is_skipped_not_an_error(self):
        grid = _grid("F.Cu")
        grids = {"F.Cu": grid}
        pads = [(20.0, 20.0, 0.75, "In1.Cu")]  # no In1.Cu grid present

        changed = apply_tank_creepage_keepout(grids, pads)

        assert changed == []

    def test_empty_pad_list_changes_nothing(self):
        grid = _grid()
        grids = {"F.Cu": grid}
        changed = apply_tank_creepage_keepout(grids, [])
        assert changed == []


class TestConstants:
    def test_tank_creepage_mm_is_pd3_as_built_governing(self):
        # PD3, not PD2 -- docs/evidence/2026-08-11-pd2-decision-record.md
        # sec 2: the PD2 sealed-compartment prerequisite does not exist.
        assert TANK_CREEPAGE_MM == 10.0

    def test_tank_net_class_matches_design_rules_py(self):
        assert TANK_NET_CLASS == "HighVoltageTank"
