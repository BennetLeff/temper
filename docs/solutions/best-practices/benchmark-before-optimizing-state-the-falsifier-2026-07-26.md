---
title: "Build the benchmark before optimising; state the falsifier before implementing — three reverted attempts at an O(n²) clearance check"
date: "2026-07-26"
category: best-practices
module: router_v6
problem_type: best_practice
component: performance
severity: medium
applies_when:
  - "optimising a loop or check before it has a benchmark you can run in under ten seconds"
  - "about to implement a prefilter, index, or caching layer whose premise is 'most items get rejected quickly'"
  - "a design idea can be stated as a one-sentence assumption about the data shape"
  - "each iteration of an optimisation attempt costs more than a minute to evaluate"
tags:
  - falsifier
  - benchmark-first
  - bounding-box-prefilter
  - spatial-grid
  - clearance-check
  - premature-optimization
  - o-n-squared
---

# Build the benchmark before optimising; state the falsifier before implementing

## Context

`router_v6/clearance_check.py`'s `verify_clearance` is O(n²) pure Python: with
3,265 emitted segments on the production board, the pairwise distance
computation is ~5.3 M pairs before zone geometry is even considered. Enabling
the manufacturing DRC stage that calls it did not finish in 27 minutes at
9.2 GB RSS (`docs/evidence/2026-07-26-manufacturing-drc-scalability.md`).
Three optimisation attempts followed, all reverted, each costing a real
end-to-end run — roughly ten minutes — to find out it didn't work:

1. **Route-level bounding-box prefilter.** Reject a route pair without
   touching segments if their bounding boxes don't overlap within clearance.
   Exact, not heuristic — and it rejected almost nothing. A route that
   crosses a dense board has a bounding box covering much of it, so route
   bboxes overlap heavily even when the actual copper is nowhere near.
   Rejection has to happen per segment, not per route.
2. **Single-radius spatial grid.** Bucket every segment by a grid cell sized
   to the search radius. Required clearance is not uniform — 0.127 mm for
   `SPI_CLK`↔`SPI_MOSI`, 14.0 mm for `AC_L`↔`PWR_RTN` and `HV_BUS`↔`GND` — so
   a single grid pitch has to be sized for the 14 mm worst case, which puts
   ~138 items in every cell and reinstates quadratic behavior for the ~99% of
   pairs that only needed 0.127 mm. Measured **14 GB RSS**, no completion.
   The memory blow-up was specifically the pair-dedup `seen` set (~2 M
   tuples) — unnecessary, because the accumulator takes a minimum and
   comparing a pair twice is idempotent.
3. **Two-tier sweep** (fine pass at 0.127 mm, second pass seeded from HV
   segments at 14 mm). Correct in shape and the direction ultimately
   recommended — but the implementation **broke 52 tests**, because
   restructuring from route-pairs to segment-pairs has to preserve several
   subtle accumulation behaviors (per-layer minima, via-to-trace but not
   via-to-via, trace-width edge distances) that the first attempt didn't
   carry over.

Each attempt was evaluated only after being built. The falsifier for attempt
1 — **"this fails if route bounding boxes overlap heavily"** — is a thirty
second check against the actual board geometry, and it fails. It was never
written down before the attempt was implemented.

## Guidance

