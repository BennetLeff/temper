"""U4 — Adapter tests: deterministic, orchestrator, router_v6."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.protocol import PipelineStage, StageInput, StageMeta


class _TestStage(Stage):
    _name: str = "test_stage"
    _return: BoardState | None = None

    @property
    def name(self) -> str:
        return self._name

    def run(self, state: BoardState) -> BoardState:
        if self._return is not None:
            return self._return
        from dataclasses import replace
        return replace(state, net_order=("A", "B"))


class TestDeterministicAdapter:
    def test_wrap_satisfies_protocol(self):
        from temper_placer.adapters.deterministic_adapter import wrap_deterministic_stage
        stage = _TestStage()
        wrapped = wrap_deterministic_stage(stage)
        assert isinstance(wrapped, PipelineStage)

    def test_wrapped_preserves_name(self):
        from temper_placer.adapters.deterministic_adapter import wrap_deterministic_stage
        stage = _TestStage()
        stage._name = "my_custom_name"
        wrapped = wrap_deterministic_stage(stage)
        assert wrapped.name == "my_custom_name"

    def test_wrapped_delegates_run(self):
        from temper_placer.adapters.deterministic_adapter import wrap_deterministic_stage
        stage = _TestStage()
        stage._return = BoardState(net_order=("X", "Y"))
        wrapped = wrap_deterministic_stage(stage)
        inp = StageInput(data=BoardState())
        out = wrapped.run(inp)
        assert out.data.net_order == ("X", "Y")

    def test_wrapped_preserves_meta(self):
        from temper_placer.adapters.deterministic_adapter import wrap_deterministic_stage
        stage = _TestStage()
        wrapped = wrap_deterministic_stage(stage)
        meta = StageMeta(seed=99)
        inp = StageInput(data=BoardState(), meta=meta)
        out = wrapped.run(inp)
        assert out.meta.seed == 99

    def test_requires_provides_passthrough(self):
        from temper_placer.adapters.deterministic_adapter import wrap_deterministic_stage
        stage = _TestStage()
        wrapped = wrap_deterministic_stage(stage, requires=["board"], provides=["placements"])
        assert wrapped.requires == ["board"]
        assert wrapped.provides == ["placements"]

    def test_internals_unmodified(self):
        from temper_placer.adapters.deterministic_adapter import wrap_deterministic_stage
        stage = _TestStage()
        original_result = stage.run(BoardState())
        wrap_deterministic_stage(stage)
        after_result = stage.run(BoardState())
        assert after_result.net_order == original_result.net_order


ORCHESTRATOR_PHASES = {
    "input": "OrchestratorInputStage",
    "semantic": "OrchestratorSemanticStage",
    "topological": "OrchestratorTopologicalStage",
    "preflight": "OrchestratorPreflightStage",
    "geometric": "OrchestratorGeometricStage",
    "routing": "OrchestratorRoutingStage",
    "refinement": "OrchestratorRefinementStage",
    "output": "OrchestratorOutputStage",
}


class TestOrchestratorAdapter:
    def _fresh_import_orchestrator(self):
        import temper_placer.strategy_registry as sr
        sr._registry.clear()
        sr._composites.clear()
        sys.modules.pop("temper_placer.adapters.orchestrator_adapter", None)
        import temper_placer.adapters.orchestrator_adapter as oa
        return oa, sr

    def test_each_phase_has_name(self):
        oa, _ = self._fresh_import_orchestrator()
        for phase_key, class_name in ORCHESTRATOR_PHASES.items():
            phase_cls = getattr(oa, class_name)
            inst = phase_cls()
            assert inst.name == f"orchestrator/{phase_key}", f"{class_name} name mismatch"

    def test_each_phase_has_requires_provides(self):
        oa, _ = self._fresh_import_orchestrator()
        for class_name in ORCHESTRATOR_PHASES.values():
            phase_cls = getattr(oa, class_name)
            inst = phase_cls()
            assert isinstance(inst.requires, list)
            assert isinstance(inst.provides, list)

    def test_phases_registered(self):
        oa, sr = self._fresh_import_orchestrator()
        stage = sr.get("geometric", "orchestrator")
        assert isinstance(stage, PipelineStage)
        assert stage.name == "orchestrator/geometric"

    def test_phase_isolation(self):
        oa, _ = self._fresh_import_orchestrator()
        stage1 = oa.OrchestratorInputStage()
        stage2 = oa.OrchestratorInputStage()
        assert stage1 is not stage2
        assert stage1.name == stage2.name
        assert isinstance(stage1.requires, list)
        assert isinstance(stage2.requires, list)
        assert stage1.requires == stage2.requires


class TestRouterV6Adapter:
    def _fresh_import_router_v6(self):
        import temper_placer.strategy_registry as sr
        sr._registry.clear()
        sr._composites.clear()
        sys.modules.pop("temper_placer.adapters.router_v6_stage_adapter", None)
        import temper_placer.adapters.router_v6_stage_adapter as rv6
        return rv6, sr

    def test_five_stages_registered(self):
        _, sr = self._fresh_import_router_v6()
        stages = sr.list_stages("routing")
        router_v6_stages = {k: v for k, v in stages.items() if "router_v6" in k}
        assert len(router_v6_stages) == 5

    def test_composite_registered(self):
        _, sr = self._fresh_import_router_v6()
        stages = sr.get_composite("router_v6_full")
        assert len(stages) == 5
        for stage in stages:
            assert isinstance(stage, PipelineStage)

    def test_stage0_expects_path(self):
        from temper_placer.adapters.router_v6_stage_adapter import RouterV6Stage0_LoadPCB
        stage = RouterV6Stage0_LoadPCB()
        inp = StageInput(data=42)
        with pytest.raises(TypeError, match="RouterV6Stage0"):
            stage.run(inp)

    def test_composite_ordering(self):
        _, sr = self._fresh_import_router_v6()
        stages = sr.get_composite("router_v6_full")
        names = [s.name for s in stages]
        expected = [
            "router_v6/load_pcb",
            "router_v6/escape_vias",
            "router_v6/channel_analysis",
            "router_v6/topological_routing",
            "router_v6/geometric_realization",
        ]
        assert names == expected

    def test_internals_unmodified(self):
        _, sr = self._fresh_import_router_v6()
        from temper_placer.adapters.router_v6_stage_adapter import RouterV6Stage0_LoadPCB
        assert RouterV6Stage0_LoadPCB.name == "router_v6/load_pcb"
