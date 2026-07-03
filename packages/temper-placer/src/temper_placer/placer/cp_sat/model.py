"""U2: CP-SAT placement model for the temper placer.

Encodes component placement as integer-grid variables with NoOverlap2D and
side constraints, plus a soft wirelength/spread objective, and solves it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ortools.sat.python import cp_model


class SolveStatus(Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class SolveResult:
    status: SolveStatus
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    objective_value: Optional[float] = None
    solve_time_s: float = 0.0
    wall_time_s: float = 0.0


@dataclass
class SolveContext:
    """Mutable context built during model construction and consumed by encoder/audit.

    Carries component variable mappings so the encoder (U3) can add per-constraint
    variables and the audit (U4) can extract positions from solver output.
    """

    x_start: dict[str, cp_model.IntVar] = field(default_factory=dict)
    y_start: dict[str, cp_model.IntVar] = field(default_factory=dict)
    x_size: dict[str, int] = field(default_factory=dict)
    y_size: dict[str, int] = field(default_factory=dict)
    x_iv: dict[str, cp_model.IntervalVar] = field(default_factory=dict)
    y_iv: dict[str, cp_model.IntervalVar] = field(default_factory=dict)
    assumption_vars: list[cp_model.IntVar] = field(default_factory=list)
    scale_factor: int = 10
    objective_terms: list[cp_model.IntVar] = field(default_factory=list)


def _to_units(mm: float, scale: int) -> int:
    return int(mm * scale)


def _component_size_mm(ref: str, dim: int, components: dict) -> float:
    """Extract component dimension in mm from a component dict."""
    c = components[ref]
    w = c.get("width_mm", c.get("w", c.get("width", 0)))
    h = c.get("height_mm", c.get("h", c.get("height", 0)))
    return w if dim == 0 else h


def build_cp_sat_model(
    components: dict[str, dict],
    board_w_mm: float,
    board_h_mm: float,
    scale_factor: int = 10,
) -> tuple[cp_model.CpModel, SolveContext]:
    """Build the CP-SAT model with per-component variables and NoOverlap2D.

    Args:
        components: dict of {ref: {width_mm, height_mm}} or {ref: {w, h}}.
        board_w_mm: Board width in mm.
        board_h_mm: Board height in mm.
        scale_factor: Grid scale (units per mm). Default 10 = 0.1mm grid.

    Returns:
        (CpModel, SolveContext) tuple. The model has NoOverlap2D already added.
        Caller adds side constraints via the helper functions, then calls solve.
    """
    model = cp_model.CpModel()
    ctx = SolveContext(scale_factor=scale_factor)

    board_w = _to_units(board_w_mm, scale_factor)
    board_h = _to_units(board_h_mm, scale_factor)

    for ref in components:
        w_mm = _component_size_mm(ref, 0, components)
        h_mm = _component_size_mm(ref, 1, components)
        w = _to_units(w_mm, scale_factor)
        h = _to_units(h_mm, scale_factor)

        ctx.x_size[ref] = w
        ctx.y_size[ref] = h

        ctx.x_start[ref] = model.NewIntVar(0, max(0, board_w - w), f"x_{ref}")
        x_end = model.NewIntVar(w, board_w, f"x_end_{ref}")
        ctx.x_iv[ref] = model.NewIntervalVar(ctx.x_start[ref], w, x_end, f"xiv_{ref}")

        ctx.y_start[ref] = model.NewIntVar(0, max(0, board_h - h), f"y_{ref}")
        y_end = model.NewIntVar(h, board_h, f"y_end_{ref}")
        ctx.y_iv[ref] = model.NewIntervalVar(ctx.y_start[ref], h, y_end, f"yiv_{ref}")

    # R1: NoOverlap2D
    add_no_overlap(model, ctx)

    return model, ctx


def add_no_overlap(model: cp_model.CpModel, ctx: SolveContext) -> None:
    """R1: Pairwise non-overlap via NoOverlap2D global constraint."""
    x_ivs = [ctx.x_iv[r] for r in ctx.x_start]
    y_ivs = [ctx.y_iv[r] for r in ctx.y_start]
    if x_ivs and y_ivs:
        model.AddNoOverlap2D(x_ivs, y_ivs)


def add_chebyshev_clearance(
    model: cp_model.CpModel,
    ctx: SolveContext,
    pairs: list[tuple[str, str]],
    clearance_mm: float,
) -> None:
    """R2: Chebyshev (L∞) disjunctive clearance between component pairs.

    Uses 4-Boolean disjunctive encoding with a ×√2 safety factor for
    Euclidean DRC compliance. Each pair gets 4 Boolean vars + 5 constraints.

    Args:
        pairs: List of (comp_a, comp_b) tuples needing clearance.
        clearance_mm: Minimum Chebyshev distance in mm (e.g., 8.5mm = 6mm × √2).
    """
    clearance = _to_units(clearance_mm, ctx.scale_factor)

    for a, b in pairs:
        b_left = model.NewBoolVar(f"clr_left_{a}_{b}")
        b_right = model.NewBoolVar(f"clr_right_{a}_{b}")
        b_below = model.NewBoolVar(f"clr_below_{a}_{b}")
        b_above = model.NewBoolVar(f"clr_above_{a}_{b}")

        # a left of b: b starts at least (a_x + a_w + clearance) from left
        model.Add(
            ctx.x_start[b] >= ctx.x_start[a] + ctx.x_size[a] + clearance
        ).OnlyEnforceIf(b_left)
        # b left of a: a starts at least (b_x + b_w + clearance) from left
        model.Add(
            ctx.x_start[a] >= ctx.x_start[b] + ctx.x_size[b] + clearance
        ).OnlyEnforceIf(b_right)
        # a below b: b starts at least (a_y + a_h + clearance) from bottom
        model.Add(
            ctx.y_start[b] >= ctx.y_start[a] + ctx.y_size[a] + clearance
        ).OnlyEnforceIf(b_below)
        # b below a: a starts at least (b_y + b_h + clearance) from bottom
        model.Add(
            ctx.y_start[a] >= ctx.y_start[b] + ctx.y_size[b] + clearance
        ).OnlyEnforceIf(b_above)

        model.AddBoolOr([b_left, b_right, b_below, b_above])


def add_edge_anchoring(
    model: cp_model.CpModel,
    ctx: SolveContext,
    components: list[str],
    max_dist_mm: float,
    edge: str = "bottom",
) -> None:
    """R3: Constrain components to within max_dist_mm of a board edge.

    Args:
        components: Component references to anchor.
        max_dist_mm: Maximum distance from edge in mm.
        edge: One of 'left', 'right', 'bottom', 'top'.
    """
    max_d = _to_units(max_dist_mm, ctx.scale_factor)

    for ref in components:
        if edge == "left":
            model.Add(ctx.x_start[ref] <= max_d)
        elif edge == "right":
            # The board dimensions aren't stored in ctx; caller must handle
            # by adding a constraint with the board width passed separately.
            raise NotImplementedError(
                "Right-edge anchoring requires board width; pass via ctx or call directly."
            )
        elif edge == "bottom":
            model.Add(ctx.y_start[ref] <= max_d)
        elif edge == "top":
            raise NotImplementedError(
                "Top-edge anchoring requires board height; pass via ctx or call directly."
            )
        else:
            raise ValueError(f"Unknown edge: {edge}")


def add_proximity(
    model: cp_model.CpModel,
    ctx: SolveContext,
    pairs: list[tuple[str, str, float]],
) -> None:
    """R4: Pairwise linear proximity (adjacency).

    Encodes that two components must have Chebyshev bounding-box span
    within max_dist_mm of each other (4 linear inequalities per pair).

    Args:
        pairs: List of (comp_a, comp_b, max_distance_mm) tuples.
    """
    for a, b, max_dist_mm in pairs:
        max_d = _to_units(max_dist_mm, ctx.scale_factor)

        model.Add(ctx.x_start[b] <= ctx.x_start[a] + ctx.x_size[a] + max_d)
        model.Add(ctx.x_start[a] <= ctx.x_start[b] + ctx.x_size[b] + max_d)
        model.Add(ctx.y_start[b] <= ctx.y_start[a] + ctx.y_size[a] + max_d)
        model.Add(ctx.y_start[a] <= ctx.y_start[b] + ctx.y_size[b] + max_d)


def add_region_membership(
    model: cp_model.CpModel,
    ctx: SolveContext,
    components: list[str],
    region_x_min_mm: float,
    region_x_max_mm: float,
    region_y_min_mm: float,
    region_y_max_mm: float,
    margin_mm: float = 0.0,
) -> None:
    """R5: Constrain components to stay within a rectangular region.

    Args:
        components: Component references.
        region_*_mm: Region bounds in mm.
        margin_mm: Additional margin to shrink the region (inward).
    """
    x_min = _to_units(region_x_min_mm + margin_mm, ctx.scale_factor)
    x_max = _to_units(region_x_max_mm - margin_mm, ctx.scale_factor)
    y_min = _to_units(region_y_min_mm + margin_mm, ctx.scale_factor)
    y_max = _to_units(region_y_max_mm - margin_mm, ctx.scale_factor)

    for ref in components:
        model.Add(ctx.x_start[ref] >= x_min)
        model.Add(ctx.x_start[ref] + ctx.x_size[ref] <= x_max)
        model.Add(ctx.y_start[ref] >= y_min)
        model.Add(ctx.y_start[ref] + ctx.y_size[ref] <= y_max)


def add_soft_wirelength_objective(
    model: cp_model.CpModel,
    ctx: SolveContext,
    net_pairs: list[tuple[str, str]],
    spread_weight: float = 1.0,
) -> None:
    """R6: Soft wirelength + spread objective (tiebreaker).

    Minimizes sum of Manhattan center-to-center distances for listed pairs
    plus a small spread term (bounding-box diagonal).

    Args:
        net_pairs: List of (comp_a, comp_b) tuples representing net connections.
        spread_weight: Weight of the spread term relative to wirelength.
    """
    board_w = max(ctx.x_size[r] for r in ctx.x_size) * 2  # rough upper bound
    board_h = max(ctx.y_size[r] for r in ctx.y_size) * 2

    for a, b in net_pairs:
        dx = model.NewIntVar(0, board_w, f"dx_{a}_{b}")
        dy = model.NewIntVar(0, board_h, f"dy_{a}_{b}")

        cx_a = ctx.x_start[a] + ctx.x_size[a] // 2
        cx_b = ctx.x_start[b] + ctx.x_size[b] // 2
        cy_a = ctx.y_start[a] + ctx.y_size[a] // 2
        cy_b = ctx.y_start[b] + ctx.y_size[b] // 2

        model.Add(dx >= cx_a - cx_b)
        model.Add(dx >= cx_b - cx_a)
        model.Add(dy >= cy_a - cy_b)
        model.Add(dy >= cy_b - cy_a)

        ctx.objective_terms.append(dx)
        ctx.objective_terms.append(dy)

    # Bounding-box spread
    if ctx.x_start:
        refs = list(ctx.x_start.keys())
        x_min = model.NewIntVar(0, board_w, "x_min")
        x_max = model.NewIntVar(0, board_w, "x_max")
        y_min = model.NewIntVar(0, board_h, "y_min")
        y_max = model.NewIntVar(0, board_h, "y_max")

        for ref in refs:
            model.Add(x_min <= ctx.x_start[ref])
            model.Add(x_max >= ctx.x_start[ref] + ctx.x_size[ref])
            model.Add(y_min <= ctx.y_start[ref])
            model.Add(y_max >= ctx.y_start[ref] + ctx.y_size[ref])

        spread = (x_max - x_min) + (y_max - y_min)
        spread_scaled = model.NewIntVar(
            0, board_w + board_h, "spread_weighted"
        )
        model.AddMultiplicationEquality(
            spread_scaled, [spread, model.NewConstant(int(spread_weight))]
        )

        all_terms = ctx.objective_terms + [spread_scaled]
    else:
        all_terms = ctx.objective_terms

    if all_terms:
        model.Minimize(sum(all_terms))


def solve_cp_sat_model(
    model: cp_model.CpModel,
    ctx: SolveContext,
    timeout_s: float = 60.0,
    num_workers: int = 8,
    log_progress: bool = True,
) -> SolveResult:
    """Solve a built CP-SAT model and extract positions.

    Args:
        model: Built CpModel.
        ctx: SolveContext from build_cp_sat_model.
        timeout_s: Solver timeout in seconds.
        num_workers: Number of parallel search workers.
        log_progress: Whether to log search progress.

    Returns:
        SolveResult with status, positions dict, and timing.
    """
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_s
    solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = log_progress

    t0 = time.monotonic()
    status = solver.Solve(model)
    wall = time.monotonic() - t0

    status_map = {
        cp_model.OPTIMAL: SolveStatus.OPTIMAL,
        cp_model.FEASIBLE: SolveStatus.FEASIBLE,
        cp_model.INFEASIBLE: SolveStatus.INFEASIBLE,
        cp_model.UNKNOWN: SolveStatus.UNKNOWN,
    }
    solve_status = status_map.get(status, SolveStatus.UNKNOWN)

    positions = {}
    obj_value = None
    if solve_status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE):
        obj_value = solver.ObjectiveValue()
        for ref in ctx.x_start:
            x_mm = solver.Value(ctx.x_start[ref]) / ctx.scale_factor
            y_mm = solver.Value(ctx.y_start[ref]) / ctx.scale_factor
            positions[ref] = (round(x_mm, 1), round(y_mm, 1))

    return SolveResult(
        status=solve_status,
        positions=positions,
        objective_value=obj_value,
        solve_time_s=solver.WallTime(),
        wall_time_s=wall,
    )
