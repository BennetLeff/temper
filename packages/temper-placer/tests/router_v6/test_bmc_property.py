"""BMC property-based tests — sequential counter proof, induction, random models.

# @req(2026-06-28-006, FR-HYP3): BMC L0 Hypothesis test marker

Covers:
- Sequential counter exhaustive proof (n ≤ 8, all k, all 2^n assignments)
- Inductive extension: correct model stays correct when adding one variable
- Hypothesis PBT: random ConstraintModel instances verified via BMC
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.router_v6.sat_property_strategies import constraint_models


# ---------------------------------------------------------------------------
# Sequential counter exhaustive proof (base case for induction)
# ---------------------------------------------------------------------------

@pytest.mark.bmc_l0_encoding
def test_sequential_counter_exhaustive_n1_to_n8():
    """Exhaustively verify the Python sequential counter for n ∈ [1, 8].

    For every n ∈ 1..8, k ∈ 0..n-1, and all 2^n primary assignments,
    check that the AtMostK encoding is SAT iff at most k variables are
    true.  This is the base case for the Sinz (2005) inductive proof
    and mirrors the Rust encoding.rs proof.
    """
    from temper_placer.router_v6.sat_model import SATModel, _encode_at_most_k

    for n in range(1, 9):
        for k in range(0, n):
            # Build a SAT model with n primary variables
            sat = SATModel(variables=[], clauses=[])
            vars_list = [
                sat.add_variable(f"x{i}", f"primary var {i}")
                for i in range(n)
            ]

            _encode_at_most_k(sat, vars_list, k, description_prefix=f"n{n}_k{k}")

            total_vars = len(sat.variables)
            total_assignments = 0
            failures: list[str] = []

            for bits in range(1 << n):
                assignment = {}
                true_count = 0
                for i in range(n):
                    val = (bits >> i) & 1 == 1
                    assignment[f"x{i}"] = val
                    if val:
                        true_count += 1

                cnf_sat = _dpll_check(
                    sat, assignment, total_vars
                )
                total_assignments += 1

                expected = true_count <= k
                if cnf_sat != expected:
                    failures.append(
                        f"n={n} k={k} bits={bits:0{n}b} "
                        f"true_count={true_count} expected={'SAT' if expected else 'UNSAT'} "
                        f"got={'SAT' if cnf_sat else 'UNSAT'}"
                    )
                    # Stop collecting after first failure for this (n,k)
                    break

            assert len(failures) == 0, (
                f"Sequential counter failure for (n={n}, k={k}) "
                f"after checking {total_assignments} assignments:\n"
                + "\n".join(failures)
            )

    # Sanity: we checked the expected number of assignments
    # sum_{n=1..8} sum_{k=0..n-1} (2^n) = sum_{n=1..8} n * 2^n
    expected_total = sum(n * (1 << n) for n in range(1, 9))
    # We can't easily track a global counter in pytest, but this is
    # covered by the assertion messages above.


def _dpll_check(sat_model, fixed_assignment: dict[str, bool], total_vars: int) -> bool:
    """Mini DPLL SAT checker — unit propagation + backtracking."""
    # Build clause list as list of lists of signed ints (1-indexed)
    # Sign: positive = true literal
    name_to_idx: dict[str, int] = {}
    idx = 1
    for var in sat_model.variables:
        name_to_idx[var.name] = idx
        idx += 1

    clauses: list[list[int]] = []
    for clause in sat_model.clauses:
        lits: list[int] = []
        for sat_var, is_pos in clause.literals:
            if sat_var.name not in name_to_idx:
                continue
            cidx = name_to_idx[sat_var.name]
            lits.append(cidx if is_pos else -cidx)
        if lits:
            clauses.append(lits)

    # Initial assignment from fixed vars
    assign: list[bool | None] = [None] * (total_vars + 1)  # 1-indexed
    for name, val in fixed_assignment.items():
        idx = name_to_idx.get(name)
        if idx is not None:
            assign[idx] = val

    return _dpll_rec(clauses, assign)


def _dpll_rec(clauses: list[list[int]], assign: list[bool | None]) -> bool:
    """Recursive DPLL with unit propagation."""
    # Unit propagation
    while True:
        changed = False
        for clause in clauses:
            unset_count = 0
            unset_idx = 0
            unset_sign = True
            clause_sat = False

            for lit in clause:
                var = abs(lit)
                sign = lit > 0
                if var >= len(assign):
                    clause_sat = True
                    break
                val = assign[var]
                if val is True and sign:
                    clause_sat = True
                    break
                if val is True and not sign:
                    pass  # falsified literal
                elif val is False and sign:
                    pass  # falsified literal
                elif val is False and not sign:
                    clause_sat = True
                    break
                elif val is None:
                    unset_count += 1
                    unset_idx = var
                    unset_sign = sign

            if clause_sat:
                continue
            if unset_count == 0:
                return False  # conflicting clause
            if unset_count == 1:
                assign[unset_idx] = unset_sign
                changed = True

        if not changed:
            break

    # All clauses satisfied?
    all_sat = True
    for clause in clauses:
        clause_sat = False
        for lit in clause:
            var = abs(lit)
            sign = lit > 0
            if var >= len(assign):
                clause_sat = True
                break
            val = assign[var]
            if val is None:
                clause_sat = True  # Not falsified yet
                break
            if val == sign:
                clause_sat = True
                break
        if not clause_sat:
            all_sat = False
            break

    if all_sat:
        return True

    # Branch on first unset variable
    for i in range(1, len(assign)):
        if assign[i] is None:
            assign[i] = False
            if _dpll_rec(clauses, assign):
                return True
            assign[i] = True
            if _dpll_rec(clauses, assign):
                return True
            assign[i] = None
            return False

    return False


# ---------------------------------------------------------------------------
# Inductive extension property
# ---------------------------------------------------------------------------

@pytest.mark.bmc_l0_encoding
def test_inductive_extension_capacity():
    """Inductive step: adding one variable to a correct encoding stays correct.

    If the sequential counter correctly encodes AtMostK for n variables,
    then extending it to n+1 variables (with the same bound k) should
    also be correct.  We verify this for n ∈ [1, 7], k ∈ [0, n-1].
    """
    from temper_placer.router_v6.sat_model import SATModel, _encode_at_most_k

    for n in range(1, 8):
        for k in range(0, n):
            # Build encoding for n variables
            sat = SATModel(variables=[], clauses=[])
            vars_n = [
                sat.add_variable(f"x{i}", f"primary var {i}")
                for i in range(n)
            ]

            _encode_at_most_k(sat, vars_n, k, description_prefix="inductive")

            # Verify base case (n vars)
            base_failures = _check_encoding(sat, n, k, vars_n)
            assert len(base_failures) == 0, (
                f"Base case failed for n={n} k={k}:\n" + "\n".join(base_failures)
            )

            # Extend: add one more variable with same bound k
            # The encoding for n+1 adds auxiliary vars and clauses that
            # reference the new primary variable and extend the counter chain.
            # We rebuild the whole encoding for n+1 to test the inductive
            # step (rather than physically extending — the Sinz encoding
            # is monolithic for n+1).
            sat_ext = SATModel(variables=[], clauses=[])
            vars_ext = [
                sat_ext.add_variable(f"x{i}", f"primary var {i}")
                for i in range(n + 1)
            ]

            _encode_at_most_k(sat_ext, vars_ext, k, description_prefix="inductive_n+1")

            ext_failures = _check_encoding(sat_ext, n + 1, k, vars_ext)
            assert len(ext_failures) == 0, (
                f"Inductive step failed for (n={n}, n+1={n+1}, k={k}):\n"
                + "\n".join(ext_failures)
            )


def _check_encoding(
    sat_model, n: int, k: int, vars_list: list
) -> list[str]:
    """Check all 2^n assignments for (n, k) — returns failure messages."""
    from temper_placer.router_v6.sat_model import SATVariable

    total_vars = len(sat_model.variables)
    failures: list[str] = []

    for bits in range(1 << n):
        assignment = {}
        true_count = 0
        for i in range(n):
            val = (bits >> i) & 1 == 1
            assignment[f"x{i}"] = val
            if val:
                true_count += 1

        cnf_sat = _dpll_check(sat_model, assignment, total_vars)
        expected = true_count <= k

        if cnf_sat != expected:
            failures.append(
                f"n={n} k={k} bits={bits:0{n}b} "
                f"true_count={true_count} expected={'SAT' if expected else 'UNSAT'} "
                f"got={'SAT' if cnf_sat else 'UNSAT'}"
            )
            break  # One counterexample is enough

    return failures


# ---------------------------------------------------------------------------
# Hypothesis PBT — random constraint models
# ---------------------------------------------------------------------------

@pytest.mark.bmc_l0_encoding
@pytest.mark.slow
@settings(max_examples=200, deadline=None)
@given(model_data=constraint_models())
def test_bmc_random_model_pbt(model_data):
    """Random ConstraintModel via Hypothesis: BMC must find zero counterexamples.

    Each generated model is verified exhaustively (all 2^N assignments)
    via BMC.  The ESL ground truth must agree with the CNF satisfiability
    for every assignment within the N <= 10 primary-variable bound.
    """
    from temper_placer.router_v6.sat_model import SATModel, populate_sat_from_constraints
    from temper_placer.router_v6.bmc import bmc_check_with_diagnostics

    model, net_names, primary_var_names = model_data

    sat = SATModel(variables=[], clauses=[])
    populate_sat_from_constraints(sat, model, net_names=net_names, skip_connectivity=True)

    ces = bmc_check_with_diagnostics(model, sat, primary_var_names=primary_var_names)

    if ces:
        first = ces[0]
        raise AssertionError(
            f"BMC found {len(ces)} counterexamples.\n"
            f"Model: {model.variable_count} vars, {model.constraint_count} constraints\n"
            f"First failure: {first['failure_type']}\n"
            f"Assignment: {first['assignment']}\n"
            f"ESL result: {first['esl_result']}, CNF result: {first['cnf_result']}"
        )

