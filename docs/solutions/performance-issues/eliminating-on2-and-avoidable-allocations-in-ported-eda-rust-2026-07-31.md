---
module: temper-placer
tags: [performance, rust, on2, allocation, differential-testing, drc, geometry]
problem_type: performance_issue
date: 2026-07-31
severity: medium
---

# Eliminating O(n²) and avoidable allocations in the ported EDA Rust crates

## Problem

The Rust geometry/DRC/quality crates were ports of Python hot paths
(channel-width sampling, congestion tensors, clearance sweeps, quality
oracles) and accumulated quadratic loops and per-iteration allocations. A
multi-round pass removed ~45 of them across the crates. Two constraints made
this delicate: **bit-identical results vs Python oracles** (differential
tests assert `==` on full f64 grids) and **deterministic DRC output**
(sorted/idempotent violations).

## Methodology

- **`clippy::perf` is nearly silent** on this codebase — the automated perf
  lints found essentially nothing. The real yield was manual pattern-hunting:
  `collect()`-for-`is_empty()`, per-pair recomputation of loop-invariant
  data, `Vec::contains` in nested loops, `format!`/`to_string`/`to_lowercase`
  in inner loops.
- Parallel `worker-bee` combs across crate groups produced candidates; **every
  finding was verified by reading the code** before fixing (the mandate was
  "be sure they're legit" — several agent suggestions were rejected for
  changing semantics).

## The highest-value patterns fixed

1. **`collect()` only to check `.is_empty()`/`.len()`** — replace with
   `.next().is_none()` / `.count()`. (Multiple: tension, overlap, zone
   checks.)
2. **Loop-invariant data recomputed per pair in O(n²) loops** — safety
   category, noise/sensitive flags, `clearance_between`, net-class lookups,
   `line_angle` (atan2) — hoist per component/pair, not per pair/segment.
3. **`Vec::contains` in nested loops** → `HashSet<&str>` (borrow, no clone).
4. **Bounding-box pre-rejection before polygon distance** — sound because the
   crate already proves bbox distance ≤ polygon distance (board.rs). Gates
   in clearance/component_overlap/wave_solder removed full polygon work for
   the vast majority of pairs.
5. **`sqrt` per pair → squared-space comparison** for via spacing (all terms
   positive ⇒ identical decision).
6. **`to_string()` per intersection** → borrowed `Vec<&str>`.
7. **`format!`/`to_uppercase`/`to_lowercase` in loops** — hoist or make
   case-insensitive without allocation.
8. **Symmetric `n×n` matrices** — compute upper triangle, mirror.
9. **BMС/SAT**: reuse one CaDiCaL solver across all 2ⁿ masks via
   `solve_assumps` instead of re-encoding every clause per mask.

## Soundness rules that kept the differential tests green

- **Preserve floating-point arithmetic order exactly.** Precomputing
  `centers`/`half-dims` is fine (same ops per pair); precomputing an inverse
  slope, or rearranging `(a.w*0.5)+(b.w*0.5)` to `(a.w+b.w)*0.5`, is not.
- **Early exits must be provably exact.** Skip a raster row outside the
  polygon's y-band (a crossing requires an edge straddling the row) or a col
  at `cx ≥ max_x` (all crossings interpolate x ≤ max_x) — exact. An
  unconditional skip on `gap_x > 0 || gap_y > 0` for *smooth* consumers is
  NOT exact (smooth_relu of a positive gap is tiny but nonzero) — only
  boolean consumers get that gate; smooth consumers may only skip at the
  underflow threshold.
- **DRC determinism** — output is sorted post-hoc, so a per-phase accumulator
  merged in arbitrary order is safe; if a rule's tie-break depends on
  iteration order, keep the order (phase accumulator preserves within-phase
  first-seen).

## A real bug hiding in "perf" clothing

`parallel_run.rs` computed `e_seg.euclidean_distance(&e_seg.start)` — the
distance from a segment to **its own start point** — which is always `0.0`,
so the accumulated parallel-run length was always `0` and the EMC rule never
fired. Fixed with the standard metric: project both segments onto the
emitter's direction and measure the overlap interval. Rule: **when a check's
output is suspiciously constant, verify the metric computes what it claims.**

## A Rust allocation trap

`HashMap<(usize, usize, String), _>` cannot be borrow-looked-up with a
`&str` (see the clippy doc). Loop-invariant `String` keys that are
re-allocated per iteration are best eliminated by changing the key shape —
a per-phase `(usize, usize)` accumulator merged once per distinct pair —
rather than by `Borrow` gymnastics.

## Related

- `docs/solutions/best-practices/clippy-cleanup-at-scale-...-2026-07-31.md`
- `docs/solutions/performance-issues/` (pre-existing router/geometry perf
  records)
