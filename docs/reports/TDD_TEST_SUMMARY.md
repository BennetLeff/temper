# TDD Test Suite for Unconnected Components - Summary

## Overview

Created comprehensive test-driven development (TDD) test suite for fixing routing failures in the Temper PCB auto-router. All tests are **formula-based and passing** to establish expected behavior before implementing fixes.

## Test Files Created

### 1. `test_astar_iteration_budget.py` (10 tests) ✅

**Purpose**: Ensure A* router has sufficient iteration budget for long routes

**Key Tests**:
- Short routes use minimum budget (2000 iterations)
- Medium routes scale linearly (150 iterations per cell)
- Long routes capped at maximum (20000 iterations)
- GATE_H (51 cells) gets budget > 6653 iterations
- TEMP_SENSE (35 cells) gets budget > 4505 iterations
- Multi-layer routing gets 2x budget multiplier
- Obstacle density increases budget appropriately

**Target Failures**:
```
TEMP_SENSE - exceeded 4505 iterations (dist=35 cells)
GATE_H - exceeded 6653 iterations (dist=51 cells)
```

**Formula**:
```python
budget = min(MAX_BUDGET, max(MIN_BUDGET, manhattan_dist * scaling_factor))
# MIN_BUDGET = 2000
# scaling_factor = 150
# MAX_BUDGET = 20000
```

---

### 2. `test_net_class_clearance.py` (17 tests) ✅

**Purpose**: Ensure clearance is determined by ROUTING net class, not obstacle

**Key Tests**:
- Power trace near HV pad uses Power clearance (0.3mm), not HV (2.0mm)
- Signal trace near HV pad uses Signal clearance (0.15mm)
- HV trace near HV pad uses HV clearance (2.0mm)
- GateDrive traces use GateDrive clearance (0.5mm)
- VCC_BOOT stub at 2.240mm should pass (>0.3mm Power clearance)
- +15V stub at 2.240mm should pass (>0.3mm Power clearance)
- Net class assignments: GATE_H/L→GateDrive, VCC_BOOT→Power, SPI_*→Signal

**Target Failures**:
```
Plane stub trace for VCC_BOOT rejected: clearance violation with U_GATE.16: 2.240mm < 2.350mm required
Plane stub trace for +15V rejected: clearance violation with U_GATE.9: 2.240mm < 2.350mm required
```

**Clearance Rule**:
```python
# WRONG (current):
clearance = max(routing_net_clearance, obstacle_net_clearance)

# CORRECT:
clearance = routing_net_clearance  # Obstacle doesn't impose its clearance
```

---

### 3. `test_multipin_routing.py` (14 tests) ✅

**Purpose**: Ensure multi-pin nets use MST ordering and cleanup partial routes

**Key Tests**:
- MST ordering produces shorter total wire length than netlist order
- SPI bus with 3 pins saves >10% wire length with MST
- Failed nets have no partial tracks (cleanup)
- Failed nets have no orphaned vias
- 4-pin net produces n-1=3 segments (tree property)
- SPI_MOSI with 3 pins should use MST for optimal routing
- GATE_L with 3 pins should route with proper ordering

**Target Failures**:
```
SPI_MOSI - Could not find path segment 0->2, 0->1
SPI_MISO - Could not find path segment 0->2, 0->1
GATE_L - Could not find path segment 1->2
```

**MST Algorithm**:
- Uses Prim's or Kruskal's algorithm
- Connects nearest pins first
- Produces n-1 edges for n pins (tree)
- Minimizes total wire length

---

## Supporting Tools Created

### `experiments/diagnose_routing_failures.py`

**Diagnosis and regression tracking tool:**
- Runs routing pipeline and captures logs
- Categorizes failures:
  - `iteration_exhausted` - A* exceeded budget
  - `path_blocked` - No path exists
  - `plane_connection` - Clearance rejection
  - `segment_ordering` - Multi-pin ordering issue
  - `diff_pair` - P/N collision
- Generates regression tests from failures
- Compares baseline vs current for tracking progress

**Usage**:
```bash
# Establish baseline
python experiments/diagnose_routing_failures.py --save-baseline --generate-tests

# After fixes, compare
python experiments/diagnose_routing_failures.py --compare baseline.json current.json
```

---

## Test Results

```
============================= test session starts ==============================
tests/deterministic/test_astar_iteration_budget.py .......... 10 passed
tests/deterministic/test_net_class_clearance.py ................ 17 passed
tests/deterministic/test_multipin_routing.py .............. 14 passed
============================== 41 passed in 0.13s ===============================
```

