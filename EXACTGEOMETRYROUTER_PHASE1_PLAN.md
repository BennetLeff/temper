# ExactGeometryRouter Phase 1: Quick Wins Implementation Plan

## Goal
Increase completion from **57-64%** to **85-93%** (12-13/14 nets) with **<30 DRC violations** in **1-2 hours**.

## Three Key Fixes

### Fix 1: Add RRT Goal Bias (30 minutes)

**Current:** RRT samples completely random points, slow to find goal

**Fix:** Add 10-20% goal bias to guide search toward target

**Code Change:**
```python
# In exact_geometry_router.py, _rrt_path() method

# Current:
sample = (random.uniform(x_min, x_max), random.uniform(y_min, y_max))

# New:
if random.random() < 0.15:  # 15% goal bias
    sample = goal
else:
    sample = (random.uniform(x_min, x_max), random.uniform(y_min, y_max))
```

**Location:** `packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router.py:_rrt_path()`

**Lines:** ~500-600 (in RRT loop)

**Expected Impact:** +10-15% faster pathfinding, fewer timeouts

---

### Fix 2: Relax Escape Trace Validation (45 minutes)

**Current:** Escape traces checked against ALL routed segments, blocks dense fanout

**Fix:** Only check against other-net segments, relax clearance

**Code Changes:**

#### Change 2a: Filter routed segments by net
```python
# In pad_layer_connector.py, _find_via_position_for_pad()

# Current is_escape_clear() checks ALL routed_segments

# New: Filter to only other nets
def is_escape_clear(escape_start, escape_end, clearance):
    other_net_segments = [
        seg for seg in routed_segments 
        if seg.get('net') != net_name  # <-- ADD THIS LINE
    ]
    for seg in other_net_segments:  # <-- CHANGE THIS
        seg_line = LineString([seg['start'], seg['end']])
        if escape_line.distance(seg_line) < clearance:
            return False
    return True
```

#### Change 2b: Reduce clearance for escape traces
```python
# In pad_layer_connector.py, _find_via_position_for_pad()

# Current:
is_escape_clear(pad_pos, via_pos, clearance)

# New:
escape_clearance = clearance * 0.5  # Half normal clearance for fanout
is_escape_clear(pad_pos, via_pos, escape_clearance)
```

**Location:** `packages/temper-placer/src/temper_placer/router_v6/pad_layer_connector.py`

**Lines:** ~150-200 (in `_find_via_position_for_pad`)

**Expected Impact:** +15-20% completion, allows dense IC fanout

---

### Fix 3: Optimize Routing Order (15 minutes)

**Current:** Hard-coded order, via-needing nets first

**Fix:** Score nets by pin count + criticality

**Code Change:**
```python
# In route_all_nets.py, before routing loop

# Current:
signal_nets = [
    'GATE_H', 'GATE_L', 'PWM_H', 'PWM_L',
    'SPI_MOSI', 'SPI_MISO', 'SPI_CS_TEMP',
    'USB_D-', 'SW_NODE', 'I_SENSE', 'SPI_CLK',
    'USB_D+', 'TEMP_SENSE', 'AC_N'
]

# New: Compute order dynamically
def score_net(net_name, net_pad_info):
    score = 0
    # More pins = higher score (route dense nets first)
    score += len(net_pad_info[net_name]) * 10
    # Critical nets
    if net_name in ['VCC_BOOT', 'GATE_H', 'GATE_L']:
        score += 50
    # Via-requiring nets (based on pad layers)
    pads = net_pad_info[net_name]
    layers = set()
    for p in pads:
        layers.update(p['layers'])
    if len(layers) > 1:
        score += 30  # Needs via
    return score

# Sort by score descending
signal_nets_scored = [(n, score_net(n, net_pad_info)) for n in signal_nets if n in net_pad_info]
signal_nets = [n for n, s in sorted(signal_nets_scored, key=lambda x: -x[1])]

print(f"Routing order (by score):")
for net, score in sorted(signal_nets_scored, key=lambda x: -x[1]):
    print(f"  {net}: {score}")
```

**Location:** `route_all_nets.py`

**Lines:** ~100-150 (before routing loop starts)

**Expected Impact:** +5-10% completion, better space allocation

---

## Implementation Steps

