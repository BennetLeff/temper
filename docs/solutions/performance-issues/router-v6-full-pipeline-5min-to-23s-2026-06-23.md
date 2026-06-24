---
title: "Router V6 full pipeline run blew up to 5+ minutes and didn't finish (3 root causes)"
date: 2026-06-23
category: performance-issue
module: router_v6
problem_type: performance_issue
component: tooling
symptoms:
  - "RouterV6Pipeline.run() on pcb/temper.kicad_pcb stalls at 13/24 (54.2%) completion in 5+ minutes and never finishes"
  - "Smoke run (100k iter cap, plain 2D A* via Numba) completes 15/24 (62.5%) in 17.7 s on the same board"
  - "Lazy theta star reroute loop runs 120 attempts x ~1 s each with no iter cap"
  - "Per-call dict.append in the A* profile wrapper adds real Python overhead in the hot path"
  - "enable_smoothing=True path is broken (SDFGrid.from_polygons missing)"
root_cause: config_error
resolution_type: code_fix
severity: high
tags:
  - router-v6
  - numba
  - astar
  - kernel-hot-path
  - closure-test
  - temper-kicad-pcb
  - profile-script
  - performance
---

# Router V6 full pipeline run blew up to 5+ minutes and didn't finish (3 root causes)

## Problem

`RouterV6Pipeline.run()` on `pcb/temper.kicad_pcb` (24 nets, 27 THT pads,
5 layers) hit 13/24 (54.2%) completion in 5+ minutes and never finished,
while the smoke runner with a 100k-iter cap achieved 15/24 (62.5%) in
17.7 s on the same board. Three independent root causes were leaving a
one- to two-orders-of-magnitude performance gap on the closure-test path:
a Numba kernel branch that did not get hoisted when `congestion_weight=0`,
a closure-test adapter enabling Python-only A* variants and a broken
smoother, and per-call dict-append overhead in the profile wrapper.

## Symptoms

- Full pipeline hangs at router stage, 13/24 nets routed after 5+ min, then killed.
- `cProfile` cumulative time dominated by `astar_core_numba._astar_search_numba`; one call reaches 1164 ms.
- Closure smoke (no cap, plain 2D A*): 15/24 in 17.6 s. The same logic in the closure-test adapter took 5x longer despite a faster path on paper.
- `enable_smoothing=True` was a silent no-op or `AttributeError`: `SDFGrid.from_polygons` does not exist.
- The profile wrapper itself was contributing measurable wall time to the run it was supposed to measure.

## What Didn't Work

- Bumping the A* iter cap from 100k -> 1M, then -> 10M. The path was Python lazy theta star, not the Numba kernel; the cap was never the bottleneck.
- Setting `congestion_weight=0.0` in the route stage. Correct, but the kernel still paid for the dead `np.log` + `np.float32(...)` branch on every expansion because Numba did not hoist it.
- Patching the profile wrapper's per-call `dict.append({...})` alone. Real overhead, but the bigger win was switching the adapter off lazy theta star -- a few ms of Python in a 5 min run is not the signal.
- Re-running only the existing wave-4 pathfinder tests after adding a new "weight-zero matches no-tensor" assertion. The new test was flaky in isolation and only stable when run with the full wave 1-4 suite; the fix was a JIT warm-up + min-of-3 timing.
- Iterating on the route stage's `congestion_weight` value (0.1, 1.0) to find a better default. The empirical result on `temper.kicad_pcb` is that any non-zero weight makes closure worse (15/24 -> 10/24); the hard signal nets need direct paths, not detours (see commit `e77d1b4a` for the diagnostic; U7 stays opt-in via `congestion_weight=0.0` default).

## Solution

**A. Hoist the `congestion_weight > 0` gate to kernel entry**
in `packages/temper-placer/src/temper_placer/router_v6/astar_core_numba.py`
so Numba can prune the U7 / R11 branch at JIT time:

```python
# before
use_congestion = congestion_flat is not None

# after
use_congestion = (
    congestion_flat is not None
    and congestion_weight > 0.0
)
```

Once `congestion_weight == 0.0` is a kernel-time constant, the
`if use_congestion:` block in the 8-neighbor inner loop is dead-coded
away. The `np.log` and `np.float32(...)` casts no longer run per
expansion, and the iter cap is no longer throttled by per-expansion
Python-equivalent math.

