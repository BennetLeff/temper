# Next Experiments Plan - Router V5

**Date**: Jan 7, 2025
**Branch**: `feat/router-v5`
**Previous**: EXP-1, EXP-2, EXP-3 completed

---

## Analysis Summary

### Key Finding: Zone Expansion Breaks Working Routes

**Critical Discovery**: Iteration 2 made routing WORSE, not better!

| Net | Iter 1 Failures | Iter 2 Failures | Change |
|-----|-----------------|-----------------|--------|
| I_SENSE | 0 | 7 | BROKE (was fully routed!) |
| SPI_CLK | 0 | 2 | BROKE (was working!) |
| SPI_CS_TEMP | 0 | 1 | BROKE (was working!) |
| USB_D+/D- | 0 | 2 | BROKE (diff pair was perfect!) |
| +3V3 | 3 | 9 | 3x worse |
| +5V | 3 | 4 | worse |
| GATE_H/L | 4 | 6 | worse |

**Root Cause**: Zone expansion (+30mm for Signal/Power zones) blocks routing channels.

### Zone Expansion Parameters (Current)
```yaml
feedback:
  violation_threshold: 5
  expansion_per_violation: 0.5mm
```

**What Happened**:
- Signal zone had 329 violations → (329-5+1) × 0.5mm = **+162.5mm** requested
- Capped by max_size to **+30mm**
- Power zone: **+30mm**
- MCU zone: **+5mm**  
- HV zone: **+15mm**

**Total zone expansion**: +80mm on a 100mm board = zones expanded into each other!

---

## Proposed Experiments

### EXP-4: Conservative Zone Expansion (HIGH PRIORITY)

**Goal**: Reduce expansion to preserve routing channels

**Changes to `configs/temper_deterministic_config.yaml`**:
```yaml
feedback:
  max_iterations: 5
  violation_threshold: 20    # Was 5 - now need more violations before expanding
  expansion_per_violation: 0.1  # Was 0.5 - now 5x less expansion per violation
```

**Reasoning**:
- Current: 5 violations triggers expansion, 0.5mm each = aggressive
- Proposed: 20 violations triggers expansion, 0.1mm each = 25x more conservative
- Even with 329 violations: (329-20+1) × 0.1mm = 31mm, still capped to max_size

**Alternative**: Reduce `max_size` in zone definitions:
```yaml
zones:
  - name: "Signal"
    max_size: [30.0, 150.0]  # Was [50.0, 150.0] - max 10mm expansion
```

**Expected Impact**:
- Preserve working routes from iteration 1
- USB diff pair should stay routed
- I_SENSE, SPI_CLK, SPI_CS_TEMP should stay routed
- Lower total DRC reduction but fewer BROKEN routes

**Risk**: May not reduce clearance violations enough

---

### EXP-5: Route Locking (MEDIUM PRIORITY)

**Goal**: Lock successful routes before zone expansion

**Implementation**:
1. After iteration 1 routing, identify successful routes
2. Mark their tracks/vias as "locked" in board state
3. Zone expansion avoids locked routing areas
4. Subsequent iterations only route remaining nets

**Changes Required**:
1. Add `locked_routes: Set[str]` to BoardState
2. Modify ZoneAdjuster to check locked areas
3. Modify sequential_routing to skip locked nets

**File**: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`

```python
# After successful routing:
if all_segments_routed:
    state.locked_routes.add(net_name)
    logger.info(f"Locked route for {net_name}")
```

**File**: `packages/temper-placer/src/temper_placer/deterministic/feedback/zone_adjuster.py`

```python
def compute_adjustments(self, violations, locked_routes):
    # Skip violations in locked areas
    violations = [v for v in violations if not self._in_locked_area(v, locked_routes)]
```

**Expected Impact**:
- USB, I_SENSE, SPI nets stay routed
- Only failed nets get new routing attempts
- Zone expansion focuses on problem areas

**Risk**: Complexity increase, may need significant refactoring

---

### EXP-6: Priority-Based Net Ordering (MEDIUM PRIORITY)

**Goal**: Route critical nets first when board is least congested

**Current Order** (from log): AC_L, AC_N, DC_BUS+, DC_BUS-, SW_NODE, USB_D-, USB_D+, +15V, SPI_CS_TEMP, ...

**Proposed Order**:
1. **Differential pairs** (USB) - already first, good
2. **Critical signals** (SPI, GATE, PWM, I_SENSE) - should be next
3. **Power rails** (+3V3, +5V, +15V) - can use planes
4. **Low-priority** (AC, DC_BUS) - PTH components, simpler routing

**Implementation**:
Add `routing_priority` to config:
```yaml
net_priority:
  USB_D+: 1
  USB_D-: 1
  SPI_CLK: 2
  SPI_MOSI: 2
  SPI_MISO: 2
  SPI_CS_TEMP: 2
  GATE_H: 3
  GATE_L: 3
  PWM_H: 3
  PWM_L: 3
  I_SENSE: 3
  TEMP_SENSE: 3
  +3V3: 5
  +5V: 5
  +15V: 5
  # Default: 10
