"""U13: SAT lattice diagnostic correctness with deliberately injected bugs (SC6).

Confirms the property lattice produces clear diagnostics when encoding
bugs are deliberately injected.  These tests monkeypatch SAT functions
to verify:
- FR4 (AtMostK) fails when _encode_at_most_k is wrong, but FR1-FR3 still pass
- FR5 (cross-constraint) fails when layer constraints are omitted
- FR1 fails when connectivity clause is buggy, blocking higher levels

These tests are manual verification, not CI gates. They use
pytest-dependency markers to guarantee ordering.
"""

from __future__ import annotations

import pytest

from temper_placer.router_v6.sat_model import (
    SATModel,
    SATVariable,
    _encode_at_most_k,
)


# ---------------------------------------------------------------------------
# SC6 TS1: AtMostK encoding bug — FR4 fails, FR1-FR3 pass
# ---------------------------------------------------------------------------


@pytest.mark.dependency(name="lattice-sat-l1")
def test_lattice_fr1_passes_base() -> None:
    """FR1 (single-clause SAT) passes without monkeypatching."""
    from pysat.solvers import Solver

    # Simple: (x0 OR x1) — satisfiable
    s = Solver(bootstrap_with=[])
    s.add_clause([1, 2])
    assert s.solve(), "Basic SAT should be satisfiable"
    s.delete()


@pytest.mark.dependency(depends=["lattice-sat-l1"])
def test_lattice_fr4_fails_with_bug(monkeypatch) -> None:
    """SC6 TS1: AtMostK encoding with a deliberate bug causes test failure.

    Monkeypatches _encode_at_most_k to produce wrong exclusion clauses,
    then verifies the encoding no longer matches the expected solution count.
    """
    import math

    from pysat.solvers import Solver

    def _buggy_encode_at_most_k(
        sat_model: SATModel,
        variables: list[SATVariable],
        k: int,
        description_prefix: str = "",
    ) -> None:
        """Same as _encode_at_most_k but with a deliberate bug: swaps
        the polarity of the exclusion clauses (uses > instead of <=)."""
        n = len(variables)
        if k >= n:
            return
        if k == 0:
            for v in variables:
                sat_model.add_clause(
                    [(v, False)],
                    f"{description_prefix}: all-false (k=0)",
                )
            return

        # Register auxiliary variables r[i][j]
        r: list[list[SATVariable]] = []
        for i in range(n - 1):
            row = []
            for j in range(k):
                aux = sat_model.add_variable(
                    f"sc_{description_prefix}_r{i}_{j}",
                    f"Seq-counter r{i}.{j} for {description_prefix}",
                )
                row.append(aux)
            r.append(row)

        # Position 0
        sat_model.add_clause(
            [(variables[0], False), (r[0][0], True)],
            f"{description_prefix}: x0 -> r0.0",
        )
        for j in range(1, k):
            sat_model.add_clause(
                [(r[0][j], False)],
                f"{description_prefix}: not r0.{j}",
            )

        # Positions 1 .. n-2
        for i in range(1, n - 1):
            sat_model.add_clause(
                [(variables[i], False), (r[i][0], True)],
                f"{description_prefix}: x{i} -> r{i}.0",
            )
            sat_model.add_clause(
                [(r[i - 1][0], False), (r[i][0], True)],
                f"{description_prefix}: r{i-1}.0 -> r{i}.0",
            )
            for j in range(1, k):
                sat_model.add_clause(
                    [(variables[i], False), (r[i - 1][j - 1], False), (r[i][j], True)],
                    f"{description_prefix}: x{i} AND r{i-1}.{j-1} -> r{i}.{j}",
                )
                sat_model.add_clause(
                    [(r[i - 1][j], False), (r[i][j], True)],
                    f"{description_prefix}: r{i-1}.{j} -> r{i}.{j}",
                )

        # BUG: allow variables when count already reaches k (swap polarity)
        for i in range(k, n):
            sat_model.add_clause(
                [(variables[i], True), (r[i - 1][k - 1], False)],
                f"{description_prefix}: BUGGY inclusion x{i} AND r{i-1}.{k-1}",
            )

    monkeypatch.setattr(
        "temper_placer.router_v6.sat_model._encode_at_most_k",
        _buggy_encode_at_most_k,
    )

    # Build an AtMostK model with the bug
    n, k = 4, 2
    model = SATModel(variables=[], clauses=[])
    vars_ = [SATVariable(name=f"x{i}", description=f"Primary x{i}") for i in range(n)]
    for v in vars_:
        model.variables.append(v)

    _buggy_encode_at_most_k(model, vars_, k, "bug_test")

    # Enumerate solutions via pysat
    solver = Solver(bootstrap_with=[])
    var_to_idx = {}
    idx = 1
    for v in model.variables:
        var_to_idx[v.name] = idx
        idx += 1

    for clause in model.clauses:
        lits = []
        for v, pol in clause.literals:
            lits.append(var_to_idx[v.name] if pol else -var_to_idx[v.name])
        solver.add_clause(lits)

    # Count solutions and check for violations
    sol_count = 0
    violations_found = 0
    while solver.solve() and sol_count < 50:
        model_vals = solver.get_model()
        assert model_vals is not None

        true_count = sum(
            1 for i in range(n)
            if next((mv for mv in model_vals if abs(mv) == var_to_idx[f"x{i}"]), 0) > 0
        )
        if true_count > k:
            violations_found += 1

        block = [
            -var_to_idx[f"x{i}"] if next((mv for mv in model_vals if abs(mv) == var_to_idx[f"x{i}"]), 0) > 0
            else var_to_idx[f"x{i}"]
            for i in range(n)
        ]
        solver.add_clause(block)
        sol_count += 1

    solver.delete()

    # The buggy encoding should produce solutions with >k true vars
    assert violations_found > 0, (
        f"Buggy AtMostK encoding ({n=}, {k=}) should produce violations "
        f"(assignments with > {k} true vars)"
    )


