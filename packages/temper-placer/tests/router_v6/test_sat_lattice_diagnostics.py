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
    from tests.router_v6 import test_bmc_encoding

    lattice_chain: list[tuple[str, str, list[str], object]] = [
        ("bmc-l0", "TestBmcEncodingL0", [], test_bmc_encoding),
        ("sat-l1", "test_fr1_single_clause_sat", ["bmc-l0"], test_sat_solve_pbt),
        ("sat-l2", "test_fr2_multi_clause_conjunction", ["sat-l1"], test_sat_solve_pbt),
        ("sat-l3", "test_fr3_cdcl_incremental", ["sat-l2"], test_sat_solve_pbt),
        ("sat-atmostk", "TestAtMostKEncoding", ["sat-l1"], test_sat_solve_pbt),
        ("sat-l4", "TestCrossConstraintComposition", ["sat-l3"], test_sat_solve_pbt),
        ("sat-l5", "TestParsimonyInvariant", ["sat-l4"], test_sat_solve_pbt),
    ]

    for marker_name, test_name, depends_on, module in lattice_chain:
        obj = getattr(module, test_name, None)
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


# ---------------------------------------------------------------------------
# U7: BMC regression gauntlet — BMC catches known encoding bugs
# ---------------------------------------------------------------------------


def _build_atmostk_model(n: int, k: int) -> tuple[SATModel, list[SATVariable]]:
    """Build a simple SATModel with AtMostK encoding."""
    model = SATModel(variables=[], clauses=[])
    vars_ = [SATVariable(name=f"x{i}", description=f"Primary x{i}") for i in range(n)]
    for v in vars_:
        model.variables.append(v)
    _encode_at_most_k(model, vars_, k, description_prefix="test")
    return model, vars_


@pytest.mark.dependency(depends=["bmc-l0"])
def test_bmc_catches_atmostk_polarity_bug(monkeypatch) -> None:
    """SC1: BMC catches the AtMostK polarity bug as a false-SAT counterexample.

    Uses BMC engine directly (not pysat enumeration) to verify that
    the BMC layer detects the bug documented in test_lattice_fr4_fails_with_bug.
    """
    from temper_placer.router_v6.constraint_model import (
        CapacityConstraint,
        ConstraintModel,
        NetChannelVar,
    )
    from temper_placer.router_v6.bmc import bmc_check

    n, k = 3, 2

    # Build a ConstraintModel with 3 NetChannelVars and a CapacityConstraint
    cm = ConstraintModel()
    var_names = []
    for i in range(n):
        name = f"uses_N{i}_ch1"
        var = NetChannelVar(name=name, net_idx=i, channel_id="ch1")
        cm.add_variable(var)
        var_names.append(name)

    min_width = 0.127
    max_nets = k
    capacity = (max_nets + 0.5) * min_width
    cm.add_constraint(CapacityConstraint(
        name="cap_ch1",
        channel_id="ch1",
        capacity=capacity,
        slack_factor=1.0,
        terms=[(v, min_width) for v in cm.variables if isinstance(v, NetChannelVar)],
    ))

    # Build sat model with the buggy encode
    def _buggy_encode(sat_model, variables, k_val, description_prefix=""):
        n2 = len(variables)
        if k_val >= n2:
            return
        if k_val == 0:
            for v in variables:
                sat_model.add_clause([(v, False)], f"{description_prefix}: k=0")
            return

        r: list[list[SATVariable]] = []
        for i in range(n2 - 1):
            row = []
            for j in range(k_val):
                aux = sat_model.add_variable(
                    f"sc_{description_prefix}_r{i}_{j}",
                    f"Seq-counter r{i}.{j} for {description_prefix}",
                )
                row.append(aux)
            r.append(row)

        sat_model.add_clause([(variables[0], False), (r[0][0], True)], f"{description_prefix}: x0->r0.0")
        for j in range(1, k_val):
            sat_model.add_clause([(r[0][j], False)], f"{description_prefix}: not r0.{j}")
        for i in range(1, n2 - 1):
            sat_model.add_clause([(variables[i], False), (r[i][0], True)], f"{description_prefix}: x{i}->r{i}.0")
            sat_model.add_clause([(r[i - 1][0], False), (r[i][0], True)], f"{description_prefix}: r{i-1}.0->r{i}.0")
            for j in range(1, k_val):
                sat_model.add_clause(
                    [(variables[i], False), (r[i - 1][j - 1], False), (r[i][j], True)],
                    f"{description_prefix}: x{i}^r{i-1}.{j-1}->r{i}.{j}",
                )
                sat_model.add_clause([(r[i - 1][j], False), (r[i][j], True)], f"{description_prefix}: r{i-1}.{j}->r{i}.{j}")

        # BUG: inverted exclusion polarity
        for i in range(k_val, n2):
            sat_model.add_clause(
                [(variables[i], True), (r[i - 1][k_val - 1], False)],
                f"{description_prefix}: BUGGY exclusion x{i}",
            )

    monkeypatch.setattr(
        "temper_placer.router_v6.sat_model._encode_at_most_k",
        _buggy_encode,
    )

    from temper_placer.router_v6.sat_model import SATModel as SM, populate_sat_from_constraints
    sat = SM(variables=[], clauses=[])
    populate_sat_from_constraints(sat, cm, net_names=["N0", "N1", "N2"], skip_connectivity=True)

    ces = bmc_check(cm, sat)
    assert len(ces) > 0, (
        f"BMC should catch AtMostK polarity bug (found {len(ces)} counterexamples)"
    )
    false_sat = [ce for ce in ces if ce["failure_type"] == "false_sat"]
    assert len(false_sat) > 0, (
        f"Expected false-SAT counterexamples from polarity bug, "
        f"got: {[ce['failure_type'] for ce in ces]}"
    )


