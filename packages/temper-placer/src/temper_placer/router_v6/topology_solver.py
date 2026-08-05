"""
Router V6 Stage 3.8: Topological solver result types.

The solver itself runs in Rust (``temper_rust_router.solve_topology_rust`` /
``solve_topology_rust_bundled``, called from ``_pipeline_route``); this module
owns only the status enum and the result dataclass that the Rust result is
marshalled into.
Part of temper-wd32 (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SolverStatus(Enum):
    """Status of SAT solver."""

    SATISFIABLE = "sat"  # Solution found
    UNSATISFIABLE = "unsat"  # No solution exists
    UNKNOWN = "unknown"  # Solver timeout or error


@dataclass
class TopologicalSolution:
    """Solution from topological routing solver."""

    status: SolverStatus
    assignment: dict[str, bool]  # Variable name -> value
    solver_time_ms: float  # Time taken to solve
    solver_stats: dict | None = None  # CDCL statistics from Rust solver
    var_to_net: list[int] | None = None  # Variable index -> net index mapping
    unsat_core: list[str] | None = None  # UNSAT core constraint names

    @property
    def is_satisfiable(self) -> bool:
        """Check if solution is satisfiable."""
        return self.status == SolverStatus.SATISFIABLE

    def get_value(self, variable_name: str) -> bool | None:
        """Get assigned value for a variable."""
        return self.assignment.get(variable_name)
