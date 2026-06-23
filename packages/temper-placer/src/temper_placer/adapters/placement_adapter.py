"""Placement adapter — wraps ``benders_placement()`` as a ``PipelineStage``.

Registers the ``"template"`` strategy under phase ``"placement"`` so
``resolve_and_run`` can dispatch placement without coupling to ``benders_loop``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.protocol import PipelineStage, StageInput, StageOutput


class TemplatePlacementStage:
    """Wraps ``benders_placement(strategy="template")`` as a PipelineStage."""

    name = "placement/template"
    requires: list[str] = []
    provides: list[str] = ["placements"]
    contract = None

    def run(self, input: StageInput) -> StageOutput:
        from temper_placer.protocol import StageOutput
        from temper_placer.placement.benders_loop import benders_placement

        parsed = input.data
        seed = input.meta.seed
        result = benders_placement(parsed, seed, strategy="template")
        return StageOutput(data=result, meta=input.meta)


def _register_placement_stages() -> None:
    from temper_placer.strategy_registry import register

    register("placement", "template", lambda: TemplatePlacementStage())


_register_placement_stages()
