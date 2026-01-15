# Pipeline Gaps and Actions

## What We Discovered

### DRC Results Across Board Versions

| Board File | Total Violations | tracks_crossing | clearance | Notes |
|------------|------------------|-----------------|-----------|-------|
| **temper_placed.kicad_pcb** | 68 | 0 | 8 | ✅ **Clean starting point** |
| **temper_router_v6_output.kicad_pcb** | 1,475 | 2 | 499 | Router V6 output |
| **temper_routed.kicad_pcb** | 3,042 | 1,767 | 500 | ❌ **Broken, unknown source** |

### Key Insights

1. **`temper_placed.kicad_pcb` is a clean starting board**
   - Only 68 violations (mostly cosmetic: silk, lib issues)
   - No routing violations (no routes!)
   - This is what we should use for testing

2. **Router V6 has quality issues but NOT the 1,767 tracks_crossing**
   - Only 2 tracks_crossing in Router V6 output
   - Main issues: clearance (499), diff_pair_gap (308)
   - Router V6 is functional but imperfect

3. **`temper_routed.kicad_pcb` came from unknown source**
   - 1,767 tracks_crossing = massive layer assignment failure
   - Different violation profile than Router V6
   - Possibly from external auto-router or manual mistakes

## Identified Gaps

### GAP 1: No DRC Validation in Pipeline ⚠️
**Problem:** Router V6 outputs routes but never verifies them with KiCad DRC
**Impact:** We shipped broken routing without knowing

**Fix:**
```python
# Add to Router V6 pipeline
from temper_placer.io.kicad_drc import run_drc

def run_with_drc_validation(pcb_file):
    # Run router
    result = pipeline.run(pcb_file)
    
    # Validate output
    drc = run_drc(output_file)
    if drc.error_count > 0:
        raise RouterError(f"Routing produced {drc.error_count} DRC errors")
    
    return result
```

### GAP 2: Router V6 Quality Issues ⚠️
**Problem:** Router V6 produces 1,475 violations even when working
**Impact:** Can't get clean board from automated routing

**Top Router V6 Issues:**
- clearance: 499 (design rule enforcement)
- diff_pair_gap_out_of_range: 308 (differential pair handling)
- shorting_items: 199 (net assignment)
- hole_clearance: 184 (via placement)

**Fix:** Debug Router V6 Stage 4 (geometric realization)
- Check clearance enforcement in A* pathfinding
- Fix diff pair gap calculation
- Verify via placement rules

### GAP 3: No Clean Test Board Was Used ⚠️
**Problem:** We tested on `temper_routed.kicad_pcb` which was already broken
**Impact:** Couldn't validate end-to-end flow

**Fix:** Use `temper_placed.kicad_pcb` (68 violations, no routing issues)

### GAP 4: No Feedback Loop ⚠️
**Problem:** DRC violations don't feed back into Benders optimization
**Impact:** Can't iterate toward zero-violation board

**Fix:** Implement DRC → Benders cut generation
```python
# Parse DRC violations
drc = run_drc(pcb_file)

# Convert to Benders cuts
for violation in drc.violations:
    if violation.type == "clearance":
        # Generate clearance cut between affected components
        cut = generate_clearance_cut(violation)
        benders.add_cut(cut)
```

### GAP 5: Benders Not Using Real Board State ⚠️
**Problem:** Benders uses `benders_input.json`, not actual PCB state
**Impact:** Optimizing against potentially stale data

**Fix:** Generate Benders input from PCB file
```python
# Extract current state from PCB
component_data = extract_component_data(pcb_file)
# Run optimization
result = run_benders_optimization(component_data)
```

## Priority Actions

### IMMEDIATE (Do Now)

**Action 1: Test Full Pipeline on Clean Board**
```bash
# Start with clean board
cp pcb/temper_placed.kicad_pcb pcb/temper_test_pipeline.kicad_pcb

# Run Benders optimization
cd packages/temper-placer
uv run python -c "
from temper_placer.placement.benders_loop import run_benders_optimization
result = run_benders_optimization(
    'data/benders_input.json',
    pcb_file='../../pcb/temper_test_pipeline.kicad_pcb',
    max_iterations=5,
)
print(f'Placed: {len(result.final_positions)} components')
"

# Run Router V6
uv run python -c "
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from pathlib import Path
pipeline = RouterV6Pipeline(verbose=True)
result = pipeline.run(Path('../../pcb/temper_test_pipeline.kicad_pcb'))
print(f'Routed: {result.success_count} nets')
"

# Check DRC
kicad-cli pcb drc --format json --severity-all pcb/temper_test_pipeline.kicad_pcb
```

**Action 2: Add DRC Check to Pipeline**
```python
# In router_v6/pipeline.py, add at end of run():
from temper_placer.io.kicad_drc import run_drc

drc = run_drc(output_path)
if drc.error_count > 0:
    print(f"WARNING: Router produced {drc.error_count} DRC errors")
    # Log top violations
    for vtype, count in drc.violations_by_type().items():
        print(f"  {vtype}: {count}")
```

### SHORT-TERM (This Week)

**Action 3: Fix Top Router V6 Issues**
- [ ] Debug clearance violations (499)
- [ ] Fix diff_pair_gap handling (308)
- [ ] Fix shorting_items (199)

**Action 4: Create End-to-End Test Script**
```python
def test_end_to_end():
    # 1. Start with clean board
    # 2. Run Benders
    # 3. Run Router V6
    # 4. Run DRC
    # 5. Assert error_count == 0
```

### MEDIUM-TERM (Next Sprint)

**Action 5: DRC → Benders Feedback Loop**
- Parse DRC violations
- Map to component pairs
- Generate Benders cuts
- Iterate until clean

**Action 6: Integrated CLI Tool**
```bash
temper optimize --pcb board.kicad_pcb --target-drc-errors 0
```

## Validation Checklist

Before declaring "violation-free routed PCB":

- [ ] Start from `temper_placed.kicad_pcb` (clean)
- [ ] Run Benders optimization
- [ ] Run Router V6 routing  
- [ ] Run actual KiCad DRC (`kicad-cli pcb drc`)
- [ ] Verify 0 errors (warnings OK)
- [ ] Document any remaining issues

## Current Best Board

**Use `temper_placed.kicad_pcb` for testing:**
- 68 violations (mostly cosmetic)
- No routing violations
- Clean starting point for Benders + Router

**Do NOT use `temper_routed.kicad_pcb`:**
- 3,042 violations
- Fundamentally broken routing
- Unknown source of corruption

## Summary

| Gap | Severity | Fix Effort | Status |
|-----|----------|------------|--------|
| No DRC validation | High | 1 hour | ❌ Not started |
| Router V6 quality | High | Days | ❌ Not started |
| No clean test board | Medium | Done | ✅ `temper_placed.kicad_pcb` |
| No feedback loop | Medium | Days | ❌ Not started |
| Stale input data | Low | Hours | ❌ Not started |

**Next immediate step:** Test full pipeline on `temper_placed.kicad_pcb` and measure real output quality.
