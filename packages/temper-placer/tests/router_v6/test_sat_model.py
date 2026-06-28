"""
Tests for Router V6 Stage 3.7: Build SAT Model

Part of temper-5eh3
"""

import pytest

from temper_placer.router_v6.sat_model import (
    SATClause,
    SATModel,
    SATVariable,
    _encode_at_most_k,
    add_capacity_to_sat,
    add_connectivity_to_sat,
    build_sat_model,
)
from temper_placer.router_v6.topology_solver import _check_assignment, solve_topology


def test_build_sat_model_empty():
    """Test building empty SAT model."""
    model = build_sat_model()

    assert model.variable_count == 0
    assert model.clause_count == 0


def test_add_variable():
    """Test adding variables to SAT model."""
    model = build_sat_model()
    
    var = model.add_variable("test_var", "Test variable")

    assert model.variable_count == 1
    assert var.name == "test_var"
    assert var.description == "Test variable"


def test_add_clause():
    """Test adding clauses to SAT model."""
    model = build_sat_model()
    
    var1 = model.add_variable("v1", "Variable 1")
    var2 = model.add_variable("v2", "Variable 2")
    
    model.add_clause([(var1, True), (var2, False)], "Test clause")

    assert model.clause_count == 1
    clause = model.clauses[0]
    assert len(clause.literals) == 2


def test_add_connectivity_to_sat():
    """Test adding connectivity constraints."""
    model = build_sat_model()
    
    add_connectivity_to_sat(model, "NET1", "A", "B")

    assert model.variable_count == 1
    assert model.clause_count == 1
    
    # Variable should represent the path
    var = model.variables[0]
    assert "route_NET1" in var.name


def test_add_capacity_to_sat():
    """Test adding capacity constraints."""
    model = build_sat_model()
    
    add_capacity_to_sat(model, "CH1", 2, ["NET1", "NET2", "NET3"])

    # Should create variables for each net
    assert model.variable_count == 3
    
    # Should add capacity constraint
    assert model.clause_count > 0


def test_sat_variable_str():
    """Test SATVariable string representation."""
    var = SATVariable("test", "Test variable")
    
    assert str(var) == "test"


def test_sat_clause_str():
    """Test SATClause string representation."""
    var1 = SATVariable("v1", "Variable 1")
    var2 = SATVariable("v2", "Variable 2")
    
    clause = SATClause([(var1, True), (var2, False)], "Test")
    
    # Should show positive and negated literals
    clause_str = str(clause)
    assert "v1" in clause_str
    assert "¬v2" in clause_str or "~v2" in clause_str


def test_sat_model_dataclass():
    """Test SATModel dataclass properties."""
    model = SATModel(variables=[], clauses=[])
    
    var1 = model.add_variable("v1", "Variable 1")
    var2 = model.add_variable("v2", "Variable 2")
    
    model.add_clause([(var1, True)], "Clause 1")
    model.add_clause([(var2, False)], "Clause 2")

    assert model.variable_count == 2
    assert model.clause_count == 2


