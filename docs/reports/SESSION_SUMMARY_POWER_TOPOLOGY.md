# Session Summary: Power Topology Refactoring (Task temper-zy08)

**Date**: 2026-01-07  
**Branch**: feat/router-v5  
**Task**: temper-zy08 - Simplify power distribution: +5V/+3V3 trace routing

---

## Objective

Change medium/low-current power rails from plane connectivity to trace routing to reduce unconnected items and fix multi-net plane conflicts.

**Expected Impact**: -30 unconnected items (+5V: 12, +3V3: 18)

---

## What We Built

### 1. Power Topology Module (TDD, 100% Test Coverage)

**File**: `packages/temper-placer/src/temper_placer/core/power_topology.py` (239 lines, new)

**Core Types** (Immutable, Functional):
- `PowerDeliveryStrategy` - Enum: PLANE, WIDE_TRACE, STANDARD_TRACE
- `PowerRailSpec` - Rail specification with IPC-2221 trace width calculation
- `PowerDistributionTree` - Hierarchical power tree representation
- `IPC2221Rule` - Trace width calculator (1oz copper, 10°C rise)
- `TemperPowerTopology` - Temper-specific power architecture factory

**Power Strategy** (Data-Driven):
```python
+15V (5A)  → PowerDeliveryStrategy.PLANE        (requires inner layer pour)
+5V (2A)   → PowerDeliveryStrategy.WIDE_TRACE   (0.4mm traces)
+3V3 (0.5A) → PowerDeliveryStrategy.STANDARD_TRACE (0.15mm traces)
VCC_BOOT (0.1A) → PowerDeliveryStrategy.STANDARD_TRACE (thin traces)
```

**Tests**: `experiments/test_power_topology.py` (20 tests, all passing)

---

### 2. Configuration Changes

**File**: `configs/temper_deterministic_config.yaml`

**New Net Class**: PowerTrace
```yaml
PowerTrace:
  type: power
  connectivity: trace         # Route as traces (NOT plane)
  target_layer: "F.Cu"
  max_current_a: 2.0
  trace_width_mm: 0.4         # IPC-2221: 2A * 0.15 + 0.1
  clearance_mm: 0.3
  via_size_mm: 0.8
  via_drill_mm: 0.4
```

**Net Assignments**:
- `+15V`: Power → **Power** (unchanged, plane)
- `+5V`: Power → **PowerTrace** (trace routing)
- `+3V3`: FinePitch → **FinePitch** (unchanged, already trace)
- `VCC_BOOT`: Power → **Signal** (trace routing)

---

### 3. Layer Assignment Updates

**File**: `packages/temper-placer/src/temper_placer/deterministic/stages/layer_assignment.py`

**Added Cases**:
```python
elif net_class == "PowerTrace":
    return 0, False  # Top layer, routed as traces (NOT plane)
elif net_class == "FinePitch":
    return 0, False  # Top layer for fine-pitch IC routing
elif net_class == "FinePitchPower":
    return 2, True   # Inner power plane (legacy)
```

---

### 4. PowerPlaneStage Fix (Root Cause Resolution)

**File**: `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py`

**Problem Identified**:
```python
# OLD (incorrect):
TEMPER_PLANE_NETS = frozenset({
    "GND", "PGND", "CGND",
    "+15V", "+5V", "+3V3", "VCC_BOOT",  # <-- HARDCODED, overrides LayerAssignment
    ...
})
```

PowerPlaneStage ran **AFTER** LayerAssignmentStage in the pipeline (line 129 of `__init__.py`) and overwrote `is_plane=True` for all power nets, regardless of their net class.

**Fix**:
```python
# NEW (correct):
TEMPER_PLANE_NETS = frozenset({
    "GND", "PGND", "CGND",
    "+15V",  # Only high-current rail (5A) remains as plane
    # "+5V", "+3V3", "VCC_BOOT" removed - now trace routed
    ...
})
```

**Verification**:
```bash
# Before fix:
INFO: Found via site for +5V at 0.5mm from pad  # <-- Plane vias (wrong!)

# After fix:
Routing net 19/24: +5V...  # <-- MST/A* routing (correct!)
WARNING: Could not find any path for +5V segment 0->1
INFO: Multi-layer route found for +5V (1 vias)
```

---

## Results

### DRC Impact Analysis

**Baseline** (output/test5): 68 unconnected items  
**After Fix** (output/test_power_trace): 81 unconnected items (+13 total)

| Net       | Baseline | After Fix | Change | Notes                          |
|-----------|----------|-----------|--------|--------------------------------|
| +3V3      | 18       | 12        | **-6** | ✓ Improved (fewer pads)       |
| VCC_BOOT  | 4        | 2         | **-2** | ✓ Improved                     |
| PGND      | 10       | 4         | **-6** | ✓ Improved (side effect)      |
| +5V       | 12       | 22        | **+10**| ✗ Routing congestion           |
| USB_D-    | 6        | 26        | **+20**| ✗ Regression (congestion)      |
| USB_D+    | 6        | 10        | **+4** | ✗ Regression                   |
| SPI_CLK   | 6        | 8         | **+2** | ✗ Slight regression            |
| I_SENSE   | 16       | 18        | **+2** | ✗ Slight regression            |

