# Pipeline Profiling Results - Timeout Analysis

## Executive Summary

**Root Cause:** The `sequential_routing` stage causes pipeline timeouts due to extremely slow A* routing for individual nets.

**Evidence:**
- `TEMP_SENSE`: **114.69s** (exceeded 55,440 iterations)
- `+5V`: **90.49s** (121,920 iterations for one segment)
- `SPI_CLK`: **34.18s** (50,400 iterations)
- `SPI_CS_TEMP`: **29.39s** (49,200 iterations)

## Stage Timing Breakdown (First 14 Stages)

| Stage | Time | Notes |
|-------|------|-------|
| 1. net_class_setup | 0.00s | ✓ Fast |
| 2. zone_geometry | 0.00s | ✓ Fast |
| 3. zone_assignment | 0.00s | ✓ Fast |
| 4. zone_aware_slot_generation | 0.00s | ✓ Fast |
| 5. phased_component_assignment | 0.03s | ✓ Fast |
| 6. apply_placements | 0.00s | ✓ Fast |
| 7. **courtyard_check** | **20.32s** | ⚠️ Slow (shapely operations) |
| 8. apply_placements | 0.00s | ✓ Fast |
| 9. drc_oracle_setup | 0.01s | ✓ Fast |
| 10. clearance_grid | 0.28s | ✓ Fast |
| 11. net_ordering | 0.00s | ✓ Fast |
| 12. layer_assignment | 0.00s | ✓ Fast |
| 13. power_plane | 0.00s | ✓ Fast |
| 14. **sequential_routing** | **>180s** | 🔥 CRITICAL TIMEOUT |

## Bottleneck Analysis

### Primary Bottleneck: `sequential_routing` (Stage 14)

**Problem:** Multi-layer A* router exceeds iteration limits and takes 30-114s per net.

**Symptoms:**
```
WARNING: Multi-layer A* for TEMP_SENSE exceeded 55440 iterations (dist=58 cells, layers=2, congestion=extreme)
```

**Root causes identified:**

1. **Extreme congestion**: All nets report `congestion=extreme`
   - The clearance grid is too restrictive
   - Already-routed traces block subsequent routing
   - Iteration limits are too high (allowing 50K-120K iterations)

2. **No early termination**: Router continues exploring even when path is unlikely
   - `TEMP_SENSE` ran 55,440 iterations for a 58-cell distance
   - That's ~950 iterations per cell of progress!

3. **Greedy locking**: Nets are marked `[LOCKED]` after routing, blocking future nets
   - Once `+5V` routes and locks, other nets can't find paths
   - No rip-up/reroute mechanism

### Secondary Bottleneck: `courtyard_check` (Stage 7)

**Time:** 20.32s

**Problem:** Shapely polygon operations on 264,528 courtyard pairs

**Top time consumers:**
```python
courtyard.check_overlap()          # 20.15s total
shapely.affinity.affine_transform  # 14.41s (1M calls)
shapely.affinity.rotate            #  9.86s (529K calls)
shapely.affinity.translate         #  8.83s (529K calls)
```

**Root cause:** 36 iterations of nudging components, checking all O(N²) pairs each time

## Recommended Fixes

### Critical Priority: Sequential Routing

1. **Reduce iteration limits**
   ```python
   # Current: 50K-120K iterations allowed
   # Suggested: 5K-10K max iterations with early termination
   ```

2. **Improve congestion handling**
   - Use looser clearances during initial routing
   - Implement ripup/reroute instead of greedy locking
   - Route critical nets first (power, diff pairs) then release lock

3. **Better A* heuristic**
   - Add penalty for high iteration count
   - Terminate early if iterations > 10×distance
   - Use beam search to limit explored nodes

4. **Adaptive routing**
   - Start with loose clearances, tighten iteratively
   - If net fails 3 times, relax clearance by 50%

### Medium Priority: Courtyard Check

1. **Spatial index**: Use R-tree instead of O(N²) pairwise checks
   ```python
   # Check only nearby components using R-tree
   rtree_index = STRtree(courtyards)
   for comp in courtyards:
       candidates = rtree_index.query(comp.buffer(margin))
       # Check only candidates, not all N components
   ```

2. **Early termination**: Stop after 10 iterations if no improvement

3. **Caching**: Cache transformed polygons between iterations

## Immediate Next Steps

1. **Profile complete run** (currently in progress) to get full stage breakdown

2. **Add iteration limit warnings** to routing stage:
   ```python
   if iterations > 10 * distance:
       logger.warning(f"Net {net}: high iteration count ({iterations} for {distance} cells)")
       break  # Early termination
   ```

3. **Implement timeout per net** (e.g., 10s max per net):
   ```python
   if time.time() - net_start > 10.0:
       logger.error(f"Net {net}: timeout after 10s")
       break
   ```

4. **Test with reduced iteration limits**:
   ```python
   max_iterations = max(5000, distance * 100)  # Cap at 5K or 100× distance
   ```

## Performance Targets

| Stage | Current | Target | Fix |
|-------|---------|--------|-----|
| courtyard_check | 20s | <5s | R-tree spatial index |
| sequential_routing | >180s | <30s | Iteration limits + early termination |
| **Total pipeline** | **>300s** | **<60s** | Combined fixes |

## Files to Modify

1. `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`
   - Line ~XXX: Add iteration limit based on distance
   - Line ~XXX: Add per-net timeout (10s)
   - Line ~XXX: Add early termination heuristic

2. `packages/temper-placer/src/temper_placer/deterministic/stages/courtyard_check.py`
   - Line ~123: Replace O(N²) with R-tree query
   - Line ~49: Add max iteration limit (10)
   - Line ~XXX: Cache transformed polygons

3. `packages/temper-placer/src/temper_placer/routing/astar.py` (multi-layer A*)
   - Add iteration/distance ratio check
   - Add timeout parameter
   - Improve heuristic for congested areas