```

**Changes Required**:
1. Add `net_priority` section to config
2. Sort nets by priority in `sequential_routing.py`
3. Route higher priority (lower number) nets first

**Expected Impact**:
- Critical signals get routed before board fills up
- Power rails route last (can use any available space)
- Better overall routing success rate

**Risk**: May conflict with current "diff pairs first" logic

---

### EXP-7: Congestion-Aware Starting Points (LOW PRIORITY)

**Goal**: Start A* from less congested points

**Observation**: Many routes fail because starting point is in congested area near fine-pitch components (U_GATE, U_MCU).

**Implementation**:
1. Before routing, compute congestion map
2. For congested start points, find nearest uncongested cell
3. Route from uncongested cell to original start via short stub
4. Then route main path

**Changes Required**:
1. Add congestion map to BoardState
2. Modify A* to check congestion at start
3. Add "escape routing" phase for congested starts

**Expected Impact**:
- Routes can escape congested areas
- Fewer immediate failures
- Better routing around fine-pitch components

**Risk**: Complex implementation, may add routing overhead

---

## Recommended Experiment Order

### Phase 1: Quick Wins (EXP-4)
**Time**: ~30 minutes
**Impact**: High
**Risk**: Low

Just change config parameters:
```yaml
feedback:
  violation_threshold: 20
  expansion_per_violation: 0.1
```

Test immediately with existing code.

### Phase 2: Smart Ordering (EXP-6)
**Time**: ~2 hours
**Impact**: Medium-High
**Risk**: Low

Add priority system to config and routing stage.

### Phase 3: Route Locking (EXP-5)
**Time**: ~4 hours
**Impact**: High
**Risk**: Medium

Requires state management changes but high payoff.

### Phase 4: Congestion Escape (EXP-7)
**Time**: ~8 hours
**Impact**: Medium
**Risk**: High

Complex implementation, save for later if needed.

---

## Success Criteria

### Minimum Success (EXP-4)
- Iteration 2 doesn't break iteration 1 routes
- USB_D+/D- stays routed across iterations
- I_SENSE stays routed across iterations
- Total violations ≤ iteration 1 (667)

### Good Success (EXP-4 + EXP-6)
- All iteration 1 successes preserved
- More nets routed due to priority ordering
- Total violations < 400
- Unconnected pads < 30

### Excellent Success (EXP-4 + EXP-5 + EXP-6)
- All successful routes locked and preserved
- Progressive improvement across iterations
- Total violations < 200
- Unconnected pads < 15
- USB, SPI, I_SENSE all fully connected

---

## Files to Modify

### EXP-4 (Config Only)
- `configs/temper_deterministic_config.yaml`

### EXP-6 (Net Priority)
- `configs/temper_deterministic_config.yaml` (add net_priority section)
- `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` (sort by priority)

### EXP-5 (Route Locking)
- `packages/temper-placer/src/temper_placer/deterministic/state.py` (add locked_routes)
- `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` (lock routes)
- `packages/temper-placer/src/temper_placer/deterministic/feedback/orchestrator.py` (preserve locks)
- `packages/temper-placer/src/temper_placer/deterministic/feedback/zone_adjuster.py` (respect locks)

---

## Next Steps

1. **Implement EXP-4** (config change only - 5 minutes)
2. **Run full test** with new parameters
3. **Compare results** to baseline
4. **If successful**, move to EXP-6
5. **If not enough**, implement EXP-5

---

## Commands

```bash
# Test EXP-4
cd /Users/bennet.leff/Documents/temper
python3.11 scripts/run_feedback_loop.py --max-iterations 3 --output-dir output/exp4_test

# Compare to baseline
diff output/exp_combined/iteration_2_drc.json output/exp4_test/iteration_2_drc.json

# Check route preservation
grep "Multi-layer route found" output/exp4_test/*.log | grep -E "I_SENSE|SPI_|USB"
```
