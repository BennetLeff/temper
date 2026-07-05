"""CP-SAT model wrapper around OR-Tools CpModel.

Provides a builder-style interface for creating CP-SAT placement models
with component variables, rotation support, and assumption management.

Design follows the SAT bridge dispatch pattern (pcl/sat_bridge.py TYPE_HANDLERS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

from ortools.sat.python import cp_model

if TYPE_CHECKING:
    pass


class SolveStatus(IntEnum):
    OPTIMAL = cp_model.OPTIMAL
    FEASIBLE = cp_model.FEASIBLE
    INFEASIBLE = cp_model.INFEASIBLE
    MODEL_INVALID = cp_model.MODEL_INVALID
    UNKNOWN = cp_model.UNKNOWN


@dataclass
class ComponentVars:
    """CP-SAT variables for a single placed component.

    Position variables use centre-of-mass coordinates.
    Size variables are set at creation time and may later be controlled
    by rotation (U5 AddElement).
    """

    ref: str
    x_center: cp_model.IntVar
    y_center: cp_model.IntVar
    x_size: cp_model.IntVar
    y_size: cp_model.IntVar
    x_start: cp_model.IntVar
    y_start: cp_model.IntVar
    x_end: cp_model.IntVar
    y_end: cp_model.IntVar
    rot_ref: cp_model.IntVar | None = None


@dataclass
class CpSolverSolution:
    """Post-solve placement result (integer grid units)."""

    status: SolveStatus
    objective_value: float
    positions: dict[str, tuple[int, int]]
    rotations: dict[str, int]
    sizes: dict[str, tuple[int, int]]
    solve_time_s: float
    unsat_assumptions: list[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return self.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)


class CpSatModel:
    """Wrapper around ``ortools.sat.python.cp_model.CpModel`` for placement.

    All coordinates are in integer grid units.  The caller supplies
    ``units_per_mm`` to convert physical mm to model units.
    """

    def __init__(self, units_per_mm: int = 100) -> None:
        self._model = cp_model.CpModel()
        self._components: dict[str, ComponentVars] = {}
        self._assumptions: list[cp_model.IntVar] = []
        self._assumption_labels: dict[int, str] = {}
        self.units_per_mm = units_per_mm
        self._objective_terms: list[tuple[cp_model.IntVar, int]] = []

    # ------------------------------------------------------------------
    # Unit conversion helpers (public for encoder use)
    # ------------------------------------------------------------------

    def mm_to_units(self, mm: float) -> int:
        return int(round(mm * self.units_per_mm))

    def units_to_mm(self, units: int) -> float:
        return units / self.units_per_mm

    # ------------------------------------------------------------------
    # Component management
    # ------------------------------------------------------------------

    def add_component(
        self,
        ref: str,
        x_start_val: int,
        y_start_val: int,
        width: int,
        height: int,
    ) -> ComponentVars:
        """Register a component.

        Position IntVars are created wide-open; the caller must add
        board-boundary constraints separately.  *width* and *height*
        are used as the initial fixed sizes.
        """
        if ref in self._components:
            raise ValueError(f"Component '{ref}' already registered")

        x_size = self._model.NewIntVar(width, width, f"x_size_{ref}")
        y_size = self._model.NewIntVar(height, height, f"y_size_{ref}")
        x_center = self._model.NewIntVar(0, 1_000_000, f"x_{ref}")
        y_center = self._model.NewIntVar(0, 1_000_000, f"y_{ref}")
        x_start = self._model.NewIntVar(0, 1_000_000, f"x_start_{ref}")
        y_start = self._model.NewIntVar(0, 1_000_000, f"y_start_{ref}")
        x_end = self._model.NewIntVar(0, 1_000_000, f"x_end_{ref}")
        y_end = self._model.NewIntVar(0, 1_000_000, f"y_end_{ref}")

        half_w = width // 2
        half_h = height // 2

        self._model.Add(x_start == x_center - half_w)  # type: ignore[operator]
        self._model.Add(y_start == y_center - half_h)  # type: ignore[operator]
        self._model.Add(x_end == x_center + half_w)  # type: ignore[operator]
        self._model.Add(y_end == y_center + half_h)  # type: ignore[operator]

        # Ensure interval consistency: start + size == end
        self._model.Add(x_start + x_size == x_end)  # type: ignore[operator]
        self._model.Add(y_start + y_size == y_end)  # type: ignore[operator]

        vars_ = ComponentVars(
            ref=ref,
            x_center=x_center,
            y_center=y_center,
            x_size=x_size,
            y_size=y_size,
            x_start=x_start,
            y_start=y_start,
            x_end=x_end,
            y_end=y_end,
        )
        self._components[ref] = vars_
        return vars_

    # ------------------------------------------------------------------
    # Rotation (U5)
    # ------------------------------------------------------------------

    def add_rotation(self, ref: str, is_polarized: bool) -> cp_model.IntVar | None:
        """Create a 4-way rotation variable for *ref*.

        Returns ``None`` for polarized components (pinned to rot=0).
        Otherwise returns an ``IntVar`` with domain [0, 3].
        """
        if ref not in self._components:
            raise ValueError(f"Component '{ref}' not registered")
        vars_ = self._components[ref]
        if is_polarized:
            rot_ref = self._model.NewConstant(0)
            vars_.rot_ref = rot_ref
            return None
        rot_ref = self._model.NewIntVar(0, 3, f"rot_{ref}")
        vars_.rot_ref = rot_ref
        return rot_ref

    # ------------------------------------------------------------------
    # Global constraints
    # ------------------------------------------------------------------

    def add_no_overlap_2d(self, refs: list[str]) -> cp_model.IntVar:
        """Add a 2D no-overlap constraint over *refs*.

        Returns an assumption literal for UNSAT-core extraction.
        """
        intervals_x: list[cp_model.IntervalVar] = []
        intervals_y: list[cp_model.IntervalVar] = []
        for ref in refs:
            v = self._components[ref]
            ix = self._model.NewIntervalVar(v.x_start, v.x_size, v.x_end, f"ix_{ref}")
            iy = self._model.NewIntervalVar(v.y_start, v.y_size, v.y_end, f"iy_{ref}")
            intervals_x.append(ix)
            intervals_y.append(iy)
        self._model.AddNoOverlap2D(intervals_x, intervals_y)
        return self.new_assumption("no_overlap_2d")

    # ------------------------------------------------------------------
    # Objective
    # ------------------------------------------------------------------

    def add_objective_term(self, var: cp_model.IntVar, weight: int) -> None:
        """Accumulate a weighted term for the linear objective (minimised)."""
        self._objective_terms.append((var, weight))

    # ------------------------------------------------------------------
    # Assumptions
    # ------------------------------------------------------------------

    def new_assumption(self, label: str) -> cp_model.IntVar:
        """Return a new Boolean assumption literal with *label*.

        The literal is added to the model's assumption list via
        ``cp_model.AddAssumption()`` so that the solver can report an
        unsat core when the model is infeasible.
        """
        b = self._model.NewBoolVar(label)
        self._model.AddAssumption(b)
        self._assumptions.append(b)
        self._assumption_labels[b.Index()] = label
        return b

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(
        self,
        time_limit_s: float = 10.0,
    ) -> CpSolverSolution:
        """Run the CP-SAT solver and return a solution."""
        if self._objective_terms:
            obj = sum(v * w for v, w in self._objective_terms)
            self._model.Minimize(obj)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_s
        solver.parameters.num_search_workers = 8

        status = solver.Solve(self._model)

        positions: dict[str, tuple[int, int]] = {}
        rotations: dict[str, int] = {}
        sizes: dict[str, tuple[int, int]] = {}

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for ref, vars_ in self._components.items():
                positions[ref] = (
                    solver.Value(vars_.x_center),
                    solver.Value(vars_.y_center),
                )
                rotations[ref] = (
                    solver.Value(vars_.rot_ref) if vars_.rot_ref is not None else 0
                )
                sizes[ref] = (
                    solver.Value(vars_.x_size),
                    solver.Value(vars_.y_size),
                )

        unsat_labels: list[str] = []
        if status == cp_model.INFEASIBLE:
            insufficient = solver.SufficientAssumptionsForInfeasibility()
            unsat_labels = [
                self._assumption_labels.get(i, f"assumption_{i}")
                for i in insufficient
            ]

        return CpSolverSolution(
            status=SolveStatus(status),
            objective_value=solver.ObjectiveValue(),
            positions=positions,
            rotations=rotations,
            sizes=sizes,
            solve_time_s=solver.WallTime(),
            unsat_assumptions=unsat_labels,
        )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def model_ref(self) -> cp_model.CpModel:
        return self._model

    @property
    def component_map(self) -> dict[str, ComponentVars]:
        return dict(self._components)

    def get_component(self, ref: str) -> ComponentVars:
        if ref not in self._components:
            raise KeyError(f"Component '{ref}' not registered")
        return self._components[ref]

    def set_bounds(
        self, x_min: int, y_min: int, x_max: int, y_max: int,
    ) -> None:
        """Constrain all components to lie within board bounds."""
        for v in self._components.values():
            self._model.Add(v.x_start >= x_min)
            self._model.Add(v.y_start >= y_min)
            self._model.Add(v.x_end <= x_max)
            self._model.Add(v.y_end <= y_max)

    def add(self, constraint: cp_model.BoundedLinearExpression | cp_model.Constraint) -> None:
        """Delegate to underlying CpModel.Add()."""
        self._model.Add(constraint)  # type: ignore[arg-type]
