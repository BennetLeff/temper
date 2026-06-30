---
title: "Profiling Cascade-Heavy Algorithms Requires Full-Load Sampling, Not Easy-Subset Profiling"
date: 2026-06-30
category: best-practices
module: router_v6
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - Profiling an algorithm where cost depends on accumulated state (grid fill, memory pressure, lock contention)
  - Routing algorithms with rip-up-and-reroute or iterative refinement
  - Any system where the first N items are qualitatively different from items N+1 after the workload fills up
tags:
  - profiling
  - sampling
  - astar
  - router-v6
  - rip-up-cascade
  - methodology
  - performance
---

# Profiling Cascade-Heavy Algorithms Requires Full-Load Sampling, Not Easy-Subset Profiling

## Context

When profiling the Router V6 DeterministicPipeline on the 24-net temper board, `sequential_routing` was 99.4% of total time (2820ms vs 13ms for the next-worst stage). A sampling profile using only the 4 easiest nets (by bounding-box distance) showed that Shapely geometry operations dominated Stage 2 at 84% of easy-net runtime. This conclusion was **wrong** — on the full 24-net board, Stage 4 A* routing with rip-up cascades was the real bottleneck.

The key insight: the hard 5th+ net behavior (rip-up cascade, iteration cap exhaustion) only manifests after the grid fills up with earlier routed nets. Sampling on easy nets gives the wrong conclusion because the cascade is invisible.

## Guidance

When profiling algorithms where cost depends on accumulated state, always test with enough workload to trigger the cascade, not just the "easy" subset. Three concrete rules:

1. **Understand the phase transition.** In sequential routing, the first few easy nets route quickly because the grid is empty. As nets fill the grid, later nets trigger rip-up-and-reroute, iteration cap exhaustion, and congestion cascades. Profiling only easy nets misses this entirely.

2. **Verify with full-load profiling.** After a sampling profile, always confirm with at least one full-load run. The `scripts/full_pipeline_profile.py` script captures per-net A* call counts, timing, cap hits, and failure reasons — this per-net breakdown reveals the cascade effect that easy-net sampling hides.

3. **Use per-net attribution, not just aggregate stats.** Aggregate cProfile stats from a full run can still mislead if rushed nets dominate the total call count. Per-net attribution (call count, wall time, cap hits per net) separates easy-net noise from cascade signal. The `full_pipeline_profile.py` script instruments `astar_core_numba._astar_search_numba` and `astar_pathfinding._astar_route_with_ripup` with cheap-running scalar counters per net:

```python
stats = {
    "a_star_call_count": 0,
    "a_star_total_ms": 0.0,
    "a_star_max_ms": 0.0,
    "a_star_min_ms": float("inf"),
    "a_star_cap_hits": 0,
    "net_calls": {},
    "net_time_ms": {},
    "net_iters_cap": {},
}
```

## Why This Matters

Sampling on easy nets led to the conclusion that Shapely geometry ops were the bottleneck to optimize next. But the full-run profile showed that 99.4% of total pipeline time went to `sequential_routing` — specifically, the N-th net (N > 5) A* searches with rip-up cascades. Optimizing Stage 2 geometry based on the sampling profile would have been wasted engineering effort.

This class of error applies to any system with state accumulation (grid fill, memory pressure, lock contention, garbage collection pressure) where the first N items are qualitatively different from items N+1. Examples include connection pool saturation, file system metadata caches, and JIT compilation warm-up — any domain where the "empty state" is cheap and the "full state" triggers pathologically different behavior.

## When to Apply

- Profiling routing, placement, or any iterative algorithm where the solution space degrades as it fills
- Any system where "first N items are easy" is a known property (connection pools, memory allocators, file system metadata)
- Whenever a sampling profile shows a surprising bottleneck in a stage that intuition says should be cheap — full-load verification is the fastest way to rule out the sampling artifact

## Examples

**Misleading: sampling profile on 4 easiest nets**

```bash
python3 scripts/profile_router_v6_sampling.py 4
```

Result: Shapely geometry operations dominate Stage 2 at 84% of runtime. Conclusion: optimize Stage 2 geometry next.

**Correct: full-pipeline profile on all 24 nets**

```bash
PYTHONPATH=packages/temper-placer/src \
python3 scripts/full_pipeline_profile.py
```

Result: `sequential_routing` is 2820ms of 2833ms total. The per-net breakdown shows easy nets 1–5 complete fast; net 6+ triggers rip-up cascades that consume the remaining time. Conclusion: optimize Stage 4 A* routing, not Stage 2 geometry.

**Verification: timing baselines confirm the cascade**

The canonical timing baseline (`power_pcb_dataset/timing_baselines.yaml`) captures per-stage wall-clock on the full board:

```yaml
- stage: sequential_routing
  wall_ms_mean: 2820.071
- stage: slot_generation
  wall_ms_mean: 0.032
- stage: zone_geometry
  wall_ms_mean: 0.018
```

The 140,000:1 ratio between `sequential_routing` and Stage 2 stages is unambiguous — and completely invisible in the easy-net sampling profile.

## Related

- `scripts/full_pipeline_profile.py` — full-load profiling with per-net attribution and A* call counters
- `scripts/profile_router_v6_sampling.py` — easy-net sampling profile (useful for rapid iteration on Stage 2 in isolation, misleading as a whole-pipeline bottleneck signal)
- `power_pcb_dataset/timing_baselines.yaml` — canonical per-stage timing baselines from full-load runs
- `docs/solutions/performance-issues/router-v6-full-pipeline-5min-to-23s-2026-06-23.md` — the performance fixes that resulted from correct full-load profiling
