"""Cost-field abstraction for physics-informed routing.

Provides a generic scalar-field-over-board type (``CostField``) and a
fail-closed ``FieldResult`` that wraps the existing ``GateResult``
three-state contract to carry both the gate status and the per-cell cost
grid.  No code path can silently convert a failed/UNMEASURED field into a
usable flat/zero field.

U4 owns the cost-field routing interface (``CostFieldInput``) so U8 (router)
and U9 (loop) both depend on it without a circular dependency.

``FieldGate`` is the abstract extension point for U5 (concrete field gates:
thermal, congestion, etc.).
"""

from temper_placer.fields.field import CostField
from temper_placer.fields.interface import CostFieldInput, FieldGate
from temper_placer.fields.result import FieldNotReadyError, FieldResult

__all__ = [
    "CostField",
    "CostFieldInput",
    "FieldGate",
    "FieldNotReadyError",
    "FieldResult",
]
