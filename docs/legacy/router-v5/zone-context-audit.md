# Zone Context Audit - Router V5

**Date:** 2026-01-03  
**Epic:** temper-d6kv (Router Zero-DRC: Zone Integration Fix)  
**Auditor:** AI Agent

---

## Executive Summary

**Finding:** The zone-aware clearance infrastructure EXISTS but is NOT INTEGRATED into the A* pathfinder.

- ✅ `ClearanceMatrix.get_clearance(net_a, net_b, x, y)` supports spatial zone overrides
- ✅ `ZoneManager` provides O(log n) spatial lookups for zone-at-point queries  
- ❌ A* pathfinder receives only **global** `clearance_mm` value, no coordinate-aware lookup
- ❌ `block_zones()` hard-blocks zones entirely (appropriate for power planes, NOT for clearance overrides)

**Impact:** HV clearance requirements are either:
1. Applied globally (causes unnecessary constraint), OR
2. Not enforced in HV zones (causes DRC violations)

---

## Data Flow Diagram

```
KiCad PCB File (zones defined)
    ↓
kicad_parser.py → Board.zones (✓ Parsed correctly)
    ↓
ClearanceMatrix.parse() → ZoneManager created (✓ Zone data captured)
    ↓
MazeRouter.from_board() → receives ClearanceMatrix (✓ Matrix available)
    ↓
route_net_rrr(clearance_mm=X) → Uses GLOBAL clearance value (✗ DISCONNECT)
    ↓
A* Pathfinder → Uses fixed `clearance_mm` for entire net (✗ No spatial awareness)
```

**The Break Point:** Between `ClearanceMatrix` (which HAS zone awareness) and `route_net_rrr()` / A* pathfinder (which do NOT use it).

---

## Detailed Audit

### 1. Zone Definition Layer

**Where are zones defined?**
- File: KiCad `.kicad_pcb` files, `(zone ...)` S-expressions
- Example:
  ```lisp
  (zone (net 2) (net_name "+15V") (layers "In2.Cu")
    (polygon (pts (xy 10.0 10.0) (xy 50.0 10.0) ...))
    (filled_polygon ...))
  ```

**How are they parsed?**
- File: `packages/temper-placer/src/temper_placer/io/kicad_parser.py`
- Method: `parse_kicad_pcb()` extracts zones into `Board.zones` list
- Structure: `Zone` dataclass with `polygon`, `net`, `layers` attributes

**What data structure?**
- File: `packages/temper-placer/src/temper_placer/core/board.py:215`
- Class: `Zone`
- Fields: `net: str`, `polygon: list[tuple[float, float]]`, `layers: list[str]`, `priority: int`

**Status:** ✅ Zones are correctly parsed and available

---

### 2. Grid Initialization

**How is the routing grid created?**
- File: `packages/temper-placer/src/temper_placer/routing/maze_router.py`
- Method: `MazeRouter.__init__()`
- Creates: `self.occupancy: np.ndarray` (3D grid: x, y, layer)

**Does grid initialization receive zone data?**
- Method: `MazeRouter.block_zones(zones, clearance=0.0)` - Line 1081
- Purpose: Hard-blocks cells within zone polygons + clearance margin
- Uses: OpenCV `fillPoly` + `dilate` for rasterization
- **Critical:** This BLOCKS zones, not "marks for special clearance"

**Is zone ID encoded per grid cell?**
- ❌ NO. The grid only stores:
  - `-1` = blocked (hard obstacle)
  - `0` = free
  - `2` = soft occupied (by trace, can rip-up)
- There is NO per-cell zone ID field

**Status:** ❌ Grid does not encode zone context, only binary blocked/free

---

### 3. Clearance Lookup

