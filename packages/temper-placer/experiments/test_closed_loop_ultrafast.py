"""
Test Benders with ultra-fast routability check (no router, no DRC).

This validates the heuristic-based iteration loop.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("BENDERS WITH ULTRA-FAST ROUTABILITY CHECK")
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

print("\nRunning Benders with ultra-fast check (max 3 iterations)...")

optimizer = BendersOptimizer(
    component_data_json=benders_input,
    pcb_file=test_board,
    max_iterations=3,
    check_routability=True,
    use_ultrafast_check=True,  # Use heuristic
    use_router_feedback=False,  # Don't run actual router
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

# Validate
assert result.status.value in ["optimal", "max_iterations"], f"Unexpected status: {result.status}"
assert result.iterations <= 3, f"Expected ≤3 iterations, got {result.iterations}"

print(f"\n✅ ULTRA-FAST CHECK WORKING")
print(f"   Converged: {result.status.value == 'optimal'}")
print(f"   Iterations: {result.iterations}")
print(f"   Time: {result.solve_time_sec:.1f}s")
