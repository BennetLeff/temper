"""Placement adapter — retired with JAX optimizer (plan 2026-07-03-002 U5).

The ``benders_placement()`` function has been deleted as part of JAX
retirement. This adapter is preserved as a stub to avoid import errors
in modules that still reference it; it will be removed in a follow-up cleanup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.protocol import StageInput, StageOutput


class TemplatePlacementStage:
    """Stub — benders_placement has been deleted."""

    name = "placement/template"
    requires: list[str] = []
    provides: list[str] = ["placements"]
    contract = None

    def run(self, input: StageInput) -> StageOutput:
        raise NotImplementedError(
            "benders_placement has been removed (plan 2026-07-03-002 U5). "
            "Use CP-SAT placer instead."
        )
