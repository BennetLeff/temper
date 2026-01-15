"""
Test: Topological ordering + MST routing.

Tests whether enabling topological net ordering resolves the
SPI_MOSI/SPI_MISO competition issue.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("TEST: Topological Ordering + MST Routing")
print("=" * 70)

test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

if not test_board.exists():
    print(f"❌ Test board not found: {test_board}")
    sys.exit(1)

print(f"\nTest board: {test_board.name}")

# Run router WITH topological ordering enabled
print("\n🔄 Running router with topological ordering ENABLED...")
from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(verbose=False, enable_topological_ordering=True)
result = pipeline.run(test_board)

pr = result.stage4.pathfinding_result

print(f"\nRouter Results (with topo ordering):")
print(f"  Success: {pr.success_count}")
print(f"  Failed: {pr.failure_count}")

total = pr.success_count + pr.failure_count
success_rate = pr.success_count / total * 100 if total > 0 else 0

if pr.failure_reports:
    print(f"\nFailed nets:")
    for name, report in pr.failure_reports.items():
        print(f"  {name}: {report.failure_reason} (pins={report.pin_count})")
        print(f"    Blocking nets: {report.blocking_nets[:5]}")

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"Total: {total} nets")
print(f"Success: {pr.success_count} ({success_rate:.1f}%)")
print(f"Failed: {pr.failure_count}")

print(f"\nComparison:")
print(f"  Without topo ordering: 15/17 (88.2%)")
print(f"  With topo ordering:    {pr.success_count}/{total} ({success_rate:.1f}%)")

if pr.success_count >= 17:
    print(f"\n🎉 ALL NETS ROUTED!")
elif pr.success_count > 15:
    print(f"\n✅ IMPROVEMENT! Gained {pr.success_count - 15} more nets")
else:
    print(f"\n⚠️  No improvement from topological ordering")
