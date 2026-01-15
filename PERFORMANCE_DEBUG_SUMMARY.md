# Performance Debug Summary - Router Pipeline Integration

## Root Cause Analysis

### Profiling Results

| Stage | Time | Notes |
|-------|------|-------|
| Stage 0: Parse PCB | 1.2s | Acceptable |
| Stage 2a: Routing Space | 4.1s | Obstacle map building |
| Stage 2b: Channel Skeleton | **55+s** | **BOTTLENECK** |
| Stage 3: Topology Solver | 10+s | SAT solving |
| Stage 4: Geometric Realization | 5+s | A* pathfinding |
| **TOTAL** | **60+s** | |

### The Bottleneck: Voronoi Skeleton Extraction

**F.Cu Layer Geometry:**
- 6,388 separate routing polygons
- 49,972 boundary points
- ~5,885 Voronoi sample points

The `extract_channel_skeleton()` function:
1. Samples boundary points every ~1mm
2. Computes Voronoi diagram from these points
3. Filters edges inside polygons

For complex MultiPolygon geometries with 6,388 polygons, this is extremely slow due to:
- O(n log n) Voronoi computation with large n
- Expensive point-in-polygon tests for filtering
- Union operations on complex shapes

## Solution: Three-Tier Routability Checking

### Tier 1: Ultra-Fast Heuristic (<0.1s)
```python
from temper_placer.router_v6.benders_routability_ultrafast import check_routability_ultrafast

result = check_routability_ultrafast(
    component_positions=positions,
    component_sizes=sizes,
    net_connections=[],
    board_bounds=bounds,
)
```

**What it checks:**
- Component overlaps (O(n²) but n=33 is fast)
- Congestion from component density
- Estimated wirelength

**What it skips:**
- All geometry operations
- All routing computations

### Tier 2: Fast Routability (~4s)
```python
from temper_placer.router_v6.benders_routability import check_routability_fast

result = check_routability_fast(pcb_file, verbose=True)
```

**What it does:**
- Parses PCB
- Computes routing space
- Grid-based capacity estimation

**What it skips:**
- Full skeleton extraction
- Topology solving
- A* pathfinding

### Tier 3: Full Max-Flow (60+s)
```python
from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(enable_routability_analysis=True)
result = pipeline.run(pcb_file)
```

**Complete analysis but very slow for iterative use.**

## Implementation

### New Files

1. **`benders_routability_ultrafast.py`**
   - `check_routability_ultrafast()` - Heuristic check
   - `check_routability_from_benders()` - Direct from JSON

2. **`benders_routability.py`**
   - `check_routability_fast()` - Skips Stages 3-4
   - Uses fast skeleton extraction

3. **`channel_skeleton_fast.py`**
   - `extract_channel_skeleton_fast()` - Grid-based
   - `extract_channel_capacities_direct()` - Area-based

### Updated Benders Loop

```python
from temper_placer.placement.benders_loop import run_benders_optimization

# Ultra-fast (default) - <1s total per iteration
result = run_benders_optimization(
    component_data_json="data/benders_input.json",
    check_routability=True,
    use_ultrafast_check=True,  # Default
)

# Full Max-Flow - ~60s per iteration
result = run_benders_optimization(
    component_data_json="data/benders_input.json",
    check_routability=True,
    use_ultrafast_check=False,
)
```

## Performance Comparison

| Mode | Time/Iteration | Speedup |
|------|----------------|---------|
| ILP-only | 0.45s | (baseline) |
| Ultra-fast check | 0.57s | 100x vs Max-Flow |
| Fast routability | ~5s | 12x vs Max-Flow |
| Full Max-Flow | 60+s | 1x |

## Recommendations

### For Development/Iteration
Use **ultra-fast check** (default):
```python
result = run_benders_optimization(
    component_data_json="input.json",
    check_routability=True,
    use_ultrafast_check=True,
)
```

### For Final Validation
Use **full Max-Flow** (slow but accurate):
```python
result = run_benders_optimization(
    component_data_json="input.json",
    check_routability=True,
    use_ultrafast_check=False,
)
```

### For Production
1. Run many iterations with ultra-fast check
2. Run single final validation with full Max-Flow
3. Or skip routability and rely on DRC post-routing

## Future Optimizations

1. **Incremental skeleton updates**: Only recompute changed areas
2. **Cached obstacle maps**: Obstacles don't change much between iterations
3. **Simplified geometry**: Merge small polygons before Voronoi
4. **Parallel layer processing**: Process F.Cu and B.Cu in parallel
5. **Rasterized routing**: Use grid-based instead of vector geometry

## Files Changed

- `packages/temper-placer/src/temper_placer/placement/benders_loop.py`
  - Added `use_ultrafast_check` parameter
  - Added `_check_routability_ultrafast()` method

- `packages/temper-placer/src/temper_placer/router_v6/benders_routability_ultrafast.py` (NEW)
- `packages/temper-placer/src/temper_placer/router_v6/benders_routability.py` (NEW)
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton_fast.py` (NEW)

## Verification

```bash
cd packages/temper-placer
uv run python experiments/test_benders_ultrafast.py
```

Expected output:
```
✅ ILP-only: feasible, 0.47s
✅ With ultra-fast: optimal, 0.57s
   Routability overhead: 0.10s

✅ All tests passed!
```
