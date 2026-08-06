"""Placement adapter — raises NotImplementedError post-JAX retirement.

Wave-4 Phase-5 R3-style record (see ``packages/temper-orchestration/VERIFICATION.md``):
a deprecated stub whose ``run()`` raises ``NotImplementedError`` (JAX
retirement) plus a registration side-effect. Nothing to migrate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.protocol import StageInput, StageOutput


class TemplatePlacementStage:
    """DEPRECATED: JAX-based placement removed. Use CP-SAT placer instead."""

    name = "placement/template"
    requires: list[str] = []
    provides: list[str] = ["placements"]
    contract = None

    def run(self, input: StageInput) -> StageOutput:
        raise NotImplementedError(
            "JAX-based placement (benders_loop) has been removed. "
            "Use the CP-SAT placer via temper_placer.placer.deterministic."
        )


def _register_placement_stages() -> None:
    from temper_placer.strategy_registry import register

    register("placement", "template", lambda: TemplatePlacementStage())


_register_placement_stages()
