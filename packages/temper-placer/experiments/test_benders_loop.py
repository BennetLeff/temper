"""
Standalone validation experiment for Benders Loop orchestration.

This validates the complete Benders decomposition workflow.
"""

import sys
import json
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.placement.benders_loop import (
    BendersOptimizer,
    BendersResult,
    BendersStatus,
    run_benders_optimization,
)


def create_test_input(num_components=3):
    """Create a temporary test input JSON."""
    data = {
        "board": {"width_mm": 100, "height_mm": 100},
        "coordinate_system": "center",
        "hv_nets": [],
        "components": [],
    }

    # Add test components
    for i in range(num_components):
        data["components"].append(
            {
                "ref": f"U{i+1}",
                "width_mm": 10.0,
                "height_mm": 5.0,
                "center_x_mm": 20.0 + i * 20.0,
                "center_y_mm": 50.0,
                "classification": "FREE",
                "hv_nets": [],
            }
        )

    # Create temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        return f.name


def test_optimizer_creation():
    """Test creating a Benders optimizer."""
    print("\n=== Test 1: Optimizer Creation ===")

    json_file = create_test_input()

    optimizer = BendersOptimizer(
        component_data_json=json_file, max_iterations=10, verbose=False
    )

    print(f"Max iterations: {optimizer.max_iterations}")
    print(f"Current iteration: {optimizer.current_iteration}")

    assert optimizer.max_iterations == 10
    assert optimizer.current_iteration == 0

    print("✓ Test passed!")


def test_single_iteration_no_routability():
    """Test running a single iteration without routability checking."""
    print("\n=== Test 2: Single Iteration (No Routability Check) ===")

    json_file = create_test_input(3)

    optimizer = BendersOptimizer(
        component_data_json=json_file,
        max_iterations=1,
        check_routability=False,
        verbose=True,
    )

    result = optimizer.optimize()

    print(f"\nResult:")
    print(f"  Status: {result.status.value}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Components placed: {len(result.final_positions)}")
    print(f"  Total movement: {result.total_movement:.2f}mm")
    print(f"  Solve time: {result.solve_time_sec:.2f}s")

    assert result.status in (BendersStatus.FEASIBLE, BendersStatus.OPTIMAL)
    assert result.iterations == 1
    assert len(result.final_positions) == 3

    print("✓ Test passed!")


def test_result_data_structure():
    """Test BendersResult data structure."""
    print("\n=== Test 3: Result Data Structure ===")

    json_file = create_test_input(2)

    optimizer = BendersOptimizer(
        component_data_json=json_file,
        max_iterations=1,
        check_routability=False,
        verbose=False,
    )

    result = optimizer.optimize()

    print("Result attributes:")
    print(f"  - status: {type(result.status).__name__}")
    print(f"  - iterations: {type(result.iterations).__name__}")
    print(f"  - final_positions: {type(result.final_positions).__name__}")
    print(f"  - total_movement: {type(result.total_movement).__name__}")
    print(f"  - cuts_added: {type(result.cuts_added).__name__}")
    print(f"  - solve_time_sec: {type(result.solve_time_sec).__name__}")

    assert isinstance(result.status, BendersStatus)
    assert isinstance(result.iterations, int)
    assert isinstance(result.final_positions, dict)
    assert isinstance(result.total_movement, float)
    assert isinstance(result.cuts_added, list)
    assert isinstance(result.solve_time_sec, float)

    print("✓ Test passed!")


