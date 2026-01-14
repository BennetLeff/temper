# Differential Pair Clearance Fix

## Problem Statement

Router V6 has **335 clearance violations** (34% of total) between USB_D+ and USB_D-, with actual spacing of 0.082mm vs DRC requirement of 0.2mm.

**Root Cause:** `astar_pathfinding.py` uses `default_clearance_mm` (0.2mm) for ALL nets, ignoring:
1. Net-specific clearance from `get_rules_for_net()`
2. Differential pair spacing requirements (`spacing_mm` ~0.127mm)

## Current Architecture

### Differential Pair Infrastructure (EXISTS ✓)

```
core/differential_pair.py
├─ DifferentialPairConstraint
│  ├─ net_pos, net_neg
│  ├─ spacing_mm (default 0.2mm for intra-pair gap)
│  └─ impedance_ohm (target impedance)
│
router_v6/diff_pair_inference.py
├─ infer_differential_pairs()
│  └─ Detects USB_D+/D- patterns
│
design_rules.py
└─ get_diff_pair_for_net(net_name)
   └─ Returns DifferentialPairConstraint if net is in a pair
```

### The Bug (astar_pathfinding.py:657-673)

```python
# Line 669-675: Marks routed path as blocked
_mark_route_blocked(
    route_path,
    all_grids,
    trace_width=design_rules.default_trace_width_mm,  # ❌ WRONG: Uses 0.2mm for ALL nets
    clearance=design_rules.default_clearance_mm,       # ❌ WRONG: Uses 0.2mm for ALL nets
    net_id=net_id,
)
```

**Correct approach** (used elsewhere in codebase):
```python
# escape_via_generator.py:74
rules = design_rules.get_rules_for_net(pin.net)
via_diameter = rules.via_diameter_mm
via_drill = rules.via_drill_mm
clearance = rules.clearance_mm  # ✓ Net-specific

# constraint_model.py:253
rule = self.design_rules.get_rules_for_net(net.name)
net_width = rule.trace_width_mm + rule.clearance_mm  # ✓ Net-specific
```

## Fix Design

### Phase 1: Use Net-Specific Rules (P0)

**Modify:** `astar_pathfinding.py` lines 657-675

```python
def route_all_nets_phase3(
    nets: list[Net],
    pcb: ParsedPCB,
    all_grids: dict[str, OccupancyGrid],
    design_rules: DesignRules,  # Has get_rules_for_net()
    ...
) -> PathFindingResult:
    ...
    for net_name in nets_to_route:
        # Get net-specific routing rules
        net_rules = design_rules.get_rules_for_net(net_name)
        trace_width = net_rules.trace_width
        clearance = net_rules.clearance

        # Route net with A* pathfinding
        route_path = astar_route_net(...)

        # Mark path blocked using NET-SPECIFIC rules
        routed_paths[net_name] = route_path
        _mark_route_blocked(
            route_path,
            all_grids,
            trace_width=trace_width,      # ✓ Net-specific (was: default_trace_width_mm)
            clearance=clearance,           # ✓ Net-specific (was: default_clearance_mm)
            net_id=net_id,
        )
```

**Also fix:** Rip-up logic (lines 654-660) to use net-specific rules for unmarking:

```python
# Handle Ripped Nets
for ripped_id in ripped_ids:
    if ripped_id in id_to_net:
        ripped_name = id_to_net[ripped_id]
        if ripped_name in routed_paths:
            # Get net-specific rules for unmarking
            ripped_rules = design_rules.get_rules_for_net(ripped_name)

            _unmark_route_blocked(
                routed_paths[ripped_name],
                all_grids,
                trace_width=ripped_rules.trace_width,  # ✓ Net-specific
                clearance=ripped_rules.clearance,      # ✓ Net-specific
                net_id=ripped_id,
            )
```

**Expected Impact:** Each net now uses correct trace width and clearance from design rules.

---

### Phase 2: Differential Pair Aware Blocking (P0)

**Problem:** Even with net-specific clearance, differential pairs need **different spacing between pair nets** than to other nets:

