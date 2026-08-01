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
    - :meth:`increment` — bump a single cell
    - :meth:`increment_path` — bump the cells along a routed path
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

Storage is the Rust ``CongestionTensor`` from the ``temper_geometry``
crate (see ``packages/temper-geometry/src/congestion_tensor.rs``);
this wrapper preserves the original Python API so router call sites
are unchanged.  ``array`` is a read-only numpy view re-copied from
Rust on every access — never cache it (per-net ``increment_path``
mutations happen between searches, so a cached array would silently
serve stale congestion).

Decay (not used in the default single-pass closure test):
    ``decay(factor)`` multiplies all cells by ``factor``
    (e.g., 0.95) for the rare case of a global iteration
    loop where we want history to fade.
"""

from __future__ import annotations

import numpy as np
import temper_geometry as _tg

# Defaults per the closure-rate plan's tunable table.
MAX_COST = 100.0
DECAY_FACTOR = 0.95  # Used by the optional global-iteration loop


class CongestionTensor:
    """Per-cell congestion cost for A* f_score augmentation.

    Attributes:
        array: ``(rows, cols)`` float32 array of usage counts
            (read-only view, re-copied from Rust on every access).
        max_cost: cap on the per-cell cost (default 100).
        weight: multiplier on the per-cell cost in the A* step
            (default 1.0).  Lower values make the history cost
            a gentle tie-breaker; higher values force aggressive
            detours.  Empirically 0.1 closes more nets than 1.0
            on the temper.kicad_pcb hard-nets (SPI/PWM/AC).
    """

    __slots__ = ("_rs",)

    def __init__(
        self,
        array=None,
        max_cost: float = MAX_COST,
        weight: float = 1.0,
    ) -> None:
        """Construct from a ``(rows, cols)`` float32 array (pre-migration
        dataclass API) or from an existing Rust instance (internal)."""
        if isinstance(array, _tg.CongestionTensor):
            self._rs = array
            return
        if array is None:
            raise TypeError("CongestionTensor requires an array or a Rust instance")
        arr = np.ascontiguousarray(array, dtype=np.float32)
        if arr.ndim != 2:
            raise ValueError(f"array must be 2-D, got shape {arr.shape}")
        rows, cols = arr.shape
        self._rs = _tg.CongestionTensor.zeros(rows, cols, max_cost, weight)
        self._rs.load_flat(arr.reshape(-1).tolist())

    @classmethod
    def zeros(
        cls,
        rows: int,
        cols: int,
        max_cost: float = MAX_COST,
        weight: float = 1.0,
    ) -> CongestionTensor:
        return cls(_tg.CongestionTensor.zeros(rows, cols, max_cost, weight))

    @property
    def array(self) -> np.ndarray:
        """(rows, cols) float32 view of the Rust storage — fresh copy."""
        flat = np.frombuffer(self._rs.to_flat_bytes(), dtype=np.float32)
        return flat.reshape((self._rs.rows, self._rs.cols))

    @property
    def max_cost(self) -> float:
        return self._rs.max_cost

    @max_cost.setter
    def max_cost(self, value: float) -> None:
        self._rs.max_cost = value

    @property
    def weight(self) -> float:
        return self._rs.weight

    @weight.setter
    def weight(self, value: float) -> None:
        self._rs.weight = value

    def increment(self, row: int, col: int, weight: float = 1.0) -> None:
        """Add ``weight`` to a single cell's usage count."""
        self._rs.increment(row, col, weight)

    def increment_path(
        self,
        coords: list[tuple[float, float]],
        grid,
        weight: float = 1.0,
    ) -> None:
        """Increment the cells touched by a routed path.

        Uses the grid's ``world_to_grid`` to map (x, y) world
        coordinates to (col, row) cell indices, and increments
        each cell along the path.  Out-of-bounds coords are
        skipped by the Rust batch method (mirroring the original
        numpy bounds check).
        """
        pairs: list[int] = []
        for x, y in coords:
            gx, gy = grid.world_to_grid(x, y)
            pairs.extend((gy, gx))
        self._rs.increment_cells(pairs, weight)

    def cost(self, row: int, col: int) -> float:
        """Read the per-cell cost.

        Cost is ``min(max_cost, 1.0 + log1p(usage))``.  1.0 at zero
        usage; logarithmic growth; capped at ``max_cost``.  Computed
        in f64 inside Rust (mirroring the original Python math), so
        the f32 result is bit-identical to the Python oracle.
        """
        return self._rs.cost(row, col)

    def decay(self, factor: float = DECAY_FACTOR) -> None:
        """Multiply all cells by ``factor`` (used by the optional
        global-iteration loop in the plan's deferred variant).
        """
        self._rs.decay(factor)

    def reset(self) -> None:
        """Zero the tensor (used between global iterations)."""
        self._rs.reset()