def test_infeasible_problem():
    """Test handling of infeasible Master Problem."""
    print("\n=== Test 4: Infeasible Problem ===")

    # Create impossible constraints (component larger than board)
    data = {
        "board": {"width_mm": 20, "height_mm": 20},
        "coordinate_system": "center",
        "hv_nets": [],
        "components": [
            {
                "ref": "U1",
                "width_mm": 25.0,  # Larger than board!
                "height_mm": 25.0,
                "center_x_mm": 10.0,
                "center_y_mm": 10.0,
                "classification": "FREE",
                "hv_nets": [],
            }
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        json_file = f.name

    optimizer = BendersOptimizer(
        component_data_json=json_file, max_iterations=1, verbose=True
    )

    result = optimizer.optimize()

    print(f"\nResult status: {result.status.value}")
    assert result.status == BendersStatus.INFEASIBLE

    print("✓ Test passed!")


def test_convenience_function():
    """Test the convenience wrapper function."""
    print("\n=== Test 5: Convenience Function ===")

    json_file = create_test_input(3)

    result = run_benders_optimization(
        component_data_json=json_file, max_iterations=1, verbose=True
    )

    print(f"\nResult: {result.status.value}")
    assert result.status in (BendersStatus.FEASIBLE, BendersStatus.OPTIMAL)

    print("✓ Test passed!")


def test_position_output():
    """Test that positions are correctly extracted."""
    print("\n=== Test 6: Position Output ===")

    json_file = create_test_input(3)

    optimizer = BendersOptimizer(
        component_data_json=json_file,
        max_iterations=1,
        check_routability=False,
        verbose=False,
    )

    result = optimizer.optimize()

    print("\nFinal positions:")
    for ref, (x, y) in result.final_positions.items():
        print(f"  {ref}: ({x:.2f}, {y:.2f})")

    # Check all components have positions
    assert "U1" in result.final_positions
    assert "U2" in result.final_positions
    assert "U3" in result.final_positions

    # Check positions are tuples of floats
    for ref, pos in result.final_positions.items():
        assert isinstance(pos, tuple)
        assert len(pos) == 2
        assert isinstance(pos[0], float)
        assert isinstance(pos[1], float)

    print("✓ Test passed!")


def test_timing_breakdown():
    """Test timing breakdown in result."""
    print("\n=== Test 7: Timing Breakdown ===")

    json_file = create_test_input(5)

    optimizer = BendersOptimizer(
        component_data_json=json_file,
        max_iterations=1,
        check_routability=False,
        verbose=False,
    )

    result = optimizer.optimize()

    print("\nTiming:")
    print(f"  Total: {result.solve_time_sec:.3f}s")
    print(f"  Master Problem: {result.master_problem_time:.3f}s")
    print(f"  Routability Check: {result.routability_check_time:.3f}s")

    assert result.solve_time_sec >= 0
    assert result.master_problem_time >= 0
    assert result.routability_check_time >= 0
    # Master time should be non-zero
    assert result.master_problem_time > 0

    print("✓ Test passed!")


def test_with_temper_data():
    """Test with actual Temper board data."""
    print("\n=== Test 8: Temper Board Data ===")

    # Path to benders_input.json
    temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

    if not temper_json.exists():
        print(f"Skipping test - {temper_json} not found")
        return

    print(f"Using input: {temper_json}")

    optimizer = BendersOptimizer(
        component_data_json=temper_json,
        max_iterations=1,
        check_routability=False,
        verbose=True,
    )

    result = optimizer.optimize()

    print(f"\nResult:")
    print(f"  Status: {result.status.value}")
    print(f"  Components: {len(result.final_positions)}")
    print(f"  Total movement: {result.total_movement:.2f}mm")
    print(f"  Solve time: {result.solve_time_sec:.2f}s")

    assert result.status in (BendersStatus.FEASIBLE, BendersStatus.OPTIMAL)
    assert len(result.final_positions) > 0

    # Print top movers
    if result.final_positions:
        print("\nTop 5 movers:")
        # Can't easily compute movement without original positions
        for i, (ref, pos) in enumerate(list(result.final_positions.items())[:5]):
            print(f"  {i+1}. {ref}: ({pos[0]:.1f}, {pos[1]:.1f})")

    print("✓ Test passed!")


def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("Benders Loop Orchestration Validation")
    print("=" * 60)

    tests = [
        test_optimizer_creation,
        test_single_iteration_no_routability,
        test_result_data_structure,
        test_infeasible_problem,
        test_convenience_function,
        test_position_output,
        test_timing_breakdown,
        test_with_temper_data,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
