"""Pre-registration records for physics-validation fields.

Provides pydantic models, YAML loading with temporal gating, and the
frozen thermal pre-registration record.  U10 reads the loaded manifest
to gate field results against pre-registered pass bars and cost budgets.
"""

from temper_placer.validation.prereg.schema import (
    BecauseThreshold,
    CheapBaseline,
    CostBudget,
    FieldPreregistration,
    KillCriterion,
    ParametricRange,
    PassBar,
    PreregistrationManifest,
    StructuralBoundingCase,
)

__all__ = [
    "BecauseThreshold",
    "CheapBaseline",
    "CostBudget",
    "FieldPreregistration",
    "KillCriterion",
    "ParametricRange",
    "PassBar",
    "PreregistrationManifest",
    "StructuralBoundingCase",
]