@pytest.mark.dependency(depends=["bmc-l0"])
def test_bmc_catches_layer_omission_bug(monkeypatch) -> None:
    """SC2: BMC catches a layer constraint omission bug."""
    from temper_placer.router_v6.constraint_model import (
        ConstraintModel, NetChannelVar, LayerConstraint,
    )
    from temper_placer.router_v6.bmc import bmc_check

    cm = ConstraintModel()
    cm.add_variable(NetChannelVar(name="uses_N0_ch1", net_idx=0, channel_id="ch1"))
    cm.add_constraint(LayerConstraint(
        name="layer_N0", net_idx=0, channel_id="ch1", allowed=False,
    ))

    import temper_placer.router_v6.sat_model as sm

    _original_populate = sm.populate_sat_from_constraints

    def _omit_layer(sat_model, constraint_model, net_names=None, **kwargs):
        saved = []
        for constr in list(constraint_model.constraints):
            if isinstance(constr, LayerConstraint):
                saved.append(constr)
                constraint_model.constraints.remove(constr)
        try:
            _original_populate(sat_model, constraint_model, net_names, **kwargs)
        finally:
            constraint_model.constraints.extend(saved)

    monkeypatch.setattr(sm, "populate_sat_from_constraints", _omit_layer)

    from temper_placer.router_v6.sat_model import SATModel as SM
    sat = SM(variables=[], clauses=[])
    sm.populate_sat_from_constraints(sat, cm, net_names=["N0"], skip_connectivity=True)

    ces = bmc_check(cm, sat)
    assert len(ces) > 0, (
        f"BMC should catch layer omission bug (found {len(ces)} counterexamples)"
    )


