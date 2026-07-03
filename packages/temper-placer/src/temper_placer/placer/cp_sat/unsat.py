"""U7: UNSAT Core Extraction for the CP-SAT placer.

When CP-SAT returns INFEASIBLE, this module extracts the minimal conflicting
constraint set using assumption-based core extraction with deletion-based MUS
(Minimal Unsatisfiable Subset) refinement.

Key exports:
    - ``UnsatReport``: Dataclass carrying sufficient and minimal cores.
    - ``extract_unsat_core()``: Full extraction pipeline (sufficient core +
      MUS refinement).
    - ``refine_mus()``: Standalone deletion-based MUS refinement.

API note (OR-Tools 9.x):
    ``SufficientAssumptionsForInfeasibility()`` returns **variable proto
    indices** (the integer values from ``var.Index()``), not positions in
    the Python list.  This module maintains an internal reverse map from
    proto index → local list index to translate between the two domains.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from ortools.sat.python import cp_model


# ---------------------------------------------------------------------------
# U7.1 — Report dataclass
# ---------------------------------------------------------------------------


@dataclass
class UnsatReport:
    # @req(2026-07-03-001, R8): UNSAT as first-class output
    """Result of UNSAT core extraction.

    Attributes:
        sufficient_core:  Constraint descriptions from
            ``SufficientAssumptionsForInfeasibility`` — a subset of
            assumptions sufficient to explain the infeasibility.
        minimal_core:    After deletion-based MUS refinement — a *minimal*
            subset (no proper subset is still infeasible).  May equal
            ``sufficient_core`` when refinement was skipped or timed out.
        solve_count:     Number of CP-SAT solves performed during
            extraction (initial solve + MUS refinement iterations).
        wall_time_s:     Wall-clock time for the entire extraction.
        is_minimal:      ``True`` if MUS refinement ran to completion;
            ``False`` if it was cut short by ``mus_timeout_s``.
    """

    sufficient_core: list[str] = field(default_factory=list)
    minimal_core: list[str] = field(default_factory=list)
    solve_count: int = 0
    wall_time_s: float = 0.0
    is_minimal: bool = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_proto_index_map(
    assumption_vars: Sequence[cp_model.IntVar],
) -> dict[int, int]:
    """Build ``{proto_index: local_index}`` lookup.

    OR-Tools' ``SufficientAssumptionsForInfeasibility`` returns variable
    proto indices (from ``var.Index()``).  This map translates them back
    to positions in the ``assumption_vars`` list.
    """
    return {v.Index(): i for i, v in enumerate(assumption_vars)}


def _add_assumptions(
    model: cp_model.CpModel,
    assumption_vars: Sequence[cp_model.IntVar],
    local_indices: list[int],
) -> None:
    """Set assumptions on the model from a list of local indices.

    Clears existing assumptions first, then adds the specified subset.
    Uses the actual ``IntVar`` objects (not proto indices).
    """
    model.ClearAssumptions()
    for idx in local_indices:
        model.AddAssumption(assumption_vars[idx])


# ---------------------------------------------------------------------------
# U7.2 — MUS refinement (deletion-based)
# ---------------------------------------------------------------------------


def refine_mus(
    model: cp_model.CpModel,
    solver: cp_model.CpSolver,
    assumption_vars: Sequence[cp_model.IntVar],
    core_indices: list[int],
    mus_timeout_s: float = 30.0,
) -> tuple[list[int], int, bool]:
    # @req(2026-07-03-001, R8): MUS refinement
    """Deletion-based MUS refinement.

    Iterates over the assumptions in ``core_indices``, temporarily removes
    each, and re-solves.  If the model remains INFEASIBLE without that
    assumption, the assumption is redundant and removed permanently.  If it
    becomes FEASIBLE, the assumption is essential and retained.

    Args:
        model: The CP-SAT model (must have been built with assumption
            Booleans wired via ``OnlyEnforceIf`` on the gated constraints).
        solver: ``CpSolver`` instance (reused across re-solves).  Its
            parameters (timeout, workers) are honoured for each re-solve.
        assumption_vars: The full list of assumption Boolean variables —
            the same list that was passed (conceptually) to the initial solve.
        core_indices: **Local** indices (into ``assumption_vars``) to refine.
            These are *positions in the Python list*, not proto indices.
        mus_timeout_s: Hard wall-time budget for the refinement loop.
            If exceeded, refinement stops early and ``is_minimal=False``.

    Returns:
        ``(minimal_indices, solve_count, is_minimal)`` where
        ``minimal_indices`` is a subset of ``core_indices`` forming an MUS
        (local indices), ``solve_count`` is the number of re-solves
        performed, and ``is_minimal`` indicates whether refinement ran to
        completion.
    """
    deadline = time.monotonic() + mus_timeout_s
    refined = list(core_indices)
    solve_count = 0  # caller's initial solve is not counted here
    is_minimal = True

    i = 0
    while i < len(refined):
        if time.monotonic() >= deadline:
            is_minimal = False
            break

        # Build local-index list without this candidate.
        test_indices = [refined[j] for j in range(len(refined)) if j != i]

        solve_count += 1
        _add_assumptions(model, assumption_vars, test_indices)
        status = solver.Solve(model)

        if status == cp_model.INFEASIBLE:
            # This assumption is redundant — remove it permanently.
            refined.pop(i)
            # Do NOT increment i: the next element shifts into position i.
        else:
            # Essential — keep it and move on.
            i += 1

    return refined, solve_count, is_minimal


# ---------------------------------------------------------------------------
# U7.3 — Core extraction entry-point
# ---------------------------------------------------------------------------


def extract_unsat_core(
    solver: cp_model.CpSolver,
    model: cp_model.CpModel,
    assumption_vars: Sequence[cp_model.IntVar],
    constraint_map: dict[int, str],
    mus_timeout_s: float = 30.0,
) -> UnsatReport:
    # @req(2026-07-03-001, R8): UNSAT as first-class output
    """Extract an UNSAT core from an infeasible CP-SAT model.

    The model is assumed to contain assumption Boolean variables that are
    wired to individual constraint groups via ``OnlyEnforceIf``, and the
    caller has populated ``constraint_map`` with human-readable descriptions.

    Workflow:
        1. Solve with **all** assumptions forced to ``True``.
        2. If the result is not INFEASIBLE, raise ``ValueError``.
        3. Retrieve the *sufficient* core via
           ``solver.SufficientAssumptionsForInfeasibility()`` and translate
           proto indices to local indices.
        4. Refine to a *minimal* core (MUS) via deletion-based refinement
           (``refine_mus``).

    Args:
        solver: ``CpSolver`` instance.  Its parameters (timeout, workers,
            log settings) are honoured for all solves.
        model: The built CP-SAT model with gated assumption variables.
        assumption_vars: Sequence of Boolean assumption variables, each
            gating one constraint group via ``OnlyEnforceIf``.
        constraint_map: Maps each **local index** in ``assumption_vars``
            to a human-readable constraint description (e.g. the PCL
            ``because`` field or a short identifier).
        mus_timeout_s: Wall-time budget for the MUS refinement loop.
            Default 30 seconds.

    Returns:
        ``UnsatReport`` with sufficient and minimal cores.

    Raises:
        ValueError: If the model is **not** INFEASIBLE when all
            assumptions are enabled.
    """
    t0 = time.monotonic()

    # Pre-build the proto-index → local-index reverse map.
    proto_to_local = _build_proto_index_map(assumption_vars)

    # ── Step 1: initial solve with all assumptions ───────────────────
    all_indices = list(range(len(assumption_vars)))
    _add_assumptions(model, assumption_vars, all_indices)
    status = solver.Solve(model)
    solve_count = 1

    if status != cp_model.INFEASIBLE:
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            raise ValueError(
                f"Cannot extract UNSAT core: model is {solver.StatusName(status)} "
                f"with all assumptions enabled — the problem is satisfiable."
            )
        raise ValueError(
            f"Cannot extract UNSAT core: solver returned "
            f"{solver.StatusName(status)} (expected INFEASIBLE). "
            f"This may indicate a timeout or unknown status."
        )

    # ── Step 2: sufficient core ─────────────────────────────────────
    # SufficientAssumptionsForInfeasibility returns proto indices.
    # Translate them to local indices before looking up in constraint_map.
    proto_indices: list[int] = list(
        solver.SufficientAssumptionsForInfeasibility()
    )
    sufficient_local_indices = sorted(
        proto_to_local[pi] for pi in proto_indices if pi in proto_to_local
    )
    sufficient_core = [
        constraint_map[i] for i in sufficient_local_indices if i in constraint_map
    ]

    # ── Step 3: MUS refinement (works with local indices) ───────────
    refined_indices, re_solves, is_minimal = refine_mus(
        model=model,
        solver=solver,
        assumption_vars=assumption_vars,
        core_indices=sufficient_local_indices,
        mus_timeout_s=mus_timeout_s,
    )
    solve_count += re_solves

    minimal_core = [
        constraint_map[i] for i in refined_indices if i in constraint_map
    ]

    wall_time = time.monotonic() - t0

    return UnsatReport(
        sufficient_core=sufficient_core,
        minimal_core=minimal_core,
        solve_count=solve_count,
        wall_time_s=wall_time,
        is_minimal=is_minimal,
    )
