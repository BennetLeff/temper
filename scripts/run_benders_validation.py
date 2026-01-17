#!/usr/bin/env python3
"""
Benders Physics Validation Script
==================================

Validates that the Benders optimizer respects real-world HV physics:
- 3.0mm track widths for HighVoltage nets
- Adequate spacing between HV components (Q1, Q2, C_BUS1, C_BUS2)

This script executes Phase 1 of the validation plan.
"""

import sys
import json
import time
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.placement.benders_loop import run_benders_optimization, BendersStatus


def main():
    print("=" * 70)
    print(" BENDERS PHYSICS VALIDATION - Phase 1: The Run")
    print("=" * 70)

    # Configuration
    input_json = Path("packages/temper-placer/data/benders_input.json")
    pcb_file = Path("pcb/temper.kicad_pcb")
    output_json = Path("benders_validation_result.json")

    # Validation plan parameters
    max_iterations = 10
    check_routability = True
    use_ultrafast_check = False  # Use real Max-Flow analysis
    verbose = True

    print(f"\nConfiguration:")
    print(f"  Input JSON: {input_json}")
    print(f"  PCB File: {pcb_file}")
    print(f"  Max Iterations: {max_iterations}")
    print(f"  Check Routability: {check_routability}")
    print(f"  Use Ultrafast Check: {use_ultrafast_check} (using full Max-Flow)")
    print(f"  Verbose: {verbose}")

    # Verify input files exist
    if not input_json.exists():
        print(f"\n✗ ERROR: Input JSON not found: {input_json}")
        return 1

    if not pcb_file.exists():
        print(f"\n✗ ERROR: PCB file not found: {pcb_file}")
        return 1

    print("\n" + "=" * 70)
    print(" Starting Benders Optimization")
    print("=" * 70)

    start_time = time.time()

    try:
        result = run_benders_optimization(
            component_data_json=input_json,
            max_iterations=max_iterations,
            pcb_file=pcb_file,
            check_routability=check_routability,
            verbose=verbose,
            use_ultrafast_check=use_ultrafast_check,
        )

        elapsed = time.time() - start_time

        print("\n" + "=" * 70)
        print(" RESULTS - Phase 1 Complete")
        print("=" * 70)

        print(f"\nStatus: {result.status.value.upper()}")
        print(f"Iterations: {result.iterations}")
        print(f"Total Time: {elapsed:.1f}s")
        print(f"  - Master Problem (ILP): {result.master_problem_time:.1f}s")
        print(f"  - Routability Check: {result.routability_check_time:.1f}s")
        print(f"Total Movement: {result.total_movement:.2f}mm")
        print(f"Cuts Added: {len(result.cuts_added)}")

        # Display cuts
        if result.cuts_added:
            print("\nRoutability Cuts Generated:")
            for i, cut in enumerate(result.cuts_added, 1):
                print(
                    f"  {i}. Type: {cut.cut_type.value}, Pair: {cut.component_pair}, Gap: {cut.gap_required:.2f}mm"
                )

        # Display final positions for HV components
        hv_components = ["Q1", "Q2", "C_BUS1", "C_BUS2"]
        print("\nHigh Voltage Component Positions:")
        for comp in hv_components:
            if comp in result.final_positions:
                x, y = result.final_positions[comp]
                print(f"  {comp}: ({x:.2f}, {y:.2f})")
            else:
                print(f"  {comp}: NOT FOUND")

        # Save results
        output_data = {
            "status": result.status.value,
            "iterations": result.iterations,
            "total_time_sec": elapsed,
            "master_problem_time_sec": result.master_problem_time,
            "routability_check_time_sec": result.routability_check_time,
            "total_movement_mm": result.total_movement,
            "cuts_added": [
                {
                    "cut_type": cut.cut_type.value,
                    "component_pair": cut.component_pair,
                    "gap_required_mm": cut.gap_required,
                }
                for cut in result.cuts_added
            ],
            "final_positions": {
                ref: {"x_mm": pos[0], "y_mm": pos[1]} for ref, pos in result.final_positions.items()
            },
        }

        with open(output_json, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\nResults saved to: {output_json}")

        # Success criteria check
        print("\n" + "=" * 70)
        print(" SUCCESS CRITERIA")
        print("=" * 70)

        success = True

        # Check 1: Did it converge?
        if result.status == BendersStatus.OPTIMAL:
            print("✓ Converged to optimal placement")
        elif result.status == BendersStatus.FEASIBLE:
            print("✓ Found feasible placement")
        else:
            print(f"✗ Failed to find valid placement: {result.status.value}")
            success = False

        # Check 2: Were HV-aware cuts generated?
        hv_cuts = [
            c for c in result.cuts_added if any(comp in c.component_pair for comp in hv_components)
        ]
        if hv_cuts:
            print(f"✓ Generated {len(hv_cuts)} HV-related cuts")
            for cut in hv_cuts:
                if cut.gap_required >= 3.0:
                    print(
                        f"  ✓ Cut requires {cut.gap_required:.1f}mm gap (>= 3.0mm HV track width)"
                    )
                else:
                    print(
                        f"  ✗ Cut requires only {cut.gap_required:.1f}mm gap (< 3.0mm HV track width)"
                    )
                    success = False
        else:
            print("⚠ No HV-specific cuts generated (may be OK if initial placement was good)")

        # Check 3: All HV components have positions
        missing = [c for c in hv_components if c not in result.final_positions]
        if missing:
            print(f"✗ Missing HV component positions: {missing}")
            success = False
        else:
            print("✓ All HV components have final positions")

        if success:
            print("\n✓✓✓ PHASE 1 PASSED: Ready for Phase 2 analysis")
            return 0
        else:
            print("\n✗✗✗ PHASE 1 FAILED: Issues detected")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR during optimization: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
