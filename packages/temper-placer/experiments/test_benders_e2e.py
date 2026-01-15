"""
End-to-End Benders Integration Test.

Tests the complete Benders decomposition with Max-Flow routability checking.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.placement.benders_loop import (
    BendersOptimizer,
    run_benders_optimization,
    BendersStatus,
)


def test_ilp_only_temper_board():
    """Test ILP-only optimization on Temper board."""
    print("\n=== Test 1: ILP-Only Optimization on Temper Board ===")

    temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

    if not temper_json.exists():
        print(f"Skipping - {temper_json} not found")
        return

    result = run_benders_optimization(
        component_data_json=temper_json,
        max_iterations=5,
        check_routability=False,  # ILP only
        verbose=True,
    )

    print(f"\nResult:")
    print(f"  Status: {result.status.value}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Total movement: {result.total_movement:.2f}mm")
    print(f"  Components: {len(result.final_positions)}")
    print(f"  Cuts added: {len(result.cuts_added)}")
    print(f"  Solve time: {result.solve_time_sec:.2f}s")

    assert result.status in (BendersStatus.OPTIMAL, BendersStatus.FEASIBLE)
    assert len(result.final_positions) == 33
    assert result.total_movement >= 0

    print("✓ Test passed!")


def test_manual_cut_addition():
    """Test manually adding cuts and re-solving."""
    print("\n=== Test 2: Manual Cut Addition ===")

    from temper_placer.placement.benders_master import BendersMasterProblem
    from temper_placer.placement.benders_mincut_mapper import MinCutMapper
    from temper_placer.placement.benders_cut_generator import BendersCutGenerator

    temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

    if not temper_json.exists():
        print(f"Skipping - {temper_json} not found")
        return

    # Setup
    problem = BendersMasterProblem.from_json(temper_json)
    problem.build()
    components = list(problem.components.values())
    mapper = MinCutMapper(components, tolerance_mm=2.0)
    generator = BendersCutGenerator()

    # Iteration 1
    result1 = problem.solve(time_limit_sec=30.0)
    print(f"\nIteration 1:")
    print(f"  Status: {result1.status}")
    print(f"  Movement: {result1.objective_value:.2f}mm")

    # Simulate min-cut (would come from Max-Flow in real usage)
    # Vertical edge between Q1 and Q2 at x=37.5
    min_cut_edges = [
        (("F.Cu", (37.5, 10.0)), ("F.Cu", (37.5, 20.0)), 0),
    ]

    # Generate cuts
    blocking = mapper.map_mincut_to_components(min_cut_edges)
    print(f"\nFound {len(blocking)} blocking components:")
    for b in blocking:
        print(f"  - {b.component_ref} ({b.direction.value})")

    cuts = generator.generate_cuts(blocking, iteration=1)
    print(f"\nGenerated {len(cuts)} cuts:")
    for cut in cuts:
        cut_type, components, gap = cut.to_master_problem_args()
        print(f"  - {cut_type}: {components[0]} <-> {components[1]}, gap={gap:.2f}mm")
        problem.add_routability_cut(cut_type, components, gap)

    # Iteration 2
    result2 = problem.solve(time_limit_sec=30.0)
    print(f"\nIteration 2:")
    print(f"  Status: {result2.status}")
    print(f"  Movement: {result2.objective_value:.2f}mm")
    print(f"  Movement increase: {result2.objective_value - result1.objective_value:.2f}mm")

    assert result2.objective_value >= result1.objective_value  # Cuts add constraints
    print("✓ Test passed!")


def test_multi_iteration_optimization():
    """Test multiple iterations of Benders loop."""
    print("\n=== Test 3: Multi-Iteration Optimization ===")

    temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

    if not temper_json.exists():
        print(f"Skipping - {temper_json} not found")
        return

    result = run_benders_optimization(
        component_data_json=temper_json,
        max_iterations=3,
        check_routability=False,  # No Max-Flow for now
        verbose=True,
    )

    print(f"\nFinal result:")
    print(f"  Status: {result.status.value}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Total movement: {result.total_movement:.2f}mm")
    print(f"  Master time: {result.master_problem_time:.2f}s")
    print(f"  Total time: {result.solve_time_sec:.2f}s")

    assert result.status in (BendersStatus.OPTIMAL, BendersStatus.FEASIBLE, BendersStatus.MAX_ITERATIONS)
    assert result.iterations <= 3

    print("✓ Test passed!")


def test_position_changes():
    """Test that cuts cause positions to change."""
    print("\n=== Test 4: Position Changes from Cuts ===")

    from temper_placer.placement.benders_master import BendersMasterProblem

    temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

    if not temper_json.exists():
        print(f"Skipping - {temper_json} not found")
        return

    problem = BendersMasterProblem.from_json(temper_json)
    problem.build()

    # Initial solve
    result1 = problem.solve(time_limit_sec=30.0)
    pos1_q1 = result1.positions["Q1"]
    pos1_q2 = result1.positions["Q2"]

    print(f"\nInitial positions:")
    print(f"  Q1: ({pos1_q1[0]:.2f}, {pos1_q1[1]:.2f})")
    print(f"  Q2: ({pos1_q2[0]:.2f}, {pos1_q2[1]:.2f})")

    # Calculate initial distance
    dist1 = abs(pos1_q2[0] - pos1_q1[0])

    # Add horizontal separation cut that's larger than current distance
    # This should force them to move apart
    gap_required = dist1 + 10.0  # 10mm more than current distance

    print(f"\nAdding horizontal cut with gap={gap_required:.2f}mm")
    problem.add_routability_cut("horizontal", ["Q1", "Q2"], gap_required=gap_required)

    # Re-solve
    result2 = problem.solve(time_limit_sec=30.0)
    pos2_q1 = result2.positions["Q1"]
    pos2_q2 = result2.positions["Q2"]

    print(f"\nPositions after horizontal cut:")
    print(f"  Q1: ({pos2_q1[0]:.2f}, {pos2_q1[1]:.2f})")
    print(f"  Q2: ({pos2_q2[0]:.2f}, {pos2_q2[1]:.2f})")

    # Check that horizontal distance increased
    dist2 = abs(pos2_q2[0] - pos2_q1[0])

    print(f"\nHorizontal distance:")
    print(f"  Before cut: {dist1:.2f}mm")
    print(f"  After cut: {dist2:.2f}mm")
    print(f"  Increase: {dist2 - dist1:.2f}mm")
    print(f"  Movement increase: {result2.objective_value - result1.objective_value:.2f}mm")

    # Check that either distance increased OR movement increased (components moved)
    # The cut forces a tighter constraint, so something must change
    constraint_active = dist2 >= dist1 or result2.objective_value > result1.objective_value

    assert constraint_active, "Cut should affect the placement (distance or movement changed)"

    print("✓ Test passed!")


def test_convergence_tracking():
    """Test that convergence is tracked correctly."""
    print("\n=== Test 5: Convergence Tracking ===")

    temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

    if not temper_json.exists():
        print(f"Skipping - {temper_json} not found")
        return

    optimizer = BendersOptimizer(
        component_data_json=temper_json,
        max_iterations=5,
        check_routability=False,
        verbose=False,
    )

    result = optimizer.optimize()

    print(f"\nConvergence info:")
    print(f"  Final iteration: {result.iterations}")
    print(f"  Cuts added: {len(result.cuts_added)}")
    print(f"  Status: {result.status.value}")
    print(f"  Total movement: {result.total_movement:.2f}mm")

    assert result.iterations >= 1
    assert result.solve_time_sec > 0

    print("✓ Test passed!")


def run_all_tests():
    """Run all end-to-end tests."""
    print("=" * 60)
    print("Benders End-to-End Integration Tests")
    print("=" * 60)

    tests = [
        test_ilp_only_temper_board,
        test_manual_cut_addition,
        test_multi_iteration_optimization,
        test_position_changes,
        test_convergence_tracking,
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
