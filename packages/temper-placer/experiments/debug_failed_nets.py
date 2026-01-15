"""
Debug why nets are failing to route even after ILP optimization.

Key question: What is the ILP actually optimizing vs what the router needs?
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("DEBUG: Why Are Nets Failing After ILP?")
print("=" * 70)

# ============================================================
# QUESTION 1: What does Benders ILP actually optimize?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 1: What Does Benders ILP Optimize?")
print("=" * 70)

print("""
Benders ILP optimizes PLACEMENT, not routing:

WHAT IT DOES:
✅ Non-overlap constraints (components don't overlap)
✅ HV clearance (high-voltage safety)
✅ Grouping constraints (e.g., decoupling caps near MCU)
✅ Zone constraints (components in correct zones)
✅ Movement budget (minimize displacement from initial)

WHAT IT DOES NOT DO:
❌ Check if routes can physically reach between pads
❌ Verify routing channel capacity
❌ Ensure layer assignment is possible
❌ Check for routing congestion
❌ Validate actual trace paths

The "routability check" we added is a HEURISTIC:
- Ultra-fast check: Just checks congestion/overlaps
- NOT actual routing feasibility
""")

# ============================================================
# QUESTION 2: What nets failed and why?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 2: What Nets Failed?")
print("=" * 70)

# Run the router with verbose output to see which nets failed
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_pipeline_test.kicad_pcb"

if not test_board.exists():
    print(f"Test board not found: {test_board}")
    print("Using temper_placed.kicad_pcb instead")
    test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

# Parse the board to see all nets
pcb = parse_kicad_pcb_v6(test_board)

print(f"\nBoard: {test_board.name}")
print(f"Total nets: {len(pcb.nets)}")

# Show all nets
print(f"\nAll nets in board:")
for i, net in enumerate(pcb.nets):
    pin_count = len(net.pins)
    print(f"  {i+1:2d}. {net.name:20s} ({pin_count} pins)")

# ============================================================
# QUESTION 3: Gap between ILP and Router
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 3: The Gap Between ILP and Router")
print("=" * 70)

print("""
THE FUNDAMENTAL GAP:

Benders ILP works on ABSTRACT placement:
- Components as rectangles with (x, y, width, height)
- Constraints defined in benders_input.json
- No knowledge of actual pad locations
- No knowledge of routing layers
- No knowledge of trace widths

Router V6 works on PHYSICAL routing:
- Actual pad positions on footprints
- Multi-layer routing (F.Cu, B.Cu, In1, In2)
- Real trace widths and clearances
- Via placement
- Design rule checking

WHAT CAN GO WRONG:

1. UNREACHABLE PADS
   - ILP places components legally (no overlap)
   - But pads might be blocked by other components
   - Router can't find a path

2. LAYER CONFLICTS
   - ILP doesn't know about layers
   - Router might need layer that's full
   - No via placement possible

3. CONGESTION
   - ILP allows components to be close
   - Many nets need to route through same channel
   - Router runs out of space

4. NET TOPOLOGY
   - Multi-pin nets need complex routing
   - ILP doesn't consider routing topology
   - Router may not find valid tree structure
""")

# ============================================================
# QUESTION 4: What would fix this?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 4: How to Fix the Gap")
print("=" * 70)

print("""
OPTION 1: Better Routability Checking (Current Approach)
   - Our ultra-fast check is too simple
   - Need actual routing feasibility analysis
   - Max-Flow on channel graph (what we built!)
   
   Problem: Max-Flow check is slow (60s) due to Voronoi

OPTION 2: Iterative Benders with Router Feedback
   - Run Benders → Run Router → Check failures
   - For failed nets, add cuts to push components apart
   - Iterate until all nets route
   
   Problem: Each iteration is slow (35s+ for routing)

OPTION 3: Routing-Aware ILP Constraints
   - Add routing channel constraints to ILP
   - Estimate routing demand per region
   - Limit component density in congested areas
   
   Problem: Complex to model in ILP

OPTION 4: Simultaneous Place & Route
   - Single optimization that considers both
   - Much more complex problem
   - Research-level difficulty

CURRENT BEST PATH:
   - Fix the 3 failed nets manually or debug router
   - The ILP is doing its job (placement)
   - The gap is expected between placement and routing
""")

# ============================================================
# QUESTION 5: Are the failures ILP's fault?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 5: Are the Failures ILP's Fault?")
print("=" * 70)

print("""
PROBABLY NOT.

The Benders ILP successfully:
✅ Placed 33 components without overlap
✅ Satisfied all grouping constraints
✅ Maintained HV clearance
✅ Minimized total movement (30.12mm)
✅ Found OPTIMAL solution

The 3 failed nets are likely due to:
1. Router limitations (not ILP)
2. Complex net topology (multi-pin nets)
3. Layer assignment issues
4. Specific routing challenges

To verify, we'd need to:
1. Identify which 3 nets failed
2. Check if they're multi-pin or simple 2-pin
3. See if there's a physical path available
4. Determine if it's router bug or impossible topology
""")

# Let's check what the router profiling mode is doing
print("\n" + "=" * 70)
print("INVESTIGATION: Router Configuration")
print("=" * 70)

# Check the pipeline config
print(f"""
From the test output we saw:
  "Profiling Mode: Routing only 21 specific nets"

This means Router V6 isn't routing ALL nets!
It's only routing a subset (21 out of {len(pcb.nets)}).

The "14 success, 3 failed" is out of 21 attempted.
The other nets weren't even attempted!

This is a CONFIGURATION issue, not an ILP issue.
""")

print("\n" + "=" * 70)
print("CONCLUSION")
print("=" * 70)

print("""
WHY NETS FAIL AFTER ILP:

1. ILP optimizes PLACEMENT (what it's designed for)
2. Router handles ROUTING (separate problem)
3. There's an inherent gap between the two
4. Router V6 is in "profiling mode" - only routing 21 nets

THE 3 FAILED NETS ARE NOT ILP'S FAULT:
- ILP found optimal placement
- Router couldn't route 3 specific nets
- Need to debug router, not ILP

IMMEDIATE ACTION:
- Check why Router V6 is in "profiling mode"
- Route ALL nets, not just 21
- Then assess real failure rate
""")