**B. Force plain 2D A* in BOTH placements-conditional branches** of the
closure-test adapter (`packages/temper-placer/src/temper_placer/router_v6/adapter.py`).
Lazy theta star and the broken smoother were carried over from an
earlier experiment and never flipped off:

```python
pipeline = RouterV6Pipeline(
    verbose=False,
    enable_theta_star=False,
    enable_lazy_theta_star=False,
    enable_smoothing=False,
)
```

A block comment at the top of the function documents why all three
flags must stay off for SM1 measurement on `temper.kicad_pcb`.

**C. Replace per-call `dict.append({...})` with cheap running counters**
in `scripts/full_pipeline_profile.py`'s A* hot-path wrapper:

```python
stats = {
    "a_star_call_count": 0,
    "a_star_total_ms": 0.0,
    "a_star_max_ms": 0.0,
    "a_star_min_ms": float("inf"),
    "a_star_cap_hits": 0,
    "iter_cap": 10_000_000,
    "iter_cap_logged": False,
}
# inside the wrapped_search: scalars only, one logging.info on first call
stats["a_star_call_count"] += 1
stats["a_star_total_ms"] += dt_ms
if dt_ms > stats["a_star_max_ms"]: stats["a_star_max_ms"] = dt_ms
if dt_ms < stats["a_star_min_ms"]: stats["a_star_min_ms"] = dt_ms
if hit_cap: stats["a_star_cap_hits"] += 1
```

The iter cap is logged **once** on the first call (`iter_cap_logged`
guard) so the production run surfaces the cap it actually saw rather
than the kernel default.