**Where is clearance determined?**
- File: `packages/temper-placer/src/temper_placer/routing/constraints/design_rules.py:152`
- Method: `ClearanceMatrix.get_clearance(net_a, net_b, x=None, y=None)`
- Logic:
  ```python
  base_clearance = self._get_base_clearance(net_a, net_b)
  if x is not None and y is not None and self.zone_manager:
      zone = self.zone_manager.get_zone_at(x, y)
      if zone and zone_applies_to_nets(net_a, net_b):
          return max(base_clearance, zone.clearance_mm)
  return base_clearance
  ```

**Is it per-cell or global?**
- **Designed to be:** Per-cell (takes `x, y` coordinates)
- **Actually used as:** Global (A* doesn't pass coordinates)

**Status:** ✅ Clearance lookup CAN be zone-aware, ❌ but is NOT CALLED with coordinates

---

### 4. A* Pathfinder

**Method signature:**
- File: `packages/temper-placer/src/temper_placer/routing/maze_router.py:2059`
- Method: `route_net_rrr(..., clearance_mm: float | None = None)`
- The `clearance_mm` is a SCALAR, not a function or grid

**What parameters does A* receive?**
- (Inferred from `route_net_rrr` signature):
  - `occupancy` grid (3D numpy array)
  - `clearance_mm` (single float value for entire net)
  - `trace_width_mm` (single float value for entire net)

**How does A* check if a cell is blocked?**
- Check: `self.occupancy[nx, ny, layer] != -1`
- No zone-specific clearance lookup

**Where is clearance used?**
- When marking path as occupied: inflate blocked radius by `trace_width/2 + clearance`
- This inflation is uniform across the entire path

**Status:** ❌ A* has no mechanism to query zone-specific clearance

---

### 5. NetClassRules Integration

**How do NetClassRules interact with zones?**
- File: `packages/temper-placer/src/temper_placer/routing/constraints/design_rules.py`
- `NetClassRules` defines: `trace_width`, `clearance`, `via_size` per net class
- `ClearanceMatrix` maps nets → net classes → rules
- Zone override logic exists in `ClearanceMatrix.get_clearance()` but is unused

**Is there zone-specific override capability?**
- ✅ YES in `ClearanceMatrix.get_clearance()`: zone clearance overrides base clearance if stricter
- ❌ NO in routing pipeline: override never executed because A* doesn't query it

**Status:** ✅ Infrastructure exists, ❌ not connected to pathfinding

---

## The Break Point

**Exact location:** `maze_router.py:2068`

```python
def route_net_rrr(
    self,
    net_name: str,
    ...
    clearance_mm: float | None = None,  # ← SCALAR value, not coordinate-aware
) -> RoutePath:
```

**Why it's broken:**
1. Caller computes `clearance_mm = clearance_matrix.get_clearance(net_a, net_b)` WITHOUT `x, y`
2. This gives a GLOBAL clearance value (base class clearance)
3. `route_net_rrr()` uses this global value for the entire path
4. A* pathfinder has no way to query zone-specific clearance at each cell expansion

**Alternative break point:** If `route_net_rrr` is being called correctly with zone-aware clearance, the issue is in how the pathfinder uses it:
- Need to check: Does the pathfinder receive a **clearance function** or a **clearance grid**?
- Current: Receives scalar → Need: Receive per-cell clearance lookup

---

## Required Changes

### Change 1: Add Zone ID Grid (Low-Impact Option)

**File:** `maze_router.py`
**Method:** `__init__()`

Add:
```python
self.zone_ids: np.ndarray = np.zeros(
    (self.grid_size[0], self.grid_size[1], self.num_layers),
    dtype=np.int16
)  # 0 = no zone, 1+ = zone index
```

**Method:** New method `_encode_zone_ids()`
```python
def _encode_zone_ids(self, zones: list, zone_manager: ZoneManager):
    """Rasterize zone IDs onto grid."""
    for zone_idx, zone in enumerate(zones):
        # Similar to block_zones(), but set zone_ids instead of occupancy
        ...
```

**Estimated effort:** ~100 lines

---

### Change 2: Add Clearance Grid (Medium-Impact Option)

**File:** `maze_router.py`
**Method:** `__init__()`

Add:
```python
self.clearance_grid: np.ndarray = np.full(
    (self.grid_size[0], self.grid_size[1], self.num_layers),
    fill_value=self.default_clearance,
    dtype=np.float32
)
```

**Method:** New method `_precompute_clearance_grid(net_name: str)`
```python
def _precompute_clearance_grid(self, net_name: str, other_nets: list[str]):
    """Precompute per-cell clearance for routing this net."""
    for x in range(self.grid_size[0]):
        for y in range(self.grid_size[1]):
            world_x = self.origin[0] + x * self.cell_size
            world_y = self.origin[1] + y * self.cell_size
            
            max_clearance = 0.0
            for other_net in other_nets:
                if self.occupancy[x, y, :].any() != 0:  # Cell has trace
                    clearance = self.clearance_matrix.get_clearance(
                        net_name, other_net, world_x, world_y
                    )
                    max_clearance = max(max_clearance, clearance)
            
            self.clearance_grid[x, y, :] = max_clearance
```

**Estimated effort:** ~150 lines + O(N²) computation per net

---

### Change 3: Pass Clearance Function to Num ba (High-Impact Option)

**Problem:** Numba doesn't support Python objects (like `ClearanceMatrix`)

**Solution:** JIT-compile a clearance lookup function that accesses pre-populated data

**File:** `maze_router.py`

```python
@numba.jit(nopython=True)
def _get_clearance_at_cell(x, y, layer, net_a_idx, net_b_idx, zone_ids, zone_clearances, base_clearances):
    """Numba-compatible clearance lookup."""
    zone_id = zone_ids[x, y, layer]
    if zone_id > 0:
        return max(base_clearances[net_a_idx, net_b_idx], zone_clearances[zone_id])
    return base_clearances[net_a_idx, net_b_idx]
```

Then pass this function + data to A* pathfinder.

**Estimated effort:** ~200 lines + refactor A* signature

---

## Recommended Approach

**Start with Change 2 (Clearance Grid)** because:
1. **Compatibility:** Doesn't require Numba refactor
2. **Performance:** O(N²) precomputation per net is acceptable (grid size ~500x750)
3. **Incremental:** Can optimize later if needed

**Steps:**
1. Add `clearance_grid` to `MazeRouter.__init__()`
2. Implement `_precompute_clearance_grid()` method
3. Modify `route_net_rrr()` to call precompute before pathfinding
4. Update A* to read from `clearance_grid` instead of scalar `clearance_mm`
5. Test with MVB Level 3 (zone test case)

---

## Estimated Effort

### Complexity Breakdown
- **Lines of code to change:** ~200-300
- **Files affected:**
  - `maze_router.py` (primary change)
  - Possibly pathfinding helper functions (if sep arate)
- **Risk areas:**
  - Performance: O(N²) clearance precomputation could be slow
  - Memory: Clearance grid adds ~4MB per layer (acceptable)
  - Numba compatibility: If pathfinding is Numba-JIT, may need special handling

### Timeline
- Design & prototype: 4 hours
- Implementation: 8 hours
- Testing & validation: 4 hours
- **Total:** ~2 days

---

## Success Criteria

- [ ] Clearance grid populated with zone-aware values
- [ ] A* pathfinder uses per-cell clearance instead of global
- [ ] MVB Level 3 routes with 0 DRC violations
- [ ] Full board: Zone bleeding violations reduced by >60%
- [ ] Performance: Routing time increase <2x baseline
- [ ] No regression on non-zone boards

---

## Next Steps

1. Review this audit with team/user
2. Get approval on recommended approach (Clearance Grid)
3. Create detailed implementation plan
4. Execute implementation (temper-d6kv.2, temper-d6kv.3)
5. Validate with MVB + full board (temper-d6kv.4)
