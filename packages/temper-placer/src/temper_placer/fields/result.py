"""FieldResult — fail-closed composition of GateResult + per-cell cost grid.

The FieldResult wraps the existing three-state GateResult contract
(GateStatus{CLEAN|VIOLATIONS|UNMEASURED}) and adds the computed scalar grid.
The fail-closed invariant ensures no code path can silently convert a
failed/UNMEASURED field into a usable flat/zero field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from temper_placer.fields.field import CostField
    from temper_placer.placer.cp_sat.gates import GateResult


class FieldNotReadyError(Exception):
    """Raised when a caller tries to use a field that is not in a usable state."""


@dataclass(frozen=True)
class FieldResult:
    """Fail-closed wrapper around a ``GateResult`` that also carries the cost grid.

    Invariants (enforced at construction):

    - ``CLEAN`` or ``VIOLATIONS`` → ``field`` must be a non-None ``(h, w)`` array.
    - ``UNMEASURED`` → ``field`` must be ``None``; there is **no** code path that
      silently substitutes a zero/flat grid.

    Callers that need the routing-format cost data call ``to_cost_field_input()``,
    which raises ``FieldNotReadyError`` when the status is ``UNMEASURED``.

    ``field`` is typed as a union rather than plain ``np.ndarray`` because
    both shapes are real, not aspirational: every CLEAN/VIOLATIONS producer
    in this codebase (``thermal_fdm.solve_thermal_fdm``, ...) constructs a
    ``CostField`` wrapper carrying ``.grid``/``.cell_size_mm``/``.origin_mm``
    plus a ``.to_flat()`` method, and ``to_cost_field_input()`` below
    branches on ``hasattr(self.field, "to_flat")`` specifically to also
    accept a bare ``np.ndarray`` (falling back to ``.ravel()``). Narrowing
    this to ``CostField`` alone would be a fix for the type checker at the
    cost of describing a contract this class does not actually enforce.
    """

    gate_result: GateResult
    field: CostField | np.ndarray | None = None
    weight: float = 1.0

    def __post_init__(self) -> None:
        from temper_placer.placer.cp_sat.gates import GateStatus

        if self.gate_result.status is GateStatus.UNMEASURED:
            if self.field is not None:
                raise ValueError(
                    "UNMEASURED FieldResult must have field=None (no silent zero/fallback grid)"
                )
        else:
            if self.field is None:
                raise ValueError(
                    f"FieldResult with status {self.gate_result.status} "
                    "requires a non-None field (no silent-flat path)"
                )

    @property
    def is_usable(self) -> bool:
        """``True`` when the field may be consumed by routing (CLEAN or VIOLATIONS)."""
        from temper_placer.placer.cp_sat.gates import GateStatus

        return self.gate_result.status is not GateStatus.UNMEASURED

    @property
    def status(self):
        """Shortcut to the wrapped ``GateStatus``."""
        return self.gate_result.status

    @property
    def violations(self):
        """Shortcut to the wrapped violations tuple."""
        return self.gate_result.violations

    @property
    def error_message(self) -> str:
        """Shortcut to the wrapped error message (only populated for UNMEASURED)."""
        return self.gate_result.error_message

    def to_cost_field_input(self):
        """Return the ``CostFieldInput`` for routing if usable; raise otherwise.

        Raises:
            FieldNotReadyError: when the wrapped status is ``UNMEASURED``.
        """
        from temper_placer.fields.interface import CostFieldInput

        if not self.is_usable:
            raise FieldNotReadyError(
                f"FieldResult is UNMEASURED: {self.gate_result.error_message or 'unknown'}"
            )
        import numpy as np

        if hasattr(self.field, "to_flat"):
            cost_flat = self.field.to_flat()
        else:
            cost_flat = np.ascontiguousarray(self.field.ravel()).astype(np.float32)
        return CostFieldInput(cost_flat=cost_flat, weight=self.weight)
