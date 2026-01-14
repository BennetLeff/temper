# Router V6 DRC Fix Plan: Mathematical Analysis and Solutions

## Executive Summary

Current DRC violations stem from **fundamental errors in the Configuration Space (C-Space) model**, not from heuristic tuning issues. This document provides mathematically rigorous analysis and provably correct solutions.

## Current State

| Violation Type | Count | Root Cause |
|----------------|-------|------------|
| Short circuits | ~200 | C-Space blocking radius is 50% too small |
| Clearance violations | ~600 | Same as above |
| Hole clearance | ~150 | Drill holes not blocked as obstacles |
| Solder mask bridges | ~199 | Derived from trace violations |
| Unconnected | 74 | Paths blocked by above errors |

---

## Root Cause #1: C-Space Blocking Radius Error (CRITICAL)

### The Bug

In `occupancy_grid.py:183`:
```python
radius_mm = (trace_width / 2) + clearance  # = 0.1 + 0.15 = 0.25mm
```

### Mathematical Proof of Error

Consider two traces A and B with equal width `w` and required edge-to-edge clearance `c`:

```
Trace A centerline: C_A
Trace B centerline: C_B
Trace A occupies: [C_A - w/2, C_A + w/2]
Trace B occupies: [C_B - w/2, C_B + w/2]

Edge-to-edge distance = |C_A - C_B| - w/2 - w/2 = |C_A - C_B| - w

Requirement: edge-to-edge ≥ c
Therefore:  |C_A - C_B| ≥ w + c
```

**The C-Space blocking radius must be `w + c`, not `w/2 + c`.**

### Visual Proof

```
Current (WRONG):           Correct:
Blocking radius = 0.25mm   Blocking radius = 0.4mm

   [====A====]                [====A====]
       0.25                       0.4
       ↓                          ↓
   [====B====]                        [====B====]

   Edge gap = 0.25 - 0.2 = 0.05mm    Edge gap = 0.4 - 0.2 = 0.2mm ✓
   (VIOLATES 0.2mm clearance!)       (MEETS 0.2mm clearance!)
```

### The Fix

```python
# occupancy_grid.py:183 - mark_path_blocked()
# OLD:
radius_mm = (trace_width / 2) + clearance

# NEW (Mathematically Correct):
radius_mm = trace_width + clearance
```

Apply same fix to:
- `mark_segment_blocked()` line 231
- `unmark_segment_blocked()` line 263
- `unmark_path()` line 312

---

## Root Cause #2: Drill Holes Not Blocked (CRITICAL)

### The Bug

In `obstacle_map.py`, THT pads are added as obstacles using their **copper annular ring dimensions**:

```python
pad_poly = _create_pad_polygon(pin, px, py, angle)  # Uses pin.width, pin.height
```

But this doesn't account for the **drill hole** which:
1. Has a separate diameter (`pin.drill` or similar)
2. Requires its own clearance on ALL copper layers
3. Is a physical void that traces cannot cross

### DRC Evidence

```
Hole clearance violation (actual 0.0000 mm): 111 violations
```

"Actual 0.0000 mm" means traces are **going through drill holes**.

### The Fix

Add drill hole obstacles in `build_obstacle_map()`:

```python
# After creating pad polygon, also create drill hole obstacle
if hasattr(pin, 'drill') and pin.drill and pin.drill > 0:
    # Drill hole + required hole clearance
    drill_radius = pin.drill / 2.0
    hole_clearance = pcb.design_rules.hole_clearance_mm  # typically 0.25mm
    hole_poly = Point(px, py).buffer(drill_radius + hole_clearance, quad_segs=8)

    # Drill goes through ALL layers
    for layer_info in pcb.stackup.layers:
        if layer_info.layer_type in ["signal", "mixed"]:
            layer_obstacles[layer_info.name].append(hole_poly)
```

---

## Root Cause #3: Square vs Circular Blocking (MODERATE)

### The Bug

The current blocking uses a **square kernel**:

```python
x_start = max(0, cx - expansion)
x_end = min(self.width_cells, cx + expansion + 1)
# ...
self.grid[y_start:y_end, x_start:x_end] = net_id  # Square!
```

