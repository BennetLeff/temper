"""Proves the Stage-3 constraint audit actually runs on the net-batching
production path -- not merely that ``audit_result`` is importable and
correct when called directly (that is already covered by
``test_stage3_constraint_audit.py``).

Origin: docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md, R3/R4.
Closes a documented-but-false correctness claim
(``docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md``:
"Constraint audit (`audit.rs`) runs unconditionally after every Rust
solve") -- true only of the monolithic ``_pipeline_route.py`` path;
``net_batching.py`` (the ``--net-batching`` production path, the one the
real 168-footprint board actually routes through -- see
``docs/evidence/2026-08-12-board-recipe-reproducibility.md``) never called
``audit_result`` at all before this file's corresponding fix in
``net_batching.py``.

**Why these tests don't (and can't cheaply) reproduce a genuine SAT-level
violation.** The Rust CNF encoder's own `AtMostK` guard
(``encoding.rs``'s ``max_nets < var_indices.len()`` check) is locally
sound for any *single* capacity constraint considered on its own: it only
skips encoding when there structurally cannot be more true variables than
the constraint allows. Manufacturing a genuine "solver says sat but
capacity is violated" case would require a real solver bug, not a test
fixture. What these tests verify instead -- and what the false claim this
file closes was actually about -- is *wiring*: does the net-batching
production path invoke ``audit_result`` on every "sat" result and *act* on
whatever it returns, exactly like the monolithic path already does. Two
independent seams are stubbed to test that, each documented at its use
site:

- ``ModelBuilder`` (``TestSolveSubsetCallsAuditResult``) -- replaced with a
  hand-built ``ConstraintModel`` (identical construction to
  ``test_stage3_constraint_audit.py``'s own solver-integration tests) so
  the solve reliably reaches "sat" without needing a real skeleton/pcb.
  ``solve_topology_rust`` and ``audit_result`` themselves are NOT stubbed.
- ``_run_subset_subprocess`` (``TestRunNetBatchedStage3RaisesOnViolation``)
  -- replaced with a canned outcome so the orchestration loop's raise
  logic is tested without paying for a real subprocess SAT solve. This is
  the one seam that has to be stubbed for a fast unit test: proving the
  *raise* fires is a different question from proving the *audit call*
  happens (that's the first class), and this repo's own real-board run
  (see the plan's U0/R3 evidence) is what actually proves the audit
  call's positive case end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_HAS_RUST = False
try:
    import temper_rust_router  # noqa: F401

    _HAS_RUST = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not _HAS_RUST, reason="temper-rust-router not installed")

from temper_placer.core.netlist import Net  # noqa: E402
from temper_placer.router_v6 import net_batching  # noqa: E402
from temper_placer.router_v6.stage0_data import NetClassRules  # noqa: E402


def _make_4net_k2_model():
    """Same construction as ``test_stage3_constraint_audit.py``'s
    ``test_4_nets_k2_rust_solver_clean``: 4 ``NetChannelVar``s sharing one
    channel, one ``CapacityConstraint`` capping it at 2. Reliably solves to
    "sat" via the real Rust solver without needing ``ModelBuilder``'s full
    skeleton/pcb machinery.
    """
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
    cm.add_constraint(
        CapacityConstraint(
            name="cap_CH1",
            channel_id="CH1",
            capacity=2.0,
            slack_factor=1.0,
            terms=[(v, 1.0) for v in vars_],
        )
    )
    return cm


class _StubModelBuilder:
    """Stands in for ``net_batching.ModelBuilder`` -- returns a fixed,
    already-built ``ConstraintModel`` instead of running the real Rust
    build orchestration, which needs real skeletons/pcb this test doesn't
    have. ``_solve_subset``'s own code past this point (``solve_topology_
    rust``, ``audit_result``) is exercised unmodified.
    """

    def __init__(self, model, **kwargs):
        self._model = model

    def build(self):
        return self._model


class TestSolveSubsetCallsAuditResult:
    """``_solve_subset`` is the one place in the subprocess-per-batch
    design that still holds ``cm.variables``/``cm.constraints`` (only the
    plain-data ``rust_result`` dict crosses back to the parent over the
    pipe) -- so this is where the audit call has to live, and where it's
    cheapest to prove it actually executes.
    """

    def test_sat_result_carries_an_audit_violations_key(self):
        """Even the clean case must carry the key -- its absence is what
        let this bug hide: `_batch_worker_entry`/the parent loop reading
        `.get("audit_violations", [])` would silently treat a missing key
        the same as "audit never ran", so the key's *presence* on every
        "sat" result is itself part of the contract.
        """
        cm = _make_4net_k2_model()
        nets = [Net(name=f"net{i}", pins=[]) for i in range(4)]

        with patch.object(
            net_batching, "ModelBuilder", lambda **kw: _StubModelBuilder(cm, **kw)
        ):
            _cm2, rust_result = net_batching._solve_subset(
                skeletons={},
                nets_subset=nets,
                channel_widths={},
                design_rules=None,
                diff_pairs_subset=[],
                pcb=None,
                enable_geographic_pruning=False,
                sat_conflict_limit=None,
                sat_time_limit_ms=None,
            )

        assert rust_result["status"] == "sat"
        assert "audit_violations" in rust_result
        assert rust_result["audit_violations"] == []

    def test_audit_result_is_actually_invoked_with_the_real_solve_data(self):
        """The decisive anti-vacuity check: replace ``temper_rust_router.
        audit_result`` itself with a spy and confirm ``_solve_subset``
        -- unprompted, with no test-side call to ``audit_result`` -- invokes
        it exactly once, with the real variables/constraints/net_names
        that came out of this solve (not empty stand-ins), and that
        whatever it returns becomes ``rust_result["audit_violations"]``.
        This is the "test exercises this" vs. "this runs in production"
        distinction the false doc claim collapsed: a test that only calls
        ``audit_result`` directly (as every test in
        ``test_stage3_constraint_audit.py`` does) cannot fail if
        production code stops calling it at all -- this one can.
        """
        cm = _make_4net_k2_model()
        nets = [Net(name=f"net{i}", pins=[]) for i in range(4)]

        calls: list[tuple] = []

        def _spy_audit_result(variables, constraints, assignments, net_names):
            calls.append((list(variables), list(constraints), dict(assignments), list(net_names)))
            return [
                {
                    "type": "capacity",
                    "channel_id": "CH1",
                    "max_nets": 2,
                    "actual_count": 3,
                    "violating_vars": ["uses_net0_CH1", "uses_net1_CH1", "uses_net2_CH1"],
                }
            ]

        with (
            patch.object(net_batching, "ModelBuilder", lambda **kw: _StubModelBuilder(cm, **kw)),
            patch.object(temper_rust_router, "audit_result", _spy_audit_result),
        ):
            _cm2, rust_result = net_batching._solve_subset(
                skeletons={},
                nets_subset=nets,
                channel_widths={},
                design_rules=None,
                diff_pairs_subset=[],
                pcb=None,
                enable_geographic_pruning=False,
                sat_conflict_limit=None,
                sat_time_limit_ms=None,
            )

        assert len(calls) == 1, "audit_result must be called exactly once for a sat result"
        called_variables, called_constraints, called_assignments, called_net_names = calls[0]
        assert called_net_names == ["net0", "net1", "net2", "net3"]
        assert len(called_variables) == 4, "must receive the real solved model's variables"
        assert len(called_constraints) == 1
        assert called_assignments, "must receive the real solver assignments, not an empty dict"

        # And the spy's return value must be what crosses the process
        # boundary -- proving the wiring, not just the call.
        assert rust_result["audit_violations"] == [
            {
                "type": "capacity",
                "channel_id": "CH1",
                "max_nets": 2,
                "actual_count": 3,
                "violating_vars": ["uses_net0_CH1", "uses_net1_CH1", "uses_net2_CH1"],
            }
        ]

    def test_audit_result_not_called_when_solve_is_not_sat(self):
        """Mirrors ``_pipeline_route.py``'s own ``if rust_result["status"]
        == "sat":`` guard -- an unsat/unknown result must not spend a
        (redundant, meaningless) audit call, and must still carry an empty
        ``audit_violations`` list rather than omit the key.
        """
        # Unsatisfiable: force a diff pair's two vars to disagree via two
        # LayerRestriction unit clauses, contradicting the DiffPair's
        # biconditional.
        from temper_placer.router_v6.constraint_model import (
            ConstraintModel,
            DiffPairConstraint,
            LayerConstraint,
            NetChannelVar,
        )

        cm = ConstraintModel()
        # LayerConstraint's Python->Rust bridge derives its target var name
        # as f"uses_N{net_idx}_{channel_id}" (types_py_bridge.rs) -- the
        # vars here must match that exact format or the unit clause silently
        # binds to no variable (see test_stage3_constraint_audit.py's own
        # TestLayerAudit for the same convention).
        p = NetChannelVar(name="uses_N0_CH1", net_idx=0, channel_id="CH1")
        n = NetChannelVar(name="uses_N1_CH1", net_idx=1, channel_id="CH1")
        cm.add_variable(p)
        cm.add_variable(n)
        cm.add_constraint(
            DiffPairConstraint(
                name="diff_CH1", channel_id="CH1", p_net_idx=0, n_net_idx=1, p_var=p, n_var=n
            )
        )
        cm.add_constraint(LayerConstraint(name="force_p_true", net_idx=0, channel_id="CH1", allowed=True))
        cm.add_constraint(LayerConstraint(name="force_n_false", net_idx=1, channel_id="CH1", allowed=False))

        nets = [Net(name="net0", pins=[]), Net(name="net1", pins=[])]

        calls: list = []

        def _spy_audit_result(*args, **kwargs):
            calls.append((args, kwargs))
            return []

        with (
            patch.object(net_batching, "ModelBuilder", lambda **kw: _StubModelBuilder(cm, **kw)),
            patch.object(temper_rust_router, "audit_result", _spy_audit_result),
        ):
            _cm2, rust_result = net_batching._solve_subset(
                skeletons={},
                nets_subset=nets,
                channel_widths={},
                design_rules=None,
                diff_pairs_subset=[],
                pcb=None,
                enable_geographic_pruning=False,
                sat_conflict_limit=None,
                sat_time_limit_ms=None,
            )

        assert rust_result["status"] == "unsat"
        assert calls == [], "audit_result must not be called on a non-sat result"
        assert rust_result["audit_violations"] == []


class _FakeDesignRulesForRunNetBatched:
    default_trace_width_mm = 0.25
    default_clearance_mm = 0.2
    default_via_diameter_mm = 0.6
    default_via_drill_mm = 0.3

    def get_rules_for_net(self, net_name: str) -> NetClassRules:
        return NetClassRules(
            name="Default", clearance_mm=0.2, trace_width_mm=0.25, via_diameter_mm=0.6, via_drill_mm=0.3
        )


def _make_violation_outcome(net_names: list[str]):
    return net_batching._SubprocessOutcome(
        got_result=True,
        result={
            "status": "sat",
            "topology_graph": {},
            "audit_violations": [
                {
                    "type": "capacity",
                    "channel_id": "CH1",
                    "max_nets": 2,
                    "actual_count": 3,
                    "violating_vars": ["x", "y", "z"],
                }
            ],
            "primary_vars": 0,
            "net_channel_vars": 0,
            "via_vars": 0,
            "constraints": 0,
            "peak_rss_kb": 0,
        },
        crashed=False,
        crash_reason=None,
        exitcode=0,
        external_peak_rss_kb=0,
        wall_s_wall=0.01,
    )


def _make_clean_outcome(net_names: list[str]):
    return net_batching._SubprocessOutcome(
        got_result=True,
        result={
            "status": "sat",
            "topology_graph": {name: {"uses_channels": [], "path_graph": [], "total_length_estimate": 0.0} for name in net_names},
            "audit_violations": [],
            "primary_vars": 0,
            "net_channel_vars": 0,
            "via_vars": 0,
            "constraints": 0,
            "peak_rss_kb": 0,
        },
        crashed=False,
        crash_reason=None,
        exitcode=0,
        external_peak_rss_kb=0,
        wall_s_wall=0.01,
    )


class TestRunNetBatchedStage3RaisesOnViolation:
    """``run_net_batched_stage3`` is the actual production entry point
    ``_pipeline_route.py:241-254`` calls when ``enable_net_batching=True``
    -- the literal ``--net-batching`` recipe the real board routes
    through. These tests stub only ``_run_subset_subprocess`` (the
    subprocess dispatch, to avoid paying for a real spawn + SAT solve in a
    unit test) and run the real, unmodified orchestration loop around it,
    proving the *raise*, not merely that ``RuntimeError`` can be raised by
    calling ``audit_result`` and checking its result by hand.
    """

    def _make_pcb_and_stage2(self, tmp_path: Path, net_names: list[str]):
        nets = [Net(name=name, pins=[]) for name in net_names]
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")  # never actually parsed -- subprocess dispatch is stubbed
        pcb = SimpleNamespace(
            nets=nets, source_path=pcb_path, design_rules=_FakeDesignRulesForRunNetBatched()
        )
        stage2 = SimpleNamespace(skeletons={}, channel_widths={})
        return pcb, stage2

    def test_raises_runtime_error_on_batch_level_violation(self, tmp_path):
        net_names = ["NET1", "NET2"]
        pcb, stage2 = self._make_pcb_and_stage2(tmp_path, net_names)

        with patch.object(
            net_batching,
            "_run_subset_subprocess",
            return_value=_make_violation_outcome(net_names),
        ), pytest.raises(RuntimeError, match="constraint violation"):
            net_batching.run_net_batched_stage3(pcb, stage2, batch_size=10)

    def test_raises_runtime_error_on_singleton_retry_violation(self, tmp_path):
        """The batch-level attempt reports non-sat (forcing the singleton
        retry path); the singleton retry itself carries a violation. Mirrors
        the batch-level test but exercises the retry mirror
        (`net_batching.py`'s singleton-retry loop), which the R3
        requirement calls out as a second, independent call site.
        """
        net_names = ["NET1"]
        pcb, stage2 = self._make_pcb_and_stage2(tmp_path, net_names)

        batch_level_unsat = net_batching._SubprocessOutcome(
            got_result=True,
            result={
                "status": "unsat",
                "topology_graph": {},
                "audit_violations": [],
                "primary_vars": 0,
                "net_channel_vars": 0,
                "via_vars": 0,
                "constraints": 0,
                "peak_rss_kb": 0,
            },
            crashed=False,
            crash_reason=None,
            exitcode=0,
            external_peak_rss_kb=0,
            wall_s_wall=0.01,
        )
        singleton_violation = _make_violation_outcome(net_names)
        # topology_graph must contain the net for the retry branch to reach
        # the audit check at all (see net_batching.py's `n.name in
        # rr1.get("topology_graph", {})` guard).
        singleton_violation.result["topology_graph"] = {
            "NET1": {"uses_channels": [], "path_graph": [], "total_length_estimate": 0.0}
        }

        with patch.object(
            net_batching,
            "_run_subset_subprocess",
            side_effect=[batch_level_unsat, singleton_violation],
        ), pytest.raises(RuntimeError, match="constraint violation"):
            net_batching.run_net_batched_stage3(pcb, stage2, batch_size=10)

    def test_does_not_raise_when_audit_is_clean(self, tmp_path):
        """Negative control: a "sat" result with an empty
        ``audit_violations`` list (the expected shape of every result this
        wiring has produced on the real board so far, per this plan's own
        measurement) must not raise -- proving the previous test's raise is
        conditional on the violation content, not unconditional on every
        "sat" result.
        """
        net_names = ["NET1", "NET2"]
        pcb, stage2 = self._make_pcb_and_stage2(tmp_path, net_names)

        with patch.object(
            net_batching,
            "_run_subset_subprocess",
            return_value=_make_clean_outcome(net_names),
        ):
            stage3_output, batch_results = net_batching.run_net_batched_stage3(
                pcb, stage2, batch_size=10
            )

        assert len(batch_results) == 1
        assert batch_results[0].status == "sat"