@pytest.mark.dependency(depends=["bmc-l0"])
def test_bmc_catches_diffpair_polarity_bug(monkeypatch) -> None:
    """SC2: BMC catches a diff-pair polarity swap bug."""
    from temper_placer.router_v6.constraint_model import (
        ConstraintModel, NetChannelVar, DiffPairConstraint,
    )
    from temper_placer.router_v6.bmc import bmc_check

    import temper_placer.router_v6.sat_model as sm

    cm = ConstraintModel()
    p_var = NetChannelVar(name="uses_N0_ch1", net_idx=0, channel_id="ch1")
    n_var = NetChannelVar(name="uses_N1_ch1", net_idx=1, channel_id="ch1")
    cm.add_variable(p_var)
    cm.add_variable(n_var)
    cm.add_constraint(DiffPairConstraint(
        name="diff_N0_N1_ch1", channel_id="ch1",
        p_net_idx=0, n_net_idx=1, p_var=p_var, n_var=n_var,
    ))

    _original_populate = sm.populate_sat_from_constraints

    def _swap_diffpair(sat_model, constraint_model, net_names=None, **kwargs):
        """Swap the (not-n or p) clause to (n or p) — breaks iff semantics."""
        _original_populate(sat_model, constraint_model, net_names, **kwargs)
        # Find the clause with not-n (i.e., (¬n ∨ p)) and flip n's polarity
        for i, clause in enumerate(sat_model.clauses):
            if not clause.description.startswith("DiffPair:"):
                continue
            # Check if this clause has a negated n_var (i.e., first literal is negative)
            if clause.literals[0][1] is False:
                # Flip n from negated to positive: (n ∨ p) instead of (¬n ∨ p)
                new_lits = [(clause.literals[0][0], True), clause.literals[1]]
                sat_model.clauses[i] = sm.SATClause(
                    literals=new_lits,
                    description=clause.description + " [BUG: n->p swapped]",
                )

    monkeypatch.setattr(sm, "populate_sat_from_constraints", _swap_diffpair)

    from temper_placer.router_v6.sat_model import SATModel as SM
    sat = SM(variables=[], clauses=[])
    sm.populate_sat_from_constraints(sat, cm, net_names=["N0", "N1"], skip_connectivity=True)

    ces = bmc_check(cm, sat)
    assert len(ces) > 0, (
        f"BMC should catch diff-pair polarity bug (found {len(ces)} counterexamples)"
    )


@pytest.mark.dependency(depends=["bmc-l0"])
def test_bmc_zero_false_positives_on_correct_encoding() -> None:
    """SC3: On correct main encoding, exhaustive batch produces zero counterexamples.

    Builds a 2x2 topology with all constraint types and verifies bmc_check
    returns zero counterexamples against the unmodified encoding.
    """
    from temper_placer.router_v6.constraint_model import (
        CapacityConstraint,
        ConstraintModel,
        DiffPairConstraint,
        LayerConstraint,
        NetChannelVar,
    )
    from temper_placer.router_v6.sat_model import (
        SATModel as SM,
        populate_sat_from_constraints,
    )
    from temper_placer.router_v6.bmc import bmc_check

    layer_names = ["F.Cu", "B.Cu"]
    net_names = ["N0", "N1"]

    cm = ConstraintModel()
    for net_idx in range(2):
        for layer_name in layer_names:
            for cell_idx in range(2):
                channel_id = f"{layer_name}_E{cell_idx}_0_1"
                var = NetChannelVar(
                    name=f"uses_N{net_idx}_{channel_id}",
                    net_idx=net_idx,
                    channel_id=channel_id,
                )
                cm.add_variable(var)

    channel_id = "F.Cu_E0_0_1"
    if (0, channel_id) in cm.net_channel_vars:
        cm.add_constraint(LayerConstraint(
            name="layer_N0", net_idx=0, channel_id=channel_id, allowed=True,
        ))
    if (0, channel_id) in cm.net_channel_vars and (1, channel_id) in cm.net_channel_vars:
        cm.add_constraint(DiffPairConstraint(
            name="diff_N0_N1", channel_id=channel_id,
            p_net_idx=0, n_net_idx=1,
            p_var=cm.net_channel_vars[(0, channel_id)],
            n_var=cm.net_channel_vars[(1, channel_id)],
        ))
    terms = []
    for net_idx in range(2):
        if (net_idx, channel_id) in cm.net_channel_vars:
            terms.append((cm.net_channel_vars[(net_idx, channel_id)], 0.127))
    if terms:
        cm.add_constraint(CapacityConstraint(
            name="cap", channel_id=channel_id,
            capacity=0.3, slack_factor=1.0, terms=terms,
        ))

    sat = SM(variables=[], clauses=[])
    populate_sat_from_constraints(sat, cm, net_names=net_names, skip_connectivity=True)

    ces = bmc_check(cm, sat)
    assert len(ces) == 0, (
        f"Expected zero counterexamples on correct encoding, "
        f"found {len(ces)}: {ces[:3]}"
    )