```
USB_D+ ←→ USB_D-:        0.127mm (pair gap for impedance matching)
USB_D+ ←→ Other Nets:    0.2mm   (normal clearance)
```

**Current blocking radius calculation** (occupancy_grid.py:183):
```python
radius_mm = trace_width + clearance  # Uses same clearance for ALL nets
```

**Issue:** This blocks USB_D+ with a 0.2mm clearance radius, preventing USB_D- from getting within 0.127mm.

**Solution:** Pass both net IDs to blocking functions and use pair-aware clearance:

```python
def mark_path_blocked(
    self,
    path: list[tuple[float, float]],
    trace_width: float,
    clearance: float,
    net_id: int,
    diff_pair_spacing: float | None = None,  # NEW: Special spacing for pair mate
) -> None:
    """
    Mark path blocked with differential-pair-aware clearance.

    Args:
        diff_pair_spacing: If provided, allows pair mate to route closer (e.g., 0.127mm)
    """
    # Standard blocking radius (for non-pair nets)
    radius_mm = trace_width + clearance

    # Store additional metadata for pair-aware routing
    if diff_pair_spacing is not None:
        self.diff_pair_radii[net_id] = trace_width + diff_pair_spacing

    # ... rest of marking logic
```

**Alternative: Grid-level pair awareness**

Instead of changing blocking radius, check pair relationship during pathfinding:

```python
# In occupancy_grid.py or astar heuristic
def get_blocking_radius_between(self, net_a: int, net_b: int) -> float:
    """Get required clearance between two specific nets."""
    # Check if net_a and net_b are a differential pair
    if self.are_diff_pair(net_a, net_b):
        return self.trace_width + self.diff_pair_spacing  # 0.127mm
    else:
        return self.trace_width + self.clearance  # 0.2mm
```

**Recommended Approach:** Modify A* cost function to use pair-aware clearance:

```python
# In astar_pathfinding.py pathfinding loop
def get_collision_penalty(current_cell, net_id):
    """Get penalty for routing near obstacles."""
    blocking_net = grid[current_cell]

    if blocking_net == 0:
        return 0  # Free cell

    # Check if blocked by our differential pair mate
    if design_rules.are_diff_pair(net_id, blocking_net):
        # Allow closer routing to pair mate
        required_clearance = diff_pair_spacing  # 0.127mm
    else:
        # Normal clearance to other nets
        required_clearance = clearance  # 0.2mm

    distance_to_obstacle = ...
    if distance_to_obstacle < required_clearance:
        return HIGH_PENALTY
    return 0
```

---

## Implementation Plan

### Step 1: Net-Specific Rules (1-2 hours)

**Files to Modify:**
- `astar_pathfinding.py` (lines 654-675)

**Changes:**
1. Add `net_rules = design_rules.get_rules_for_net(net_name)` before routing
2. Pass `net_rules.trace_width` and `net_rules.clearance` to `_mark_route_blocked()`
3. Do same for rip-up logic in `_unmark_route_blocked()`

**Test:**
```bash
python run_router_v6.py
```

**Success Criteria:**
- Power nets use wider traces (2.5-3.0mm per HighVoltage class)
- Signal nets use 0.2mm traces
- No change in DRC violations yet (differential pairs still wrong)

### Step 2: Add Differential Pair Check (2-3 hours)

**Files to Modify:**
- `design_rules.py` - Add `are_diff_pair(net_a, net_b)` helper
- `occupancy_grid.py` - Store diff pair metadata
- `astar_pathfinding.py` - Use pair-aware clearance in collision detection

**New Helper Function:**

```python
# design_rules.py
def are_diff_pair(self, net_a: str, net_b: str) -> tuple[bool, float | None]:
    """
    Check if two nets are a differential pair.

    Returns:
        (is_pair, pair_spacing) - pair_spacing is the required gap between traces
    """
    for pair_constraint in self.differential_pairs:
        if {net_a, net_b} == {pair_constraint.net_pos, pair_constraint.net_neg}:
            return (True, pair_constraint.spacing_mm)
    return (False, None)
```

