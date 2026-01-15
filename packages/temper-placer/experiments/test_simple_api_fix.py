"""Simple test to verify API fixes work."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.placement.benders_loop import run_benders_optimization, BendersStatus

# Test 1: ILP-only (should be fast)
print("=" * 70)
print("TEST: ILP-Only Optimization (Fast)")
print("=" * 70)

temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"

if not temper_json.exists():
    print(f"❌ Input not found: {temper_json}")
    sys.exit(1)

print(f"\n📄 Running ILP-only optimization...")

result = run_benders_optimization(
    component_data_json=temper_json,
    max_iterations=3,
    check_routability=False,  # ILP only - fast!
    verbose=True,
)

print(f"\n{'='*70}")
print("RESULTS")
print(f"{'='*70}")
print(f"Status:       {result.status.value}")
print(f"Components:   {len(result.final_positions)}")
print(f"Movement:     {result.total_movement:.2f}mm")
print(f"Time:         {result.solve_time_sec:.2f}s")

success = (
    result.status in (BendersStatus.OPTIMAL, BendersStatus.FEASIBLE)
    and len(result.final_positions) == 33
)

if success:
    print(f"\n✅ API fixes work! ILP optimization successful.")
    sys.exit(0)
else:
    print(f"\n❌ Test failed")
    sys.exit(1)
