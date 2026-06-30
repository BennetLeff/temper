---
title: "EDT-based channel width computation replaces 864K Shapely distance queries for 33× Stage 2 speedup"
date: 2026-06-30
category: performance-issues
module: router_v6
problem_type: performance_issue
component: tooling
symptoms:
  - "Stage 2 channel width computation consumed ~8s of ~10s pipeline time per layer"
  - "864K Shapely distance(point, ring) queries with O(N×M) complexity and no spatial index"
root_cause: wrong_api
resolution_type: code_fix
severity: high
tags: [shapely, edt, distance-transform, scipy, routing, channel-width, spatial-index]
---

# EDT-based channel width computation replaces 864K Shapely distance queries for 33× Stage 2 speedup

## Problem

Stage 2 channel width computation called `shapely.distance(point, ring)` 864K times — for each of ~12,000 skeleton sample points, it checked distance against ALL polygon rings (O(N×M) with no spatial index). This consumed ~8s of the ~10s pipeline time for easy nets on a single layer.

## Symptoms

- `compute_channel_widths` dominated Stage 2 wall-clock time (~8s out of ~10s per layer)
- Per-point `_compute_width_at_point` made O(M) distance queries against every polygon ring, with zero spatial reuse
- Pipeline throughput was bottlenecked on width computation for simple routing areas

## What Didn't Work

- Pre-caching prepared geometry and pre-extracting exterior/interior rings (`cached_exteriors` / `cached_interiors` in the original `_compute_width_at_point` hot-loop) yielded only a ~2.2× speedup — it reduced the per-call `_get_ring` overhead but did not eliminate the fundamental O(N×M) complexity of querying every ring for every point.

## Solution

Replace per-point Shapely distance queries with a precomputed Euclidean Distance Transform (EDT) grid. The EDT is computed once per layer using scipy's `distance_transform_edt`, cached to disk keyed by a SHA-256 board fingerprint. Width queries become O(1) array lookups with bilinear interpolation.

Key changes in `packages/temper-placer/src/temper_placer/router_v6/channel_widths.py`:

**Before** — O(N×M) per-point distance to every ring:

```python
# For each of ~12K sample points:
for exterior, interiors in zip(_exteriors, _interiors):
    d = pt.distance(exterior)        # Shapely distance to each ring
    if d < min_distance:
        min_distance = d
    for interior in interiors:
        d = pt.distance(interior)    # Shapely distance to each hole
        if d < min_distance:
            min_distance = d
```

**After** — O(1) EDT grid lookup per point:

```python
def _edt_width_lookup(x, y, edt, mask, bounds, cell_size):
    """Bilinear interpolation on precomputed EDT grid."""
    gx, gy = (x - min_x) / cell_size, (y - min_y) / cell_size
    ix, iy = int(np.floor(gx)), int(np.floor(gy))
    fx, fy = gx - ix, gy - iy
    d00 = edt[iy, ix] if mask[iy, ix] else 0.0
    d10 = edt[iy, ix + 1] if mask[iy, ix + 1] else 0.0
    d01 = edt[iy + 1, ix] if mask[iy + 1, ix] else 0.0
    d11 = edt[iy + 1, ix + 1] if mask[iy + 1, ix + 1] else 0.0
    d = (d00 * (1 - fx) + d10 * fx) * (1 - fy) + (d01 * (1 - fx) + d11 * fx) * fy
    return 2.0 * d * cell_size
```

The EDT grid is built once per layer with disk caching:

```python
def _build_edt(routing_space, cell_size, use_cache=True):
    bounds = routing_space.available_area.bounds
    fp = _compute_board_fingerprint(routing_space)
    if use_cache:
        cache_path = _edt_cache_path(fp, routing_space.layer_name)
        if cache_path.exists():
            data = np.load(cache_path)
            return data["edt"], data["mask"], bounds
    mask = _rasterize_boundary_mask(routing_space.available_area, bounds, cell_size)
    from scipy.ndimage import distance_transform_edt
    edt = distance_transform_edt(mask.astype(np.uint8))
    if use_cache:
        np.savez_compressed(cache_path, edt=edt, mask=mask)
    return edt, mask, bounds
```

## Why This Works

The EDT replaces O(N×M) per-point Shapely distance calculations with a single O(grid_size) precompute step plus O(1) per-query bilinear lookups. Instead of computing distance to every polygon ring independently for each of ~12,000 sample points, the distance field is computed once and queried on demand.

The correctness proof has three parts:

1. **Base case**: Points exactly on the polygon boundary are marked `False` in the rasterized mask (Shapely `contains` returns `False` for boundary points), so the EDT assigns distance 0. This matches `shapely.distance(point, ring) = 0` for boundary points.

2. **Induction**: The EDT propagates distances through the grid using the Eikonal equation. For any cell at grid distance `d` from the nearest boundary, the error relative to the true Euclidean distance is bounded by `cell_size × √2` (the diagonal of one cell). With `cell_size = 0.1 mm`, the maximum theoretical error is ~0.14 mm — well within manufacturing tolerance.

3. **Empirical**: 200 Hypothesis property-based test cases verify the error bound across random board dimensions (`tests/router_v6/test_channel_widths_edt.py:80`).

Result: **33× speedup** on Stage 2 for the temper F.Cu layer (1.35s → 0.04s).

## Prevention

- When many distance queries are needed against the same geometry, prefer spatial precomputation (EDT, distance fields, signed distance functions) over repeated per-point geometry queries.
- Write property-based tests that verify error bounds between the approximate and exact methods across a representative parameter space.
- Cache precomputed distance fields to disk keyed by geometry hash so they survive process restarts.
- Use `scipy.ndimage.distance_transform_edt` for Euclidean distance transforms on binary masks — it is highly optimized and handles arbitrary-shaped interior regions.

## Related

- `packages/temper-placer/src/temper_placer/router_v6/channel_widths.py` — EDT build + lookup + integration into `compute_channel_widths`
- `packages/temper-placer/tests/router_v6/test_channel_widths_edt.py` — base case, induction (Hypothesis PBT), monotonicity, idempotency, temper-board regression smoke test