**Modify Grid Blocking:**

```python
# occupancy_grid.py
def check_clearance(self, x, y, current_net_id) -> float:
    """
    Get minimum clearance required at this cell.

    Returns:
        Required clearance in mm (may be reduced for differential pair mate)
    """
    blocking_net = self.grid[y, x]

    if blocking_net <= 0:
        return 0.0  # Free cell

    # Check if blocked by differential pair mate
    is_pair, pair_spacing = self.design_rules.are_diff_pair(
        self.net_id_to_name[current_net_id],
        self.net_id_to_name[blocking_net]
    )

    if is_pair:
        return pair_spacing  # 0.127mm for USB pairs
    else:
        return self.default_clearance  # 0.2mm standard
```

**Test:**
```bash
python run_router_v6.py
# Check DRC specifically for USB_D+/D-
grep "USB_D" pcb/temper_router_v6_drc.json
```

**Success Criteria:**
- USB_D+ and USB_D- violations drop from 335 → <10
- Other differential pairs (if any) also improve
- Total violations drop by ~34%

### Step 3: Validate and Tune (1 hour)

1. **DRC Report Analysis:**
   ```bash
   python scripts/check_drc_v6.py
   ```
   - Verify USB_D violations resolved
   - Check no new violations introduced

2. **Differential Pair Quality Check:**
   - Measure actual USB_D+/D- spacing in routed PCB
   - Should be ~0.127mm ± 0.05mm
   - Verify coupling length is maintained

3. **Tune Spacing if Needed:**
   - If DRC still fails, adjust `spacing_mm` in differential_pair.py
   - USB 2.0 typical: 0.127mm (5 mils)
   - May need to account for trace width: `spacing = pair_gap - trace_width/2`

---

## Expected Results

### Before Fix:
```
Total Violations: 992
├─ Clearance (USB_D+/D-): 335 (34%)
├─ Other clearance:       ~145
├─ Shorts (PTH):          ~140
├─ Hole clearance:         29
└─ Solder mask:           ~343
```

### After Phase 1 (Net-Specific Rules):
```
Total Violations: ~992 (no change)
- Power nets use correct widths
- Signal nets use correct widths
- BUT: Still using wrong clearance for diff pairs
```

### After Phase 2 (Diff Pair Aware):
```
Total Violations: ~657 (-34%)
├─ Clearance (USB_D+/D-): <10 (-335) ✓
├─ Other clearance:       ~145
├─ Shorts (PTH):          ~140
├─ Hole clearance:         29
└─ Solder mask (derivative): Reduced by ~100
```

---

## Alternative Approaches

### Option A: Pre-Route Differential Pairs

Route USB_D+ and USB_D- **simultaneously** as a pair, enforcing 0.127mm spacing:

**Pros:**
- Guarantees impedance matching
- Maintains coupling throughout route
- Proven approach in commercial EDA tools

**Cons:**
- Requires new "paired pathfinding" algorithm
- More complex than fixing blocking radius
- Higher implementation effort (4-6 hours)

### Option B: Post-Route Pair Optimization

Route normally, then **adjust pair spacing** in post-processing:

**Pros:**
- Doesn't complicate pathfinding
- Can optimize existing routes

**Cons:**
- May introduce new DRC violations while fixing pair spacing
- Doesn't guarantee routability of pairs
- Band-aid solution

**Recommendation:** Implement **Option in this document** (Phase 1 + 2), then consider Option A for Router V7.

---

## References

- **DRC Deep Analysis:** `DRC_DEEP_ANALYSIS.md` - Root cause #1
- **C-Space Theory:** `ROUTER_DRC_FIX_PLAN.md` - Mathematical foundation
- **Differential Pair Detection:** `router_v6/diff_pair_inference.py`
- **Design Rules:** `core/design_rules.py`

---

**Document Version:** 1.0
**Date:** 2026-01-14
**Status:** Ready for Implementation
