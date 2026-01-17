# ExactGeometryRouter Improvement Plan

## Current State

**Performance:** 8-9/14 nets (57-64% completion), 59 DRC violations  
**Failed Nets:** GATE_L, PWM_H, PWM_L, SPI_MOSI, I_SENSE, TEMP_SENSE  
**Time:** 15-30s timeout per net, ~90-120s total

## Priority Fixes

### 1. RRT Pathfinding Improvements (HIGH PRIORITY)

**Problem:** Timeouts and failures in congested areas

**Fixes:**
- [ ] **Add goal bias** to RRT: 10-20% chance to sample toward goal instead of random
- [ ] **Increase max iterations** from current (varies) to 10,000+ for critical nets
- [ ] **Add local replanning**: If RRT fails, try from intermediate waypoints
- [ ] **Implement A* fallback**: If RRT times out, use grid-based A* as backup
- [ ] **Add path caching**: Cache successful paths between similar start/end points

**Files to modify:**
- `packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router.py`
  - `_rrt_path()` method

**Estimated impact:** +20-30% completion rate

---

### 2. Escape Trace Validation (HIGH PRIORITY)

**Problem:** Too strict - blocks valid fanout from dense ICs

**Fixes:**
- [ ] **Only check same-net segments** for escape traces (pads fanout before other routes)
- [ ] **Relax clearance** for escape traces to 0.5× normal clearance
- [ ] **Allow escape traces to cross same-net traces** (will be merged later)
- [ ] **Increase via search radius** from current to 2-3× pad size
- [ ] **Try multiple escape angles** (0°, 45°, 90°, 135°, etc.) not just radial

**Files to modify:**
- `packages/temper-placer/src/temper_placer/router_v6/pad_layer_connector.py`
  - `_find_via_position_for_pad()` method
  - `is_escape_clear()` helper

**Estimated impact:** +15-25% completion rate

---

### 3. Routing Order Optimization (MEDIUM PRIORITY)

**Problem:** Current order doesn't account for congestion or criticality

**Fixes:**
- [ ] **Score nets** by multiple factors:
  - Pin count (more pins = route earlier to claim space)
  - Via requirement (via-needing nets = route earlier)
  - Criticality (power/clock = route earlier)
  - Congestion (nets crossing dense areas = route earlier)
- [ ] **Use topological order** from RouterV6Pipeline's SAT solution
- [ ] **Group differential pairs** and route together

**Files to modify:**
- `packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router.py`
  - Add `_compute_routing_order()` method
- `route_all_nets.py`
  - Use computed order instead of hard-coded list

**Estimated impact:** +10-15% completion rate

---

### 4. Obstacle Handling Refinement (MEDIUM PRIORITY)

**Problem:** Traces still violate clearance with pads/traces

**Fixes:**
- [ ] **Verify pad inflation** is correct for all pad shapes (rect, oval, circle)
- [ ] **Add per-layer obstacles**: Don't inflate pads on other layers
- [ ] **Tune safety margins**:
  - `pad_safety_margin`: 0.15mm → 0.12mm (less conservative)
  - `track_safety_margin`: 0.15mm → 0.10mm
- [ ] **Add obstacle validation**: Check that all base obstacles are in obstacle list
- [ ] **Debug obstacle visualization**: Export obstacle polygons to verify

**Files to modify:**
- `packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router.py`
  - `_get_obstacles_for_net()` method

**Estimated impact:** -10-20 DRC violations

---

### 5. Via Placement Relaxation (LOW PRIORITY)

**Problem:** Via placement too constrained, limits routing options

**Fixes:**
- [ ] **Increase via search attempts** from current to 50-100 positions
- [ ] **Allow via-in-pad** for dense components (already implemented for U_GATE)
- [ ] **Relax hole clearance** from 0.25mm to 0.20mm if needed
- [ ] **Use smaller vias** for signal nets: 0.6mm/0.3mm instead of 0.8mm/0.4mm
- [ ] **Add via stitching** hints from RouterV6 pipeline

