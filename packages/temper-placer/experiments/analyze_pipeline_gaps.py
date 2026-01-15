"""
Analyze pipeline gaps revealed by real DRC results.

Key question: What produced the broken routing with 3,042 violations?
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("PIPELINE GAP ANALYSIS")
print("=" * 70)

# ============================================================
# QUESTION 1: Where did the broken routes come from?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 1: Where did the broken routes come from?")
print("=" * 70)

print("""
The temper_routed.kicad_pcb has 5,995 traces with 3,042 DRC violations.

Possible sources:
1. Router V6 pipeline output?
2. Manual routing (incomplete)?
3. External auto-router (failed)?
4. Test/development artifacts?

Let's check the file history and router output...
""")

# Check if there are other PCB files to compare
pcb_dir = Path(__file__).parent.parent.parent.parent / "pcb"
pcb_files = list(pcb_dir.glob("*.kicad_pcb"))

print(f"\nPCB files in {pcb_dir.name}/:")
for pcb in sorted(pcb_files):
    print(f"  - {pcb.name}")

# ============================================================
# QUESTION 2: What's broken in the routing?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 2: What's broken in the routing?")
print("=" * 70)

print("""
Top violations (from KiCad DRC):

1. tracks_crossing: 1,767 errors
   - Traces on SAME LAYER crossing without vias
   - This is the most severe - impossible to manufacture
   - Root cause: Router didn't properly assign layers OR
                 placed traces without checking conflicts

2. clearance: 500 errors
   - Traces too close to each other
   - Root cause: Router not respecting design rules OR
                 design rules not loaded correctly

3. shorting_items: 199 errors
   - Components creating shorts
   - Root cause: Routing connected wrong nets OR
                 traces overlapping with pads incorrectly

4. holes_co_located: 91 errors
   - Multiple drill holes in same location
   - Root cause: Duplicate vias or broken via placement
""")

# ============================================================
# QUESTION 3: What's missing in our pipeline?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 3: Pipeline Gaps Identified")
print("=" * 70)

print("""
GAP 1: NO DRC VALIDATION IN PIPELINE
   - Router V6 outputs routes but doesn't verify them
   - We had no way to know routing was broken
   - ACTION: Add DRC check after routing

GAP 2: ROUTER V6 QUALITY ISSUES
   - If Router V6 produced these routes, it has bugs
   - tracks_crossing = layer assignment failures
   - clearance = design rule enforcement failures
   - ACTION: Debug Router V6 output quality

GAP 3: NO CLEAN STARTING BOARD
   - We've been testing on a broken board
   - Can't verify Benders + Router works end-to-end
   - ACTION: Create clean board (footprints only, no routes)

GAP 4: NO ITERATIVE FEEDBACK LOOP
   - Benders doesn't know about DRC violations
   - Router doesn't feed back to placement
   - ACTION: Implement DRC → Benders cut generation

GAP 5: STALE DATA ASSUMPTIONS
   - Trusted old DRC report without verification
   - Assumed 5,995 traces = good routing
   - ACTION: Always run fresh DRC, not cached reports
""")

# ============================================================
# QUESTION 4: What are the priority actions?
# ============================================================
print("\n" + "=" * 70)
print("QUESTION 4: Priority Actions")
print("=" * 70)

print("""
PRIORITY 1 (Immediate): Create Clean Test Board
   - Copy temper_routed.kicad_pcb
   - Remove all traces and vias (keep footprints, zones, outline)
   - This gives us a valid starting point
   - Time: 5 minutes in KiCad

PRIORITY 2 (Immediate): Verify Router V6 Output
   - Run Router V6 on clean board
   - Check DRC on result
   - Identify if router is the problem source
   - Time: ~60 seconds

PRIORITY 3 (Short-term): Add DRC to Pipeline
   - After routing, automatically run DRC
   - Fail if errors > 0
   - Report violations clearly
   - Time: 1 hour coding

PRIORITY 4 (Short-term): Debug Router V6
   - If router produces violations, find bugs
   - Focus on layer assignment (tracks_crossing)
   - Focus on clearance checking
   - Time: Hours to days depending on bugs

PRIORITY 5 (Medium-term): DRC Feedback Loop
   - Parse DRC violations
   - Generate Benders cuts from violations
   - Iterate until violations = 0
   - Time: Days of work
""")

# ============================================================
# Let's check what Router V6 actually does
# ============================================================
print("\n" + "=" * 70)
print("INVESTIGATION: Router V6 Pipeline Check")
print("=" * 70)

# Check router outputs
router_outputs = list(Path(__file__).parent.parent.parent.parent.glob("routed_*.kicad_pcb"))
print(f"\nRouter V6 output files found: {len(router_outputs)}")
for f in router_outputs[:5]:
    print(f"  - {f.name}")

# Check if there's a "clean" or "unrouted" version
unrouted = list(Path(__file__).parent.parent.parent.parent.glob("*unrouted*.kicad_pcb"))
unrouted += list(Path(__file__).parent.parent.parent.parent.glob("*placed*.kicad_pcb"))
print(f"\nUnrouted/placed files found: {len(unrouted)}")
for f in unrouted[:5]:
    print(f"  - {f.name}")

print("\n" + "=" * 70)
print("SUMMARY: What We Learned")
print("=" * 70)

print("""
1. Our "routed" board is broken (3,042 violations)
2. We don't know if Router V6 caused this or it was pre-existing
3. We have no DRC validation in the pipeline
4. We need a clean starting point to test properly
5. The Benders work is valuable but can't be validated end-to-end yet

NEXT STEP: Create a clean board and test Router V6 properly
""")