**D. New `scripts/full_pipeline_profile.py`**: closure-test profile
with cProfile + per-net A* logging + JSON summary written to
`/tmp/full_pipeline_profile.{log,pstats,json}`. Manifest entry added
to `scripts/manifest.yaml` (per the project's script-manifest
convention; CI's `check_manifest_gate` rejects new scripts without one).

**E. Regression-guard test** in
`packages/temper-placer/tests/router_v6/test_wave4_pathfinder.py::test_kernel_with_weight_zero_matches_no_tensor`.
Uses JIT warm-up + min-of-3 timing with 50% slack:

```python
weight_zero_ms = min(weight_zero_runs)
ratio = weight_zero_ms / max(no_tensor_ms, 0.01)
assert ratio < 1.5, f"weight=0 took {weight_zero_ms:.1f}ms vs no-tensor ..."
```

## Why This Works

- **A.** Numba specializes per scalar argument value; once `congestion_weight == 0.0` is a kernel-time constant, the `if use_congestion:` block in the 8-neighbor inner loop is dead-coded away. The `np.log` and `np.float32(...)` casts no longer run per expansion, and the iter cap is no longer throttled by per-expansion Python-equivalent math. With `congestion_weight=0.0` (the closure-test default), the kernel now costs roughly the same as the no-tensor baseline (the new test enforces `weight_zero_ms / no_tensor_ms < 1.5`).
- **B.** Lazy theta star and plain theta star are Python A* implementations with no iter cap; the reroute loop runs 120 attempts x ~1 s each on a difficult-to-route board. Plain 2D A* is the Numba kernel -- fast and bounded. Smoothing had a `SDFGrid.from_polygons` dependency that no longer exists, so enabling it was either a silent no-op or a fatal `AttributeError`. The adapter was the only thing keeping the closure test on the slow path.
- **C.** Per-call `dict.append({...})` allocates a dict + list entry on every A* call; in a 320-call run that is ~320 allocations. The scalar-counter version allocates zero; the JSON summary is built once at the end from the running totals.
- **D.** A standalone profile with cProfile, per-net A* attribution, and a machine-readable JSON summary lets the next regression be diagnosed in seconds rather than re-deriving the same evidence.

Verified outcome (commit `1acc2209`): full pipeline **23.0 s total**
(router 21.4 s), **62.5% completion** (15/24), 320 A* calls, 109 cap
hits, A* mean 31.5 ms / max 1164 ms. Smoke unchanged at 15/24 in 17.6 s.
All 34 wave 1-4 tests pass.

## Prevention

- Any Numba kernel that branches on a runtime scalar (weight, cap, mode flag) should hoist the gate to the **kernel entry**, not the per-expansion inner loop. Numba specializes per scalar, but only if the value is reachable from the call signature without crossing a Python boundary.
- Closure tests and smoke runners must converge on the same `enable_*` flags, or the closure metric is meaningless. When a flag is broken or python-only, **fail loudly** (raise on construction) rather than silently degrading; "smooth no-op, or fatal" is the worst combo because the no-op path looks like a successful run.
- Profile wrappers must use scalar counters in the hot path and aggregate into a dict once at the end. No `dict.append({...})` inside a per-call wrapper. One-shot logging (`iter_cap_logged` guard) is the right pattern for surfacing the effective config the production run actually saw.
- Timing-based regression tests need **JIT warm-up + min-of-N**, not single-shot. Numba first-call latency and OS scheduling noise both move single-run timings by 2-3x. Run with the full wave 1-4 suite in CI; isolated runs of new JIT-touching tests are flaky.
- New scripts go in with their `scripts/manifest.yaml` entry on the same commit; `check_manifest_gate` is the enforcement.
- The U7 / R11 PathFinder history cost (commit `e77d1b4a`) is **opt-in** by default. The hard signal nets on `temper.kicad_pcb` need direct paths; any non-zero `congestion_weight` makes closure worse (15/24 -> 10/24). If a future board benefits, set `congestion_weight` on the `RouterV6Pipeline` or `BoardState` to opt in.

## Related Issues

- `docs/solutions/performance-issues/2026-06-23-pcb-autorouter-completion-rate-47x-speedup.md` -- the 47x doc captures a prior pipeline-wide speedup (15min -> 19s) via gnhf + KD dedup + placement contract change. **Moderate overlap (same area, different angle):** the 47x doc's scope is the placement+routing pipeline; this doc's scope is the closure-test path on `temper.kicad_pcb`. The new doc's PRs (Numba + adapter flag fix) are *additive* to the 47x doc's fixes, not redundant.
- `docs/plans/2026-06-23-009-feat-router-v6-closure-rate-90-percent-plan.md` -- the active plan. The new doc is the implementation record of U5 (4D bit tensor) + U6 (Numba A*) + U7 (PathFinder history) and the supporting diagnostic work. When this doc lands, plan 009's U5/U6/U7 status can be marked complete with a pointer here.
- `docs/ideation/2026-06-23-sequential-routing-performance-and-completion-ideation.md` -- the source ideation that produced the "3-idea combo" (4D bit tensor, Numba A*, PathFinder history) which plan 009 re-mapped from sequential_routing -> router_v6.
- `docs/brainstorms/2026-06-23-router-v6-closure-rate-90-percent-requirements.md` -- the requirements doc (R9 = 4D tensor, R10 = Numba, R11 = PathFinder).
- `docs/plans/2026-06-22-013-feat-router-v6-performance-plan.md` -- the earlier (2026-06-22) performance plan that identified 4 hot paths (grid lookup 33s, A* 112s, channel skeleton 23s, geometry 21s) on a 180s baseline. The current doc's 5min baseline is the same pipeline 6 months later; the 2026-06-22 work is a prerequisite for the fixes here.
- `docs/solutions/architecture-patterns/strangler-fig-pipeline-decomposition-2026-06-22.md` and `docs/solutions/architecture-patterns/unified-stage-protocol-multi-pipeline-2026-06-22.md` -- the adapter pattern that hosts the `router_v6_full` strategy that this doc fixes.
- `scripts/manifest.yaml` -- the new `full_pipeline_profile.py` entry lives here.
- Beads: `temper-kfi8` (closed 2026-01-19) -- "PERF-EPIC: Router Performance Optimization - Numba/NumPy Acceleration". Closed with reason "Deferred -- not on immediate roadmap for correctness". This doc's U6 / PR-B is the concrete shipping of that epic; the closed status should be revisited or a child molecule created.
- Beads: `temper-34xa` (open) -- "Implement rip-up-and-reroute for Router V6". This doc's U7 / PR-C (PathFinder) replaces the existing rip-up loop. Direct contradiction: the bead asks to implement rip-up, this work removes it. Reconcile.
