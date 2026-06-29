"""PathFinder-style per-cell congestion tensor (R11).

The 33% completion wall on ``temper.kicad_pcb`` is a structural
problem: the current sequential net-by-net A* doesn't know which
cells are "popular" until the net after the popular one tries
to route through the same channel.  PathFinder (McMurchie &
Ebeling, ICCAD 1995) solves this with a per-cell history cost:
each net's A* ``f_score`` is augmented with the history cost of
the cells it visits, so the next net naturally detours around
already-routed channels.

This module provides:

- :class:`CongestionTensor` — a 2D ``(rows, cols)`` float32 array
  storing per-cell usage counts.  Methods:
    - :meth:`increment` — bump the cells along a routed path
      (called after each successful net commit)
    - :meth:`cost` — read the cost at a cell, with cap and decay
      (called by A* at expansion time)
    - :meth:`reset` / :meth:`decay` — for the rare case of a
      global iteration loop (we use single-pass so this is
      a no-op for the closure test)

Cost formula (per the plan's tunable defaults):
    raw = usage_count
    cost = min(MAX_COST, 1.0 + log(1.0 + raw))
    # 1.0 at zero usage; grows logarithmically; capped at 100

In a hot path, the Numba A* inner loop reads
``congestion[cell_idx]`` per expansion and adds it to
``f_score``.  The cost is folded into ``g_score`` so it's
admissible only as a tie-breaker (logarithmic growth keeps
paths reasonable).

Decay (not used in the default single-pass closure test):
    ``decay(factor)`` multiplies all cells by ``factor``
    (e.g., 0.95) for the rare case of a global iteration
    loop where we want history to fade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Defaults per the closure-rate plan's tunable table.
MAX_COST = 100.0
DECAY_FACTOR = 0.95  # Used by the optional global-iteration loop


@dataclass
class CongestionTensor:
    """Per-cell congestion cost for A* f_score augmentation.

    Attributes:
        array: ``(rows, cols)`` float32 array of usage counts.
        max_cost: cap on the per-cell cost (default 100).
        weight: multiplier on the per-cell cost in the A* step
            (default 1.0).  Lower values make the history cost
            a gentle tie-breaker; higher values force aggressive
            detours.  Empirically 0.1 closes more nets than 1.0
            on the temper.kicad_pcb hard-nets (SPI/PWM/AC).
    """

    array: np.ndarray
    max_cost: float = MAX_COST
    weight: float = 1.0

    @classmethod
    def zeros(
        cls, rows: int, cols: int,
        max_cost: float = MAX_COST, weight: float = 1.0,
    ) -> CongestionTensor:
        return cls(
            array=np.zeros((rows, cols), dtype=np.float32),
            max_cost=max_cost, weight=weight,
        )

    def increment(self, row: int, col: int, weight: float = 1.0) -> None:
        """Add ``weight`` to a single cell's usage count."""
        self.array[row, col] = self.array[row, col] + weight

    def increment_path(
        self,
        coords: list[tuple[float, float]],
        grid,
        weight: float = 1.0,
    ) -> None:
        """Increment the cells touched by a routed path.

        Uses the grid's ``world_to_grid`` to map (x, y) world
        coordinates to (col, row) cell indices, and increments
        each cell along the path.  Skips out-of-bounds coords.
        """
        for x, y in coords:
            gx, gy = grid.world_to_grid(x, y)
            if 0 <= gx < self.array.shape[1] and 0 <= gy < self.array.shape[0]:
                self.array[gy, gx] = self.array[gy, gx] + weight

    def cost(self, row: int, col: int) -> float:
        """Read the per-cell cost.

        Cost is ``min(max_cost, 1.0 + log(1 + usage))``.  1.0 at zero
        usage; logarithmic growth; capped at ``max_cost``.
        """
        raw = float(self.array[row, col])
        if raw <= 0.0:
            return 1.0
        return min(self.max_cost, 1.0 + math.log1p(raw))

    def decay(self, factor: float = DECAY_FACTOR) -> None:
        """Multiply all cells by ``factor`` (used by the optional
        global-iteration loop in the plan's deferred variant).
        """
        self.array *= factor

    def reset(self) -> None:
        """Zero the tensor (used between global iterations)."""
        self.array.fill(0.0)
