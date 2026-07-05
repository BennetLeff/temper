"""End-to-end integration test — U8: temper induction board with all 8 constraint types."""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.pcl.constraints import (
    ConstraintType,
)
from temper_placer.pcl.parser import parse_pcl_file
from temper_placer.placer.cp_sat.audit import Placement, PlacementAuditor
from temper_placer.placer.cp_sat.encoder import (
    EncoderContext,
    encode_constraints,
)
from temper_placer.placer.cp_sat.model import CpSatModel

# Temper board dimensions (mm) — standard 2-layer induction cooker PCB
TEMPER_BOARD_W_MM = 100.0
TEMPER_BOARD_H_MM = 60.0
TEMPER_BOARD_W_UNITS = 10_000
TEMPER_BOARD_H_UNITS = 6_000

# Zones from the temper_induction.yaml PCL config
TEMPER_ZONES: dict[str, tuple[float, float, float, float]] = {
    "HV_ZONE": (5.0, 5.0, 50.0, 55.0),
    "MCU_ZONE": (60.0, 5.0, 95.0, 55.0),
}

# Component refs that appear in the temper induction PCL config
TEMPER_COMPONENTS: dict[str, tuple[int, int]] = {
    "Q1": (150, 100),  # IGBT high-side
    "Q2": (150, 100),  # IGBT low-side
    "D1": (50, 80),    # Diode
    "C_DC": (200, 150), # DC-link capacitor
    "C1": (60, 30),    # Decoupling cap
    "C2": (60, 30),
    "C3": (60, 30),
    "C4": (60, 30),
    "U_GATE_DRV": (150, 100),  # Gate driver
    "U_MCU": (250, 250),       # MCU
    "J_AC": (200, 80),         # AC connector
    "J_COIL": (200, 80),       # Coil connector
}

# Polarized parts on temper board (electrolytic caps, diodes, ICs)
POLARIZED_REFS: set[str] = {"K_5", "K_6", "D_1", "D_2", "D1", "U_MCU", "U_GATE_DRV"}


PCL_FIXTURE = Path(__file__).parent.parent.parent.parent / \
    "configs" / "pcl" / "temper_induction.yaml"


