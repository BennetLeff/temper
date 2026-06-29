"""Register placement and routing strategies with the strategy registry.

This module is imported as a side effect to wire the legacy
``benders_placement()`` and ``route_pcb()`` adapters into the unified
``PipelineStage`` protocol via the strategy registry.

Without this module imported, the closure test reports "No stage
registered for phase='placement'/'routing'" — the strategies are
implemented but never wired up.

Import side effect:
    import temper_placer.adapters.register_strategies  # noqa: F401
"""
from __future__ import annotations

from dataclasses import dataclass

from temper_placer.protocol import PipelineStage, StageInput, StageOutput
from temper_placer.strategy_registry import register


@dataclass
class PlacementStage(PipelineStage):
    """Adapter: wraps ``benders_placement()`` as a ``PipelineStage``.

    Reads a parsed PCB from ``StageInput.data``, calls the legacy
    placement function, and returns a ``StageOutput`` whose ``data``
    has ``.placements``, ``.iterations``, ``.cuts`` attributes.
    """

    name: str = "placement_template"
    requires: list[str] = None  # type: ignore[assignment]
    provides: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.requires is None:
            self.requires = []
        if self.provides is None:
            self.provides = []

    def run(self, input: StageInput) -> StageOutput:
        from temper_placer.placement.benders_loop import benders_placement

        parsed = input.data
        seed = getattr(input.meta, "seed", 42) if input.meta else 42
        strategy = "template"

        if input.meta and input.meta.trace_context:
            tc_strategy = input.meta.trace_context.get("strategy")
            if tc_strategy:
                strategy = tc_strategy

        result = benders_placement(parsed, strategy=strategy, seed=seed)
        return StageOutput(
            data=result,
            meta=input.meta,
        )


@dataclass
class RoutingStage(PipelineStage):
    """Adapter: wraps ``route_pcb()`` as a ``PipelineStage``.

    Reads a parsed PCB + placements from ``StageInput.data`` /
    ``trace_context``, calls the legacy routing function, and returns
    a ``StageOutput`` whose ``data`` has ``.completion_rate`` attribute.
    """

    name: str = "router_v6_full"
    requires: list[str] = None  # type: ignore[assignment]
    provides: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.requires is None:
            self.requires = []
        if self.provides is None:
            self.provides = []

    def run(self, input: StageInput) -> StageOutput:
        from temper_placer.router_v6 import route_pcb

        parsed = input.data
        seed = getattr(input.meta, "seed", 42) if input.meta else 42

        placements: dict[str, tuple[float, float]] = {}
        if input.meta and input.meta.trace_context:
            placements = input.meta.trace_context.get("placements", {}) or {}

        result = route_pcb(parsed, placements=placements, _seed=seed)
        return StageOutput(
            data=result,
            meta=input.meta,
        )


def _register() -> None:
    register("placement", "template", lambda: PlacementStage())
    register("routing", "router_v6_full", lambda: RoutingStage())


_register()
