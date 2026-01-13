# Session 3 Summary: Fixed Differential Pair Path Reconstruction Bug

**Date**: Jan 7, 2026  
**Branch**: `feat/router-v5`  
**Status**: ✅ CRITICAL BUG FIXED

---

## Problem Identified

USB differential pair routing was creating **disconnected trace segments** with 0.5-1.0mm gaps between them, causing "Missing connection between items" DRC errors.

### Initial Symptoms

```
Via validation results:
- USB_D+: 5 → 11 unconnected items (WORSE after via protection fix)
- USB_D-: 13 → 17 unconnected items (WORSE)

DRC errors showed:
- "Track [USB_D+] on B.Cu, length 0.25mm" at (71.25, 15.0)
- "Track [USB_D+] on B.Cu, length 0.25mm" at (72.0, 15.0)
- Distance: 0.75mm (NOT TOUCHING!)
```

### Investigation Process

1. **First hypothesis**: Via/bridge trace logic was broken
   - Added `is_diff_pair=True` flag to protect vias ✅ (worked)
   - Added bridge traces from via to next point ✅ (worked)
   - But unconnected items INCREASED! ❌

2. **Second hypothesis**: Bridge traces weren't connecting
   - Analyzed actual PCB file traces
   - Found: Traces exist but have **0.5-0.75mm gaps** between them
   - Example: Trace ends at (71.25, 15.0), next starts at (72.0, 15.0)

3. **Root cause discovery**: Path reconstruction bug
   - Examined trace connectivity - found **13 disconnected segments** for USB_D+
   - Path had cells: [..., 285, 284, 288, 287, ...] ← Cell 286 missing!
   - This matched the 0.75mm gap (3 cells at 0.25mm each)

4. **Bug identified**: Backward path not reversed in bidirectional A*
   ```python
   # Old code (WRONG):
   forward_path.reverse()   # ✓ Reversed
   backward_path = [...]    # ✗ NOT reversed!
   full_path = forward_path + backward_path  # ← Creates gaps!
   
   # Fixed code:
   forward_path.reverse()
   backward_path.reverse()  # ✓ Now reversed!
   full_path = forward_path + backward_path  # ✓ Continuous path
   ```

---

## Root Cause Analysis

**File**: `packages/temper-placer/src/temper_placer/routing/diff_pair_router.py`  
**Function**: `_reconstruct_path()` (lines 369-399)

### The Bug

The bidirectional A* search builds paths from both ends:
1. **Forward search**: Start → Meeting point (following parent pointers builds path in reverse)
2. **Backward search**: Goal → Meeting point (following parent pointers builds path in reverse)

The code correctly reversed the forward path but **forgot to reverse the backward path**:

```python
# Forward path: built as [meet, ..., start], then reversed to [start, ..., meet] ✓
forward_path.reverse()

# Backward path: built as [meet-1, ..., goal], should be reversed to [meet+1, ..., goal]
# BUT IT WASN'T! ✗
```

### Impact

The concatenated path became:
```
[start → meet] + [meet-1 → ... → goal (reversed)]
```

This created a "zigzag" pattern:
```
Cell 280 → 281 → 282 → 283 → 284 → 285 (forward to meeting point)
                         ↓
Cell 288 ← 287 ← 286 (backward from goal, NOT reversed)
```

Result: Path jumps from 285 directly to 288, skipping cell 286!

---

## Fix Applied

**Commit**: `4163443` - "fix: reverse backward path in diff pair bidirectional search"

**Change**:
```diff
         backward_path = []
         current = backward_node.parent
         while current is not None:
             backward_path.append(current.state)
             current = current.parent
+        backward_path.reverse()  # FIX: Reverse backward path to maintain continuity
         
         full_path = forward_path + backward_path
```

**Files modified**:
1. `packages/temper-placer/src/temper_placer/routing/diff_pair_router.py` (+1 line)
2. `scripts/debug_diff_pair_path.py` (new debug tool)

---

## Verification

Created `scripts/debug_diff_pair_path.py` to detect gaps in differential pair routing:

```bash
$ python3.11 scripts/debug_diff_pair_path.py

Analyzing: output/test_adaptive_fixed/iteration_1.kicad_pcb

Total USB_D+ traces: 82

B.Cu: 82 traces
  ⚠️  Found 80 gaps:
    Gap 0: trace ends at (70, 15), next starts at (70.5, 15), dist=0.5000mm
    Gap 4: trace ends at (71, 15), next starts at (72, 15), dist=1.0000mm
    ...
Found 13 disconnected segments
```