1. **Before writing a fix, write one sentence: "this fails if X" — then check
   X first.** For a prefilter, X is usually a statement about the data's
   shape ("route bboxes rarely overlap," "clearance is uniform," "most pairs
   are far apart"). These are checkable against the real board in well under
   a minute, before any code is written.
2. **Before optimising, build the benchmark. Get the measurement loop under
   ten seconds before iterating on it.** Each of these three attempts cost a
   ten-minute full run to evaluate — the router plus the DRC stage plus test
   suite — which is why three fit in the time one disciplined attempt would
   have taken. A benchmark isolating just `verify_clearance` on a fixed
   segment set, runnable in seconds, would have let each idea be falsified or
   confirmed an order of magnitude faster.
3. **A memory blow-up in an optimisation attempt is itself a datum, not just
   a failure.** The 14 GB grid attempt's blow-up traced to a `seen` dedup set
   that was never necessary, because the accumulator already takes a minimum
   — comparing a pair twice is idempotent. Diagnosing *why* an attempt failed
   is often cheaper than the attempt itself and narrows the next one.
4. **"Correct in principle" is not "safe to land."** The two-tier sweep was
   the right direction and still broke 52 tests, because it changed the unit
   of iteration (route-pairs → segment-pairs) without first enumerating every
   behavior the old unit implicitly carried (per-layer minima, via-vs-trace
   exclusions, trace-width edge distances). State those invariants before
   restructuring around a different iteration unit, and test against them
   directly rather than discovering the gaps via a broken suite.
5. **When a fix requires restructuring an accumulation, not just adding a
   filter in front of it, say so before starting.** The recommendation this
   arc converged on — do the segment-pair restructuring in Rust
   (`temper-drc-rs`), not Python — was reached only after three Python
   attempts established that no local, filter-shaped fix exists for this
   specific clearance distribution.

## Why This Matters

None of the three failure modes were exotic. "Bounding boxes overlap on a
dense board," "one grid pitch can't serve both a 0.127 mm and a 14 mm
clearance requirement," and "restructuring an accumulation breaks its
existing invariants" are all facts that were already implicitly known about
the board and the clearance rules before any of the three attempts started.
The falsifier discipline is not about finding new information — it's about
checking, cheaply, the information already available before spending an
expensive build-and-run cycle to rediscover it. Three attempts fit in the
wall-clock time one disciplined attempt would have taken specifically because
each one skipped a thirty-second check in favor of a ten-minute one.

## When to Apply

- Before implementing any prefilter, cache, or index whose value depends on
  an assumption about the data's shape or distribution — state the
  assumption, then check it against a real sample first.
- Before any optimisation attempt where evaluating success costs more than a
  minute — build a narrower benchmark first, even if it takes ten minutes to
  set up once.
- Before restructuring the unit of iteration in an existing algorithm
  (route-level → segment-level, per-item → per-pair) — enumerate the
  invariants the old unit carried and test against them directly.
- When a "correct in principle" design breaks existing tests — treat the
  test failures as missing invariants in the design, not as noise to silence.

## Examples

```
Attempt 1 falsifier (never written down, would have taken ~30s to check):
  "This bounding-box prefilter fails if route bboxes overlap heavily on a
   dense board."
  -> pick 5 route pairs on pcb/temper.kicad_pcb, compute bbox overlap
  -> they do overlap heavily -> prefilter rejects ~nothing -> don't build it

Attempt 2's actual defect, once diagnosed:
  clearance requirement range: 0.127 mm (signal) .. 14.0 mm (HV)
  single grid pitch sized for 14.0 mm -> ~138 items/cell -> O(n^2) inside
    each cell for the 99% of pairs needing only 0.127 mm
  memory blow-up cause: `seen` pair-dedup set (~2M tuples) -- unnecessary,
    the accumulator takes min() so re-visiting a pair is harmless
```

## Related

- `docs/METHODOLOGY.md` §5, "State the falsifier before implementing" — the
  rule this doc instantiates, one sentence, checked first
- `docs/evidence/2026-07-26-manufacturing-drc-scalability.md` — full detail
  on all three attempts, the stack sample that diagnosed the hot path, and
  the recommendation to restructure in `temper-drc-rs`
- `docs/solutions/logic-errors/clearance-false-negatives-per-net-pair-2026-06-28.md`
  — a different bug in the same module (`clearance_check.py`): per-net-pair
  aggregation silently dropping multi-layer violations, found by a brute-force
  completeness oracle rather than a performance benchmark
- `docs/solutions/best-practices/profiling-cascade-algorithms-sampling-insufficient-2026-06-30.md`
  — a sibling case where the cheap check (sampling) was insufficient and a
  different falsifier was needed
