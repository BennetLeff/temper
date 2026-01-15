"""
Test Benders ILP with new closed-loop parameters (but don't run router).

This validates that the BendersLoop changes don't break existing ILP functionality.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("BENDERS ILP TEST (No Router)")
print("=" * 70)

benders_input = Path(__file__).parent.parent / "data" / "benders_input.json"
test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

if not benders_input.exists():
    print(f"❌ {benders_input.name} not found")
    sys.exit(1)

if not test_board.exists():
    print(f"❌ {test_board.name} not found")
    sys.exit(1)

print(f"\nBenders input: {benders_input.name}")
print(f"Test board: {test_board.name}")

from temper_placer.placement.benders_loop import BendersOptimizer

print("\nRunning Benders ILP (1 iteration, no routability check)...")

optimizer = BendersOptimizer(
    component_data_json=benders_input,
    pcb_file=test_board,
    max_iterations=1,
    check_routability=False,  # Skip routability - just test ILP
    use_router_feedback=False,
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
assert result.status.value in ["feasible", "optimal"], f"Unexpected status: {result.status}"
assert result.iterations == 1, f"Expected 1 iteration, got {result.iterations}"
assert len(result.final_positions) > 0, "No positions returned"

print(f"\n✅ ILP WORKING: Placed {len(result.final_positions)} components")
print(f"   Movement: {result.total_movement:.2f}mm")
print(f"   Time: {result.solve_time_sec:.1f}s")