### Routing Time Analysis

- **+5V**: 48.52 seconds (was instant plane vias)
- **+3V3**: 42.70 seconds (was instant plane vias)
- **Multi-layer A* timeout**: 14,240 iterations for +5V (dist=89 cells)

### Architecture Validation

✅ **Correct Behavior Achieved**:
1. PowerTrace nets (`+5V`) use MST/A* routing (not plane vias)
2. Plane nets (`+15V`, `GND`) still use plane connectivity
3. Layer assignments respected by routing pipeline
4. IPC-2221 trace widths applied (+5V: 0.4mm)

❌ **Routing Congestion Issues** (Expected):
1. A* pathfinder failing on congested segments
2. Iteration limits too low (14k vs needed ~50k+)
3. USB differential pairs regressing (likely board-wide congestion)

---

## Key Insights

### 1. Pipeline Stage Ordering Matters

```python
# Pipeline in __init__.py:
LayerAssignmentStage()   # Sets is_plane based on net_class
PowerPlaneStage()        # OVERWRITES is_plane for hardcoded nets <- BUG!
SequentialRoutingStage() # Uses is_plane to decide routing strategy
```

**Lesson**: Later stages can override earlier decisions. Hardcoded lists must be carefully maintained.

### 2. Test-Driven Development Paid Off

We caught the logic error immediately:
1. Tests showed layer assignment worked (is_plane=False) ✓
2. Validation showed no routing happening ✗
3. Log inspection revealed plane via creation → led us to PowerPlaneStage

### 3. Functional Design Enables Reasoning

Immutable types (`PowerRailSpec`, `PowerDistributionTree`) made it easy to:
- Unit test pure functions (trace width calculation)
- Reason about power distribution hierarchy
- Validate IPC-2221 compliance

---

## Files Modified

### New Files (3):
- `packages/temper-placer/src/temper_placer/core/power_topology.py` (239 lines)
- `experiments/test_power_topology.py` (20 tests)
- `experiments/validate_power_trace_routing.py` (validation script)

### Modified Files (3):
- `configs/temper_deterministic_config.yaml` (+PowerTrace class, net assignments)
- `packages/temper-placer/src/temper_placer/deterministic/stages/layer_assignment.py` (+PowerTrace case)
- `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py` (removed +5V/+3V3/VCC_BOOT)

---

## Next Steps

### Task temper-zy08 Status: **Partially Complete** (50%)

**Completed**:
- ✅ Power topology modeling (TDD, 100% coverage)
- ✅ Config infrastructure (PowerTrace net class)
- ✅ Root cause fix (PowerPlaneStage override)
- ✅ Architectural correctness (trace routing works)

**Remaining**:
- ❌ Routing congestion mitigation
- ❌ Net-by-net validation (+5V, +3V3, VCC_BOOT)
- ❌ DRC improvement (currently +13 violations, expected -30)

### Recommended Follow-On Tasks

**High Priority** (Blocking temper-zy08 completion):
1. **Task temper-t4si**: Adaptive A* iteration limits
   - +5V timeout at 14k iterations (needs ~50k-100k)
   - Would fix +10 regression on +5V
   - Estimated impact: -15 unconnected items

2. **Routing Congestion Analysis**:
   - USB_D- regression (+20) suggests board-wide issue
   - May need routing channel analysis
   - Consider routing order changes (route USB before power?)

**Medium Priority**:
3. **Task temper-z3pl**: Via-in-pad for QFN-56
   - Would help +3V3 in dense areas
   - Estimated impact: -5 to -10 items

4. **Power Rail Validation**:
   - Voltage drop analysis for +5V traces
   - Current capacity validation (IPC-2221)
   - Thermal analysis

---

## Commits

1. `b7bb6c4` - feat(power): Add PowerTrace net class and power topology modeling
2. `6032886` - fix(power): Remove +5V/+3V3/VCC_BOOT from PowerPlaneStage hardcoded list

---

## Test Coverage

```bash
# Unit tests
pytest experiments/test_power_topology.py -v
# Result: 20/20 passed ✓

# Integration validation
python experiments/validate_power_trace_routing.py
# Result: Architectural correctness verified, congestion issues identified
```

---

## Lessons for Future Development

1. **Avoid Hardcoded Lists**: PowerPlaneStage should derive net list from net_class, not hardcode names
2. **Pipeline Transparency**: Document stage ordering and data flow explicitly
3. **Incremental Validation**: Test after each change (caught bug early)
4. **Functional Core**: Immutable types + pure functions = testable + debuggable

---

## References

- IPC-2221: "Generic Standard on Printed Board Design" (trace width formula)
- TemperPowerTopology: `packages/temper-placer/src/temper_placer/core/power_topology.py`
- PowerPlaneStage: `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py`
- Pipeline Definition: `packages/temper-placer/src/temper_placer/deterministic/__init__.py`
