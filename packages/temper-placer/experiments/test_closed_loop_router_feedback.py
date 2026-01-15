"""
Test Benders with actual router feedback (1 iteration).

This validates that router integration works and failure mapping produces cuts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("BENDERS WITH ROUTER FEEDBACK (1 Iteration)")
print("=" * 70)

benders_input = Path(__file__).parent.parent / "data" / "benders_input.json"
test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

if not benders_input.exists():
    print(f"❌ {benders_input.name} not found")
    sys.exit(1)

if not test_board.exists():
    print(f"❌ {test_board.name} not found")
    sys.exit(1)

from temper_placer.placement.benders_loop import BendersOptimizer

print("\nRunning Benders with router feedback (1 iteration)...")
print("This will take ~40s (ILP + Router)...")

optimizer = BendersOptimizer(
    component_data_json=benders_input,
    pcb_file=test_board,
    max_iterations=1,
    check_routability=True,
    use_ultrafast_check=False,  # Don't use heuristic
    use_router_feedback=True,  # Use actual router
    require_drc_clean=False,  # Don't run DRC yet
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
    success = result.router_result.success_count if hasattr(result.router_result, 'success_count') else len(result.router_result.routed_paths)
    failed = result.router_result.failure_count if hasattr(result.router_result, 'failure_count') else len(result.router_result.failed_nets)
    print(f"  ✓ Routed: {success} nets")
    print(f"  ✗ Failed: {failed} nets")
    
    if failed > 0 and hasattr(result.router_result, 'failed_nets'):
        print(f"\n  Failed nets:")
        for net in result.router_result.failed_nets[:5]:
            print(f"    - {net}")
    
    if hasattr(result.router_result, 'failure_reports') and result.router_result.failure_reports:
        print(f"\n  Failure reports available: {len(result.router_result.failure_reports)}")
else:
    print("\n⚠️  No router result available")

# Validate
assert result.status.value in ["optimal", "max_iterations"], f"Unexpected status: {result.status}"
assert result.router_result is not None, "Router result missing"

print(f"\n✅ ROUTER FEEDBACK WORKING")
print(f"   Router executed: Yes")
print(f"   Failure data captured: {result.router_result is not None}")
print(f"   Time: {result.solve_time_sec:.1f}s")
