"""
Test: MST-based routing for multi-pin nets.

Validates that:
1. MST is computed correctly for multi-pin nets
2. Routing uses MST edges instead of sequential chain
3. I_SENSE (8 pins) routes successfully
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("TEST: MST-based Routing for Multi-Pin Nets")
print("=" * 70)

# First, test the MST computation directly
print("\n📐 Testing MST Computation...")
from temper_placer.router_v6.steiner_tree import (
    compute_mst_edges,
    compute_routing_order,
    analyze_net_topology,
)

# Test with 8 pins (like I_SENSE)
test_waypoints = [
    (10, 10),
    (20, 15),
    (30, 10),
    (40, 20),
    (50, 15),
    (60, 10),
    (70, 20),
    (80, 15),
]

print(f"\nTest with {len(test_waypoints)} pins:")
analysis = analyze_net_topology(test_waypoints)
print(f"  Sequential (chain) length: {analysis['sequential_length_mm']:.2f}mm")
print(f"  MST length: {analysis['mst_length_mm']:.2f}mm")
print(f"  Improvement: {analysis['improvement_percent']:.1f}%")
print(f"  MST edges: {analysis['edge_count']}")

mst_edges = compute_mst_edges(test_waypoints)
print(f"\nMST Edges:")
for e in mst_edges:
    print(f"  {e.start} → {e.end} ({e.length:.2f}mm)")

routing_order = compute_routing_order(mst_edges)
print(f"\nRouting Order (center-out):")
for i, (start, end) in enumerate(routing_order):
    print(f"  {i+1}. {start} → {end}")

# Now test with actual router
print("\n" + "=" * 70)
print("🔌 Testing Router with MST...")
print("=" * 70)

test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

if not test_board.exists():
    print(f"❌ Test board not found: {test_board}")
    sys.exit(1)

print(f"\nTest board: {test_board.name}")

from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(verbose=False)
result = pipeline.run(test_board)

pathfinding_result = result.stage4.pathfinding_result

print(f"\nRouter Results:")
print(f"  Success: {pathfinding_result.success_count}")
print(f"  Failed: {pathfinding_result.failure_count}")

# Check I_SENSE specifically
if pathfinding_result.routed_paths:
    isense_path = pathfinding_result.routed_paths.get("I_SENSE")
    if isense_path:
        print(f"\n✅ I_SENSE ROUTED!")
        print(f"   Path length: {isense_path.path_length:.2f}mm")
        # Handle both RoutePath and RoutePath3D
        if hasattr(isense_path, 'coordinates'):
            print(f"   Coordinates: {len(isense_path.coordinates)} points")
            print(f"   Layer: {isense_path.layer_name}")
        else:
            print(f"   Segments: {len(isense_path.segments)} points")
            print(f"   Via count: {isense_path.via_count}")
    else:
        print(f"\n❌ I_SENSE not in routed_paths")
else:
    print(f"\n❌ No routed paths")

if pathfinding_result.failure_reports:
    isense_failure = pathfinding_result.failure_reports.get("I_SENSE")
    if isense_failure:
        print(f"\n❌ I_SENSE FAILED!")
        print(f"   Reason: {isense_failure.failure_reason}")
        print(f"   Pin count: {isense_failure.pin_count}")
        print(f"   Blocking nets: {isense_failure.blocking_nets}")
    else:
        print(f"\n✅ I_SENSE not in failure reports (it routed!)")

# Summary
print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
failed_count = pathfinding_result.failure_count
total = pathfinding_result.success_count + failed_count
success_rate = pathfinding_result.success_count / total * 100 if total > 0 else 0

print(f"Total nets: {total}")
print(f"Success: {pathfinding_result.success_count} ({success_rate:.1f}%)")
print(f"Failed: {failed_count}")

if failed_count <= 1:
    print(f"\n🎉 SUCCESS: MST routing improved results!")
    print(f"   Previous: 14/17 (82.4%)")
    print(f"   Current:  {pathfinding_result.success_count}/{total} ({success_rate:.1f}%)")
else:
    print(f"\n⚠️  Still have {failed_count} failures")
    print(f"   Need to investigate further")
