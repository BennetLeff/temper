"""Stage 3 auto-batch safety net (2026-08-16, Stage 3 memory fix option 1).

The monolithic Stage 3 SAT model is exactly ``|nets| x |edges|`` raw
variables, and its Sinz sequential-counter CNF encoding multiplies that
by ~17.7x CNF vars / ~34x clauses (measured in
``docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md``).
On the production board (110 nets x ~204K edges = ~22.5M raw vars) the
monolith demands ~182-200 GB against a 62 GB machine and is OOM-killed
at ~58 GB inside ``encode_to_cnf`` before CaDiCaL even loads.

``_run_stage3`` now estimates the raw variable count whenever batching
was not explicitly requested (and the caller is not already reducing the
model via bundling or geographic pruning), and routes through the batched
path -- the documented production recipe -- instead of attempting an OOM.
These tests pin that decision: the estimate arithmetic, when auto-batch
fires, and -- just as importantly -- when it deliberately does NOT (small
boards, explicit batching, bundling, pruning, selective-SAT subsets under
the threshold), so the safety net cannot silently change behavior for
models that fit.

Patch-target note: ``_run_stage3`` imports ``run_net_batched_stage3``,
``solve_topology_rust`` and ``audit_result`` *inside* the function, so
those are patched on their home modules (``net_batching`` /
``temper_rust_router``), while ``ModelBuilder`` is a module-level import
and is patched on ``_pipeline_route`` itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from temper_placer.router_v6 import net_batching
from temper_placer.router_v6 import _pipeline_route as pr
from temper_placer.router_v6._pipeline_core import RouterV6Pipeline
from temper_placer.router_v6.topology_solver import SolverStatus

_HAS_RUST = False
try:
    import temper_rust_router  # noqa: F401

    _HAS_RUST = True
except ImportError:
    pass

# Importing _pipeline_route pulls in temper_orchestration (Rust pyo3), so
# the whole module is Rust-gated, matching the sibling
# test_net_batching_constraint_audit.py.
pytestmark = pytest.mark.skipif(not _HAS_RUST, reason="temper-rust-router not installed")

from temper_placer.core.netlist import Net  # noqa: E402


def _fake_pcb(n_nets: int):
    """Minimal ParsedPCB stand-in: only ``.nets`` (for ``net_names`` and
    the estimate) and ``.design_rules`` (threaded to the stubbed
    ModelBuilder) are consumed by the paths these tests exercise."""
    return SimpleNamespace(
        nets=[Net(name=f"net{i}", pins=[]) for i in range(n_nets)],
        design_rules=None,
    )


def _fake_stage2(edges_per_layer: list[int]):
    """Stage2Output stand-in with skeletons whose edge counts sum to the
    given per-layer totals (``ChannelSkeleton.edge_count`` is the only
    attribute the estimate reads). ``channel_widths`` is also provided so
    the monolithic tail of ``_run_stage3`` can pass it to the (stubbed)
    ModelBuilder."""
    skeletons = {
        f"layer{i}": SimpleNamespace(edge_count=n)
        for i, n in enumerate(edges_per_layer)
    }
    return SimpleNamespace(skeletons=skeletons, channel_widths={})


# A "sat" rust_result that drives the monolithic tail of _run_stage3 with
# zero nets/constraints -- no Rust solver needed.
_SAT_RESULT = {
    "status": "sat",
    "assignments": {},
    "solver_time_ms": 0.0,
    "solver_stats": {},
    "var_to_net": {},
    "tensions": [],
    "num_vars": 0,
    "num_clauses": 0,
    "topology_graph": {},
}


class TestEstimateStage3ModelVars:
    """The estimate is |nets| x |edges|, exactly the raw model size
    ModelBuilder builds (verified exact in the 2026-08-15 investigation).
    """

    def test_exact_math(self):
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([52_815, 22_538, 29_504, 29_504])  # 134,361 edges
        assert pr._estimate_stage3_model_vars(pcb, stage2, None) == 110 * 134_361

    def test_net_filter_subsets_nets(self):
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([59_008])
        # max_sat_nets=10 selects 10 nets -> estimate drops by 100/110.
        assert pr._estimate_stage3_model_vars(pcb, stage2, ["n"] * 10) == 10 * 59_008

    def test_no_skeletons_returns_zero(self):
        pcb = _fake_pcb(110)
        assert pr._estimate_stage3_model_vars(pcb, SimpleNamespace(skeletons=None), None) == 0
        assert pr._estimate_stage3_model_vars(pcb, SimpleNamespace(skeletons={}), None) == 0


class TestRunStage3AutoBatchDecision:
    """The safety net must fire exactly when the monolith would be too big
    -- and must NOT fire when the model fits, so small-board behavior is
    unchanged."""

    def _pipeline(self, **kwargs):
        return RouterV6Pipeline(verbose=False, **kwargs)

    def test_auto_batches_when_estimate_exceeds_threshold(self):
        """Production-board scale (110 nets x ~204K edges = 22.5M raw vars,
        far above the 2.5M threshold): a caller that never asked for
        batching must get the batched path, not the OOMing monolith."""
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([204_144])
        assert pr._estimate_stage3_model_vars(pcb, stage2, None) > pr._AUTO_BATCH_VAR_THRESHOLD

        pipe = self._pipeline()  # enable_net_batching defaults False
        stub_output = SimpleNamespace()
        calls: list[tuple] = []

        def _spy_run_batched(*args, **kwargs):
            calls.append((args, kwargs))
            return (stub_output, [])

        with patch.object(
            net_batching, "run_net_batched_stage3", _spy_run_batched
        ):
            out = pipe._run_stage3(pcb, stage2)

        assert len(calls) == 1, "expected exactly one batched Stage 3 run"
        assert calls[0][1]["batch_size"] == pipe.net_batch_size
        assert out is stub_output  # the stage3 output the spy returned

    def test_does_not_auto_batch_when_estimate_fits(self):
        """Small board (10 nets x 1,000 edges = 10K raw vars): the monolith
        must run exactly as before -- no batched call, real monolith path."""
        pcb = _fake_pcb(10)
        stage2 = _fake_stage2([1_000])
        assert pr._estimate_stage3_model_vars(pcb, stage2, None) < pr._AUTO_BATCH_VAR_THRESHOLD

        pipe = self._pipeline()
        with (
            patch.object(pr, "ModelBuilder") as mb,
            patch.object(net_batching, "run_net_batched_stage3") as spy_batched,
            patch(
                "temper_rust_router.solve_topology_rust",
                return_value=dict(_SAT_RESULT),
            ),
            patch("temper_rust_router.audit_result", return_value=[]),
        ):
            mb.return_value.build.return_value = SimpleNamespace(
                variables=[], constraints=[]
            )
            out = pipe._run_stage3(pcb, stage2)

        spy_batched.assert_not_called()
        assert out.solution.status == SolverStatus.SATISFIABLE
        assert out.constraint_model is not None

    def test_explicit_batching_is_untouched(self):
        """enable_net_batching=True (the old documented recipe) still goes
        straight to the batched branch; the estimate is irrelevant."""
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([204_144])
        pipe = self._pipeline(enable_net_batching=True)

        with patch.object(
            net_batching,
            "run_net_batched_stage3",
            return_value=(SimpleNamespace(), []),
        ) as spy_batched:
            pipe._run_stage3(pcb, stage2)

        assert spy_batched.call_count == 1

    def test_geographic_pruning_skips_auto_batch(self):
        """Geographic pruning is an explicit model-reduction opt-in: the
        raw |nets| x |edges| estimate wildly over-estimates the pruned
        model, so auto-batch must not fire (the caller chose pruning)."""
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([204_144])
        pipe = self._pipeline(enable_geographic_pruning=True)

        with (
            patch.object(pr, "ModelBuilder") as mb,
            patch.object(net_batching, "run_net_batched_stage3") as spy_batched,
            patch(
                "temper_rust_router.solve_topology_rust",
                return_value=dict(_SAT_RESULT),
            ),
            patch("temper_rust_router.audit_result", return_value=[]),
        ):
            mb.return_value.build.return_value = SimpleNamespace(
                variables=[], constraints=[]
            )
            pipe._run_stage3(pcb, stage2)

        spy_batched.assert_not_called()

    def test_bundling_skips_auto_batch(self):
        """Bundling (type-gated lazy grounding) is its own reduction; the
        raw estimate does not apply and auto-batch must not fire."""
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([204_144])
        pipe = self._pipeline(enable_bundling=True)

        with (
            patch.object(pr, "ModelBuilder") as mb,
            patch(
                "temper_placer.router_v6.bundle_analyzer.BundleAnalyzer"
            ) as ba,
            patch.object(net_batching, "run_net_batched_stage3") as spy_batched,
            # solve_topology_rust_bundled is imported inside _run_stage3's
            # bundling branch; it is absent from the installed
            # temper_rust_router build (bundling is off by default), so
            # create=True lets this decision test stub it without claiming
            # the symbol exists in production.
            patch.object(
                temper_rust_router,
                "solve_topology_rust_bundled",
                return_value=dict(_SAT_RESULT),
                create=True,
            ),
        ):
            mb.return_value.build.return_value = SimpleNamespace(
                variables=[], constraints=[]
            )
            ba.return_value.analyze.return_value = SimpleNamespace(
                bundle_count=0,
                bundles={},
                bundle_id_for_net={},
                unbundled_net_indices=[],
            )
            pipe._run_stage3(pcb, stage2)

        spy_batched.assert_not_called()

    def test_selective_sat_subset_below_threshold_keeps_monolith(self):
        """max_sat_nets=N shrinks the model to N x |edges|: with N small
        enough the monolith fits and must run (selective SAT is the
        documented escape hatch for callers who want the monolith on a
        large board)."""
        pcb = _fake_pcb(110)
        stage2 = _fake_stage2([204_144])
        pipe = self._pipeline(max_sat_nets=10)  # 10 x 204,144 = 2.04M < 2.5M

        with (
            patch.object(
                pipe, "_select_sat_nets", return_value=[f"net{i}" for i in range(10)]
            ),
            patch.object(pr, "ModelBuilder") as mb,
            patch.object(net_batching, "run_net_batched_stage3") as spy_batched,
            patch(
                "temper_rust_router.solve_topology_rust",
                return_value=dict(_SAT_RESULT),
            ),
            patch("temper_rust_router.audit_result", return_value=[]),
        ):
            mb.return_value.build.return_value = SimpleNamespace(
                variables=[], constraints=[]
            )
            pipe._run_stage3(pcb, stage2)

        spy_batched.assert_not_called()
