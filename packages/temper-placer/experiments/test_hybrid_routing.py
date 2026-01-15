"""
Test: Hybrid routing with oscillation detection and negotiated routing.

Tests whether the hybrid approach routes competing SPI nets successfully.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("TEST: Hybrid Routing (Sequential + Negotiated)")
print("=" * 70)

test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

if not test_board.exists():
    print(f"❌ Test board not found: {test_board}")
    sys.exit(1)

print(f"\nTest board: {test_board.name}")
print("Running hybrid router...")

from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(verbose=True)
result = pipeline.run(test_board)

pr = result.stage4.pathfinding_result

print(f"\n{'='*70}")
print("RESULTS")
print(f"{'='*70}")
print(f"Total nets: {pr.success_count + pr.failure_count}")
print(f"Success: {pr.success_count}")
print(f"Failed: {pr.failure_count}")

if pr.competing_nets:
    print(f"\nCompeting nets detected: {len(pr.competing_nets)}")
    print(f"  {', '.join(sorted(pr.competing_nets))}")

if pr.failure_reports:
    print(f"\nFailed nets:")
    for name, report in pr.failure_reports.items():
        print(f"  {name}: {report.failure_reason} (pins={report.pin_count})")

# Check specific nets
spi_nets = ["SPI_MOSI", "SPI_MISO", "SPI_CLK", "SPI_CS_TEMP"]
print(f"\n{'='*70}")
print("SPI NET STATUS")
print(f"{'='*70}")
for net in spi_nets:
    if net in pr.routed_paths:
        print(f"✅ {net}: ROUTED")
    elif net in pr.failed_nets:
        print(f"❌ {net}: FAILED")
    else:
        print(f"⚠️  {net}: UNKNOWN")

total = pr.success_count + pr.failure_count
success_rate = pr.success_count / total * 100 if total > 0 else 0

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"Previous (MST only): 15/17 (88.2%)")
print(f"Current (Hybrid):    {pr.success_count}/{total} ({success_rate:.1f}%)")

if pr.success_count >= 17:
    print(f"\n🎉 ALL NETS ROUTED! Hybrid routing SUCCESS!")
elif pr.success_count > 15:
    print(f"\n✅ IMPROVEMENT! Gained {pr.success_count - 15} more nets")
else:
    print(f"\n⚠️  No improvement or regression")
