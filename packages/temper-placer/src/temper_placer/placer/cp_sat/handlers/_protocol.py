"""ConstraintHandler Protocol — structural subtyping interface for all 8 handler modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.model import ComponentVars

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import CpSatModel

# Assumption literal type alias (a CP-SAT Boolean variable).
AssumptionLiteral = cp_model.IntVar


@runtime_checkable
class ConstraintHandler(Protocol):
    """Protocol for a CP-SAT constraint encoder handler.

    Each handler encodes exactly one PCL constraint type into CP-SAT model
    constraints and returns a list of assumption literal indices for
    UNSAT-core extraction.
    """

    def __call__(
        self,
        constraint: object,
        components: dict[str, ComponentVars],
        model: CpSatModel,
        ctx: EncoderContext,
    ) -> list[AssumptionLiteral]:
        """Encode *constraint* into *model*, returning assumption literals."""
        ...
