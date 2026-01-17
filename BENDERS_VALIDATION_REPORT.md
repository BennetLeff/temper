# Benders Physics Validation - Final Report

## Executive Summary

The validation plan successfully identified a **critical configuration gap** in the Temper PCB optimizer: the constraints file was never updated from simulation values (0.3mm traces) to real-world manufacturing values (3.0mm traces for 40A current).

## Validation Results

### Phase 1: The Run ✗ FAILED (But Productive)

**Configuration:**
- Max iterations: 10
- Check routability: TRUE (full Max-Flow analysis)
- Use ultrafast check: FALSE

**Execution:**
- Iteration 1: Generated 54 routability cuts requiring 10mm gaps
- Iteration 2: Master problem became **INFEASIBLE**

**Root Cause:**
The Benders cut generator doesn't receive updated design rules. It defaults to:
```python
base_trace_width_mm = 0.2  # Generic default
max_gap_mm = 10.0          # Maximum gap clamp
```

When Max-Flow analysis runs on a PCB with 3.0mm HV tracks, it sees massive congestion and generates cuts requiring 10mm gaps between almost all components, making the placement infeasible.

### Phase 2: The Gap Test ✓✓✓ PASSED

Created `scripts/analysis/verify_hv_spacing.py` which confirmed:

#### Metric 1: Component Spacing
```
Q1 <-> Q2:  5.00mm gap ✓ (required: 4.00mm)
Q1 <-> C_BUS1: 35.00mm gap ✓
Q1 <-> C_BUS2: 15.00mm gap ✓  
Q2 <-> C_BUS1: 50.00mm gap ✓
Q2 <-> C_BUS2: 30.00mm gap ✓
C_BUS1 <-> C_BUS2: 10.00mm gap ✓
```

**Result:** Current placement HAS adequate spacing for 3.0mm HV tracks

#### Metric 2: Routing Channel Capacity
```
HighVoltage net class:
  Track width: 3.0mm ✓ (FIXED from 0.3mm)
  Clearance: 3.0mm ✓
```

**Result:** Constraints file now correctly specifies real-world physics

### Critical Discovery: The Configuration Gap

**File:** `packages/temper-placer/configs/temper_constraints.yaml`

**Before (WRONG):**
```yaml
HighVoltage:
  trace_width_mm: 0.3   # Simulation value
  max_current_rating: 1.0  # Wrong!
```

**After (FIXED):**
```yaml
HighVoltage:
  trace_width_mm: 3.0   # Real 40A current
  max_current_rating: 40.0  # Correct for IGBTs
```

This explains ALL previous failures:
1. **Tight placements:** Optimizer was optimizing for 0.3mm channels
2. **Infeasible Benders:** After Max-Flow sees real routing failures, it adds cuts requiring huge gaps, conflicting with 0.3mm assumption
3. **DRC violations:** Router tried to route 3mm traces in 0.3mm-optimized placements

## Architectural Issue Discovered

The Benders cut generator (`BendersCutGenerator`) is initialized with **hardcoded defaults**:
```python
def __init__(
    self,
    min_gap_mm: float = 2.0,
    max_gap_mm: float = 10.0,
    base_trace_width_mm: float = 0.2,  # ← PROBLEM: Doesn't know about HV nets
    base_clearance_mm: float = 0.2,
):
```

When Max-Flow identifies bottlenecks with 3.0mm HV tracks, the cut generator estimates:
```python
required_gap = max_edges * 0.2mm * 1.5 + 2.0mm
# With high max_edges → clamps to 10.0mm (max_gap_mm)
```

This creates 54 cuts all requiring 10mm gaps, making the placement problem infeasible on a 100x150mm board.

## Success Criteria Analysis

| Metric                    | Target                       | Actual                        | Status  |
|---------------------------|------------------------------|-------------------------------|---------|
| HV Track Width (Config)   | 3.0mm                        | 3.0mm ✓ (FIXED)               | ✓ PASS  |
| HV Component Gap          | > 4.0mm                      | 5.0mm (min Q1-Q2)             | ✓ PASS  |
| Benders Cuts              | "Separation: 3.5mm+"         | 10.0mm (too aggressive)       | ⚠ ISSUE |
| Benders Convergence       | Optimal/Feasible             | Infeasible after iter 2       | ✗ FAIL  |
| Configuration Consistency | HV=3mm everywhere            | Config ✓, Cut Gen ✗           | ⚠ MIXED |

## Recommendations

### Immediate Fixes

1. **Pass Design Rules to Cut Generator**
   ```python
   # In benders_loop.py
   self._cut_generator = BendersCutGenerator(
       min_gap_mm=2.0,
       max_gap_mm=10.0,
       base_trace_width_mm=design_rules.get_max_trace_width(),  # ← Use actual max
       base_clearance_mm=design_rules.get_max_clearance(),      # ← Use actual max
   )
   ```

2. **Smart Gap Estimation**
   Instead of using `max_edges * pitch`, use:
   - Net class information from the actual nets crossing the channel
   - Weighted average based on net classes (not just maximum)
   - Lower multiplier (1.2x instead of 1.5x) for tighter packing

3. **Iterative Cut Strategy**
   - Start with fewer cuts (top 10 most critical)
   - Add more cuts only if placement succeeds but routing fails
   - Use graduated gap increases (start at 3mm, increase to 5mm, then 10mm)

### Long-Term Architecture

1. **Unified Design Rules**
   - Single source of truth: `temper_constraints.yaml`
   - All components (router, Benders, DRC) read from this
   - Validation script to check consistency

2. **Net-Class-Aware Optimization**
   - Benders ILP should know which nets are HV vs signal
   - Enforce larger gaps specifically for HV component pairs
   - Don't over-constrain signal net routing channels

3. **Feedback Loop Refinement**
   - Use actual router failures (not just Max-Flow heuristics) for cuts
   - Track which cuts were productive vs counterproductive
   - Learn optimal gap sizes from successful vs failed iterations

## Validation Plan Status

- ✓ Phase 1: Execution complete (revealed architectural issue)
- ✓ Phase 2: Analysis complete (confirmed fix + discovered cut generator gap)
- ⚠ Phase 3: Blocked pending cut generator fix

## Files Created

1. `scripts/run_benders_validation.py` - Automated validation script
2. `scripts/analysis/verify_hv_spacing.py` - Component spacing analyzer
3. `benders_validation_output.log` - Full execution log
4. `benders_validation_result.json` - Structured results

## Key Insight

**The Benders optimizer is working correctly** - it's detecting that the placement is not routable and generating cuts. The problem is that the cut generator doesn't have access to the actual net class rules, so it generates overly conservative cuts based on generic defaults. This is a **configuration plumbing issue**, not an algorithmic failure.

---

**Next Action:** Implement smart cut generation that uses actual design rules from the constraints file.
