"""
Test closed-loop with 2 iterations max (to validate it works).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("CLOSED-LOOP TEST: 2 Iterations with Router Feedback")
print("=" * 70)

benders_input = Path(__file__).parent.parent / "data" / "benders_input.json"
test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

from temper_placer.placement.benders_loop import BendersOptimizer

print("\nRunning Benders with router feedback (max 2 iterations)...")

optimizer = BendersOptimizer(
    component_data_json=benders_input,
    pcb_file=test_board,
    max_iterations=2,
    check_routability=True,
    use_ultrafast_check=False,
    use_router_feedback=True,
    require_drc_clean=False,
    verbose=True,
)

result = optimizer.optimize()

print(f"\n{'='*70}")
print("RESULTS")
print(f"{'='*70}")
print(f"Status: {result.status.value}")
print(f"Iterations: {result.iterations}")
print(f"Total movement: {result.total_movement:.2f}mm")
print(f"Solve time: {result.solve_time_sec:.1f}s")
print(f"Cuts added: {len(result.cuts_added)}")

if result.router_result:
    print(f"\nRouter Results:")
    print(f"  ✓ Routed: {result.router_result.success_count} nets")
    print(f"  ✗ Failed: {result.router_result.failure_count} nets")
    
    if result.router_result.failure_count > 0:
        print(f"\n  Failed nets:")
        for net in result.router_result.failed_nets:
            print(f"    - {net}")
    
    if result.router_result.failure_reports:
        print(f"\n  Failure reports: {len(result.router_result.failure_reports)}")
        for net, report in list(result.router_result.failure_reports.items())[:3]:
            print(f"    {net}: {report.failure_reason}, blockers={len(report.blocking_nets)}")

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")

if result.router_result:
    success_rate = result.router_result.success_count / (result.router_result.success_count + result.router_result.failure_count) * 100
    print(f"Routing success: {success_rate:.1f}%")
    print(f"Cuts generated: {len(result.cuts_added)}")
    
    if len(result.cuts_added) > 0:
        print(f"\n✅ CLOSED-LOOP WORKING:")
        print(f"   - Router executed and reported failures")
        print(f"   - Failures mapped to {len(result.cuts_added)} cuts")
        print(f"   - Cuts added to ILP for next iteration")
    else:
        if result.router_result.failure_count == 0:
            print(f"\n✅ ALL NETS ROUTED!")
        else:
            print(f"\n⚠️  Router failed but no cuts generated")
            print(f"   This means failure mapping needs improvement")
else:
    print(f"\n❌ No router result")

print(f"\nTime breakdown:")
print(f"  ILP: {result.master_problem_time:.1f}s")
print(f"  Router: {result.solve_time_sec - result.master_problem_time:.1f}s")