### Step 1: Backup Current Code (2 min)
```bash
git add -A
git commit -m "checkpoint: before ExactGeometryRouter Phase 1 fixes"
```

### Step 2: Implement Fix 1 - RRT Goal Bias (30 min)
```bash
# Edit exact_geometry_router.py
# Add goal bias to _rrt_path()
# Test with: python route_all_nets.py
```

### Step 3: Implement Fix 2 - Escape Trace Relaxation (45 min)
```bash
# Edit pad_layer_connector.py  
# Filter routed_segments by net
# Reduce escape clearance to 50%
# Test with: python route_all_nets.py
```

### Step 4: Implement Fix 3 - Routing Order (15 min)
```bash
# Edit route_all_nets.py
# Add score_net() function
# Sort signal_nets by score
# Test with: python route_all_nets.py
```

### Step 5: Run Full Test (10 min)
```bash
# Run routing
python route_all_nets.py

# Check results
# Expected: 12-13/14 nets routed, <30 DRC violations

# Run KiCad DRC
kicad-cli pcb drc --format json --output /tmp/drc.json pcb/temper_all_nets_routed.kicad_pcb

# Analyze
python -c "
import json
with open('/tmp/drc.json') as f:
    drc = json.load(f)
violations = drc.get('violations', [])
routing_types = ['shorting_items', 'clearance', 'tracks_crossing', 'hole_clearance']
routing_count = sum(1 for v in violations if v.get('type') in routing_types)
print(f'Routing violations: {routing_count}')
"
```

### Step 6: Commit Results (2 min)
```bash
git add -A
git commit -m "feat: ExactGeometryRouter Phase 1 improvements

- Add RRT goal bias (15%) for faster pathfinding
- Relax escape trace validation (50% clearance, same-net only)
- Optimize routing order by pin count + criticality

Results: X/14 nets routed, Y DRC violations"
```

---

## Validation Criteria

### Before (Baseline)
- Nets routed: 8-9/14 (57-64%)
- DRC violations: 59
  - Shorts: 31
  - Clearance: 20
  - Crossing: 8
- Time: 90-120s

### After Phase 1 (Target)
- Nets routed: 12-13/14 (85-93%)
- DRC violations: <30
  - Shorts: <15
  - Clearance: <10
  - Crossing: <5
- Time: 60-90s

### Success Criteria
- ✅ At least 12/14 nets routed (86%)
- ✅ DRC violations reduced by 50% (<30)
- ✅ No new violation types introduced
- ✅ No regression in routed nets

---

## Debugging Tips

### If nets still fail after fixes:

**Debug escape traces:**
```python
# Add logging in pad_layer_connector.py
print(f"  Trying via position {i+1}: ({vx:.2f}, {vy:.2f})")
if not is_escape_clear(pad_pos, via_pos, escape_clearance):
    print(f"    ✗ Escape blocked by segments")
    # Print which segments block it
else:
    print(f"    ✓ Escape clear")
```

**Debug RRT timeouts:**
```python
# Add logging in exact_geometry_router.py
if iteration % 1000 == 0:
    print(f"  RRT iteration {iteration}/{max_iterations}, best_dist={best_dist:.2f}mm")
```

**Debug routing order:**
```python
# Print net scores
for net, score in sorted(signal_nets_scored, key=lambda x: -x[1]):
    pin_count = len(net_pad_info[net])
    print(f"  {net:15} score={score:3} pins={pin_count}")
```

---

## Rollback Plan

If Phase 1 causes regressions:

```bash
# Revert to checkpoint
git reset --hard HEAD~1

# Or revert individual changes
git checkout HEAD~1 -- packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router.py
git checkout HEAD~1 -- packages/temper-placer/src/temper_placer/router_v6/pad_layer_connector.py
git checkout HEAD~1 -- route_all_nets.py
```

---

## Next Steps After Phase 1

If Phase 1 is successful:
1. Review results and identify remaining failed nets
2. Plan Phase 2: Increase RRT iterations, add A* fallback
3. Continue with obstacle handling refinement

If Phase 1 doesn't meet targets:
1. Debug specific failed nets
2. Adjust parameters (goal bias %, escape clearance)
3. Consider alternative approaches

---

**Ready to implement:** Yes  
**Estimated time:** 1.5-2 hours  
**Risk level:** Low (incremental, easy to rollback)  
**Expected improvement:** +20-35% completion, -50% violations