**Files to modify:**
- `packages/temper-placer/src/temper_placer/router_v6/via_planner.py`
  - `find_legal_position()` method
- `packages/temper-placer/src/temper_placer/router_v6/pad_layer_connector.py`
  - `_find_via_position_for_pad()` method

**Estimated impact:** +5-10% completion rate, -5-10 DRC violations

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 hours)
1. Escape trace validation relaxation
2. Routing order optimization  
3. RRT goal bias

**Target:** 12-13/14 nets (85-93%), <30 DRC violations

### Phase 2: Core Improvements (2-4 hours)
4. RRT max iterations increase
5. Obstacle handling refinement
6. A* fallback implementation

**Target:** 13-14/14 nets (93-100%), <15 DRC violations

### Phase 3: Polish (2-3 hours)
7. Via placement relaxation
8. Path caching
9. Local replanning

**Target:** 14/14 nets (100%), <5 DRC violations

---

## Testing Strategy

### Unit Tests
```python
# Test each fix independently
def test_rrt_with_goal_bias():
    # Verify RRT finds paths faster with goal bias
    pass

def test_escape_trace_relaxation():
    # Verify escape traces can fanout from dense ICs
    pass

def test_routing_order_optimization():
    # Verify critical nets route first
    pass
```

### Integration Tests
```bash
# Run full routing pipeline
python route_all_nets.py

# Expected results after Phase 1:
# - 12-13/14 nets routed
# - <30 DRC violations
# - Time: 60-90s

# Expected results after Phase 2:
# - 13-14/14 nets routed
# - <15 DRC violations
# - Time: 45-75s

# Expected results after Phase 3:
# - 14/14 nets routed
# - <5 DRC violations
# - Time: 30-60s
```

### DRC Validation
```bash
# After each phase, run real KiCad DRC
kicad-cli pcb drc --format json --output /tmp/drc.json pcb/output.kicad_pcb

# Check:
# - Routing violations (shorts, clearance, crossing)
# - Via violations (hole clearance, hole-to-hole)
# - Unconnected items
```

---

## Alternative Approach: Hybrid Router

If ExactGeometryRouter still struggles after fixes, consider a **hybrid approach**:

1. **Use ExactGeometryRouter** for critical nets (power, differential pairs)
2. **Fall back to RouterV6Pipeline** for remaining nets
3. **Post-process** RouterV6 routes with DRC-aware cleanup

This would combine:
- ExactGeometryRouter's DRC awareness
- RouterV6Pipeline's completion guarantee

**Trade-off:** More violations but 100% completion

---

## Files to Modify Summary

1. `exact_geometry_router.py` - Core routing logic
2. `pad_layer_connector.py` - Escape trace validation
3. `via_planner.py` - Via placement
4. `route_all_nets.py` - Routing order
5. Test files (create new):
   - `tests/test_exact_router_improvements.py`

---

## Success Metrics

| Metric | Current | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|--------|---------|----------------|----------------|----------------|
| **Completion** | 57-64% | 85-93% | 93-100% | 100% |
| **Nets Routed** | 8-9/14 | 12-13/14 | 13-14/14 | 14/14 |
| **DRC Violations** | 59 | <30 | <15 | <5 |
| **Shorts** | 31 | <15 | <5 | 0 |
| **Clearance** | 20 | <10 | <5 | <3 |
| **Time (s)** | 90-120 | 60-90 | 45-75 | 30-60 |

---

## Next Steps

1. **Review this plan** - Discuss priorities and approach
2. **Implement Phase 1** - Quick wins for immediate improvement
3. **Test and validate** - Run DRC after each fix
4. **Iterate** - Continue to Phase 2 and 3 based on results
5. **Integrate with Benders** - Use improved router in optimization loop

---

**Status:** Planning complete, ready for implementation  
**Estimated Total Time:** 5-9 hours for all three phases  
**Priority:** Phase 1 (escape trace + routing order + RRT goal bias)
