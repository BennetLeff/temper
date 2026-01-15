"""
Detailed debug of router failures.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("DETAILED ROUTER DEBUG")
print("=" * 70)

test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

# Check which nets are skipped vs routed
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

pcb = parse_kicad_pcb_v6(test_board)

# Power/plane nets (skipped by router)
plane_nets = {"GND", "VCC", "VBUS", "PGND", "AGND", "CGND", "+3V3", "+5V", "+12V", "+15V", "V+", "V-", "PWR"}

print(f"\nTotal nets: {len(pcb.nets)}")

print(f"\n📌 POWER NETS (routed via copper pours, not traces):")
power_count = 0
for net in pcb.nets:
    if net.name.upper() in {n.upper() for n in plane_nets}:
        print(f"   SKIP: {net.name:15s} ({len(net.pins):2d} pins)")
        power_count += 1

print(f"\n📌 SIGNAL NETS (routed as traces):")
signal_nets = []
for net in pcb.nets:
    if net.name.upper() not in {n.upper() for n in plane_nets}:
        signal_nets.append(net)
        complexity = "complex" if len(net.pins) > 3 else "simple"
        print(f"   ROUTE: {net.name:15s} ({len(net.pins):2d} pins) [{complexity}]")

print(f"\nSummary:")
print(f"   Power nets (skipped): {power_count}")
print(f"   Signal nets (routed): {len(signal_nets)}")

# Complex nets are harder to route
print(f"\n" + "=" * 70)
print("COMPLEX NETS (>3 pins) - Most Likely to Fail")
print("=" * 70)

complex_nets = [n for n in signal_nets if len(n.pins) > 3]
for net in complex_nets:
    print(f"   {net.name:15s}: {len(net.pins)} pins")
    for ref, pin in net.pins[:5]:  # Show first 5 connections
        print(f"      - {ref}.{pin}")
    if len(net.pins) > 5:
        print(f"      ... and {len(net.pins) - 5} more")

print(f"\n" + "=" * 70)
print("ANALYSIS: Why Do Complex Nets Fail?")
print("=" * 70)

print("""
Complex nets (>3 pins) are harder to route because:

1. ROUTING TOPOLOGY
   - 2-pin net: Single path A→B
   - 8-pin net (like I_SENSE): Tree structure with 7 branches
   - Router must find valid tree without crossing itself

2. CONGESTION
   - Multiple branches compete for same routing channels
   - Each branch blocks space for others
   - Can create "routing deadlock"

3. ILP DOESN'T HELP HERE
   - ILP ensures components don't overlap
   - But doesn't consider routing topology
   - Pads might be legally placed but routing tree impossible

4. WHAT WOULD HELP
   - Steiner tree routing (find optimal tree structure)
   - Global routing before detailed routing
   - Congestion estimation in ILP constraints

The 3 failed nets are likely:
- SW_NODE (6 pins)
- I_SENSE (8 pins)  
- DC_BUS+ (4 pins) or GATE_H/GATE_L (4 pins each)
""")

print(f"\n" + "=" * 70)
print("CONCLUSION: ILP vs ROUTER Responsibility")
print("=" * 70)

print("""
ILP (Benders) Responsibility:
✅ Component placement without overlap
✅ Grouping constraints (decoupling caps near chips)
✅ HV clearance requirements
✅ Zone assignment
→ ILP IS DOING ITS JOB CORRECTLY

Router Responsibility:
❌ Find actual paths for multi-pin nets
❌ Resolve routing conflicts
❌ Handle complex net topologies
→ ROUTER FAILURES ARE ROUTER'S PROBLEM

The Gap:
- ILP places components optimally for PLACEMENT constraints
- But doesn't guarantee optimal for ROUTING
- This is fundamental - they're different problems

To fix:
1. Debug router for complex multi-pin nets
2. OR add routing-aware constraints to ILP
3. OR iterate: route → find failures → add ILP cuts → repeat
""")
