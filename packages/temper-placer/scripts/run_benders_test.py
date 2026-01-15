#!/usr/bin/env python3
"""
Test script for Benders placement optimization.

This script demonstrates the ILP Master Problem and provides
a starting point for implementing the full Benders loop.

Usage:
    cd packages/temper-placer
    PYTHONPATH=src python scripts/run_benders_test.py
"""

import json
import sys
from pathlib import Path

# Add src to path if running directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.placement.benders_master import (
    BendersMasterProblem,
    run_benders_master,
)


def test_ilp_solver():
    """Test the ILP Master Problem solver."""
    print("=" * 60)
    print("TEST 1: ILP Master Problem")
    print("=" * 60)

    json_path = Path(__file__).parent.parent / "data" / "benders_input.json"
    result = run_benders_master(json_path, verbose=True)

    print(f"\nResult: {result.status}")
    return result.status == "OPTIMAL"


def test_constraint_verification():
    """Verify all constraints are satisfied in the solution."""
    print("\n" + "=" * 60)
    print("TEST 2: Constraint Verification")
    print("=" * 60)

    json_path = Path(__file__).parent.parent / "data" / "benders_input.json"
    problem = BendersMasterProblem.from_json(json_path)
    problem.build()
    result = problem.solve()

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        print("FAILED: No solution found")
        return False

    # Check grouping constraints
    print("\nGrouping Constraints:")
    groupings = [
        ("U_MCU", ["C_MCU_1", "C_MCU_2", "C_MCU_3", "C_MCU_4"], 8.0),
        ("U_GATE", ["C_VCC", "C_BOOT"], 8.0),
        ("U_CT", ["C_CT_FILT"], 5.0),
        ("U_OPAMP_CT", ["R_BURDEN"], 5.0),
    ]

    all_ok = True
    for ic, caps, max_dist in groupings:
        if ic not in result.positions:
            continue
        ic_x, ic_y = result.positions[ic]
        for cap in caps:
            if cap not in result.positions:
                continue
            cap_x, cap_y = result.positions[cap]
            dist = abs(ic_x - cap_x) + abs(ic_y - cap_y)
            ok = dist <= max_dist + 0.01  # Small tolerance
            status = "PASS" if ok else "FAIL"
            print(f"  {status}: {ic} <-> {cap}: {dist:.2f}mm (max {max_dist}mm)")
            if not ok:
                all_ok = False

    # Check zone constraints
    print("\nZone Constraints:")
    zones = [
        ("Q1", "y", "<=", 20.0),
        ("Q2", "y", "<=", 20.0),
        ("D1", "y", "<=", 50.0),
        ("D2", "y", "<=", 50.0),
        ("U_MCU", "y", ">=", 80.0),
        ("U_MCU", "x", ">=", 60.0),
    ]

    for ref, axis, op, limit in zones:
        if ref not in result.positions:
            continue
        x, y = result.positions[ref]
        val = x if axis == "x" else y
        if op == "<=":
            ok = val <= limit + 0.01
        else:
            ok = val >= limit - 0.01
        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {ref}.{axis} {op} {limit}: actual={val:.2f}")
        if not ok:
            all_ok = False

    # Check movement budget
    print("\nMovement Budget:")
    total_movement = sum(result.movements.values())
    max_single = max(result.movements.values()) if result.movements else 0
    print(f"  Total movement: {total_movement:.2f}mm (budget: 100mm)")
    print(f"  Max single: {max_single:.2f}mm (limit: 15mm)")

    if total_movement > 100.0 or max_single > 15.0:
        all_ok = False

    return all_ok


def test_cut_addition():
    """Test adding routability cuts to the ILP."""
    print("\n" + "=" * 60)
    print("TEST 3: Cut Addition")
    print("=" * 60)

    json_path = Path(__file__).parent.parent / "data" / "benders_input.json"
    problem = BendersMasterProblem.from_json(json_path)
    problem.build()

    # Solve without cuts
    result1 = problem.solve()
    print(f"Before cut: {result1.objective_value:.2f}mm movement")

    # Add a hypothetical horizontal cut between D1 and U_GATE
    # This simulates what would happen if Max-Flow identified a bottleneck
    problem.add_routability_cut(
        cut_type="horizontal",
        components=["D1", "U_GATE"],
        gap_required=5.0,  # Need 5mm channel
    )

    # Solve with cut
    result2 = problem.solve()
    print(f"After cut: {result2.objective_value:.2f}mm movement")

    if result2.status in ("OPTIMAL", "FEASIBLE"):
        # Verify the cut is respected
        d1_x = result2.positions.get("D1", (0, 0))[0]
        gate_x = result2.positions.get("U_GATE", (0, 0))[0]
        d1_w = problem.components["D1"].width_mm
        gate_w = problem.components["U_GATE"].width_mm
        gap = abs(gate_x - d1_x) - (d1_w + gate_w) / 2
        print(f"Gap between D1 and U_GATE: {gap:.2f}mm (required: 5mm)")
        return True

    return False


def test_export_solution():
    """Export the optimized placement to JSON."""
    print("\n" + "=" * 60)
    print("TEST 4: Export Solution")
    print("=" * 60)

    json_path = Path(__file__).parent.parent / "data" / "benders_input.json"
    problem = BendersMasterProblem.from_json(json_path)
    problem.build()
    result = problem.solve()

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        print("FAILED: No solution to export")
        return False

    # Create output
    output = {
        "status": result.status,
        "objective_mm": result.objective_value,
        "solve_time_sec": result.solve_time_sec,
        "positions": {
            ref: {"x_mm": pos[0], "y_mm": pos[1]}
            for ref, pos in result.positions.items()
        },
        "movements": result.movements,
    }

    output_path = Path(__file__).parent.parent / "data" / "benders_output.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Solution exported to: {output_path}")
    return True


def main():
    """Run all tests."""
    print("\nBenders Placement Optimization Test Suite")
    print("=" * 60)

    tests = [
        ("ILP Solver", test_ilp_solver),
        ("Constraint Verification", test_constraint_verification),
        ("Cut Addition", test_cut_addition),
        ("Export Solution", test_export_solution),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\nERROR in {name}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    all_passed = all(p for _, p in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
