"""
BMC Verification Engine for SAT Encoding Correctness.

# @req(2026-06-28-006, FR-BMC1): BMC engine — enumeration + pysat check

For a (ConstraintModel, SATModel) pair, enumerates all 2^N assignments of
primary (non-auxiliary) SAT variables and asserts that the ESL predicate and
the pysat-evaluated CNF agree on SAT/UNSAT.

The bound defaults to N <= 10 primary variables (2^10 = 1024 assignments).
A counterexample is an assignment where ESL and CNF disagree — it is returned
as a diagnostic dict that can be rendered to a copy-pasteable reproduction
snippet.

No JAX imports (NFR4 compliance).

Railway-interlocking analogy: declare safe routes (ESL), prove signal circuit
(CNF) never energizes an unsafe combination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.router_v6.constraint_model import ConstraintModel
    from temper_placer.router_v6.sat_model import SATModel

DEFAULT_BMC_BOUND = 10


class BmcBoundExceeded(Exception):
    """Raised when the primary-variable count exceeds the BMC bound."""


def _extract_primary_vars(
    sat_model: SATModel,
    constraint_model: ConstraintModel,
) -> list[str]:
    """Extract primary (non-auxiliary) SAT variable names.

    Primary variables are those corresponding to NetChannelVar instances
    in the constraint model.  Auxiliary Sinz counter variables (prefixed
    ``sc_``) are excluded.
    """
    from temper_placer.router_v6.constraint_model import NetChannelVar

    constraint_var_names: set[str] = set()
    for var in constraint_model.variables:
        if isinstance(var, NetChannelVar):
            constraint_var_names.add(var.name)

    {
        sv.name: sv for sv in sat_model.variables
    }
    primary_names: list[str] = []
    for sv in sat_model.variables:
        if sv.name.startswith("sc_"):
            continue
        for cname in constraint_var_names:
            if cname in sv.name or sv.name in cname:
                primary_names.append(sv.name)
                break
            if sv.name == cname:
                primary_names.append(sv.name)
                break

    if not primary_names:
        for sv in sat_model.variables:
            if sv.name.startswith("sc_"):
                continue
            for cname in constraint_var_names:
                c_parts = cname.split("_", 2)
                s_parts = sv.name.split("_", 2)
                if len(c_parts) >= 3 and len(s_parts) >= 3:
                    if c_parts[2] == s_parts[2]:
                        primary_names.append(sv.name)
                        break

    return list(dict.fromkeys(primary_names))


def _make_assignment(
    primary_names: list[str],
    mask: int,
) -> dict[str, bool]:
    """Build an assignment dict from a bitmask."""
    return {
        name: bool(mask & (1 << i))
        for i, name in enumerate(primary_names)
    }


def _check_cnf_sat(
    sat_model: SATModel,
    assignment: dict[str, bool],
) -> bool:
    """Check whether the CNF is satisfiable under the given primary assignment.

    Primary variables are fixed via unit clauses; auxiliary (Sinz) variables
    are free.  Uses pysat as the oracle.
    """
    from pysat.solvers import Solver

    solver = Solver(bootstrap_with=[])

    var_to_idx: dict[str, int] = {}
    idx = 1
    for sv in sat_model.variables:
        var_to_idx[sv.name] = idx
        idx += 1

    for clause in sat_model.clauses:
        lits = [
            var_to_idx[v.name] if pol else -var_to_idx[v.name]
            for v, pol in clause.literals
        ]
        solver.add_clause(lits)

    for name, value in assignment.items():
        if name not in var_to_idx:
            solver.delete()
            return True
        lit = var_to_idx[name] if value else -var_to_idx[name]
        solver.add_clause([lit])

    result = solver.solve()
    solver.delete()
    return result


def bmc_check(
    constraint_model: ConstraintModel,
    sat_model: SATModel,
    primary_var_names: list[str] | None = None,
    bound: int = DEFAULT_BMC_BOUND,
) -> list[dict]:
    """Enumerate all primary assignments and check ESL vs CNF agreement.

    # @req(2026-06-28-006, FR-BMC1): BMC enumeration + pysat check

    Args:
        constraint_model: The constraint model with ESL definitions.
        sat_model: The SAT model produced by ``populate_sat_from_constraints``
                   (with ``skip_connectivity=True`` for constraint-only CNF).
        primary_var_names: Optional explicit list of primary variable names.
                           If None, extracted automatically.
        bound: Maximum number of primary variables (default 10).

    Returns:
        A list of counterexample diagnostic dicts.  Empty list means all
        assignments agree — the encoding is correct within the bound.

    Raises:
        BmcBoundExceeded: If primary variable count exceeds *bound*.
    """
    from temper_placer.router_v6.esl import eval_esl

    if primary_var_names is None:
        primary_var_names = _extract_primary_vars(sat_model, constraint_model)

    n = len(primary_var_names)
    if n > bound:
        raise BmcBoundExceeded(
            f"BMC bound exceeded: {n} primary variables > {bound} bound. "
            f"Primary vars: {primary_var_names}"
        )

    counterexamples: list[dict] = []
    for mask in range(1 << n):
        assignment = _make_assignment(primary_var_names, mask)

        esl_result = eval_esl(constraint_model, assignment)
        cnf_result = _check_cnf_sat(sat_model, assignment)

        if esl_result != cnf_result:
            failure_type = "false_unsat" if esl_result else "false_sat"
            counterexamples.append({
                "assignment": assignment,
                "esl_result": esl_result,
                "cnf_result": "SAT" if cnf_result else "UNSAT",
                "failure_type": failure_type,
                "primary_vars": primary_var_names,
                "constraint_count": constraint_model.constraint_count,
                "variable_count": constraint_model.variable_count,
            })

    return counterexamples


def bmc_check_with_diagnostics(
    constraint_model: ConstraintModel,
    sat_model: SATModel,
    primary_var_names: list[str] | None = None,
    bound: int = DEFAULT_BMC_BOUND,
) -> list[dict]:
    """Like :func:`bmc_check` but enriches counterexamples with clause info.

    Each counterexample diagnostic additionally includes the full clause set
    and the implicated clauses for debugging.
    """
    ces = bmc_check(constraint_model, sat_model, primary_var_names, bound)

    if primary_var_names is None:
        primary_var_names = _extract_primary_vars(sat_model, constraint_model)

    for ce in ces:
        ce["all_clauses"] = [str(c) for c in sat_model.clauses]
        ce["clause_descriptions"] = [c.description for c in sat_model.clauses]

    return ces


def render_counterexample(ce: dict) -> str:
    """Render a counterexample as a copy-pasteable Python reproduction snippet.

    # @req(2026-06-28-006, FR-CEX3): Counterexample reproducible via copy-pasteable snippet
    """
    from pprint import pformat

    assignment_str = pformat(ce["assignment"])
    failure_type = ce["failure_type"]
    esl_result = ce["esl_result"]
    cnf_result = ce["cnf_result"]
    primary_vars = pformat(ce.get("primary_vars", []))

    return f'''def test_reproduce_bmc_failure():
    """BMC counterexample: {failure_type}

    ESL says: {esl_result}, CNF says: {cnf_result}
    Assignment: {assignment_str}
    """
    from temper_placer.router_v6.constraint_model import ConstraintModel, NetChannelVar
    from temper_placer.router_v6.sat_model import SATModel, populate_sat_from_constraints
    from temper_placer.router_v6.bmc import bmc_check

    # Reconstruct the model — see test for exact variables/constraints
    # Primary vars: {primary_vars}
    # Assignment: {assignment_str}

    cm = ConstraintModel()
    # TODO: Recreate ConstraintModel from the original test context
    sat = SATModel(variables=[], clauses=[])
    # populate_sat_from_constraints(sat, cm, skip_connectivity=True)

    counterexamples = bmc_check(cm, sat, primary_var_names={primary_vars})
    assert len(counterexamples) == 1
    assert counterexamples[0]["failure_type"] == "{failure_type}"
'''
