"""Cost-field routing interface and FieldGate extension point.

U4 owns this interface so U8 (router) and U9 (loop) can depend on it without a
circular dependency.  The single field-passing contract bundles the flattened
cost array (float32, ``congestion_flat``-compatible shape) with a weight
multiplier for integration into A* ``f_score``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from temper_placer.fields.result import FieldResult
    from temper_placer.placer.cp_sat.gates import (
        BoardState,
        GateResult,
        GateStage,
        Violation,
    )


@dataclass(frozen=True, slots=True)
class CostFieldInput:
    """Field-passing contract for routing integration (U8, U9).

    Carries the flattened per-cell cost array and a weight multiplier that
    A* folds into ``f_score``:

        ``min(max_congestion_cost, 1 + log(1 + raw)) * weight``

    The ``cost_flat`` shape is ``(height_cells * width_cells,)`` float32,
    row-major (C-order) to match the A* ``r * cols + c`` cell-indexing scheme.
    """

    cost_flat: np.ndarray  # (height_cells * width_cells,) float32
    weight: float = 1.0


class FieldGate:
    """Abstract base for field-generating gates (U5 extension point).

    A ``FieldGate`` is a ``Gate`` subclass that computes a scalar field over
    the board grid and wraps the result in a ``FieldResult`` — composing the
    existing ``GateResult`` with the computed grid.

    Subclasses override ``compute_field()``; the default ``check()``
    delegates to ``compute_field()`` and strips the grid, returning a plain
    ``GateResult`` so the gate can participate in compound gate chains.

    U5 implements concrete gates (thermal, congestion, etc.) by subclassing
    this.  U8/U9 consume the ``CostFieldInput`` produced by
    ``FieldResult.to_cost_field_input()``.
    """

    stage: GateStage | None = None
    name: str = ""

    def compute_field(self, state: BoardState) -> FieldResult:
        """Compute the scalar field and return a fail-closed ``FieldResult``.

        Subclasses must override this.  The returned ``FieldResult`` must
        satisfy the fail-closed invariant: ``UNMEASURED`` → ``field=None``;
        ``CLEAN`` / ``VIOLATIONS`` → ``field`` is a non-None grid.
        """
        raise NotImplementedError

    def check(self, state: BoardState) -> GateResult:
        """Default ``Gate.check()`` — delegates to ``compute_field()``.

        Returns only the ``GateResult`` portion (stripping the grid) so this
        gate can participate in compound gate chains that only need the
        three-state status.  Subclasses may override for custom logic.
        """
        result = self.compute_field(state)
        return result.gate_result

    def to_delta(self, violation: Violation):
        """Map a violation to a constraint delta.

        Returns ``None`` by default; subclasses may override.
        """
        return None