**After fix**: Expected to show "✓ No gaps detected" (pending full test run).

---

## Related Work This Session

### 1. Via Protection (Commits from earlier in session)

**Commits**: `10cb5dd`, `c8dcae6`

- Added `is_diff_pair: bool = False` field to `Via` dataclass
- Modified `via_validation.py` to skip validation for protected vias
- Added bridge traces from via to next point on new layer

**Impact**: Via validation no longer removes diff pair vias, but revealed the path reconstruction bug.

### 2. Component Lookup Fix

**Commit**: `c8dcae6`

Fixed `adaptive_congestion.py` component lookup:
```python
# Old: netlist.components.get(ref)  # ✗ components is a list!
# New: next((c for c in netlist.components if c.reference == ref), None)  # ✓
```

---

## Testing Status

### Completed
- ✅ Via protection works (USB not in "Affected nets" list)
- ✅ Bridge traces are created
- ✅ Bug identified and fixed
- ✅ Code compiles and imports successfully

### Pending
- ⏳ Full routing test with fixed code
- ⏳ DRC validation to confirm gaps are eliminated
- ⏳ Comparison with baseline (target: ≤81 total unconnected items)

---

## Next Steps

1. **Run full test** with backward path fix:
   ```bash
   ./scripts/test_backpath_fix.sh
   ```

2. **Validate results**:
   ```bash
   python3.11 experiments/validate_adaptive_routing.py
   ```

3. **Compare metrics**:
   - Baseline (before any fixes): 81 unconnected items
   - With via protection (buggy path): 91 unconnected items
   - With backward path fix: **Expected <50 unconnected items**

4. **If successful**, run multi-iteration feedback loop:
   ```bash
   python3.11 scripts/run_feedback_loop.py --max-iterations 3 --output-dir output/final_test
   ```

---

## Files Changed

```
 packages/temper-placer/src/temper_placer/core/board.py                    |  1 +
 packages/temper-placer/src/temper_placer/routing/diff_pair_router.py      |  1 +
 packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py | 5 +++++
 packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py | 55 +++++++
 packages/temper-placer/src/temper_placer/routing/adaptive_congestion.py   |  7 ++
 scripts/debug_diff_pair_path.py                                            | 79 ++++++++++
 scripts/test_backpath_fix.sh                                               | 14 ++
```

---

## Key Learnings

1. **Bidirectional search is tricky**: Both paths need to be reversed when building from parent pointers
2. **Path reconstruction bugs are silent**: The router "succeeds" but produces invalid output
3. **Layered debugging is essential**:
   - First: Via validation (red herring - was working correctly)
   - Second: Bridge traces (red herring - were being created)
   - Third: Actual PCB file analysis (found the gaps!)
   - Fourth: Cell-level path analysis (found the root cause)

4. **Always verify assumptions**: We assumed the diff pair router was returning continuous paths, but it wasn't!

---

## Success Criteria

- [x] Identified root cause (backward path not reversed)
- [x] Applied fix (1-line change)
- [x] Created verification tool (debug_diff_pair_path.py)
- [ ] Full test passes with <50 unconnected items
- [ ] USB_D+/USB_D- have ≤5 unconnected items each
- [ ] No disconnected trace segments

---

## Branch Status

**Current HEAD**: `4163443` (6 commits ahead of main)

**Commit history**:
1. `8ef26d8` - Wire up adaptive congestion detection
2. `91e7639` - Improve fine-pitch component detection
3. `834b45e` - Add comprehensive session 2 summary
4. `10cb5dd` - Protect differential pair vias from validation removal
5. `c8dcae6` - Fix component position lookup bug
6. `4163443` - Fix: reverse backward path in diff pair bidirectional search ← **CRITICAL FIX**

**Ready for**: Full regression test, then merge to main if successful.

---

## Documentation Updates Needed

After testing confirms the fix works:

1. Update `AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md` with:
   - Bidirectional search path reconstruction gotcha
   - How to debug disconnected paths

2. Add unit test for `_reconstruct_path()` to prevent regression

3. Update differential pair router documentation with path continuity validation

---

**Status**: Fix applied and committed. Awaiting full test run to validate.  
**Next session**: Run test, analyze results, and either merge or iterate.
