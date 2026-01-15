"""
Test fast routability check for Benders integration.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("Testing Fast Routability Check for Benders")
print("=" * 70)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

if not temper_pcb.exists():
    print(f"❌ PCB not found: {temper_pcb}")
    sys.exit(1)

print(f"\n📄 PCB: {temper_pcb.name}")

# Test the fast routability check
print("\n🔄 Running fast routability check...")
start = time.time()

from temper_placer.router_v6.benders_routability import check_routability_fast

result = check_routability_fast(temper_pcb, verbose=True)

total_time = time.time() - start

print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)

print(f"\n✅ Feasible: {result.is_feasible}")
print(f"   Total capacity: {result.total_capacity:.1f} traces")
print(f"   Utilization: {result.utilization:.1%}")
print(f"   Bottleneck: {result.bottleneck_layer}")

print(f"\n⏱️  Timing:")
print(f"   Parse PCB:       {result.parse_time_sec:.2f}s")
print(f"   Routing space:   {result.routing_space_time_sec:.2f}s")
print(f"   Analysis:        {result.analysis_time_sec:.2f}s")
print(f"   TOTAL:           {result.total_time_sec:.2f}s")

print(f"\n📊 Per-layer capacities:")
for layer, cap in result.capacities.items():
    print(f"   {layer}:")
    print(f"      Area: {cap['total_area_mm2']:.1f} mm²")
    print(f"      Channels: {cap['estimated_channels']}")
    print(f"      Traces: {cap['capacity_traces']}")

print(f"\n📊 Fast skeletons:")
for layer, skel in result.skeletons.items():
    print(f"   {layer}: {skel.node_count} nodes, {skel.edge_count} edges")

print("\n" + "=" * 70)
print("COMPARISON")
print("=" * 70)

print(f"""
Fast routability check:  {result.total_time_sec:.2f}s
Full pipeline (prev):    60+ seconds

Speedup: ~{60 / max(result.total_time_sec, 0.1):.0f}x faster!

This is suitable for iterative Benders optimization.
""")
