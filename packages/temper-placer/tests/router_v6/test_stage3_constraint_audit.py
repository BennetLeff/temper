"""Constraint audit tests for Stage 3 — validate solver output directly against
the constraint model, not against Python-generated golden fixtures.

These tests require a CDCL-capable solver (the Rust backend with splr).
The Python greedy solver cannot propagate the sequential-counter encoding
that makes AtMostK constraints correct — it does round-robin assignment
with no clause learning or watched literals.

Tests that exercise the sequential counter directly (without requiring
CDCL) live in test_sat_model.py and validate via exhaustive search.

Origin: U2 (replaced) of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
"""

import os
import sys

import pytest

# All tests in this file require the Rust backend for CDCL solving.
pytestmark = pytest.mark.skipif(
    os.environ.get("TEMPER_SAT_BACKEND") != "rust",
    reason="Requires CDCL solver (TEMPER_SAT_BACKEND=rust and temper-rust-router installed). "
           "The Python greedy solver cannot correctly handle sequential-counter AtMostK encoding.",
)

_HAS_RUST = False
try:
    import temper_rust_router  # noqa: F401
    _HAS_RUST = True
except ImportError:
    pass


def _requires_rust(f):
    """Decorator: skip test if the Rust crate is not importable."""
    return pytest.mark.skipif(not _HAS_RUST, reason="temper-rust-router not installed")(f)


class TestCapacityAudit:
    """Validate capacity enforcement — requires CDCL solver."""

    @_requires_rust
    def test_audit_api_imports(self):
        """The audit_result function is importable from the Rust crate."""
        from temper_rust_router import audit_result
        assert callable(audit_result)

    @_requires_rust
    def test_empty_model_clean(self):
        """Audit on an empty model returns zero violations."""
        from temper_rust_router import audit_result
        violations = audit_result([], [], {}, [])
        assert len(violations) == 0

    @_requires_rust
    def test_4_nets_k2_rust_solver_clean(self):
        """4 nets sharing CH1, capacity 2 — Rust solver produces clean output."""
        from temper_rust_router import solve_topology_rust, audit_result
        from temper_placer.router_v6.constraint_model import (
            CapacityConstraint,
            ConstraintModel,
            NetChannelVar,
        )

        cm = ConstraintModel()
        vars_ = []
        for i in range(4):
            v = NetChannelVar(name=f"uses_net{i}_CH1", net_idx=i, channel_id="CH1")
            cm.add_variable(v)
            vars_.append(v)
        cm.add_constraint(CapacityConstraint(
            name="cap_CH1", channel_id="CH1", capacity=2.0, slack_factor=1.0,
            terms=[(v, 1.0) for v in vars_],
        ))

        py_vars = list(cm.variables)
        py_cons = list(cm.constraints)
        net_names = [f"net{i}" for i in range(4)]

        result = solve_topology_rust(py_vars, py_cons, net_names)
        assert result["status"] == "sat"

        violations = audit_result(py_vars, py_cons, dict(result["assignments"]), net_names)
        assert len(violations) == 0, f"Audit violations: {violations}"


class TestDiffPairAudit:
    """Validate diff-pair enforcement — requires CDCL solver."""

    @_requires_rust
    def test_diff_pair_rust_solver_clean(self):
        """Diff pair must have matching truth values."""
        from temper_rust_router import solve_topology_rust, audit_result
        from temper_placer.router_v6.constraint_model import (
            ConstraintModel,
            DiffPairConstraint,
            NetChannelVar,
        )

        cm = ConstraintModel()
        p_var = NetChannelVar(name="uses_net0_CH1", net_idx=0, channel_id="CH1")
        n_var = NetChannelVar(name="uses_net1_CH1", net_idx=1, channel_id="CH1")
        cm.add_variable(p_var)
        cm.add_variable(n_var)
        cm.add_constraint(DiffPairConstraint(
            name="diff_CH1", channel_id="CH1",
            p_net_idx=0, n_net_idx=1, p_var=p_var, n_var=n_var,
        ))

        py_vars = list(cm.variables)
        py_cons = list(cm.constraints)
        result = solve_topology_rust(py_vars, py_cons, ["net0", "net1"])
        assert result["status"] == "sat"

        violations = audit_result(py_vars, py_cons, dict(result["assignments"]), ["net0", "net1"])
        assert len(violations) == 0, f"Audit violations: {violations}"


class TestLayerAudit:
    """Validate layer-restriction enforcement — requires CDCL solver."""

    @_requires_rust
    def test_layer_restriction_rust_solver(self):
        """Net restricted to false on a channel must be false."""
        from temper_rust_router import solve_topology_rust, audit_result
        from temper_placer.router_v6.constraint_model import (
            ConstraintModel,
            LayerConstraint,
            NetChannelVar,
        )

        cm = ConstraintModel()
        v = NetChannelVar(name="uses_N0_CH1", net_idx=0, channel_id="CH1")
        cm.add_variable(v)
        cm.add_constraint(LayerConstraint(
            name="restr", net_idx=0, channel_id="CH1", allowed=False,
        ))

        py_vars = list(cm.variables)
        py_cons = list(cm.constraints)
        result = solve_topology_rust(py_vars, py_cons, ["net0"])
        # This should be SAT (the var is forced false, which is satisfiable
        # even though the connectivity clause for net0 requires at least one
        # true var — but net0 only has one var and it's forced false, so it
        # should be UNSAT).
        # Actually: the Rust solver doesn't add connectivity clauses
        # automatically (those are added by populate_sat_from_constraints).
        # The Rust solver only encodes the constraints given. So this should
        # be SAT with v=False.
        assert result["status"] == "sat"

        violations = audit_result(py_vars, py_cons, dict(result["assignments"]), ["net0"])
        assert len(violations) == 0