class TestTemperIntegration:
    """E2E: PCL YAML -> encoder -> model -> solve -> audit."""

    @pytest.mark.slow
    def test_e2e_temper_board_feasible(self) -> None:
        """Temper board with all 8 constraint types should find a feasible placement."""
        if not PCL_FIXTURE.exists():
            pytest.skip(f"PCL fixture not found: {PCL_FIXTURE}")

        collection = parse_pcl_file(PCL_FIXTURE)
        constraints = collection.constraints
        assert len(constraints) >= 7

        model = CpSatModel(units_per_mm=100)
        for ref, (w_units, h_units) in TEMPER_COMPONENTS.items():
            model.add_component(ref, 0, 0, w_units, h_units)
            model.add_rotation(ref, is_polarized=(ref in POLARIZED_REFS))

        model.add_no_overlap_2d(list(TEMPER_COMPONENTS.keys()))
        model.set_bounds(0, 0, TEMPER_BOARD_W_UNITS, TEMPER_BOARD_H_UNITS)

        ctx = EncoderContext(
            board_w_mm=TEMPER_BOARD_W_MM,
            board_h_mm=TEMPER_BOARD_H_MM,
            zones=TEMPER_ZONES,
            zone_components={
                "HV_ZONE": ["Q1", "Q2", "D1", "C_DC"],
                "MCU_ZONE": ["U_MCU", "U_GATE_DRV"],
            },
            board_x_max_units=TEMPER_BOARD_W_UNITS,
            board_y_max_units=TEMPER_BOARD_H_UNITS,
            loop_components={"commutation": ["C_DC", "Q1", "Q2", "D1"]},
        )
        encode_constraints(constraints, model, ctx)

        sol = model.solve(time_limit_s=30.0)
        assert sol.feasible, f"Solver status: {sol.status}"
        assert len(sol.positions) == len(TEMPER_COMPONENTS)

        # Build audit placement and verify all constraints pass
        positions_mm: dict[str, tuple[float, float]] = {}
        sizes_mm: dict[str, tuple[float, float]] = {}
        for ref, (x, y) in sol.positions.items():
            sx, sy = sol.sizes.get(ref, (0, 0))
            positions_mm[ref] = (x / 100.0, y / 100.0)
            sizes_mm[ref] = (sx / 100.0, sy / 100.0)

        placement = Placement(
            positions_mm=positions_mm,
            sizes_mm=sizes_mm,
            rotations=sol.rotations,
            board_w_mm=TEMPER_BOARD_W_MM,
            board_h_mm=TEMPER_BOARD_H_MM,
            zones=TEMPER_ZONES,
            zone_components={
                "HV_ZONE": ["Q1", "Q2", "D1", "C_DC"],
                "MCU_ZONE": ["U_MCU", "U_GATE_DRV"],
            },
        )

        auditor = PlacementAuditor(placement)
        report = auditor.audit(constraints)
        assert report.all_pass, (
            f"Audit failed: {report.failed}/{report.passed + report.failed} checks failed\n"
            + "\n".join(v.description for v in report.violations)
        )

    @pytest.mark.slow
    def test_all_constraint_types_present(self) -> None:
        """Temper PCL config exercises most ConstraintType values.

        KEEPOUT is optional — not all boards define keepout zones.
        """
        if not PCL_FIXTURE.exists():
            pytest.skip(f"PCL fixture not found: {PCL_FIXTURE}")

        collection = parse_pcl_file(PCL_FIXTURE)
        present_types = {c.constraint_type for c in collection.constraints}
        expected = set(ConstraintType) - {ConstraintType.KEEPOUT}
        missing = expected - present_types
        assert not missing, f"Missing constraint types in temper PCL: {missing}"
        assert len(present_types) >= 7

    def test_mini_e2e_with_3_types(self) -> None:
        """Small-scale E2E with separated + adjacent + aligned."""
        model = CpSatModel(units_per_mm=100)
        for ref in ["Q1", "Q2", "C1", "C2"]:
            model.add_component(ref, 0, 0, 100, 100)
            model.add_rotation(ref, is_polarized=False)
        model.add_no_overlap_2d(["Q1", "Q2", "C1", "C2"])
        model.set_bounds(0, 0, 2000, 2000)

        from temper_placer.pcl.constraints import (
            AdjacentConstraint,
            AlignedConstraint,
            Axis,
            ConstraintTier,
            SeparatedConstraint,
        )

        constraints: list = [
            SeparatedConstraint("Q1", "Q2", min_distance_mm=3.0, tier=ConstraintTier.HARD,
                                because="HV isolation requirement for half-bridge pair"),
            AdjacentConstraint("Q1", "Q2", max_distance_mm=15.0, tier=ConstraintTier.HARD,
                               because="Minimize commutation loop area in half bridge"),
            AlignedConstraint(["C1", "C2"], axis=Axis.X, tolerance_mm=1.0,
                              tier=ConstraintTier.SOFT,
                              because="Align decoupling capacitors for routing consistency"),
        ]
        ctx = EncoderContext(board_w_mm=20.0, board_h_mm=20.0,
                             board_x_max_units=2000, board_y_max_units=2000)
        encode_constraints(constraints, model, ctx)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible

        positions_mm = {r: (x / 100.0, y / 100.0) for r, (x, y) in sol.positions.items()}
        sizes_mm = {r: (sx / 100.0, sy / 100.0) for r, (sx, sy) in sol.sizes.items()}
        placement = Placement(
            positions_mm=positions_mm, sizes_mm=sizes_mm,
            rotations=sol.rotations, board_w_mm=20.0, board_h_mm=20.0,
        )
        auditor = PlacementAuditor(placement)
        report = auditor.audit(constraints)
        assert report.all_pass, f"Mini E2E audit failed: {report.violations}"
