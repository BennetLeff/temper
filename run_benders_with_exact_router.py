#!/usr/bin/env python3
"""
Run Benders optimization with ExactGeometryRouter for DRC-aware placement.

This uses the placement-routing feedback loop to find a placement that
can be routed with minimal DRC violations.
"""

import sys
from pathlib import Path

sys.path.insert(0, 'packages/temper-placer/src')

from temper_placer.placement.benders_loop import BendersOptimizer, BendersStatus
from temper_placer.io.kicad_drc import run_drc
import json


def main():
    print("=" * 70)
    print(" Benders Optimization with Router Feedback")
    print("=" * 70)
    
    # Run Benders with router feedback
    optimizer = BendersOptimizer(
        component_data_json='packages/temper-placer/data/benders_input.json',
        max_iterations=10,
        pcb_file='pcb/temper.kicad_pcb',
        verbose=True,
        use_router_feedback=True,
        require_drc_clean=True,  # Iterate until DRC clean
    )
    
    result = optimizer.optimize()
    
    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Status: {result.status}")
    print(f"Iterations: {result.iterations}")
    print(f"Cuts added: {len(result.cuts_added)}")
    print(f"Total time: {result.solve_time_sec:.1f}s")
    
    if result.router_result:
        print(f"\nRouter result:")
        if hasattr(result.router_result, 'success_count'):
            print(f"  Routed: {result.router_result.success_count}")
            print(f"  Failed: {result.router_result.failure_count}")
    
    if result.drc_result:
        print(f"\nDRC result:")
        print(f"  Actionable errors: {result.drc_result.actionable_error_count}")
    
    # Run final DRC check
    print("\n" + "=" * 70)
    print(" Final DRC Check")
    print("=" * 70)
    
    try:
        run_drc('pcb/temper.kicad_pcb', 'pcb/temper_benders_drc.json')
        
        with open('pcb/temper_benders_drc.json') as f:
            drc_data = json.load(f)
        
        violations = drc_data.get('violations', [])
        print(f"Total violations: {len(violations)}")
        
        # Categorize
        by_type = {}
        for v in violations:
            t = v.get('type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1
        
        print("\nBy type:")
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {t}: {count}")
        
        # Count routing-related
        routing_types = ['shorting_items', 'clearance', 'tracks_crossing', 'hole_clearance', 'hole_to_hole']
        routing_count = sum(by_type.get(t, 0) for t in routing_types)
        print(f"\nRouting-related violations: {routing_count}")
        
    except Exception as e:
        print(f"DRC failed: {e}")
    
    return 0 if result.status == BendersStatus.OPTIMAL else 1


if __name__ == '__main__':
    sys.exit(main())
