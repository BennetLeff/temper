"""Stage 3 direct capacity-aware topology solver — vacuity-fix tests.

2026-08-16 (docs/evidence/2026-08-16-sat-capacity-vacuity-fix.md): the
Stage 3 SAT model is structurally vacuous — nothing forces a
`NetChannelVar` true, so every solve returns "0 conflicts, 0 decisions"
and an *empty* topology (measured: 0/30 nets with non-empty
`uses_channels`), while the monolithic CNF costs 182-200 GB. The
monolithic default now routes Stage 3 through the direct capacity-aware
solver (`_run_stage3_direct` → `temper_rust_router.solve_topology_direct_py`),
which computes a real per-net channel path with capacity enforced by
construction.

These tests pin the vacuity regression at the pipeline level: a two-pad
net on a connected skeleton MUST come back with a non-empty
`uses_channels` through the real wiring, not only through the Rust
kernel.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from temper_placer.core.netlist import Net
from temper_placer.router_v6._pipeline_route import _run_stage3_direct
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths

_HAS_RUST = False
try:
    import temper_rust_router  # noqa: F401

    _HAS_RUST = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not _HAS_RUST, reason="temper-rust-router not installed")


def _make_skeleton(*edges: tuple[tuple[float, float], tuple[float, float]], layer: str = "F.Cu") -> ChannelSkeleton:
    """A ChannelSkeleton whose graph is the given edge list (nodes implied)."""
    import temper_design_bundle_python as _tdb

    # Attribute access, not `import ...channel_skeleton_contracts` — the pyo3
    # submodule is registered as a parent attribute, not in sys.modules (the
    # same convention channel_skeleton.py itself uses).
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    for u, v in edges:
        g.add_edge(u, v, 1.0)
    return ChannelSkeleton(graph=g, layer_name=layer, total_length=0.0)


def _make_pcb(nets: list[Net], design_rules=None) -> SimpleNamespace:
    return SimpleNamespace(
        nets=nets,
        source_path=None,
        design_rules=design_rules,
        components=[],
    )


def _make_pipeline(**kwargs):
    from temper_placer.router_v6._pipeline_core import RouterV6Pipeline

    return RouterV6Pipeline(**kwargs)


def _make_net(name: str, pads: list[tuple[float, float]]) -> Net:
    # Net pins are (component_ref, pin_name); pads come from
    # _net_pad_positions which walks pcb.components. For the direct
    # solver tests we bypass pin resolution entirely: _run_stage3_direct
    # computes pads via `_net_pad_positions(net, comp_by_ref)` which
    # returns [] for an empty component map, so we monkeypatch it in the
    # tests that need real pads.
    return Net(name=name, pins=[])


class _FakeDesignRules:
    """DesignRules duck-type: per-net width lookups."""

    def __init__(self, widths: dict[str, float]):
        self._widths = widths

    def get_rules_for_net(self, net_name: str) -> SimpleNamespace:
        return SimpleNamespace(
            trace_width_mm=self._widths.get(net_name, 0.2),
            clearance_mm=0.1,
        )


class TestRunStage3DirectVacuityRegression:
    """The vacuity regression: real topology, through the real wiring."""

    def _run(self, pcb, stage2, **kw):
        pipeline = _make_pipeline(verbose=False)
        return _run_stage3_direct(pipeline, pcb, stage2, **kw)

    def test_two_pad_net_gets_nonempty_topology(self):
        """A two-pad net on a connected line skeleton must come back with a
        non-empty uses_channels. Before the fix, Stage 3 returned an empty
        topology for every net."""
        a, b, c = (0.0, 0.0), (10.0, 0.0), (20.0, 0.0)
        skeleton = _make_skeleton((a, b), (b, c))
        widths = ChannelWidths(
            layer_name="F.Cu",
            node_widths={a: 5.0, b: 5.0, c: 5.0},
            edge_widths={(a, b): 5.0, (b, c): 5.0},
            min_width=5.0,
            max_width=5.0,
            avg_width=5.0,
        )
        stage2 = SimpleNamespace(
            skeletons={"F.Cu": skeleton},
            channel_widths={"F.Cu": widths},
        )
        net = _make_net("n1", [a, c])
        pcb = _make_pcb([net], design_rules=_FakeDesignRules({"n1": 0.2}))

        with patch(
            "temper_placer.router_v6._pipeline_grid._net_pad_positions",
            return_value=[a, c],
        ):
            out = self._run(pcb, stage2)

        assert out.topology_graph is not None
        topo = out.topology_graph.get_topology("n1")
        assert topo is not None
        assert list(topo.uses_channels), (
            "vacuity regression: a two-pad net must receive non-empty "
            f"uses_channels, got {list(topo.uses_channels)}"
        )
        assert not out.degraded_nets

    def test_disconnected_pads_reported_degraded(self):
        """A net whose pads lie in different skeleton components gets no
        topology and is reported degraded (Stage 4 fallback takes over)."""
        a, b = (0.0, 0.0), (10.0, 0.0)
        x, y = (100.0, 100.0), (110.0, 100.0)
        skeleton = _make_skeleton((a, b), (x, y))
        widths = ChannelWidths(
            layer_name="F.Cu",
            node_widths={a: 5.0, b: 5.0, x: 5.0, y: 5.0},
            edge_widths={(a, b): 5.0, (x, y): 5.0},
            min_width=5.0,
            max_width=5.0,
            avg_width=5.0,
        )
        stage2 = SimpleNamespace(
            skeletons={"F.Cu": skeleton},
            channel_widths={"F.Cu": widths},
        )
        net = _make_net("dis", [a, y])
        pcb = _make_pcb([net], design_rules=_FakeDesignRules({"dis": 0.2}))

        with patch(
            "temper_placer.router_v6._pipeline_grid._net_pad_positions",
            return_value=[a, y],
        ):
            out = self._run(pcb, stage2)

        assert "dis" in out.degraded_nets
        assert out.topology_graph.get_topology("dis") is None or not list(
            out.topology_graph.get_topology("dis").uses_channels
        )

    def test_capacity_conflict_reroutes_second_net(self):
        """Two nets both wanting a narrow bridge: the first takes it, the
        second is re-routed around it (never silently over-committed)."""
        a, b = (0.0, 0.0), (10.0, 0.0)
        x, y = (0.0, 10.0), (10.0, 10.0)
        skeleton = _make_skeleton((a, b), (a, x), (x, y), (y, b))
        # Bridge (a,b) capacity 0.2mm — a 0.25mm-width net (0.2 trace + 0.1
        # clearance = 0.3... choose widths so the bridge fits exactly one).
        widths = ChannelWidths(
            layer_name="F.Cu",
            node_widths={p: 5.0 for p in (a, b, x, y)},
            edge_widths={(a, b): 0.5, (a, x): 5.0, (x, y): 5.0, (y, b): 5.0},
            min_width=0.5,
            max_width=5.0,
            avg_width=3.0,
        )
        stage2 = SimpleNamespace(
            skeletons={"F.Cu": skeleton},
            channel_widths={"F.Cu": widths},
        )
        # width = trace 0.25 + clearance 0.1 = 0.35. Bridge usable =
        # 0.5 * 0.8 = 0.4 >= 0.35 → fits one net; remaining 0.05 < 0.35 →
        # second net re-routes around.
        nets = [_make_net("n1", [a, b]), _make_net("n2", [a, b])]
        pcb = _make_pcb(nets, design_rules=_FakeDesignRules({"n1": 0.25, "n2": 0.25}))

        with patch(
            "temper_placer.router_v6._pipeline_grid._net_pad_positions",
            return_value=[a, b],
        ):
            out = self._run(pcb, stage2)

        assert out.topology_graph is not None
        n1 = out.topology_graph.get_topology("n1")
        n2 = out.topology_graph.get_topology("n2")
        assert n1 is not None and n2 is not None
        # Both nets are routable (the alternate path exists) and the
        # capacity conflict (usable 0.4, width 0.35/net — the second net
        # must re-route around the bridge) is resolved WITHOUT
        # over-commitment: the post-condition audit in the Rust kernel
        # raised on any violation (a raised RuntimeError would fail this
        # test). The emitted pad-waypoint ids do not expose the internal
        # path choice, so the assertion here is: both routed, non-empty
        # pad-pair guidance, capacity enforced by construction.
        assert list(n1.uses_channels) and list(n2.uses_channels)
        assert all("_PW_" in ch for ch in n1.uses_channels + n2.uses_channels), (
            f"emitted channel ids must be pad-waypoint ids: {n1.uses_channels} {n2.uses_channels}"
        )


class TestRunStage3Dispatch:
    """The `_run_stage3` wiring: the monolithic default now uses the
    direct solver; SAT remains reachable behind flags / the env hatch."""

    def test_default_monolith_dispatches_to_direct(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        pipeline = _make_pipeline(verbose=False)
        assert not pipeline.enable_net_batching
        assert not pipeline.enable_bundling

        stage2 = SimpleNamespace(skeletons={}, channel_widths={})
        net = Net(name="n1", pins=[])
        pcb = SimpleNamespace(
            nets=[net], source_path=pcb_path, design_rules=None, components=[]
        )

        # `self._run_stage3_direct` resolves through the class attribute
        # assigned in _pipeline_core.py — patch that, not the module name.
        from temper_placer.router_v6._pipeline_core import RouterV6Pipeline

        with patch.object(
            RouterV6Pipeline, "_run_stage3_direct", return_value="DIRECT"
        ) as direct, patch(
            "temper_placer.router_v6._pipeline_route.ModelBuilder"
        ) as mb:
            result = pipeline._run_stage3(pcb, stage2)
        assert result == "DIRECT"
        direct.assert_called_once()
        mb.assert_not_called()

    def test_force_sat_env_hatch_reaches_sat_path(self, tmp_path, monkeypatch):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        monkeypatch.setenv("TEMPER_STAGE3_FORCE_SAT", "1")
        pipeline = _make_pipeline(verbose=False)

        stage2 = SimpleNamespace(skeletons={}, channel_widths={})
        net = Net(name="n1", pins=[])
        pcb = SimpleNamespace(
            nets=[net], source_path=pcb_path, design_rules=None, components=[]
        )

        from temper_placer.router_v6._pipeline_core import RouterV6Pipeline

        with patch.object(
            RouterV6Pipeline, "_run_stage3_direct", return_value="DIRECT"
        ) as direct, patch(
            "temper_rust_router.solve_topology_rust"
        ) as solve:
            out = pipeline._run_stage3(pcb, stage2)
        # The SAT path ran (solve_topology_rust called) and the direct path
        # was NOT taken.
        assert solve.called
        direct.assert_not_called()
        assert out is not None

    def test_net_batching_still_takes_priority(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        pipeline = _make_pipeline(enable_net_batching=True)

        stage2 = SimpleNamespace(skeletons={}, channel_widths={})
        net = Net(name="n1", pins=[])
        pcb = SimpleNamespace(
            nets=[net], source_path=pcb_path, design_rules=None, components=[]
        )

        with patch(
            "temper_placer.router_v6._pipeline_route._run_stage3_direct",
            return_value="DIRECT",
        ) as direct, patch(
            "temper_placer.router_v6.net_batching.run_net_batched_stage3",
            return_value=("BATCHED", []),
        ) as batched:
            result = pipeline._run_stage3(pcb, stage2)
        assert result == "BATCHED"
        batched.assert_called_once()
        direct.assert_not_called()


class TestPostConditionRaise:
    """Post-condition violations raise (the direct analog of the SAT
    path's `audit_result` contract: raise, don't warn)."""

    def test_violation_raises(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        pipeline = _make_pipeline(verbose=False)
        stage2 = SimpleNamespace(skeletons={}, channel_widths={})
        net = Net(name="n1", pins=[])
        pcb = SimpleNamespace(
            nets=[net], source_path=pcb_path, design_rules=None, components=[]
        )

        fake_result = {
            "status": "sat",
            "topology_graph": {},
            "unrouted_nets": [],
            "post_condition_violations": ["capacity over-committed on channel X"],
            "solver_time_ms": 1.0,
            "solver_stats": {},
        }
        with patch(
            "temper_rust_router.solve_topology_direct_py", return_value=fake_result
        ), pytest.raises(RuntimeError, match="post-condition"):
            pipeline._run_stage3(pcb, stage2)
