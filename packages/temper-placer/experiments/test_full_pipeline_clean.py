"""
Test full pipeline on clean board (temper_placed.kicad_pcb).

This is the real end-to-end test:
1. Start with clean board (68 violations, no routes)
2. Run Benders optimization
3. Run Router V6
4. Check DRC
5. Report results
"""

import sys
import time
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("FULL PIPELINE TEST ON CLEAN BOARD")
print("=" * 70)

# Paths
clean_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"
test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_pipeline_test.kicad_pcb"
benders_json = Path(__file__).parent.parent / "data" / "benders_input.json"

if not clean_board.exists():
    print(f"❌ Clean board not found: {clean_board}")
    sys.exit(1)

# Step 0: Copy clean board
print(f"\n📋 Step 0: Copy clean board")
shutil.copy(clean_board, test_board)
print(f"   Copied {clean_board.name} → {test_board.name}")

# Step 1: Initial DRC
print(f"\n📋 Step 1: Initial DRC on clean board")
from temper_placer.io.kicad_drc import run_drc

initial_drc = run_drc(test_board)
print(f"   Violations: {initial_drc.total_count}")
print(f"   Errors: {initial_drc.error_count}")
print(f"   Warnings: {initial_drc.warning_count}")

# Step 2: Benders optimization
print(f"\n📋 Step 2: Benders Optimization")
from temper_placer.placement.benders_loop import run_benders_optimization

start = time.time()
benders_result = run_benders_optimization(
    component_data_json=benders_json,
    pcb_file=test_board,
    max_iterations=5,
    check_routability=True,
    use_ultrafast_check=True,
    verbose=False,
)
benders_time = time.time() - start

print(f"   Status: {benders_result.status.value}")
print(f"   Components: {len(benders_result.final_positions)}")
print(f"   Movement: {benders_result.total_movement:.2f}mm")
print(f"   Time: {benders_time:.2f}s")

# Step 3: Post-Benders DRC
print(f"\n📋 Step 3: Post-Benders DRC")
post_benders_drc = run_drc(test_board)
print(f"   Violations: {post_benders_drc.total_count}")
print(f"   Change: {post_benders_drc.total_count - initial_drc.total_count:+d}")

# Step 4: Router V6 (this is slow)
print(f"\n📋 Step 4: Router V6 Routing")
print(f"   ⚠️  This will take ~60 seconds...")

from temper_placer.router_v6.pipeline import RouterV6Pipeline

start = time.time()
try:
    pipeline = RouterV6Pipeline(verbose=False)
    router_result = pipeline.run(test_board)
    router_time = time.time() - start
    router_success = True
    print(f"   Success: {router_result.success_count} nets routed")
    print(f"   Failed: {router_result.failure_count} nets")
    print(f"   Time: {router_time:.2f}s")
except Exception as e:
    router_time = time.time() - start
    router_success = False
    print(f"   ❌ Router failed: {e}")
    print(f"   Time before failure: {router_time:.2f}s")

# Step 5: Final DRC
print(f"\n📋 Step 5: Final DRC")
final_drc = run_drc(test_board)
print(f"   Total violations: {final_drc.total_count}")
print(f"   Errors: {final_drc.error_count}")
print(f"   Warnings: {final_drc.warning_count}")

if final_drc.total_count > 0:
    print(f"\n   Top violations:")
    for vtype, count in sorted(final_drc.violations_by_type().items(), key=lambda x: -x[1])[:5]:
        print(f"      {vtype}: {count}")

# Summary
print("\n" + "=" * 70)
print("PIPELINE RESULTS SUMMARY")
print("=" * 70)

print(f"""
Initial board:
   DRC errors: {initial_drc.error_count}

After Benders:
   Status: {benders_result.status.value}
   Movement: {benders_result.total_movement:.2f}mm
   Time: {benders_time:.2f}s
   DRC errors: {post_benders_drc.error_count} (change: {post_benders_drc.error_count - initial_drc.error_count:+d})

After Router V6:
   Success: {'✅' if router_success else '❌'}
   Time: {router_time:.2f}s
   DRC errors: {final_drc.error_count}

VERDICT: {'✅ CLEAN BOARD' if final_drc.error_count == 0 else f'❌ {final_drc.error_count} DRC ERRORS REMAIN'}
""")

if final_drc.error_count > 0:
    print("Router V6 needs debugging to produce clean output.")
    print("Top issues to fix:")
    for vtype, count in sorted(final_drc.violations_by_type().items(), key=lambda x: -x[1])[:3]:
        print(f"   - {vtype}: {count}")
