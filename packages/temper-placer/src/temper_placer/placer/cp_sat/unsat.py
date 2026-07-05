"""
UNSAT core extraction from CP-SAT solver infeasibility.

Uses OR-Tools ``SufficientAssumptionsForInfeasibility`` API and refines
to a Minimal Unsatisfiable Subset (MUS) via iterative assumption removal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintType

if TYPE_CHECKING:
    from ortools.sat.python import cp_model


@dataclass
class UnsatConstraint:
    """A single constraint participating in the unsatisfiable core.

    Attributes:
        name: Human-readable constraint name (e.g. "loop_area 'commutation'").
        constraint_type: The PCL constraint type.
        because: Rationale from PCL spec (None if unannotated).
        assumption_literal: The CP-SAT assumption literal index.
    """

    name: str
    constraint_type: ConstraintType
    because: str | None
    assumption_literal: int


@dataclass
class UnsatReport:
    """Structured report of an unsatisfiable constraint set.

    Attributes:
        sufficient_core: All conflicting assumptions (raw OR-Tools output).
        minimal_core: MUS-refined subset of sufficient_core.
        is_minimal: True if MUS refinement converged (core is minimal).
    """

    sufficient_core: list[UnsatConstraint]
    minimal_core: list[UnsatConstraint]
    is_minimal: bool = False

    @property
    def data_quality_gaps(self) -> list[dict[str, str]]:
        """Return constraints whose ``because`` field is missing or empty."""
        gaps: list[dict[str, str]] = []
        for c in self.minimal_core:
            if not c.because:
                gaps.append(
                    {
                        "constraint_name": c.name,
                        "gap": "because field unannotated; rationale not available from PCL spec",
                    }
                )
        return gaps


def _build_proto_index_map(
    assumption_vars: list[cp_model.IntVar],
) -> dict[int, cp_model.IntVar]:
    """Map CP-SAT proto-index to the original variable.

    ``SufficientAssumptionsForInfeasibility`` returns the same integer
    indices as ``var.Index()``, so this builds a lookup for MUS refinement.

    Args:
        assumption_vars: The assumption literal variables.

    Returns:
        Dict mapping proto-index -> variable.
    """
    return {var.Index(): var for var in assumption_vars}


def _decode_assumption_literals(
    proto_indices: list[int],
    constraint_map: dict[int, UnsatConstraint],
) -> list[UnsatConstraint]:
    """Translate proto-indices to UnsatConstraint objects.

    Falls back to constructing a placeholder constraint for unknown indices.

    Args:
        proto_indices: Proto-indices from the solver.
        constraint_map: Mapping from assumption literal index -> UnsatConstraint.

    Returns:
        List of UnsatConstraint objects corresponding to the proto-indices.
    """
    result: list[UnsatConstraint] = []
    for pi in proto_indices:
        if pi in constraint_map:
            result.append(constraint_map[pi])
        else:
            result.append(
                UnsatConstraint(
                    name=f"unknown_literal_{pi}",
                    constraint_type=ConstraintType.SEPARATED,
                    because=None,
                    assumption_literal=pi,
                )
            )
    return result


def extract_unsat_core(
    solver: cp_model.CpSolver,
    model: cp_model.CpModel,
    assumption_vars: list[cp_model.IntVar],
    constraint_map: dict[int, UnsatConstraint],
    mus_max_iterations: int = 20,
) -> UnsatReport:
    """Extract the UNSAT core and refine to a minimal unsatisfiable subset.

    Args:
        solver: A CpSolver that has already solved to INFEASIBLE.
        model: The CP-SAT model.
        assumption_vars: Assumption literal variables.
        constraint_map: Mapping from assumption literal index -> UnsatConstraint.
        mus_max_iterations: Maximum MUS refinement iterations.

    Returns:
        UnsatReport with sufficient_core and (optionally) minimal_core.
    """
    # Step 1: Get sufficient assumptions for infeasibility.
    proto_indices: list[int] = solver.SufficientAssumptionsForInfeasibility()

    sufficient_core = _decode_assumption_literals(proto_indices, constraint_map)

    if not sufficient_core:
        return UnsatReport(
            sufficient_core=[],
            minimal_core=[],
            is_minimal=False,
        )

    # Step 2: Refine to MUS by iterative removal.
    minimal_core, is_minimal = _refine_mus(
        model,
        assumption_vars,
        constraint_map,
        proto_indices,
        mus_max_iterations,
    )

    return UnsatReport(
        sufficient_core=sufficient_core,
        minimal_core=minimal_core,
        is_minimal=is_minimal,
    )


def _refine_mus(
    model: cp_model.CpModel,
    assumption_vars: list[cp_model.IntVar],
    constraint_map: dict[int, UnsatConstraint],
    proto_indices: list[int],
    max_iterations: int,
) -> tuple[list[UnsatConstraint], bool]:
    """Refine the sufficient core to a Minimal Unsatisfiable Subset.

    Iteratively removes assumptions and re-solves. If the problem becomes
    satisfiable, the removed assumption is necessary and is added back.

    WARNING: Mutates the model's assumptions. After refinement, model
    assumptions will be set to the MUS subset.

    Args:
        model: The original CpModel.
        assumption_vars: All assumption literal variables.
        constraint_map: Mapping from assumption literal index -> UnsatConstraint.
        proto_indices: Proto-indices of the sufficient core.
        max_iterations: Maximum refinement iterations.

    Returns:
        Tuple of (minimal_core, is_minimal).
    """
    if len(proto_indices) <= 1:
        return _decode_assumption_literals(proto_indices, constraint_map), True

    working_set = list(proto_indices)
    necessary: set[int] = set()

    # Build proto_idx -> variable lookup.
    var_lookup = _build_proto_index_map(assumption_vars)

    for _iteration in range(max_iterations):
        made_progress = False

        for idx in list(working_set):
            if idx in necessary:
                continue

            # Try removing this assumption.
            test_set = [i for i in working_set if i != idx]
            if not test_set:
                necessary.add(idx)
                made_progress = True
                continue

            # Check if the remaining set is still infeasible.
            is_still_infeasible = _check_assumptions_infeasible(
                model, var_lookup, test_set
            )

            if is_still_infeasible:
                # This assumption is NOT necessary; remove it.
                working_set.remove(idx)
                made_progress = True
            else:
                # This assumption IS necessary.
                necessary.add(idx)
                made_progress = True

        if not made_progress:
            break

    result = list(necessary) if necessary else list(working_set)
    is_minimal = len(necessary) == len(result)

    # Restore model assumptions to the MUS for the caller.
    _set_assumptions(model, var_lookup, result)

    return _decode_assumption_literals(result, constraint_map), is_minimal


def _check_assumptions_infeasible(
    model: cp_model.CpModel,
    var_lookup: dict[int, cp_model.IntVar],
    assumption_indices: list[int],
) -> bool:
    """Check if the model with only the given assumptions is still INFEASIBLE.

    Clones the model via proto serialization, sets the test assumptions,
    and solves with a fresh solver.

    Args:
        model: The CP-SAT model (original, unmodified expectation).
        var_lookup: Mapping from proto-index to variable.
        assumption_indices: Proto-indices of assumptions to test.

    Returns:
        True if the test assumptions produce INFEASIBLE.
    """
    from ortools.sat.python import cp_model as cp

    model_proto = model.Proto()

    # Build a fresh model.
    test_model = cp.CpModel()
    test_model.Proto().copy_from(model_proto)

    # Set assumptions to only the test subset.
    _set_assumptions(test_model, var_lookup, assumption_indices)

    new_solver = cp.CpSolver()
    new_solver.parameters.log_search_progress = False
    new_solver.parameters.max_time_in_seconds = 5.0

    status = new_solver.Solve(test_model)
    return status == cp.INFEASIBLE


def _set_assumptions(
    model: cp_model.CpModel,
    var_lookup: dict[int, cp_model.IntVar],
    assumption_indices: list[int],
) -> None:
    """Replace the model's assumption list with the given subset."""
    model.ClearAssumptions()
    vars_to_add = [var_lookup[i] for i in assumption_indices if i in var_lookup]
    if vars_to_add:
        model.AddAssumptions(vars_to_add)