class TestAtMostKEncoding:
    """Validate the Sinz sequential-counter AtMostK encoding."""

    @staticmethod
    def _solve(model: SATModel) -> dict[str, bool] | None:
        """Exhaustive search over all 2^N assignments to find a satisfying one."""
        from itertools import product

        names = [v.name for v in model.variables]
        for bits in product([False, True], repeat=len(names)):
            assignment = dict(zip(names, bits))
            if _check_assignment(model, assignment):
                return assignment
        return None

    def test_k0_all_false(self):
        """AtMostK(k=0) forces all variables false."""
        model = build_sat_model()
        v = [model.add_variable(f"v{i}", f"var {i}") for i in range(3)]
        _encode_at_most_k(model, v, 0, "test")

        sol = self._solve(model)
        assert sol is not None
        assert sum(sol[vi.name] for vi in v) == 0

    def test_k_geq_n_trivial(self):
        """AtMostK(k >= n) adds no clauses (trivially satisfiable)."""
        model = build_sat_model()
        v = [model.add_variable(f"v{i}", f"var {i}") for i in range(2)]
        _encode_at_most_k(model, v, 5, "test")

        assert model.clause_count == 0  # No encoding needed

    def test_k1_pairwise(self):
        """AtMostK(k=1) via sequential counter ≡ pairwise exclusion."""
        model = build_sat_model()
        v = [model.add_variable(f"v{i}", f"var {i}") for i in range(4)]
        _encode_at_most_k(model, v, 1, "test")

        sol = self._solve(model)
        assert sol is not None
        assert sum(sol[vi.name] for vi in v) <= 1

    def test_4vars_k2_capacity_enforced(self):
        """4 nets, capacity 2 — at most 2 may be true. The existing
        Python solver previously allowed up to 6 on a 3-net channel;
        this test replicates the AE1 scenario directly."""
        model = build_sat_model()
        v = [model.add_variable(f"uses_net{i}_ch1", f"net {i}") for i in range(4)]
        _encode_at_most_k(model, v, 2, "cap_ch1")

        sol = self._solve(model)
        assert sol is not None
        true_count = sum(sol[vi.name] for vi in v)
        assert true_count <= 2, (
            f"AtMostK(4 vars, k=2) allowed {true_count} true vars;"
            f" expected at most 2"
        )

        # Verify that an assignment with 3 true variables is UNSAT
        model2 = build_sat_model()
        v2 = [model2.add_variable(f"uses_net{i}_ch1", f"net {i}") for i in range(4)]
        _encode_at_most_k(model2, v2, 2, "cap_ch1")
        # Force 3 vars true
        for vi in v2[:3]:
            model2.add_clause([(vi, True)], "force_true")
        sol2 = self._solve(model2)
        assert sol2 is None, (
            "AtMostK(4 vars, k=2) was SAT when 3 vars were forced true"
        )

    def test_6vars_k6_at_capacity(self):
        """6 nets, capacity 6 — all 6 can be true."""
        model = build_sat_model()
        v = [model.add_variable(f"v{i}", f"var {i}") for i in range(6)]
        _encode_at_most_k(model, v, 6, "test")
        assert model.clause_count == 0  # k >= n, trivial

    def test_single_var_k0(self):
        """1 variable, k=0 — must be false."""
        model = build_sat_model()
        v = [model.add_variable("v0", "var 0")]
        _encode_at_most_k(model, v, 0, "test")

        sol = self._solve(model)
        assert sol is not None
        assert sol["v0"] is False

    def test_single_var_k1(self):
        """1 variable, k=1 — trivially satisfiable."""
        model = build_sat_model()
        v = [model.add_variable("v0", "var 0")]
        clauses_before = model.clause_count
        _encode_at_most_k(model, v, 1, "test")
        assert model.clause_count == clauses_before  # No clauses added

    def test_10vars_k3_unsat_overflow(self):
        """10 nets, capacity 3 — force 4 true must be UNSAT.
        The original unsound encoding allowed up to 7 on this case.
        Exhaustive search over 2^N is infeasible with aux vars, so we
        only validate the UNSAT direction (forced overflow) and use
        the greedy solver to verify a satisfiable assignment exists."""
        from temper_placer.router_v6.topology_solver import solve_topology

        # Force 4 vars true — must be UNSAT
        model = build_sat_model()
        v = [model.add_variable(f"v{i}", f"var {i}") for i in range(10)]
        _encode_at_most_k(model, v, 3, "test")
        for vi in v[:4]:
            model.add_clause([(vi, True)], "force")
        sol = solve_topology(model, timeout_ms=10000)
        assert not sol.is_satisfiable, (
            f"Forced 4 true on k=3 but solver returned {sol.status}"
        )

        # Without force clauses, a SAT assignment must exist
        model2 = build_sat_model()
        v2 = [model2.add_variable(f"v{i}", f"var {i}") for i in range(10)]
        _encode_at_most_k(model2, v2, 3, "test")
        sol2 = solve_topology(model2, timeout_ms=10000)
        assert sol2.is_satisfiable
        true_count = sum(sol2.assignment.get(vi.name, False) for vi in v2)
        assert true_count <= 3, f"Allowed {true_count}, expected at most 3"

    def test_0vars_noop(self):
        """Empty variable list is a no-op."""
        model = build_sat_model()
        _encode_at_most_k(model, [], 3, "test")
        assert model.clause_count == 0
