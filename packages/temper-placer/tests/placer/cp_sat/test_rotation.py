"""Tests for discrete 4-way rotation (U5)."""

from __future__ import annotations

from temper_placer.placer.cp_sat.model import CpSatModel


class TestRotationBasics:
    """Basic rotation variable and size correctness."""

    def test_non_polarized_gets_variable_sizes(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("R_SMD", 0, 0, 80, 30)
        rot = model.add_rotation("R_SMD", is_polarized=False)
        assert rot is not None
        # Sizes should now be variable via AddElement
        comp = model.get_component("R_SMD")
        assert comp.rot_ref is not None

    def test_polarized_sizes_pinned(self) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("K_5", 0, 0, 120, 120)
        model.add_rotation("K_5", is_polarized=True)
        model.set_bounds(0, 0, 1000, 1000)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        assert sol.sizes["K_5"] == (120, 120)
        assert sol.rotations["K_5"] == 0

    def test_rotated_component_sizes_swap(self) -> None:
        """At rot=1 (90 deg), width and height should swap."""
        model = CpSatModel(units_per_mm=100)
        model.add_component("C_SMD", 0, 0, 80, 30)
        model.add_rotation("C_SMD", is_polarized=False)
        model.set_bounds(0, 0, 2000, 2000)

        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        rot = sol.rotations["C_SMD"]
        w, h = sol.sizes["C_SMD"]
        if rot == 0 or rot == 2:
            assert (w, h) == (80, 30), f"rot={rot} sizes=({w},{h}) expected (80,30)"
        elif rot == 1 or rot == 3:
            assert (w, h) == (30, 80), f"rot={rot} sizes=({w},{h}) expected (30,80)"

    def test_rotation_pinned_to_fixed_value(self) -> None:
        """Pin rotation to a specific value and verify sizes."""
        model = CpSatModel(units_per_mm=100)
        model.add_component("R1", 0, 0, 100, 50)
        rot = model.add_rotation("R1", is_polarized=False)
        assert rot is not None
        model.add(rot == 1)
        model.set_bounds(0, 0, 1000, 1000)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        assert sol.rotations["R1"] == 1
        assert sol.sizes["R1"] == (50, 100)

    def test_many_rotatable_parts(self) -> None:
        """~15 rotatable parts should solve quickly."""
        model = CpSatModel(units_per_mm=100)
        refs = []
        for i in range(15):
            ref = f"R{i:02d}"
            w, h = (60 + i, 30 + i) if i % 2 == 0 else (80, 40)
            model.add_component(ref, 0, 0, w, h)
            polarized = (i % 3 == 0)
            model.add_rotation(ref, is_polarized=polarized)
            refs.append(ref)
        model.add_no_overlap_2d(refs)
        model.set_bounds(0, 0, 5000, 5000)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible
        assert len(sol.positions) == 15

        for ref in refs:
            assert sol.sizes[ref][0] > 0
            assert sol.sizes[ref][1] > 0
