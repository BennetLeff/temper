"""
Tests for Router V6 Stage 3.8: Solve Topology

Part of temper-wd32
"""


from temper_placer.router_v6.sat_model import build_sat_model
from temper_placer.router_v6.topology_solver import (
    SolverStatus,
    TopologicalSolution,
    solve_topology,
)


def test_solve_empty_model():
    """Test solving empty SAT model."""
    model = build_sat_model()
    solution = solve_topology(model)

    assert solution.is_satisfiable
    assert solution.status == SolverStatus.SATISFIABLE


def test_solve_simple_model():
    """Test solving simple SAT model."""
    model = build_sat_model()

    # Add a simple variable and clause
    var = model.add_variable("test", "Test variable")
    model.add_clause([(var, True)], "Test must be true")

    solution = solve_topology(model)

    assert solution.is_satisfiable
    assert solution.get_value("test") is True


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


def test_unsatisfiable_model():
    """Test detecting unsatisfiable model."""
    model = build_sat_model()

    # Add contradictory clauses: v AND NOT v
    var = model.add_variable("v", "Variable")
    model.add_clause([(var, True)], "Must be true")
    model.add_clause([(var, False)], "Must be false")

    solution = solve_topology(model)

    # Model is unsatisfiable
    assert not solution.is_satisfiable
    assert solution.status == SolverStatus.UNSATISFIABLE


def test_solver_timeout():
    """Test solver timeout parameter."""
    model = build_sat_model()
    solution = solve_topology(model, timeout_ms=100.0)

    # Should complete quickly for empty model
    assert solution.solver_time_ms < 100.0


def test_solver_status_enum():
    """Test SolverStatus enum."""
    assert SolverStatus.SATISFIABLE.value == "sat"
    assert SolverStatus.UNSATISFIABLE.value == "unsat"
    assert SolverStatus.UNKNOWN.value == "unknown"