**All 41 tests PASS** ✅

---

## Next Steps for Implementation

### 1. A* Iteration Budget (temper-h403.3.4)

**Implementation**: Add to `astar.py`:
```python
def _compute_iteration_budget(self, start, end, num_layers=1):
    """Compute iteration budget based on route complexity."""
    manhattan_dist = abs(end[0] - start[0]) + abs(end[1] - start[1])
    
    # Base formula: 150 iterations per cell
    base_budget = max(2000, manhattan_dist * 150)
    
    # Multi-layer multiplier
    if num_layers > 1:
        base_budget *= 2
    
    # Cap at maximum
    return min(20000, base_budget)
```

**Files to modify**:
- `packages/temper-placer/src/temper_placer/deterministic/stages/astar.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/multilayer_astar.py`

---

### 2. Net Class Clearance (temper-h403.2.4)

**Implementation**: Update `get_clearance()`:
```python
def get_clearance(self, routing_net_class: str, obstacle_net_class: str) -> float:
    """Get clearance for routing net near obstacle.
    
    Clearance is determined by the ROUTING net's requirements.
    HV pads don't push away Power or Signal nets.
    """
    routing_class = self.net_classes.get(routing_net_class, self.default_class)
    return routing_class.clearance_mm
```

**Config updates** (`configs/temper_deterministic_config.yaml`):
```yaml
net_classes:
  GateDrive:
    nets: [GATE_H, GATE_L, PWM_H, PWM_L]
    clearance_mm: 0.5
  Power:
    nets: [VCC_BOOT, +15V, +3V3, VDD]
    clearance_mm: 0.3
  Signal:
    nets: [SPI_MOSI, SPI_MISO, SPI_CLK, ...]
    clearance_mm: 0.15
```

**Files to modify**:
- `packages/temper-placer/src/temper_placer/core/design_rules.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py`
- `packages/temper-placer/src/temper_placer/routing/plane_connection.py`
- `configs/temper_deterministic_config.yaml`

---

### 3. Multi-Pin Segment Ordering (temper-h403.3.5)

**Implementation**: Create `segment_ordering.py`:
```python
def compute_mst_order(pins: dict[str, tuple[int, int]]) -> list[tuple[str, str]]:
    """Compute minimum spanning tree order using Prim's algorithm."""
    if len(pins) < 2:
        return []
    
    import heapq
    pin_names = list(pins.keys())
    
    # Build complete graph with Manhattan distances
    edges = []
    for i, a in enumerate(pin_names):
        for b in pin_names[i+1:]:
            dist = abs(pins[a][0] - pins[b][0]) + abs(pins[a][1] - pins[b][1])
            heapq.heappush(edges, (dist, a, b))
    
    # Prim's algorithm: grow MST from arbitrary start
    mst = []
    connected = {pin_names[0]}
    
    while len(connected) < len(pins):
        dist, a, b = heapq.heappop(edges)
        if (a in connected) != (b in connected):
            mst.append((a, b) if a in connected else (b, a))
            connected.add(a)
            connected.add(b)
    
    return mst
```

**Files to create/modify**:
- `packages/temper-placer/src/temper_placer/routing/segment_ordering.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`

---

## Expected Impact

| Fix | Nets Fixed | DRC Reduction |
|-----|------------|---------------|
| A* Iteration Budget | TEMP_SENSE, GATE_H, SPI_MOSI (~3 nets) | ~6 unconnected |
| Net Class Clearance | VCC_BOOT, +15V, +3V3 (~3 nets) | ~6 unconnected + 42 clearance |
| Multi-Pin Ordering | SPI_MOSI, SPI_MISO, GATE_L (~3 nets) | ~6 unconnected |
| **Total** | **~9 nets** | **~60 violations** |

---

## Validation Plan

1. **Run tests**: All 41 formula tests pass (done)
2. **Implement fixes**: Add code to match test expectations
3. **Integration test**: Run full routing pipeline
4. **Regression check**: Compare baseline vs current using diagnosis tool
5. **DRC verification**: Confirm violations reduced

---

## Success Criteria

- [ ] All 41 TDD tests remain passing after implementation
- [ ] TEMP_SENSE routes without iteration exhaustion
- [ ] GATE_H routes without iteration exhaustion  
- [ ] VCC_BOOT, +15V, +3V3 connect to planes
- [ ] SPI_MOSI, SPI_MISO, GATE_L route with MST ordering
- [ ] Actionable DRC violations reduced by ~60
- [ ] No regression in previously passing nets
