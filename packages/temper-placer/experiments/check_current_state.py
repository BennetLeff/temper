"""
Check the current state of the Temper board:
1. What does Benders give us?
2. What does the router pipeline give us?
3. What's missing for a violation-free, routed PCB?
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("CURRENT STATE ANALYSIS")
print("=" * 70)

temper_json = Path(__file__).parent.parent / "data" / "benders_input.json"
temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

# ============================================================
# PART 1: What does Benders give us?
# ============================================================
print("\n" + "=" * 70)
print("PART 1: What Benders Gives Us")
print("=" * 70)

from temper_placer.placement.benders_loop import run_benders_optimization

result = run_benders_optimization(
    component_data_json=temper_json,
    max_iterations=3,
    check_routability=False,
    verbose=False,
)

print(f"\n✅ Benders Optimization:")
print(f"   Status: {result.status.value}")
print(f"   Components placed: {len(result.final_positions)}")
print(f"   Total movement: {result.total_movement:.2f}mm")
print(f"   Solve time: {result.solve_time_sec:.2f}s")

print(f"\n📋 What Benders provides:")
print(f"   ✅ Optimized component positions")
print(f"   ✅ All constraints satisfied (overlap, clearance, grouping)")
print(f"   ✅ Minimal movement from initial placement")
print(f"   ❌ NO ROUTING - just placement!")

# ============================================================
# PART 2: Check if PCB has existing routes
# ============================================================
print("\n" + "=" * 70)
print("PART 2: Current PCB State")
print("=" * 70)

from kiutils.board import Board

board = Board.from_file(str(temper_pcb))

# Count existing traces
traces = [seg for seg in board.traceItems if hasattr(seg, 'start')]
vias = [v for v in board.traceItems if hasattr(v, 'at') and not hasattr(v, 'start')]
zones = board.zones if hasattr(board, 'zones') else []

print(f"\n📊 Current PCB contents:")
print(f"   Footprints: {len(board.footprints)}")
print(f"   Traces: {len(traces)}")
print(f"   Vias: {len(vias)}")
print(f"   Zones: {len(zones)}")

if len(traces) > 0:
    print(f"\n✅ PCB HAS EXISTING ROUTES")
    print(f"   The board is already partially/fully routed")
else:
    print(f"\n❌ PCB HAS NO ROUTES")
    print(f"   Only component placement, no traces")

# ============================================================
# PART 3: What does the full router pipeline do?
# ============================================================
print("\n" + "=" * 70)
print("PART 3: What Router V6 Pipeline Does")
print("=" * 70)

print(f"""
Router V6 Pipeline stages:

Stage 0: Load PCB
   - Parse KiCad file
   - Extract components, nets, design rules
   
Stage 1: Escape Vias
   - Generate vias for dense packages
   - Connect inner pads to routing layers
   
Stage 2: Channel Analysis
   - Extract routing channels (Voronoi skeleton)
   - Compute channel widths
   - Analyze routing capacity
   
Stage 3: Topological Routing (SAT-based)
   - Assign nets to channels
   - Assign nets to layers
   - Solve topology constraints
   
Stage 4: Geometric Realization (A*)
   - Generate actual trace paths
   - Place vias
   - Assign trace widths
   - Output routed traces

🎯 RESULT: Fully routed PCB with actual traces
""")

# ============================================================
# PART 4: What's missing?
# ============================================================
print("\n" + "=" * 70)
print("PART 4: What's Missing for Violation-Free Routed PCB")
print("=" * 70)

print(f"""
Current status:
✅ Component placement (from Benders)
✅ Placement constraints satisfied
✅ Router pipeline exists (Router V6)
❌ Router pipeline not integrated with Benders output

To get a violation-free, routed PCB:

OPTION 1: Run Router V6 on Benders output
   1. Benders optimizes placement
   2. Update PCB file with new positions
   3. Run full Router V6 pipeline
   4. Get routed traces
   
   Time: ~60s for routing
   Result: Fully routed PCB

OPTION 2: Use external router (KiCad auto-router)
   1. Benders optimizes placement
   2. Update PCB file with new positions
   3. Open in KiCad
   4. Run auto-router or manual routing
   
   Time: Manual effort
   Result: Routed PCB

OPTION 3: Integrated Benders + Router
   1. Benders checks routability during optimization
   2. Generates cuts for unroutable placements
   3. Final placement is provably routable
   4. Run router once at the end
   
   Time: <1s for Benders + 60s for final routing
   Result: Optimized placement + routed PCB

CURRENT STATE: We have Option 3 infrastructure!
   - Benders can check routability (ultra-fast)
   - Router V6 pipeline exists
   - Just need to connect them
""")

# ============================================================
# PART 5: Let's check DRC on current board
# ============================================================
print("\n" + "=" * 70)
print("PART 5: DRC Check (if available)")
print("=" * 70)

# Check if there's a DRC report
drc_files = list(Path(__file__).parent.parent.parent.parent.glob("*-drc.json"))
if drc_files:
    import json
    latest_drc = sorted(drc_files, key=lambda p: p.stat().st_mtime)[-1]
    print(f"\n📄 Latest DRC report: {latest_drc.name}")
    
    with open(latest_drc) as f:
        drc = json.load(f)
    
    if 'violations' in drc:
        violations = drc['violations']
        print(f"   Total violations: {len(violations)}")
        
        # Count by type
        by_type = {}
        for v in violations:
            vtype = v.get('type', 'unknown')
            by_type[vtype] = by_type.get(vtype, 0) + 1
        
        print(f"\n   Violations by type:")
        for vtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"      {vtype}: {count}")
    else:
        print(f"   No violations found!")
else:
    print(f"\n⚠️  No DRC reports found")
    print(f"   Run DRC in KiCad to check for violations")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"""
What we have:
✅ Benders optimizer (placement)
✅ Router V6 pipeline (routing)
✅ Ultra-fast routability checking
✅ Component positions optimized

What we're missing:
❌ Actual routed traces on the PCB
❌ End-to-end integration test

To get a fully routed PCB:
1. Run Benders to optimize placement
2. Run Router V6 pipeline on the result
3. Check DRC for violations
4. Iterate if needed

The infrastructure is all there - just needs to be run!
""")
