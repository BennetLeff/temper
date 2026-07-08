"""CP-SAT model wrapper around OR-Tools CpModel.

Provides a builder-style interface for creating CP-SAT placement models
with component variables, rotation support, and assumption management.

Design follows the SAT bridge dispatch pattern (pcl/sat_bridge.py TYPE_HANDLERS).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

from ortools.sat.python import cp_model

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
    Size variables are created with domain supporting both orientations;
    rotation (U5 AddElement) selects the active size post-solve.
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
    orig_w: int = 0
    orig_h: int = 0


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
        self._keepout_intervals_x: list[cp_model.IntervalVar] = []
        self._keepout_intervals_y: list[cp_model.IntervalVar] = []

    # ------------------------------------------------------------------
    # Unit conversion helpers (public for encoder use)
    # ------------------------------------------------------------------

    def mm_to_units(self, mm: float) -> int:
        """Convert physical mm to integer model units, rounding to nearest even.

        Even rounding is REQUIRED by the midpoint constraint
        ``x_start + x_end == 2 * x_center``: sizes must be even so that
        ``2 * x_start + x_size`` is even, matching ``2 * x_center``.
        """
        raw = int(round(mm * self.units_per_mm))
        return raw - (raw % 2) if raw % 2 else raw

    def units_to_mm(self, units: int) -> float:
        return units / self.units_per_mm

    # ------------------------------------------------------------------
    # Component management
    # ------------------------------------------------------------------

    def add_component(
        self,
        ref: str,
        x_start_val: int,  # noqa: ARG002
        y_start_val: int,  # noqa: ARG002
        width: int,
        height: int,
    ) -> ComponentVars:
        """Register a component with rotation-ready size variables.

        Size IntVars are created with domain covering both orientations.
        Call ``add_rotation`` to pin sizes (polarized) or enable AddElement
        (non-polarized).
        """
        if ref in self._components:
            raise ValueError(f"Component '{ref}' already registered")

        min_dim = max(1, min(width, height))
        max_dim = max(width, height)
        x_size = self._model.NewIntVar(min_dim, max_dim, f"x_size_{ref}")
        y_size = self._model.NewIntVar(min_dim, max_dim, f"y_size_{ref}")
        x_center = self._model.NewIntVar(0, 1_000_000, f"x_{ref}")
        y_center = self._model.NewIntVar(0, 1_000_000, f"y_{ref}")
        x_start = self._model.NewIntVar(0, 1_000_000, f"x_start_{ref}")
        y_start = self._model.NewIntVar(0, 1_000_000, f"y_start_{ref}")
        x_end = self._model.NewIntVar(0, 1_000_000, f"x_end_{ref}")
        y_end = self._model.NewIntVar(0, 1_000_000, f"y_end_{ref}")

        # Centre is midpoint (works with variable sizes)
        self._model.Add(x_start + x_end == 2 * x_center)  # type: ignore[operator]
        self._model.Add(y_start + y_end == 2 * y_center)  # type: ignore[operator]

        # Interval consistency: start + size == end
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
            orig_w=width,
            orig_h=height,
        )
        self._components[ref] = vars_
        return vars_

    # ------------------------------------------------------------------
    # Rotation (U5)
    # ------------------------------------------------------------------

    def add_rotation(self, ref: str, is_polarized: bool) -> cp_model.IntVar | None:
        """Create a 4-way rotation variable for *ref*.

        Returns ``None`` for polarized components (pinned to rot=0, sizes
        pinned to original w/h).  Otherwise returns an ``IntVar`` with
        domain [0, 3] and wires AddElement for size selection.
        """
        if ref not in self._components:
            raise ValueError(f"Component '{ref}' not registered")
        vars_ = self._components[ref]
        w0, h0 = vars_.orig_w, vars_.orig_h

        if is_polarized:
            rot_ref = self._model.NewConstant(0)
            vars_.rot_ref = rot_ref
            self._model.Add(vars_.x_size == w0)
            self._model.Add(vars_.y_size == h0)
            return None

        rot_ref = self._model.NewIntVar(0, 3, f"rot_{ref}")
        vars_.rot_ref = rot_ref

        self._model.AddElement(rot_ref, [w0, h0, w0, h0], vars_.x_size)
        self._model.AddElement(rot_ref, [h0, w0, h0, w0], vars_.y_size)

        return rot_ref

    # ------------------------------------------------------------------
    # Global constraints
    # ------------------------------------------------------------------

    def add_no_overlap_2d(
        self,
        refs: list[str],
        extra_x_intervals: list[cp_model.IntervalVar] | None = None,
        extra_y_intervals: list[cp_model.IntervalVar] | None = None,
    ) -> cp_model.IntVar:
        """Add a 2D no-overlap constraint over *refs*.

        Returns an assumption literal for UNSAT-core extraction.
        Extra intervals (e.g. keepout zones) are included in NoOverlap2D.
        """
        intervals_x: list[cp_model.IntervalVar] = []
        intervals_y: list[cp_model.IntervalVar] = []
        for ref in refs:
            v = self._components[ref]
            ix = self._model.NewIntervalVar(v.x_start, v.x_size, v.x_end, f"ix_{ref}")
            iy = self._model.NewIntervalVar(v.y_start, v.y_size, v.y_end, f"iy_{ref}")
            intervals_x.append(ix)
            intervals_y.append(iy)
        if extra_x_intervals:
            intervals_x.extend(extra_x_intervals)
        if extra_y_intervals:
            intervals_y.extend(extra_y_intervals)
        self._model.AddNoOverlap2D(intervals_x, intervals_y)
        return self.new_assumption("no_overlap_2d")

    # ------------------------------------------------------------------
    # KEEPOUT zone support (U4)
    # ------------------------------------------------------------------

    def add_keepout_interval(
        self,
        label: str,
        kx_start: int,
        ky_start: int,
        kx_size: int,
        ky_size: int,
    ) -> tuple[cp_model.IntervalVar, cp_model.IntervalVar]:
        """Create a fixed interval for a keepout zone.

        The returned intervals should be passed to ``add_no_overlap_2d`` via
        ``extra_x_intervals`` / ``extra_y_intervals``.
        """
        ks = self._model.NewConstant(kx_start)
        ksize = self._model.NewConstant(kx_size)
        ke = self._model.NewConstant(kx_start + kx_size)
        ix = self._model.NewIntervalVar(ks, ksize, ke, f"kx_{label}")

        ks_y = self._model.NewConstant(ky_start)
        ksize_y = self._model.NewConstant(ky_size)
        ke_y = self._model.NewConstant(ky_start + ky_size)
        iy = self._model.NewIntervalVar(ks_y, ksize_y, ke_y, f"ky_{label}")

        self._keepout_intervals_x.append(ix)
        self._keepout_intervals_y.append(iy)
        return ix, iy

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
    # Constraint helpers for encoder
    # ------------------------------------------------------------------

    def add_constraint_enforced(
        self, constraint: cp_model.BoundedLinearExpression | cp_model.Constraint,
        assumption: cp_model.IntVar,
    ) -> None:
        """Add a constraint that is only enforced when *assumption* is True."""
        self._model.Add(constraint).OnlyEnforceIf(assumption)  # type: ignore[union-attr]

    def add_multiplication_equality(
        self,
        target: cp_model.IntVar,
        a: cp_model.IntVar,
        b: cp_model.IntVar,
    ) -> None:
        self._model.AddMultiplicationEquality(target, [a, b])

    def add_abs_diff_le(
        self,
        a: cp_model.IntVar,
        b: cp_model.IntVar,
        max_diff: int,
        label: str = "",
    ) -> cp_model.IntVar:
        """Constrain |a - b| <= max_diff using two linear inequalities."""
        self._model.Add(a - b <= max_diff)  # type: ignore[operator]
        self._model.Add(b - a <= max_diff)  # type: ignore[operator]
        # For UNSAT-core: create a helper var for the max
        d = self._model.NewIntVar(-max_diff, max_diff, f"diff_{label}" if label else "")
        self._model.Add(d == a - b)  # type: ignore[operator]
        return d

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

    @property
    def components(self) -> list[ComponentVars]:
        return list(self._components.values())

    def get_component(self, ref: str) -> ComponentVars:
        if ref not in self._components:
            raise KeyError(f"Component '{ref}' not registered")
        return self._components[ref]

    def set_bounds(
        self, x_min: int, y_min: int, x_max: int, y_max: int,
    ) -> None:
        """Constrain all components to lie within board bounds.

        Each component's four bounds are guarded by an ``edge_margin_<ref>``
        assumption literal so that ``SufficientAssumptionsForInfeasibility``
        can identify which component violates the edge clearance.
        """
        for v in self._components.values():
            label = f"edge_margin_{v.ref}"
            assumption = self.new_assumption(label)
            self.add_constraint_enforced(v.x_start >= x_min, assumption)
            self.add_constraint_enforced(v.y_start >= y_min, assumption)
            self.add_constraint_enforced(v.x_end <= x_max, assumption)
            self.add_constraint_enforced(v.y_end <= y_max, assumption)

    def add(self, constraint: cp_model.BoundedLinearExpression | cp_model.Constraint) -> None:
        """Delegate to underlying CpModel.Add()."""
        self._model.Add(constraint)  # type: ignore[arg-type]

    def new_int_var(self, lb: int, ub: int, name: str) -> cp_model.IntVar:
        """Create a new integer variable."""
        return self._model.NewIntVar(lb, ub, name)

    def new_bool_var(self, name: str) -> cp_model.IntVar:
        return self._model.NewBoolVar(name)
