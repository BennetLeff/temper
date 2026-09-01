"""Stage-3 native model handoff characterization and parity tests."""

from __future__ import annotations

import pytest

try:
    import temper_rust_router as _router
except ImportError:
    _router = None

pytestmark = pytest.mark.skipif(_router is None, reason="temper-rust-router not installed")


def _fixture_model():
    from temper_placer.router_v6.constraint_model import (
        CapacityConstraint,
        ConstraintModel,
        NetChannelVar,
    )

    model = ConstraintModel()
    variables = [
        NetChannelVar(name="uses_N0_CH1", net_idx=0, channel_id="CH1"),
        NetChannelVar(name="uses_N1_CH1", net_idx=1, channel_id="CH1"),
    ]
    for variable in variables:
        model.add_variable(variable)
    model.add_constraint(
        CapacityConstraint(
            name="cap_CH1",
            channel_id="CH1",
            capacity=1.0,
            slack_factor=1.0,
            terms=[(variable, 1.0) for variable in variables],
        )
    )
    return model, ["net0", "net1"]


def test_native_handoff_has_no_getter_round_trip_and_matches_legacy():
    """The production handoff must bypass the object-rebuilding getters."""

    import temper_rust_router as router

    model, net_names = _fixture_model()
    legacy_variables = list(model.variables)
    legacy_constraints = list(model.constraints)
    expected = router.solve_topology_rust(legacy_variables, legacy_constraints, net_names)

    got = model.solve_native(net_names)
    for key in ("status", "assignments", "topology_graph", "num_vars", "num_clauses", "unsat_core", "var_to_net"):
        assert got[key] == expected[key]

    audit_expected = list(
        router.audit_result(
            legacy_variables,
            legacy_constraints,
            dict(expected["assignments"]),
            net_names,
        )
    )
    assert list(model.audit_native(dict(got["assignments"]), net_names)) == audit_expected


def test_batch_production_handoff_never_reads_legacy_getters(monkeypatch):
    """The batching adapter calls native methods even when getters explode."""

    from types import SimpleNamespace

    from temper_placer.router_v6 import net_batching

    expected = {"status": "sat", "assignments": {}}

    class GetterBomb:
        def native_model_supported(self):
            return True

        @property
        def variables(self):
            raise AssertionError("native Stage-3 path accessed .variables")

        @property
        def constraints(self):
            raise AssertionError("native Stage-3 path accessed .constraints")

        def solve_native(self, *_args, **_kwargs):
            return expected

        def audit_native(self, *_args, **_kwargs):
            return []

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def build(self):
            return GetterBomb()

    monkeypatch.setattr(net_batching, "ModelBuilder", Builder)
    net = SimpleNamespace(name="n0")
    _model, result = net_batching._solve_subset(
        skeletons={},
        nets_subset=[net],
        channel_widths={},
        design_rules=None,
        diff_pairs_subset=[],
        pcb=SimpleNamespace(),
        enable_geographic_pruning=False,
        sat_conflict_limit=None,
        sat_time_limit_ms=None,
    )
    assert result == {**expected, "audit_violations": []}


def test_monolith_production_handoff_never_reads_legacy_getters(monkeypatch):
    """The regular Stage-3 route also uses the originating model methods."""

    from types import SimpleNamespace
    from unittest.mock import patch

    from temper_placer.core.netlist import Net
    from temper_placer.router_v6._pipeline_core import RouterV6Pipeline

    class GetterBomb:
        variable_count = 1
        constraint_count = 0

        @property
        def variables(self):
            raise AssertionError("native Stage-3 path accessed .variables")

        @property
        def constraints(self):
            raise AssertionError("native Stage-3 path accessed .constraints")

        def native_model_supported(self):
            return True

        def solve_native(self, *_args, **_kwargs):
            return {
                "status": "unsat",
                "assignments": {},
                "topology_graph": {},
                "num_vars": 1,
                "num_clauses": 0,
                "unsat_core": [],
                "solver_time_ms": 0.0,
                "var_to_net": [],
            }

        def native_clause_origins(self):
            return []

        def audit_native(self, *_args, **_kwargs):
            return []

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def build(self):
            return GetterBomb()

    pipeline = RouterV6Pipeline(verbose=False)
    monkeypatch.setenv("TEMPER_STAGE3_FORCE_SAT", "1")
    pcb = SimpleNamespace(
        nets=[Net(name="n0", pins=[])],
        source_path=None,
        design_rules=None,
        components=[],
    )
    stage2 = SimpleNamespace(skeletons={}, channel_widths={})
    with patch("temper_placer.router_v6._pipeline_route.ModelBuilder", Builder):
        output = pipeline._run_stage3(pcb, stage2)
    assert output.solution is not None
    assert output.solution.status.value == "unsat"
