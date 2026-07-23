"""Unit tests for UNSAT core extraction pipeline."""

from __future__ import annotations

from ortools.sat.python import cp_model

from temper_placer.pcl.constraints import ConstraintType
from temper_placer.placer.cp_sat.unsat import (
    UnsatConstraint,
    UnsatReport,
    _build_proto_index_map,
    _decode_assumption_literals,
    extract_unsat_core,
)


def _solve_infeasible(model, assumption_vars):
    """Add assumptions and solve; return solver and status."""
    model.AddAssumptions(list(assumption_vars))
    solver = cp_model.CpSolver()
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    return solver, status


def _build_artificially_infeasible_model():
    """Build a model that is infeasible due to conflicting assumptions.

    Creates two Boolean assumption literals with mutually exclusive constraints:
    lit0 forces x=0, lit1 forces x=1. Together they are INFEASIBLE.
    """
    model = cp_model.CpModel()
    x = model.NewIntVar(0, 1, "x")

    lit0 = model.NewBoolVar("assume_x_eq_0")
    lit1 = model.NewBoolVar("assume_x_eq_1")

    model.Add(x == 0).OnlyEnforceIf(lit0)
    model.Add(x == 1).OnlyEnforceIf(lit1)

    assumption_vars = [lit0, lit1]
    constraint_map: dict[int, UnsatConstraint] = {
        lit0.Index(): UnsatConstraint(
            name="separated 'Q1_HV_LV'",
            constraint_type=ConstraintType.SEPARATED,
            because="Reinforced isolation per IEC 60335-1",
            assumption_literal=lit0.Index(),
        ),
        lit1.Index(): UnsatConstraint(
            name="enclosing 'HV_ZONE'",
            constraint_type=ConstraintType.ENCLOSING,
            because="HV segregation for touch safety",
            assumption_literal=lit1.Index(),
        ),
    }

    return model, assumption_vars, constraint_map


def _build_infeasible_with_unannotated_constraint():
    """Build infeasible model where one constraint has no ``because`` field."""
    model = cp_model.CpModel()
    x = model.NewIntVar(0, 1, "x")

    lit0 = model.NewBoolVar("assume_x_eq_0")
    lit1 = model.NewBoolVar("assume_x_eq_1")

    model.Add(x == 0).OnlyEnforceIf(lit0)
    model.Add(x == 1).OnlyEnforceIf(lit1)

    assumption_vars = [lit0, lit1]
    constraint_map: dict[int, UnsatConstraint] = {
        lit0.Index(): UnsatConstraint(
            name="separated 'Q1_Q2'",
            constraint_type=ConstraintType.SEPARATED,
            because=None,
            assumption_literal=lit0.Index(),
        ),
        lit1.Index(): UnsatConstraint(
            name="loop_area 'commutation'",
            constraint_type=ConstraintType.LOOP_AREA,
            because="IGBT overvoltage destruction above 635 mm2 at 1 A/ns di/dt",
            assumption_literal=lit1.Index(),
        ),
    }

    return model, assumption_vars, constraint_map


class TestBuildProtoIndexMap:
    def test_maps_indices(self):
        model = cp_model.CpModel()
        a = model.NewBoolVar("a")
        b = model.NewBoolVar("b")
        idx_map = _build_proto_index_map([a, b])
        assert a.Index() in idx_map
        assert b.Index() in idx_map
        assert idx_map[a.Index()] is a


class TestDecodeAssumptionLiterals:
    def test_decodes_known_literals(self):
        cmap: dict[int, UnsatConstraint] = {
            0: UnsatConstraint(
                name="c1",
                constraint_type=ConstraintType.SEPARATED,
                because="test",
                assumption_literal=0,
            ),
        }
        result = _decode_assumption_literals([0], cmap)
        assert len(result) == 1
        assert result[0].name == "c1"

    def test_decodes_unknown_literal_with_placeholder(self):
        cmap: dict[int, UnsatConstraint] = {}
        result = _decode_assumption_literals([99], cmap)
        assert len(result) == 1
        assert result[0].name == "unknown_literal_99"
        assert result[0].because is None


class TestExtractUnsatCore:
    def test_infeasible_model_returns_report(self):
        model, assumption_vars, constraint_map = _build_artificially_infeasible_model()
        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        assert isinstance(report, UnsatReport)
        assert len(report.sufficient_core) >= 2
        assert len(report.minimal_core) >= 1

    def test_sufficient_core_lists_conflicting_constraints(self):
        model, assumption_vars, constraint_map = _build_artificially_infeasible_model()
        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        names = {c.name for c in report.sufficient_core}
        assert "separated 'Q1_HV_LV'" in names
        assert "enclosing 'HV_ZONE'" in names

    def test_minimal_core_is_subset_of_sufficient(self):
        model, assumption_vars, constraint_map = _build_artificially_infeasible_model()
        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        min_names = {c.name for c in report.minimal_core}
        suff_names = {c.name for c in report.sufficient_core}
        assert min_names.issubset(suff_names)

    def test_constraint_with_because_carries_text(self):
        model, assumption_vars, constraint_map = _build_artificially_infeasible_model()
        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        for c in report.sufficient_core:
            if c.name == "separated 'Q1_HV_LV'":
                assert c.because == "Reinforced isolation per IEC 60335-1"

    def test_constraint_without_because_is_none(self):
        model, assumption_vars, constraint_map = _build_infeasible_with_unannotated_constraint()
        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        unannotated = [c for c in report.sufficient_core if c.name == "separated 'Q1_Q2'"]
        assert len(unannotated) == 1
        assert unannotated[0].because is None

    def test_unannotated_produces_data_quality_gap(self):
        model, assumption_vars, constraint_map = _build_infeasible_with_unannotated_constraint()
        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        gaps = report.data_quality_gaps
        assert len(gaps) >= 1
        assert any("Q1_Q2" in g["constraint_name"] for g in gaps)

    def test_single_constraint_core_mus_is_minimal(self):
        """Single-constraint core is trivially minimal."""
        model = cp_model.CpModel()
        x = model.NewIntVar(0, 1, "x")
        lit = model.NewBoolVar("assume_impossible")
        model.Add(x == 2).OnlyEnforceIf(lit)

        assumption_vars = [lit]
        constraint_map: dict[int, UnsatConstraint] = {
            lit.Index(): UnsatConstraint(
                name="impossible_constraint",
                constraint_type=ConstraintType.ANCHORED,
                because="Test impossible constraint",
                assumption_literal=lit.Index(),
            ),
        }

        solver, status = _solve_infeasible(model, assumption_vars)
        assert status == cp_model.INFEASIBLE

        report = extract_unsat_core(solver, model, assumption_vars, constraint_map)
        assert len(report.sufficient_core) >= 1
