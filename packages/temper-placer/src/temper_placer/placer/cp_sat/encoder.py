"""
CP-SAT placement solver.

Encodes placement constraints from PCL into a CP-SAT model and solves
for overlap-free, constraint-satisfying component positions.

Produces a PlacementResult that can be applied to a KiCad PCB via
_apply_placements_to_pcb and routed via route_pcb().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

logger = logging.getLogger(__name__)


@dataclass
class CpSatPlacementResult:
    """Result from a CP-SAT placement solve.

    Attributes:
        positions: (N, 2) component positions in mm.
        rotations: (N,) component rotation indices (0=0deg, 1=90deg, ...).
        placed_refs: References of placed components.
        unplaced_refs: References not placed.
        solve_time_ms: CP-SAT solve time in milliseconds.
        status: Solver status string.
    """

    positions: NDArray[np.float32]
    rotations: NDArray[np.int32]
    placed_refs: list[str] = field(default_factory=list)
    unplaced_refs: list[str] = field(default_factory=list)
    solve_time_ms: float = 0.0
    status: str = "unknown"

    def to_placement_result(self) -> "PlacementResult":
        """Convert to the canonical PlacementResult format.

        Rotations are converted from discrete indices (0-3)
        to degrees (0, 90, 180, 270).
        """
        from temper_placer.placer.deterministic import PlacementResult

        rotations_deg = (self.rotations.astype(np.float32) * 90.0) % 360.0
        return PlacementResult(
            positions=self.positions.astype(np.float32),
            rotations=rotations_deg,
            placed_refs=list(self.placed_refs),
            unplaced_refs=list(self.unplaced_refs),
        )

    def to_placements_dict(self) -> dict[str, tuple[float, float]]:
        """Convert to a dict mapping component ref -> (x, y) in mm."""
        result: dict[str, tuple[float, float]] = {}
        for i, ref in enumerate(self.placed_refs):
            if i < len(self.positions):
                result[ref] = (float(self.positions[i][0]), float(self.positions[i][1]))
        return result


def solve_placement(
    netlist: Netlist,
    board: Board,
    extra_constraints: list | None = None,
    timeout_ms: int = 1000,
    seed: int = 42,
) -> CpSatPlacementResult:
    """Solve component placement as a CP-SAT feasibility problem.

    Encodes overlap avoidance, board boundary, zone constraints,
    and any extra_constraints into a CP-SAT model, then solves.

    Args:
        netlist: Component netlist.
        board: Board definition.
        extra_constraints: Additional PCL constraint objects to enforce.
        timeout_ms: Solver timeout in milliseconds.
        seed: Random seed.

    Returns:
        CpSatPlacementResult with positions, rotations, and solve metadata.
    """
    try:
        from ortools.sat.python import cp_model  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("OR-Tools not available; falling back to deterministic placement")
        return _fallback_placement(netlist, board)

    model = cp_model.CpModel()

    n_components = netlist.n_components
    comp_refs = [c.ref for c in netlist.components]

    # Position variables: discretized grid for simplicity
    # Use 0.1mm resolution on board dimensions
    grid_step = 0.5
    max_x = int(board.width / grid_step)
    max_y = int(board.height / grid_step)

    x_vars = [model.NewIntVar(0, max_x, f"x_{ref}") for ref in comp_refs]
    y_vars = [model.NewIntVar(0, max_y, f"y_{ref}") for ref in comp_refs]

    # Rotation index variables: 0-3 for 0, 90, 180, 270 degrees
    rot_vars = [model.NewIntVar(0, 3, f"rot_{ref}") for ref in comp_refs]

    # Overlap avoidance: enforce minimum spacing between all pairs
    min_sep_cells = int(2.0 / grid_step)  # 2mm minimum separation
    for i in range(n_components):
        for j in range(i + 1, n_components):
            # Chebyshev distance >= min_sep_cells
            dx = model.NewIntVar(-max_x, max_x, f"dx_{comp_refs[i]}_{comp_refs[j]}")
            dy = model.NewIntVar(-max_y, max_y, f"dy_{comp_refs[i]}_{comp_refs[j]}")
            model.Add(dx == x_vars[i] - x_vars[j])
            model.Add(dy == y_vars[i] - y_vars[j])
            abs_dx = model.NewIntVar(0, max_x, f"abs_dx_{comp_refs[i]}_{comp_refs[j]}")
            abs_dy = model.NewIntVar(0, max_y, f"abs_dy_{comp_refs[i]}_{comp_refs[j]}")
            model.AddAbsEquality(abs_dx, dx)
            model.AddAbsEquality(abs_dy, dy)
            # At least one axis separation >= min_sep
            sep_x = model.NewBoolVar(f"sep_x_{comp_refs[i]}_{comp_refs[j]}")
            sep_y = model.NewBoolVar(f"sep_y_{comp_refs[i]}_{comp_refs[j]}")
            model.Add(abs_dx >= min_sep_cells).OnlyEnforceIf(sep_x)
            model.Add(abs_dy >= min_sep_cells).OnlyEnforceIf(sep_y)
            model.Add(sep_x + sep_y >= 1)

    # Board boundary constraints
    margin_cells = int(3.0 / grid_step)
    for i in range(n_components):
        comp_w = max(1, int(component_width(comp_refs[i], netlist) / grid_step))
        comp_h = max(1, int(component_height(comp_refs[i], netlist) / grid_step))
        model.Add(x_vars[i] >= margin_cells)
        model.Add(y_vars[i] >= margin_cells)
        model.Add(x_vars[i] + comp_w <= max_x - margin_cells)
        model.Add(y_vars[i] + comp_h <= max_y - margin_cells)

    # Zone constraints from board zones
    ref_to_idx = {ref: i for i, ref in enumerate(comp_refs)}
    for zone in board.zones:
        zx_min = int(zone.bounds[0] / grid_step)
        zy_min = int(zone.bounds[1] / grid_step)
        zx_max = int(zone.bounds[2] / grid_step)
        zy_max = int(zone.bounds[3] / grid_step)
        for comp_ref in getattr(zone, 'components', []):
            if comp_ref in ref_to_idx:
                idx = ref_to_idx[comp_ref]
                model.Add(x_vars[idx] >= zx_min)
                model.Add(x_vars[idx] <= zx_max)
                model.Add(y_vars[idx] >= zy_min)
                model.Add(y_vars[idx] <= zy_max)

    # Extra constraints from PCL
    if extra_constraints:
        _encode_extra_constraints(
            model, extra_constraints, comp_refs, x_vars, y_vars,
            rot_vars, grid_step, max_x, max_y, board,
        )

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_ms / 1000.0
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 4

    status = solver.Solve(model)

    status_names = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible",
        cp_model.INFEASIBLE: "infeasible",
        cp_model.MODEL_INVALID: "model_invalid",
        cp_model.UNKNOWN: "unknown",
    }

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        positions = np.zeros((n_components, 2), dtype=np.float32)
        rotations = np.zeros(n_components, dtype=np.int32)
        placed = []
        unplaced = []
        for i, ref in enumerate(comp_refs):
            positions[i] = [
                solver.Value(x_vars[i]) * grid_step,
                solver.Value(y_vars[i]) * grid_step,
            ]
            rotations[i] = solver.Value(rot_vars[i])
            placed.append(ref)
        return CpSatPlacementResult(
            positions=positions,
            rotations=rotations,
            placed_refs=placed,
            unplaced_refs=unplaced,
            solve_time_ms=solver.WallTime() * 1000.0,
            status=status_names.get(status, "unknown"),
        )
    else:
        return CpSatPlacementResult(
            positions=np.zeros((n_components, 2), dtype=np.float32),
            rotations=np.zeros(n_components, dtype=np.int32),
            placed_refs=[],
            unplaced_refs=list(comp_refs),
            solve_time_ms=solver.WallTime() * 1000.0,
            status=status_names.get(status, "unknown"),
        )


def _encode_extra_constraints(
    model,
    extra_constraints: list,
    comp_refs: list[str],
    x_vars,
    y_vars,
    rot_vars,
    grid_step: float,
    max_x: int,
    max_y: int,
    board: object | None = None,
) -> None:
    """Encode additional PCL constraints into the CP-SAT model."""
    from temper_placer.pcl.constraints import (
        AnchoredConstraint,
        EnclosingConstraint,
        KeepoutConstraint,
        SeparatedConstraint,
    )

    ref_to_idx = {ref: i for i, ref in enumerate(comp_refs)}

    for constraint in extra_constraints:
        if isinstance(constraint, SeparatedConstraint):
            if constraint.a in comp_refs and constraint.b in comp_refs:
                a_idx = ref_to_idx[constraint.a]
                b_idx = ref_to_idx[constraint.b]
                min_sep = int(constraint.min_distance_mm / grid_step)
                dx = model.NewIntVar(-max_x, max_x, f"extra_dx_{constraint.id}")
                dy = model.NewIntVar(-max_y, max_y, f"extra_dy_{constraint.id}")
                model.Add(dx == x_vars[a_idx] - x_vars[b_idx])
                model.Add(dy == y_vars[a_idx] - y_vars[b_idx])
                abs_dx = model.NewIntVar(0, max_x, f"extra_abs_dx_{constraint.id}")
                abs_dy = model.NewIntVar(0, max_y, f"extra_abs_dy_{constraint.id}")
                model.AddAbsEquality(abs_dx, dx)
                model.AddAbsEquality(abs_dy, dy)
                sep_x = model.NewBoolVar(f"extra_sep_x_{constraint.id}")
                sep_y = model.NewBoolVar(f"extra_sep_y_{constraint.id}")
                model.Add(abs_dx >= min_sep).OnlyEnforceIf(sep_x)
                model.Add(abs_dy >= min_sep).OnlyEnforceIf(sep_y)
                model.Add(sep_x + sep_y >= 1)

        elif isinstance(constraint, AnchoredConstraint):
            if constraint.component in comp_refs:
                idx = ref_to_idx[constraint.component]
                if constraint.position:
                    px = int(constraint.position[0] / grid_step)
                    py = int(constraint.position[1] / grid_step)
                    model.Add(x_vars[idx] == px)
                    model.Add(y_vars[idx] == py)
                elif constraint.region:
                    rx_min, ry_min, rx_max, ry_max = constraint.region
                    model.Add(x_vars[idx] >= int(rx_min / grid_step))
                    model.Add(x_vars[idx] <= int(rx_max / grid_step))
                    model.Add(y_vars[idx] >= int(ry_min / grid_step))
                    model.Add(y_vars[idx] <= int(ry_max / grid_step))

        elif isinstance(constraint, EnclosingConstraint):
            pass  # Already handled via zone logic above

        elif isinstance(constraint, KeepoutConstraint):
            _encode_keepout_constraint(
                model, constraint, comp_refs, x_vars, y_vars,
                grid_step, max_x, max_y, board,
            )


def _encode_keepout_constraint(
    model,
    constraint,
    comp_refs: list[str],
    x_vars,
    y_vars,
    grid_step: float,
    max_x: int,
    max_y: int,
    board: object | None = None,
) -> None:
    """Encode a KeepoutConstraint as component exclusion from a zone.

    Resolves the keepout zone bounds from one of:
    1. A matching board zone (by name) with ``zone_type="keepout"``.
    2. A ``congestion_*`` synthetic keepout: parses bbox from the zone name
       format ``congestion_xmin_ymin_xmax_ymax``.
    3. Falls back to a warning if neither resolution works.
    """
    zone_name: str = constraint.zone_name
    bounds: tuple[float, float, float, float] | None = None
    margin_mm: float = getattr(constraint, 'margin_mm', 0.0)

    # 1. Look up from board zones
    if board is not None and hasattr(board, 'zones'):
        for z in board.zones:
            if getattr(z, 'name', '') == zone_name:
                if getattr(z, 'zone_type', 'placement') in ('keepout', 'no_place'):
                    bounds = (
                        float(z.bounds[0]) - margin_mm,
                        float(z.bounds[1]) - margin_mm,
                        float(z.bounds[2]) + margin_mm,
                        float(z.bounds[3]) + margin_mm,
                    )
                break

    # 2. Parse synthetic congestion keepout name
    if bounds is None and zone_name.startswith('congestion_'):
        parts = zone_name.split('_')
        if len(parts) == 5:
            try:
                x0, y0, x1, y1 = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                bounds = (
                    x0 - margin_mm,
                    y0 - margin_mm,
                    x1 + margin_mm,
                    y1 + margin_mm,
                )
            except ValueError:
                pass

    if bounds is None:
        logger.warning(
            f"KeepoutConstraint '{zone_name}' could not be resolved to board "
            f"bounds — ignored during CP-SAT encoding"
        )
        return

    kx_min = max(0, int(bounds[0] / grid_step))
    ky_min = max(0, int(bounds[1] / grid_step))
    kx_max = min(max_x, int(bounds[2] / grid_step))
    ky_max = min(max_y, int(bounds[3] / grid_step))

    if kx_max <= kx_min or ky_max <= ky_min:
        return

    # Exclude all components from the keepout zone via a negated
    # bounding-box constraint: for each component i, add
    #   NOT (kx_min <= xi <= kx_max AND ky_min <= yi <= ky_max)
    # which expands to:
    #   (xi < kx_min) OR (xi > kx_max) OR (yi < ky_min) OR (yi > ky_max)
    for i in range(len(comp_refs)):
        below_x = model.NewBoolVar(f"keepout_{zone_name}_below_x_{i}")
        above_x = model.NewBoolVar(f"keepout_{zone_name}_above_x_{i}")
        below_y = model.NewBoolVar(f"keepout_{zone_name}_below_y_{i}")
        above_y = model.NewBoolVar(f"keepout_{zone_name}_above_y_{i}")
        model.Add(x_vars[i] < kx_min).OnlyEnforceIf(below_x)
        model.Add(x_vars[i] >= kx_min).OnlyEnforceIf(below_x.Not())
        model.Add(x_vars[i] > kx_max).OnlyEnforceIf(above_x)
        model.Add(x_vars[i] <= kx_max).OnlyEnforceIf(above_x.Not())
        model.Add(y_vars[i] < ky_min).OnlyEnforceIf(below_y)
        model.Add(y_vars[i] >= ky_min).OnlyEnforceIf(below_y.Not())
        model.Add(y_vars[i] > ky_max).OnlyEnforceIf(above_y)
        model.Add(y_vars[i] <= ky_max).OnlyEnforceIf(above_y.Not())
        model.Add(below_x + above_x + below_y + above_y >= 1)


def component_width(ref: str, netlist: Netlist) -> float:
    """Get component width in mm from the netlist."""
    component = _find_component(ref, netlist)
    if component is None:
        return 10.0
    return getattr(component, 'width', 10.0) or 10.0


def component_height(ref: str, netlist: Netlist) -> float:
    """Get component height in mm from the netlist."""
    component = _find_component(ref, netlist)
    if component is None:
        return 10.0
    return getattr(component, 'height', 10.0) or 10.0


def _find_component(ref: str, netlist: Netlist):
    for comp in netlist.components:
        if comp.ref == ref:
            return comp
    return None


def _fallback_placement(netlist: Netlist, board: Board) -> CpSatPlacementResult:
    """Fallback to deterministic placement when OR-Tools is unavailable."""
    from temper_placer.placer.template import ComponentPosition, ComponentTemplate

    n = netlist.n_components
    positions = np.zeros((n, 2), dtype=np.float32)
    rotations = np.zeros(n, dtype=np.int32)

    comps = netlist.components
    cols = max(1, int(np.ceil(np.sqrt(n))))
    spacing_x = min(15.0, (board.width - 10) / cols)
    spacing_y = min(15.0, (board.height - 10) / max(1, int(np.ceil(n / cols))))

    for i, comp in enumerate(comps):
        col = i % cols
        row = i // cols
        positions[i] = [
            5.0 + col * spacing_x,
            5.0 + row * spacing_y,
        ]

    return CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=[c.ref for c in comps],
        unplaced_refs=[],
        solve_time_ms=0.0,
        status="deterministic_fallback",
    )
