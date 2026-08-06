"""
Tests for Router V6 Stage 3.8 solver result types.

Part of temper-wd32

The Python ``solve_topology`` heuristic was retired (production Stage 3 solves
in Rust via ``temper_rust_router.solve_topology_rust``), so the four tests that
drove it are gone.  These two cover the ``SolverStatus`` / ``TopologicalSolution``
types that the Rust result is still marshalled into by ``_pipeline_route``.
"""

from temper_placer.router_v6.topology_solver import SolverStatus, TopologicalSolution


def test_solution_dataclass():
    """Test TopologicalSolution dataclass."""
    solution = TopologicalSolution(
        status=SolverStatus.SATISFIABLE,
        assignment={"v1": True, "v2": False},
        solver_time_ms=10.5,
    )

    assert solution.is_satisfiable
    assert solution.get_value("v1") is True
    assert solution.get_value("v2") is False
    assert solution.get_value("v3") is None  # Not in assignment


def test_solver_status_enum():
    """Test SolverStatus enum."""
    assert SolverStatus.SATISFIABLE.value == "sat"
    assert SolverStatus.UNSATISFIABLE.value == "unsat"
    assert SolverStatus.UNKNOWN.value == "unknown"