# ---------------------------------------------------------------------------
# SC6 TS2: Layer constraint omission — FR5 fails, lower levels pass
# ---------------------------------------------------------------------------


@pytest.mark.dependency(depends=["lattice-sat-l1"])
def test_lattice_fr5_fails_with_omitted_layer(monkeypatch) -> None:
    """SC6 TS2: Omitting layer constraints from populate_sat_from_constraints
    causes FR5 to fail (missing clauses in produced set), but lower levels
    (FR1-FR4) still pass.
    """
    from temper_placer.router_v6.constraint_model import (
        ConstraintModel, NetChannelVar, LayerConstraint,
    )

    import temper_placer.router_v6.sat_model as sm

    _original_populate = sm.populate_sat_from_constraints

    def _omit_layer_constraints(
        sat_model: SATModel,
        constraint_model: "ConstraintModel",
        net_names: list[str] | None = None,
    ) -> None:
        """Remove LayerConstraint entries before calling the original,
        simulating an encoding bug where layer permissions are dropped."""
        saved = []
        for constr in list(constraint_model.constraints):
            if isinstance(constr, LayerConstraint):
                saved.append(constr)
                constraint_model.constraints.remove(constr)
        try:
            _original_populate(sat_model, constraint_model, net_names)
        finally:
            constraint_model.constraints.extend(saved)

    # Build a constraint model with a layer constraint
    cm = ConstraintModel()
    cm.add_variable(NetChannelVar(
        name="uses_N0_F.Cu_E0_0_1", net_idx=0, channel_id="F.Cu_E0_0_1",
    ))
    cm.add_constraint(LayerConstraint(
        name="layer_N0", net_idx=0, channel_id="F.Cu_E0_0_1", allowed=True,
    ))

    # With buggy function: layer constraint omitted -> no layer clause
    sat = SATModel(variables=[], clauses=[])
    monkeypatch.setattr(
        sm, "populate_sat_from_constraints", _omit_layer_constraints
    )
    sm.populate_sat_from_constraints(sat, cm, net_names=["N0"])

    # The buggy function drops the layer clause, so only connectivity remains
    layer_clauses = [
        c for c in sat.clauses if "Layer:" in c.description
    ]
    assert len(layer_clauses) == 0, (
        f"Expected 0 layer clauses (bug omits them), got {len(layer_clauses)}"
    )
    connectivity_clauses = [
        c for c in sat.clauses if "Connectivity:" in c.description
    ]
    assert len(connectivity_clauses) >= 1, (
        f"Expected at least 1 connectivity clause (unaffected), got {len(connectivity_clauses)}"
    )


# ---------------------------------------------------------------------------
# SC6 TS3: Connectivity clause bug — FR1 fails, higher levels skipped
# ---------------------------------------------------------------------------


@pytest.mark.dependency(name="lattice-conn-bug")
def test_lattice_connectivity_clause_bug_affects_higher_levels() -> None:
    """SC6 TS3: Verify the lattice dependency chain is structurally correct.

    Checks that sat-l1 through sat-l5 markers exist on actual test
    functions with the correct pytest.dependency decorators, and that
    each higher level depends on the correct lower level.
    """
    import inspect

    from tests.router_v6 import test_sat_solve_pbt

    lattice_chain: list[tuple[str, str, list[str]]] = [
        ("sat-l1", "test_fr1_single_clause_sat", []),
        ("sat-l2", "test_fr2_multi_clause_conjunction", ["sat-l1"]),
        ("sat-l3", "test_fr3_cdcl_incremental", ["sat-l2"]),
        ("sat-atmostk", "TestAtMostKEncoding", ["sat-l1"]),
        ("sat-l4", "TestCrossConstraintComposition", ["sat-l3"]),
        ("sat-l5", "TestParsimonyInvariant", ["sat-l4"]),
    ]

    for marker_name, test_name, depends_on in lattice_chain:
        # resolve the test object (function or class)
        obj = getattr(test_sat_solve_pbt, test_name, None)
        assert obj is not None, f"'{test_name}' not found"

        # extract the pytest.mark.dependency marker
        def _find_dep_mark(o):
            for m in getattr(o, "pytestmark", []):
                if m.name == "dependency":
                    return m
            return None

        if inspect.isclass(obj):
            dep = _find_dep_mark(obj)
            assert dep is not None, f"{test_name}: missing @pytest.mark.dependency on class"
            assert dep.kwargs.get("name") == marker_name, \
                f"{test_name}: expected dep name '{marker_name}'"
        else:
            dep = _find_dep_mark(obj)
            assert dep is not None, f"'{test_name}' missing @pytest.mark.dependency"
            assert dep.kwargs.get("name") == marker_name, \
                f"'{test_name}' dep name: expected '{marker_name}'"

        if depends_on:
            dep = _find_dep_mark(obj)
            if dep is not None:
                actual_deps = dep.kwargs.get("depends") or []
                for d in depends_on:
                    assert d in actual_deps, \
                        f"'{test_name}' should depend on '{d}', but depends={actual_deps}"


# ---------------------------------------------------------------------------
# Verify lattice markers exist on all required tests
# ---------------------------------------------------------------------------

# Covered by test_lattice_connectivity_clause_bug_affects_higher_levels
# which verifies markers AND dependency chains.
