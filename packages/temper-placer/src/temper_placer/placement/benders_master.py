"""
Benders Master Problem: ILP formulation for placement optimization.

This module implements the Master Problem of a Benders decomposition approach
for achieving provably routable PCB placements. The ILP encodes:
  - Component positions (continuous variables)
  - Non-overlap constraints (disjunctive with binary variables)
  - Board boundary constraints
  - HV clearance constraints
  - Fixed component positions
  - Routability cuts (added iteratively from Max-Flow subproblem)

The objective minimizes total movement from initial placement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ortools.linear_solver import pywraplp

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class ComponentData:
    """Component placement data."""
    ref: str
    width_mm: float
    height_mm: float
    x_mm: float  # Initial X position (center-based)
    y_mm: float  # Initial Y position (center-based)
    classification: str  # FIXED, HV, FREE
    hv_nets: list[str] = field(default_factory=list)


@dataclass
class BoardData:
    """Board dimensions."""
    width_mm: float
    height_mm: float
    origin_x: float = 0.0
    origin_y: float = 0.0


@dataclass
class PlacementConstraints:
    """Configuration for placement constraints."""

    # Manufacturing clearance between all components
    min_component_clearance_mm: float = 0.2

    # HV clearance requirements
    hv_clearance_mm: float = 3.0  # HighVoltage to LV
    ac_clearance_mm: float = 6.0  # ACMains to LV

    # Movement budget
    max_single_movement_mm: float = 15.0
    max_total_movement_mm: float = 100.0

    # Component grouping (IC -> [capacitors])
    grouping_constraints: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    # Example: {"U_MCU": [("C_MCU_1", 5.0), ("C_MCU_2", 5.0)]}

    # Zone constraints: component -> (axis, direction, limit)
    # axis: 'x' or 'y', direction: 'min' or 'max'
    zone_constraints: dict[str, list[tuple[str, str, float]]] = field(default_factory=dict)
    # Example: {"Q1": [("y", "max", 20.0)]}  # Q1.y <= 20.0


@dataclass
class BendersMasterResult:
    """Result from solving the master problem."""
    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, etc.
    objective_value: float
    positions: dict[str, tuple[float, float]]  # ref -> (x, y)
    movements: dict[str, float]  # ref -> L1 movement
    solve_time_sec: float
    iteration: int = 0


class BendersMasterProblem:
    """
    ILP Master Problem for Benders decomposition placement optimization.

    Uses OR-Tools with SCIP backend for mixed-integer programming.
    """

    BIG_M = 300.0  # Board diagonal is ~180mm, so 300mm is safely large

    def __init__(
        self,
        components: list[ComponentData],
        board: BoardData,
        constraints: PlacementConstraints | None = None,
    ):
        self.components = {c.ref: c for c in components}
        self.board = board
        self.constraints = constraints or PlacementConstraints()

        # Component indices for constraint generation
        self._comp_list = list(self.components.values())
        self._n = len(self._comp_list)

        # Solver and variables (created in build())
        self._solver: pywraplp.Solver | None = None
        self._x: dict[str, pywraplp.Variable] = {}
        self._y: dict[str, pywraplp.Variable] = {}
        self._delta_x: dict[str, pywraplp.Variable] = {}
        self._delta_y: dict[str, pywraplp.Variable] = {}

        # Binary variables for disjunctive non-overlap
        self._b_left: dict[tuple[str, str], pywraplp.Variable] = {}
        self._b_right: dict[tuple[str, str], pywraplp.Variable] = {}
        self._b_above: dict[tuple[str, str], pywraplp.Variable] = {}
        self._b_below: dict[tuple[str, str], pywraplp.Variable] = {}

        # Cut constraints (added iteratively)
        self._cuts: list[pywraplp.Constraint] = []

    def build(self) -> None:
        """Build the ILP model with all base constraints."""
        self._solver = pywraplp.Solver.CreateSolver("SCIP")
        if not self._solver:
            raise RuntimeError("SCIP solver not available")

        # 1. Create position variables
        self._create_position_variables()

        # 2. Add board boundary constraints
        self._add_board_bounds()

        # 3. Add fixed component constraints
        self._add_fixed_constraints()

        # 4. Add non-overlap constraints
        self._add_non_overlap_constraints()

        # 5. Add HV clearance constraints
        self._add_hv_clearance_constraints()

        # 6. Add zone constraints
        self._add_zone_constraints()

        # 7. Add grouping constraints
        self._add_grouping_constraints()

        # 8. Add movement budget constraints
        self._add_movement_constraints()

        # 9. Set objective (minimize total movement)
        self._set_objective()

    def _create_position_variables(self) -> None:
        """Create continuous position variables for all components."""
        solver = self._solver

        for comp in self._comp_list:
            ref = comp.ref

            # Position variables (center-based coordinates)
            self._x[ref] = solver.NumVar(
                -solver.infinity(), solver.infinity(), f"x_{ref}"
            )
            self._y[ref] = solver.NumVar(
                -solver.infinity(), solver.infinity(), f"y_{ref}"
            )

            # Movement auxiliary variables (for L1 norm)
            self._delta_x[ref] = solver.NumVar(0, solver.infinity(), f"dx_{ref}")
            self._delta_y[ref] = solver.NumVar(0, solver.infinity(), f"dy_{ref}")

            # |x - x0| <= delta_x linearization
            # x - x0 <= delta_x
            solver.Add(self._x[ref] - comp.x_mm <= self._delta_x[ref])
            # -(x - x0) <= delta_x
            solver.Add(-(self._x[ref] - comp.x_mm) <= self._delta_x[ref])

            # |y - y0| <= delta_y linearization
            solver.Add(self._y[ref] - comp.y_mm <= self._delta_y[ref])
            solver.Add(-(self._y[ref] - comp.y_mm) <= self._delta_y[ref])

    def _add_board_bounds(self) -> None:
        """Add constraints to keep components within board boundaries."""
        solver = self._solver
        board = self.board

        for comp in self._comp_list:
            ref = comp.ref
            w = comp.width_mm
            h = comp.height_mm

            # Component center must be at least w/2 from left edge
            solver.Add(self._x[ref] >= board.origin_x + w / 2)
            # And at most board_width - w/2 from right edge
            solver.Add(self._x[ref] <= board.origin_x + board.width_mm - w / 2)

            # Same for Y
            solver.Add(self._y[ref] >= board.origin_y + h / 2)
            solver.Add(self._y[ref] <= board.origin_y + board.height_mm - h / 2)

    def _add_fixed_constraints(self) -> None:
        """Fix positions for FIXED components (connectors, mounting holes)."""
        solver = self._solver

        for comp in self._comp_list:
            if comp.classification == "FIXED":
                solver.Add(self._x[comp.ref] == comp.x_mm)
                solver.Add(self._y[comp.ref] == comp.y_mm)

    def _add_non_overlap_constraints(self) -> None:
        """
        Add disjunctive non-overlap constraints using Big-M formulation.

        For each pair (i, j), at least one of these must hold:
          - i is left of j:  x_i + w_i/2 + clearance <= x_j - w_j/2
          - i is right of j: x_j + w_j/2 + clearance <= x_i - w_i/2
          - i is below j:    y_i + h_i/2 + clearance <= y_j - h_j/2
          - i is above j:    y_j + h_j/2 + clearance <= y_i - h_i/2
        """
        solver = self._solver
        M = self.BIG_M
        clearance = self.constraints.min_component_clearance_mm

        # Only create constraints for movable pairs
        movable = [c for c in self._comp_list if c.classification != "FIXED"]

        for i, comp_i in enumerate(movable):
            for comp_j in movable[i + 1:]:
                ref_i, ref_j = comp_i.ref, comp_j.ref

                # Binary variables for this pair
                b_left = solver.BoolVar(f"b_left_{ref_i}_{ref_j}")
                b_right = solver.BoolVar(f"b_right_{ref_i}_{ref_j}")
                b_above = solver.BoolVar(f"b_above_{ref_i}_{ref_j}")
                b_below = solver.BoolVar(f"b_below_{ref_i}_{ref_j}")

                self._b_left[(ref_i, ref_j)] = b_left
                self._b_right[(ref_i, ref_j)] = b_right
                self._b_above[(ref_i, ref_j)] = b_above
                self._b_below[(ref_i, ref_j)] = b_below

                w_i, h_i = comp_i.width_mm, comp_i.height_mm
                w_j, h_j = comp_j.width_mm, comp_j.height_mm

                # x_i + w_i/2 + clearance <= x_j - w_j/2 + M(1 - b_left)
                solver.Add(
                    self._x[ref_i] + w_i / 2 + clearance
                    <= self._x[ref_j] - w_j / 2 + M * (1 - b_left)
                )

                # x_j + w_j/2 + clearance <= x_i - w_i/2 + M(1 - b_right)
                solver.Add(
                    self._x[ref_j] + w_j / 2 + clearance
                    <= self._x[ref_i] - w_i / 2 + M * (1 - b_right)
                )

                # y_i + h_i/2 + clearance <= y_j - h_j/2 + M(1 - b_below)
                solver.Add(
                    self._y[ref_i] + h_i / 2 + clearance
                    <= self._y[ref_j] - h_j / 2 + M * (1 - b_below)
                )

                # y_j + h_j/2 + clearance <= y_i - h_i/2 + M(1 - b_above)
                solver.Add(
                    self._y[ref_j] + h_j / 2 + clearance
                    <= self._y[ref_i] - h_i / 2 + M * (1 - b_above)
                )

                # At least one separation must hold
                solver.Add(b_left + b_right + b_above + b_below >= 1)

    def _add_hv_clearance_constraints(self) -> None:
        """
        Add clearance constraints between HV and LV components.

        Uses L1-norm approximation of Euclidean distance.
        """
        solver = self._solver

        # Identify HV and LV components
        hv_components = [c for c in self._comp_list if c.classification == "HV" or c.hv_nets]
        lv_components = [c for c in self._comp_list if c.classification not in ("HV", "FIXED") and not c.hv_nets]

        for hv in hv_components:
            # Determine clearance requirement
            has_ac = any(n in ("AC_L", "AC_N", "PE") for n in hv.hv_nets)
            clearance = self.constraints.ac_clearance_mm if has_ac else self.constraints.hv_clearance_mm

            for lv in lv_components:
                # L1-norm approximation: |dx| + |dy| >= clearance * sqrt(2)
                # This is conservative (L1 >= L2 when scaled properly)
                l1_clearance = clearance * 1.414  # sqrt(2)

                # Add auxiliary variables for absolute differences
                dx = solver.NumVar(0, self.BIG_M, f"dx_{hv.ref}_{lv.ref}")
                dy = solver.NumVar(0, self.BIG_M, f"dy_{hv.ref}_{lv.ref}")

                # |x_hv - x_lv| <= dx
                solver.Add(self._x[hv.ref] - self._x[lv.ref] <= dx)
                solver.Add(self._x[lv.ref] - self._x[hv.ref] <= dx)

                # |y_hv - y_lv| <= dy
                solver.Add(self._y[hv.ref] - self._y[lv.ref] <= dy)
                solver.Add(self._y[lv.ref] - self._y[hv.ref] <= dy)

                # dx + dy >= l1_clearance
                solver.Add(dx + dy >= l1_clearance)

    def _add_zone_constraints(self) -> None:
        """Add zone constraints (thermal, EMC boundaries)."""
        solver = self._solver

        for ref, constraints in self.constraints.zone_constraints.items():
            if ref not in self._x:
                continue
            for axis, direction, limit in constraints:
                if axis == "x":
                    var = self._x[ref]
                else:
                    var = self._y[ref]

                if direction == "max":
                    solver.Add(var <= limit)
                else:  # min
                    solver.Add(var >= limit)

    def _add_grouping_constraints(self) -> None:
        """Add component grouping constraints (IC to decoupling caps)."""
        solver = self._solver

        for ic_ref, group in self.constraints.grouping_constraints.items():
            if ic_ref not in self._x:
                continue
            for cap_ref, max_dist in group:
                if cap_ref not in self._x:
                    continue

                # L1 distance constraint: |dx| + |dy| <= max_dist
                dx = solver.NumVar(0, self.BIG_M, f"grp_dx_{ic_ref}_{cap_ref}")
                dy = solver.NumVar(0, self.BIG_M, f"grp_dy_{ic_ref}_{cap_ref}")

                solver.Add(self._x[ic_ref] - self._x[cap_ref] <= dx)
                solver.Add(self._x[cap_ref] - self._x[ic_ref] <= dx)
                solver.Add(self._y[ic_ref] - self._y[cap_ref] <= dy)
                solver.Add(self._y[cap_ref] - self._y[ic_ref] <= dy)

                solver.Add(dx + dy <= max_dist)

    def _add_movement_constraints(self) -> None:
        """Add per-component and global movement budget constraints."""
        solver = self._solver

        # Per-component maximum movement
        max_single = self.constraints.max_single_movement_mm
        for comp in self._comp_list:
            if comp.classification == "FIXED":
                continue
            solver.Add(
                self._delta_x[comp.ref] + self._delta_y[comp.ref] <= max_single
            )

        # Global movement budget
        max_total = self.constraints.max_total_movement_mm
        total_movement = solver.Sum([
            self._delta_x[c.ref] + self._delta_y[c.ref]
            for c in self._comp_list
            if c.classification != "FIXED"
        ])
        solver.Add(total_movement <= max_total)

    def _set_objective(self) -> None:
        """Set objective to minimize weighted total movement."""
        solver = self._solver

        # Weight factors by component type
        weights = {
            "HV": 1.5,
            "FREE": 1.0,
            "FIXED": 0.0,  # Won't contribute anyway
        }

        objective = solver.Sum([
            weights.get(c.classification, 1.0) * (self._delta_x[c.ref] + self._delta_y[c.ref])
            for c in self._comp_list
            if c.classification != "FIXED"
        ])

        solver.Minimize(objective)

    def add_routability_cut(self, cut_type: str, components: list[str], gap_required: float) -> None:
        """
        Add a routability cut from Max-Flow analysis.

        Args:
            cut_type: "horizontal" or "vertical"
            components: List of component refs involved in the bottleneck
            gap_required: Minimum channel width needed (mm)
        """
        if len(components) < 2:
            return

        solver = self._solver

        # For horizontal bottleneck, require horizontal separation
        # For vertical bottleneck, require vertical separation
        if cut_type == "horizontal":
            # Find leftmost and rightmost components
            # Require: x_right - x_left >= gap_required + (w_left + w_right) / 2
            c1, c2 = components[0], components[1]
            if c1 in self._x and c2 in self._x:
                w1 = self.components[c1].width_mm
                w2 = self.components[c2].width_mm
                constraint = solver.Add(
                    self._x[c2] - self._x[c1] >= gap_required + (w1 + w2) / 2
                )
                self._cuts.append(constraint)
        else:  # vertical
            c1, c2 = components[0], components[1]
            if c1 in self._y and c2 in self._y:
                h1 = self.components[c1].height_mm
                h2 = self.components[c2].height_mm
                constraint = solver.Add(
                    self._y[c2] - self._y[c1] >= gap_required + (h1 + h2) / 2
                )
                self._cuts.append(constraint)

    def solve(self, time_limit_sec: float = 60.0, iteration: int = 0) -> BendersMasterResult:
        """
        Solve the ILP master problem.

        Args:
            time_limit_sec: Maximum solve time
            iteration: Current Benders iteration (for logging)

        Returns:
            BendersMasterResult with solution data
        """
        solver = self._solver
        solver.SetTimeLimit(int(time_limit_sec * 1000))

        import time
        start = time.time()
        status_code = solver.Solve()
        solve_time = time.time() - start

        status_map = {
            pywraplp.Solver.OPTIMAL: "OPTIMAL",
            pywraplp.Solver.FEASIBLE: "FEASIBLE",
            pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
            pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
            pywraplp.Solver.ABNORMAL: "ABNORMAL",
            pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
        }
        status = status_map.get(status_code, "UNKNOWN")

        if status in ("OPTIMAL", "FEASIBLE"):
            positions = {
                ref: (self._x[ref].solution_value(), self._y[ref].solution_value())
                for ref in self._x
            }
            movements = {
                ref: (self._delta_x[ref].solution_value() + self._delta_y[ref].solution_value())
                for ref in self._delta_x
            }
            obj_value = solver.Objective().Value()
        else:
            positions = {}
            movements = {}
            obj_value = float("inf")

        return BendersMasterResult(
            status=status,
            objective_value=obj_value,
            positions=positions,
            movements=movements,
            solve_time_sec=solve_time,
            iteration=iteration,
        )

    @classmethod
    def from_json(cls, json_path: str | Path) -> "BendersMasterProblem":
        """
        Create a BendersMasterProblem from a benders_input.json file.

        Args:
            json_path: Path to benders_input.json

        Returns:
            Configured BendersMasterProblem
        """
        with open(json_path) as f:
            data = json.load(f)

        # Parse board
        board = BoardData(
            width_mm=data["board"]["width_mm"],
            height_mm=data["board"]["height_mm"],
        )

        # Parse components
        components = []
        for c in data["components"]:
            components.append(ComponentData(
                ref=c["ref"],
                width_mm=c["width_mm"],
                height_mm=c["height_mm"],
                x_mm=c.get("center_x_mm", c.get("x_mm", 0)),
                y_mm=c.get("center_y_mm", c.get("y_mm", 0)),
                classification=c.get("classification", "FREE"),
                hv_nets=c.get("hv_nets", []),
            ))

        # Default constraints (can be customized)
        constraints = PlacementConstraints(
            # Grouping from design doc
            grouping_constraints={
                "U_MCU": [
                    ("C_MCU_1", 10.0),
                    ("C_MCU_2", 10.0),
                    ("C_MCU_3", 10.0),
                    ("C_MCU_4", 15.0),
                ],
                "U_GATE": [
                    ("C_VCC", 15.0),
                    ("C_BOOT", 15.0),
                ],
                "U_CT": [
                    ("C_CT_FILT", 10.0),
                ],
                "U_OPAMP_CT": [
                    ("R_BURDEN", 10.0),
                ],
            },
            # Zone constraints - power stage at bottom, MCU at right side
            # Updated to match actual placement
            zone_constraints={
                # Power stage (IGBTs) in lower-left quadrant
                "Q1": [("x", "max", 60.0), ("y", "min", 90.0), ("y", "max", 140.0)],
                "Q2": [("x", "max", 60.0), ("y", "min", 90.0), ("y", "max", 140.0)],
                # Rectifier diodes in upper-left
                "D1": [("x", "max", 50.0), ("y", "min", 50.0), ("y", "max", 90.0)],
                "D2": [("x", "max", 50.0), ("y", "min", 50.0), ("y", "max", 90.0)],
                # MCU in right side, middle height
                "U_MCU": [("x", "min", 70.0), ("y", "min", 60.0), ("y", "max", 110.0)],
                # Gate driver near IGBTs
                "U_GATE": [("x", "max", 70.0), ("y", "min", 100.0), ("y", "max", 140.0)],
            },
        )

        return cls(components=components, board=board, constraints=constraints)


def run_benders_master(json_path: str | Path, verbose: bool = True) -> BendersMasterResult:
    """
    Convenience function to run the Benders master problem.

    Args:
        json_path: Path to benders_input.json
        verbose: Print progress info

    Returns:
        BendersMasterResult
    """
    if verbose:
        print(f"Loading component data from {json_path}...")

    problem = BendersMasterProblem.from_json(json_path)

    if verbose:
        print(f"Building ILP model with {len(problem.components)} components...")

    problem.build()

    if verbose:
        print("Solving ILP...")

    result = problem.solve()

    if verbose:
        print(f"Status: {result.status}")
        print(f"Objective: {result.objective_value:.2f}mm total movement")
        print(f"Solve time: {result.solve_time_sec:.2f}s")

        if result.movements:
            top_movers = sorted(result.movements.items(), key=lambda x: -x[1])[:5]
            print("\nTop movers:")
            for ref, movement in top_movers:
                if movement > 0.01:
                    old_x, old_y = problem.components[ref].x_mm, problem.components[ref].y_mm
                    new_x, new_y = result.positions[ref]
                    print(f"  {ref}: {movement:.2f}mm ({old_x:.1f},{old_y:.1f}) -> ({new_x:.1f},{new_y:.1f})")

    return result


if __name__ == "__main__":
    # Quick test with benders_input.json
    import sys

    json_path = sys.argv[1] if len(sys.argv) > 1 else "packages/temper-placer/data/benders_input.json"
    run_benders_master(json_path)