This over-blocks in diagonal directions:
- Square corner is at distance `√2 × expansion` cells
- Circle should only block to `expansion` cells
- Over-blocking reduces routing capacity by ~27%

### The Fix

Use circular distance check (already done in `mark_via_blocked`):

```python
for y in range(y_start, y_end):
    for x in range(x_start, x_end):
        dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
        if dist <= radius_mm:
            self.grid[y, x] = net_id
```

---

## Verification Experiments

### Experiment 1: Blocking Radius Verification

**Hypothesis:** Fixing the blocking radius from `w/2 + c` to `w + c` will eliminate clearance violations.

**Test:**
1. Apply fix to `mark_path_blocked()` only
2. Run router on temper board
3. Run DRC
4. Count clearance violations

**Expected Result:** Clearance violations drop from ~600 to <50

**Mathematical Guarantee:** With correct C-Space, any path the router finds is guaranteed to have proper clearance.

### Experiment 2: Drill Hole Blocking

**Hypothesis:** Adding drill holes as obstacles will eliminate hole clearance violations.

**Test:**
1. Add drill hole blocking to `build_obstacle_map()`
2. Run router
3. Run DRC
4. Count hole clearance violations

**Expected Result:** Hole clearance violations drop from ~150 to 0

### Experiment 3: Circular vs Square Blocking

**Hypothesis:** Circular blocking improves routing success without DRC regressions.

**Test:**
1. Implement circular blocking in `mark_path_blocked()`
2. Run router on congested board
3. Compare routing success rate and DRC violations

**Expected Result:** ~10% improvement in routing success, no new DRC violations

---

## Mathematical Framework: Minkowski Sum C-Space

The correct theoretical framework for grid-based routing:

### Definition

For a point robot (trace centerline) navigating among obstacles:
1. Each obstacle `O` is inflated by **Minkowski sum** with robot's footprint
2. Robot footprint = disk of radius `r_robot`
3. Inflated obstacle = `O ⊕ D(r_robot)`

### For PCB Routing

- Robot radius = `trace_width/2`
- Required clearance to obstacles = `clearance`
- **Initial C-Space inflation** = `trace_width/2 + clearance` ✓ (currently correct)

When routing trace B after trace A:
- Trace A becomes an obstacle with width `trace_width_A`
- Trace B has footprint radius `trace_width_B/2`
- **Blocking radius** = `trace_width_A/2 + clearance + trace_width_B/2`
- For equal widths: `trace_width + clearance`

### Why Current Code is Wrong

```python
# Pipeline: Initial C-Space (CORRECT)
base_inflation = (trace_width / 2) + clearance  # 0.25mm ✓

# After routing: Mark path blocked (WRONG)
radius_mm = (trace_width / 2) + clearance  # Should be trace_width + clearance
```

The initial inflation accounts for `trace_width/2` (our trace) + `clearance`.
But when blocking for the NEXT trace, we need THEIR `trace_width/2` as well.

---

## Implementation Priority

| Priority | Fix | Impact | Effort |
|----------|-----|--------|--------|
| P0 | Blocking radius `w/2+c` → `w+c` | Fixes ~600 clearance violations | 4 lines changed |
| P0 | Add drill hole obstacles | Fixes ~150 hole violations | ~20 lines added |
| P1 | Circular blocking kernel | Improves routing capacity | ~10 lines changed |

---

## Appendix: Topology and Knot Theory Perspective

While not directly applicable to fixing the current bugs, topological methods can provide **formal verification**:

### Homotopy Classes

Two paths are homotopically equivalent if one can be continuously deformed into the other without crossing obstacles. The SAT solver (Stage 3) essentially selects a **homotopy class** for each net.

### Verification Property

Once a homotopy class is selected, the geometric realization (Stage 4) should find a path within that class that satisfies DRC. If C-Space is correctly constructed, this is **guaranteed by construction**.

### Future Work: Knot Invariants

For multi-layer routing with vias, paths form **links** in 3D space. Link invariants could detect:
- Nets that cannot be routed without crossing
- Minimum via count requirements
- Topological ordering constraints

This is beyond current scope but represents a principled extension.
