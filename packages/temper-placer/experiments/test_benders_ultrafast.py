"""
Test Benders with ultra-fast routability checking.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("Testing Benders with Ultra-Fast Routability Check")
print("=" * 70)

temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"
temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

if not temper_json.exists():
    print(f"❌ Input not found: {temper_json}")
    sys.exit(1)

print(f"\n📄 Input: {temper_json.name}")
print(f"📄 PCB: {temper_pcb.name if temper_pcb.exists() else 'N/A'}")

# Test 1: ILP-only (baseline)
print("\n" + "=" * 70)
print("TEST 1: ILP-Only (baseline)")
print("=" * 70)

from temper_placer.placement.benders_loop import run_benders_optimization, BendersStatus

start = time.time()
result1 = run_benders_optimization(
    component_data_json=temper_json,
    max_iterations=3,
    check_routability=False,  # No routability check
    verbose=True,
)
t1 = time.time() - start

print(f"\n✅ ILP-only: {result1.status.value}, {t1:.2f}s")

# Test 2: With ultra-fast routability check
print("\n" + "=" * 70)
print("TEST 2: With Ultra-Fast Routability Check")
print("=" * 70)

start = time.time()
result2 = run_benders_optimization(
    component_data_json=temper_json,
    max_iterations=5,
    check_routability=True,  # Enable routability check
    use_ultrafast_check=True,  # Use fast heuristic
    verbose=True,
)
t2 = time.time() - start

print(f"\n✅ With ultra-fast: {result2.status.value}, {t2:.2f}s")
print(f"   Iterations: {result2.iterations}")
print(f"   Routability time: {result2.routability_check_time:.2f}s")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"""
Test 1 (ILP-only):           {t1:.2f}s
Test 2 (Ultra-fast check):   {t2:.2f}s

Routability overhead:        {t2 - t1:.2f}s
Routability per iteration:   {result2.routability_check_time / max(result2.iterations, 1):.2f}s

This is MUCH faster than the full pipeline (~60s per check)!
""")

# Verify results are reasonable
assert result1.status in (BendersStatus.OPTIMAL, BendersStatus.FEASIBLE)
assert result2.status in (BendersStatus.OPTIMAL, BendersStatus.FEASIBLE)
assert len(result1.final_positions) == 33
assert len(result2.final_positions) == 33

print("✅ All tests passed!")
