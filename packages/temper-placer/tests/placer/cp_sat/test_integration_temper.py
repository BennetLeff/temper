"""End-to-end integration test — U8: temper induction board with all 8 constraint types.

Extended by plan 2026-08-02-016 U3: the post-solve audit is wired into the
solve pipeline as a run-failing step at the solve boundary.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from temper_placer.pcl.constraints import (
    ConstraintTier,
    ConstraintType,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import parse_pcl_file
from temper_placer.placer.cp_sat.audit import (
    AuditReport,
    AuditViolation,
    Placement,
    PlacementAuditor,
    UnregisteredConstraintTypeError,
)
from temper_placer.placer.cp_sat.encoder import (
    EncoderContext,
    encode_constraints,
    solve_placement,
)
from temper_placer.placer.cp_sat.model import CpSatModel

# Temper board dimensions (mm) — standard 2-layer induction cooker PCB
TEMPER_BOARD_W_MM = 100.0
TEMPER_BOARD_H_MM = 60.0
TEMPER_BOARD_W_UNITS = 10_000
TEMPER_BOARD_H_UNITS = 6_000

# Zones from the temper_induction.yaml PCL config.
#
# VERIFIED 2026-07-18: HV_ZONE's y_max was 55.0, leaving only a 5mm strip
# (55-60mm) outside the zone at the board's top edge. The fixture's
# on_side(Q1, Q2, side=top) constraint requires y_end within
# max_distance_mm=5.0 of board_y_max (i.e. y_end >= 55mm), while
# enc_HV_ZONE requires margin_mm=2 inside the zone bounds (i.e.
# y_end <= zone_y_max - 2). With zone_y_max=55 those ranges
# (>=55 vs <=53) never overlap -- CP-SAT correctly proved this
# INFEASIBLE. Extended to the board edge (60.0) so both constraints can
# be satisfied simultaneously (y_end in [55, 58]). See docs/solutions/
# test-failures/integration-temper-hardcoded-components-drifted-from-pcl-fixture.md.
TEMPER_ZONES: dict[str, tuple[float, float, float, float]] = {
    "HV_ZONE": (5.0, 5.0, 50.0, 60.0),
    "MCU_ZONE": (60.0, 5.0, 95.0, 55.0),
}

# Component refs that appear in the temper induction PCL config.
#
# VERIFIED 2026-07-18: this dict had drifted from temper_induction.yaml's
# actual component refs (C_DC vs C_BUS1/C_BUS2, C1-4 vs C_MCU_1-4, J_AC
# vs J_AC_IN, U_GATE_DRV vs U_GATE), causing several constraints to
# silently fail to resolve ("comp 'X' not found" warnings) rather than
# apply -- the model was solving a materially weaker constraint set than
# the fixture actually specifies. Renamed to match exactly. C_DC's
# (200, 150) area is split into two bus capacitors (C_BUS1, C_BUS2) at
# (100, 150) each -- both dimensions kept even, since CpSatModel's
# midpoint constraint (x_start + x_end == 2*x_center) requires even
# sizes and raw unit values passed to add_component() bypass
# mm_to_units()'s automatic even-rounding.
TEMPER_COMPONENTS: dict[str, tuple[int, int]] = {
    "Q1": (150, 100),  # IGBT high-side
    "Q2": (150, 100),  # IGBT low-side
    "D1": (50, 80),  # Diode
    "C_BUS1": (100, 150),  # DC-link bus capacitor 1
    "C_BUS2": (100, 150),  # DC-link bus capacitor 2
    "C_MCU_1": (60, 30),  # Decoupling cap
    "C_MCU_2": (60, 30),
    "C_MCU_3": (60, 30),
    "C_MCU_4": (60, 30),
    "U_GATE": (150, 100),  # Gate driver
    "U_MCU": (250, 250),  # MCU
    "J_AC_IN": (200, 80),  # AC connector
    "J_COIL": (200, 80),  # Coil connector
}

# Polarized parts on temper board (electrolytic caps, diodes, ICs).
# VERIFIED 2026-07-18: removed K_5/K_6/D_1/D_2, which never appear in
# TEMPER_COMPONENTS (leftover cruft, presumably copy-pasted from a
# different board's fixture) and renamed U_GATE_DRV -> U_GATE.
POLARIZED_REFS: set[str] = {"D1", "U_MCU", "U_GATE"}


PCL_FIXTURE = (
    Path(__file__).parent.parent.parent.parent / "configs" / "pcl" / "temper_induction.yaml"
)


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
                "HV_ZONE": ["Q1", "Q2", "D1", "C_BUS1", "C_BUS2"],
                "MCU_ZONE": ["U_MCU", "U_GATE"],
            },
            board_x_max_units=TEMPER_BOARD_W_UNITS,
            board_y_max_units=TEMPER_BOARD_H_UNITS,
            loop_components={"commutation_loop": ["C_BUS1", "C_BUS2", "Q1", "Q2", "D1"]},
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
                "HV_ZONE": ["Q1", "Q2", "D1", "C_BUS1", "C_BUS2"],
                "MCU_ZONE": ["U_MCU", "U_GATE"],
            },
        )

        auditor = PlacementAuditor(placement)
        report = auditor.audit(
            constraints,
            loop_components=ctx.loop_components,
        )
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
            SeparatedConstraint(
                "Q1",
                "Q2",
                min_distance_mm=3.0,
                tier=ConstraintTier.HARD,
                because="HV isolation requirement for half-bridge pair",
            ),
            AdjacentConstraint(
                "Q1",
                "Q2",
                max_distance_mm=15.0,
                tier=ConstraintTier.HARD,
                because="Minimize commutation loop area in half bridge",
            ),
            AlignedConstraint(
                ["C1", "C2"],
                axis=Axis.X,
                tolerance_mm=1.0,
                tier=ConstraintTier.SOFT,
                because="Align decoupling capacitors for routing consistency",
            ),
        ]
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )
        encode_constraints(constraints, model, ctx)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible

        positions_mm = {r: (x / 100.0, y / 100.0) for r, (x, y) in sol.positions.items()}
        sizes_mm = {r: (sx / 100.0, sy / 100.0) for r, (sx, sy) in sol.sizes.items()}
        placement = Placement(
            positions_mm=positions_mm,
            sizes_mm=sizes_mm,
            rotations=sol.rotations,
            board_w_mm=20.0,
            board_h_mm=20.0,
        )
        auditor = PlacementAuditor(placement)
        report = auditor.audit(constraints)
        assert report.all_pass, f"Mini E2E audit failed: {report.violations}"


# ---------------------------------------------------------------------------
# Plan 2026-08-02-016 U3: the post-solve audit is wired into solve_placement
# as a run-failing step at the solve boundary.
# ---------------------------------------------------------------------------


def _minimal_netlist_and_board():
    """A tiny 2-component netlist + board for solve-boundary tests."""
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Netlist, Pin

    comps = [
        Component(ref="Q1", footprint="test:fp", bounds=(10.0, 10.0),
                  pins=[Pin(name="1", number="1", net="AC", position=(0.0, 0.0))]),
        Component(ref="Q2", footprint="test:fp", bounds=(10.0, 10.0),
                  pins=[Pin(name="1", number="1", net="AC", position=(0.0, 0.0))]),
    ]
    netlist = Netlist(components=comps, nets=[])
    board = Board(width=100.0, height=60.0)
    return netlist, board


class TestPostSolveAuditWiring:
    """U3: the audit runs at the solve boundary and fails the run on
    mismatch; INFEASIBLE solves skip it; fail-closed raises surface as a
    run failure naming the type."""

    def test_normal_solve_records_audit_pass(self) -> None:
        netlist, board = _minimal_netlist_and_board()
        constraints = [
            SeparatedConstraint(
                "Q1",
                "Q2",
                min_distance_mm=3.0,
                tier=ConstraintTier.HARD,
                because="HV isolation requirement for half-bridge pair",
            )
        ]
        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=constraints,
            timeout_ms=3_000,
            seed=42,
        )
        assert result.status in ("optimal", "feasible"), result.status
        # U3 scenario 1: the audit pass is recorded on the result.
        assert result.audit_report is not None
        assert result.audit_report.all_pass, (
            [v.description for v in result.audit_report.violations]
        )
        # The full encoded surface was audited — courtyard SEPARATEDs too.
        assert result.audit_report.passed >= len(constraints)

    def test_forged_violating_coordinates_fail_the_audit(self) -> None:
        """U3 scenario 2: a placement whose coordinates violate an encoded
        constraint is rejected with the violations attached."""
        from temper_placer.pcl.constraints import AnchoredConstraint
        from temper_placer.placer.cp_sat._encoder_solve import _run_post_solve_audit

        netlist, board = _minimal_netlist_and_board()
        # Forge the solved coordinates: Q1 anchored at (5,5) but placed at (90,50).
        forged_positions = {"Q1": (90.0, 50.0), "Q2": (20.0, 20.0)}
        constraints = [
            AnchoredConstraint(
                "Q1",
                tier=ConstraintTier.HARD,
                position=(5.0, 5.0),
                because="MCU centered in MCU zone for antenna clearance in design",
            )
        ]
        ctx = EncoderContext(board_w_mm=100.0, board_h_mm=60.0)
        report, _barrier = _run_post_solve_audit(
            positions_mm=forged_positions,
            sizes_mm={"Q1": (10.0, 10.0), "Q2": (10.0, 10.0)},
            rotations={"Q1": 0, "Q2": 0},
            board_w_mm=100.0,
            board_h_mm=60.0,
            zones={},
            zone_components={},
            constraints=constraints,
            netlist=netlist,
            netclass_rules_data=None,
            model=CpSatModel(units_per_mm=100),
            ctx=ctx,
            isolation_barrier_report=None,
        )
        assert not report.all_pass
        assert report.failed >= 1
        assert any("ANCHORED" in v.description for v in report.violations)

    def test_non_passing_audit_converts_solve_to_audit_failed(self) -> None:
        """A non-passing audit report converts the solve result to a failure
        verdict carrying the violations (pipeline wiring)."""
        netlist, board = _minimal_netlist_and_board()
        constraints = [
            SeparatedConstraint(
                "Q1",
                "Q2",
                min_distance_mm=3.0,
                tier=ConstraintTier.HARD,
                because="HV isolation requirement for half-bridge pair",
            )
        ]
        failing = AuditReport(
            passed=0,
            failed=1,
            violations=[
                AuditViolation(
                    constraint_id="forged",
                    constraint_type="separated",
                    description="SEPARATED forged",
                    detail="gap=0.0",
                )
            ],
        )
        with mock.patch.object(PlacementAuditor, "audit", return_value=failing):
            result = solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=constraints,
                timeout_ms=3_000,
                seed=42,
            )
        assert result.status == "audit_failed"
        assert result.audit_report is failing
        assert result.audit_report.violations[0].constraint_type == "separated"

    def test_infeasible_skips_audit(self) -> None:
        """U3 scenario 3: an INFEASIBLE solve has no placement to audit and
        is not mislabeled as an audit pass."""
        from ortools.sat.python import cp_model

        netlist, board = _minimal_netlist_and_board()
        with mock.patch.object(cp_model.CpSolver, "Solve", return_value=cp_model.INFEASIBLE):
            result = solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=[],
                timeout_ms=1_000,
                seed=42,
            )
        assert result.status == "infeasible"
        assert result.audit_report is None
        assert result.positions == {}

    def test_audit_raise_surfaces_as_run_failure_naming_type(self) -> None:
        """U3 scenario 4: the audit fail-closing (U1) surfaces as a run
        failure naming the type, not a swallowed exception."""
        netlist, board = _minimal_netlist_and_board()
        constraints = [
            SeparatedConstraint(
                "Q1",
                "Q2",
                min_distance_mm=3.0,
                tier=ConstraintTier.HARD,
                because="HV isolation requirement for half-bridge pair",
            )
        ]

        def _raise_unregistered(self, *args, **kwargs):
            raise UnregisteredConstraintTypeError("Constraint type 'bogus' (bogus)")

        with mock.patch.object(PlacementAuditor, "audit", new=_raise_unregistered):
            result = solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=constraints,
                timeout_ms=3_000,
                seed=42,
            )
        assert result.status == "audit_failed"
        assert result.audit_report is not None
        assert not result.audit_report.all_pass
        assert "bogus" in result.audit_report.violations[0].description

    def test_loop_treats_audit_failed_as_failure(self) -> None:
        """The place-route loop must exit with AUDIT_FAILED, not continue
        routing from an audit-rejected placement."""
        from temper_placer.placer.cp_sat._loop_types import LoopExitReason
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
        from temper_placer.placer.cp_sat.loop import PlaceRouteLoop

        netlist, board = _minimal_netlist_and_board()
        forged = CpSatPlacementResult(
            positions={"Q1": (5.0, 5.0), "Q2": (6.0, 5.0)},
            rotations={},
            placed_refs=["Q1", "Q2"],
            status="audit_failed",
            audit_report=AuditReport(
                passed=0,
                failed=1,
                violations=[
                    AuditViolation(
                        constraint_id="forged",
                        constraint_type="separated",
                        description="SEPARATED forged",
                    )
                ],
            ),
        )
        loop = PlaceRouteLoop(_placement_solver=lambda **_kwargs: forged)
        result = loop.run(
            netlist=netlist,
            board=board,
            pcl_constraints=[],
        )
        assert not result.success
        assert result.reason == LoopExitReason.AUDIT_FAILED.value
