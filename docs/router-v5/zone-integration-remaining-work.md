# Zone Integration - Remaining Implementation Work

**Date:** 2026-01-03  
**Epic:** temper-d6kv (Router Zero-DRC: Zone Integration Fix)  
**Status:** Partial implementation complete, integration pending

---

## Completed Work

### temper-d6kv.1 - Audit (✅ Done)
- Documented zone data flow through routing pipeline
- Identified break point: `route_net_rrr(clearance_mm: float)` receives scalar, not zone-aware function
- Recommended approach: Add clearance_grid precomputation
- Document: `docs/router-v5/zone-context-audit.md`

### temper-d6kv.2 - Grid Infrastructure (✅ Done)
**File:** `maze_router.py`

**Added:**
1. `self.clearance_grid` field (lines ~258):
   ```python
   self.clearance_grid = np.full(
       (grid_size[0], grid_size[1], num_layers),
       fill_value=min_clearance,
       dtype=np.float32
   )
   ```

2. `_precompute_clearance_grid(net_name, clearance_matrix)` method (lines ~1091):
   - Queries `ClearanceMatrix.get_clearance(net_a, net_b, x, y)` with world coordinates
   - Populates clearance_grid with zone-aware values
   - O(grid_cells) complexity, runs once per net

---

## Remaining Work

### temper-d6kv.3 - Integration (⏳ In Progress)

**Key Finding:** Routing is done via `route_net_mst()` and `route_net_topology()`, not `route_net_rrr()` directly.

**Integration Points:**

1. **Add ClearanceMatrix parameter to MazeRouter**
   - Current: `MazeRouter.__init__()` doesn't receive ClearanceMatrix
   - Need: Pass clearance_matrix from `from_board()` factory method
   - File: `maze_router.py:352` (`from_board` method)

2. **Call _precompute_clearance_grid before routing each net**
   - Location: `rrr_route_all_nets()` around line 3050-3067
   - Before calling `route_net_mst()` or `route_net_topology()`
   - Add:
     ```python
     # Precompute zone-aware clearance for this net
     if hasattr(self, 'clearance_matrix') and self.clearance_matrix:
         self._precompute_clearance_grid(net_name, self.clearance_matrix)
     ```

3. **Update pathfinding to use clearance_grid**
   - Current: Uses scalar `clearance_mm` passed to routing methods
   - Need: Read `self.clearance_grid[x, y, layer]` during cell expansion
   - Possible locations:
     - `_compute_cell_cost()` method (lines ~600)
     - `_get_inflated_cells()` method (checks clearance)
     - Or wherever clearance is used in A* neighbor validation

4. **Update _get_inflated_cells or similar blocking methods**
   - Current: Uses global `clearance` parameter
   - Need: Use `clearance_grid[x, y, layer]` value
   - This affects how occupied cells block neighboring cells

**Estimated Remaining Effort:** ~4-6 hours
- Add clearance_matrix parameter: 1 hour
- Integrate precompute call: 1 hour  
- Update pathfinding to use grid: 2-3 hours
- Testing & debugging: 1-2 hours

---

### temper-d6kv.4 - Validation (⏳ Not Started)

**Test with:**
1. MVB Level 3 (zone test case)
   - Board: `test-boards/mvb/mvb_level_3.kicad_pcb`
   - Expected: Routes with 0 DRC violations
   - Validates: Zone-aware routing works

2. Full board routing
   - Board: `pcb/temper_routed_v2.kicad_pcb`
   - Current: 339 baseline violations
   - Target: Zone bleeding violations eliminated (expect ~200-250 violations remaining)

**Acceptance Criteria:**
- [ ] MVB Level 3: 0 violations
- [ ] Full board: Zone bleeding gone (>60% reduction in zone-related violations)
- [ ] Performance: routing time increase <2x baseline
- [ ] No regression on non-zone boards

---

## Priority Next Steps

For next session:

1. **Add ClearanceMatrix to MazeRouter:**
   ```python
   # In MazeRouter.__init__()
   self.clearance_matrix: ClearanceMatrix | None = clearance_matrix
   
   # In from_board() factory
   clearance_matrix = ClearanceMatrix.parse(board)
   return cls(..., clearance_matrix=clearance_matrix)
   ```

2. **Call precompute in rrr_route_all_nets:**
   ```python
   # Before route_net_mst() call (line ~3067)
   if self.clearance_matrix:
       self._precompute_clearance_grid(net_name, self.clearance_matrix)
   ```

3. **Find where clearance is used in pathfinding** (grep for "clearance_mm" usage)

4. **Replace scalar clearance lookups with grid lookups**

5. **Test with MVB Level 3**

---

## Notes

- The clearance grid infrastructure is COMPLETE and READY
- Integration is straightforward but needs careful testing
- Main complexity: Finding all places where scalar clearance is used and replacing with grid lookup
- Performance should be GOOD (grid lookup is O(1), precompute is amortized over routing)

## Session Handoff

This work can be completed in a focused 4-6 hour session. The hardest part (designing the architecture) is done. The remaining work is mechanical integration and testing.
