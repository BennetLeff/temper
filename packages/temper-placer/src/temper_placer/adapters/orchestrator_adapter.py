"""PipelineOrchestrator adapter — 8 individually callable ``PipelineStage`` instances.

Each phase from ``PipelineOrchestrator`` is exposed as a standalone stage
without modifying the original ``PipelineOrchestrator`` class.

Strategy: create a fresh orchestrator per phase call, inject data into
``self.state``, call only the target phase handler, and return the result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.pipeline.orchestrator import PipelineState, PipelineConfig  # noqa: F401
    from temper_placer.protocol import PipelineStage, StageInput, StageOutput  # noqa: F401


def _make_orchestrator_stage(
    phase_value: str,
    handler_name: str,
    requires: list[str],
    provides: list[str],
) -> type:
    """Factory: create a ``PipelineStage`` class for one orchestrator phase."""

    class _OrchestratorPhaseStage:
        name: str = f"orchestrator/{phase_value}"
        requires: list[str] = requires
        provides: list[str] = provides
        contract = None

        def run(self, input):
            from temper_placer.pipeline.orchestrator import (
                PipelineOrchestrator,
                PipelineState,
                PipelineConfig,
                PipelinePhase,
            )
            from temper_placer.protocol import StageOutput

            phase = PipelinePhase(phase_value)
            data = input.data

            if isinstance(data, PipelineConfig):
                orchestrator = PipelineOrchestrator(data)
            elif isinstance(data, PipelineState):
                orchestrator = PipelineOrchestrator(data.config)
                orchestrator.state = data
            else:
                raise TypeError(
                    f"Orchestrator adapter expected PipelineConfig or "
                    f"PipelineState, got {type(data).__name__}"
                )

            handler = getattr(orchestrator, handler_name)
            new_state = handler(orchestrator.state)
            return StageOutput(data=new_state, meta=input.meta)

    _OrchestratorPhaseStage.__name__ = f"Orchestrator{phase_value.title()}Stage"
    _OrchestratorPhaseStage.__qualname__ = _OrchestratorPhaseStage.__name__
    return _OrchestratorPhaseStage


# ---- 8 phase-specific stages ------------------------------------------------

OrchestratorInputStage = _make_orchestrator_stage(
    "input", "_run_input", requires=[], provides=["board", "netlist", "constraints"],
)
OrchestratorSemanticStage = _make_orchestrator_stage(
    "semantic", "_run_semantic", requires=["board", "netlist"], provides=["loops"],
)
OrchestratorTopologicalStage = _make_orchestrator_stage(
    "topological", "_run_topological",
    requires=["board", "netlist", "constraints"],
    provides=["deterministic_result"],
)
OrchestratorPreflightStage = _make_orchestrator_stage(
    "preflight", "_run_preflight",
    requires=["board", "netlist", "constraints"],
    provides=["preflight_report"],
)
OrchestratorGeometricStage = _make_orchestrator_stage(
    "geometric", "_run_geometric",
    requires=["board", "netlist", "deterministic_result"],
    provides=["placement_state"],
)
OrchestratorRoutingStage = _make_orchestrator_stage(
    "routing", "_run_routing",
    requires=["board", "netlist", "placement_state"],
    provides=["routing_result"],
)
OrchestratorRefinementStage = _make_orchestrator_stage(
    "refinement", "_run_refinement",
    requires=["board", "netlist", "placement_state", "routing_result"],
    provides=["placement_state"],
)
OrchestratorOutputStage = _make_orchestrator_stage(
    "output", "_run_output",
    requires=["board", "netlist", "placement_state"],
    provides=["output_pcb"],
)


# ---- Register all 8 phases at import time -----------------------------------

def _register_orchestrator_stages() -> None:
    from temper_placer.strategy_registry import register

    register("input", "orchestrator", lambda: OrchestratorInputStage())
    register("semantic", "orchestrator", lambda: OrchestratorSemanticStage())
    register("topological", "orchestrator", lambda: OrchestratorTopologicalStage())
    register("preflight", "orchestrator", lambda: OrchestratorPreflightStage())
    register("geometric", "orchestrator", lambda: OrchestratorGeometricStage())
    register("routing", "orchestrator", lambda: OrchestratorRoutingStage())
    register("refinement", "orchestrator", lambda: OrchestratorRefinementStage())
    register("output", "orchestrator", lambda: OrchestratorOutputStage())


_register_orchestrator_stages()
