# `point_to_segment_distance`: epsilon table, the merits-based decision, and what was (and wasn't) consolidated — 2026-08-13

<!-- provenance: commit=96db2ccde669efa82d85fb494d5d152d8af8848f dirty=UNKNOWN -->

## Summary

Five Rust bodies of "closest (perpendicular, clamped) distance from a point
to a line segment" were found, one of them (`creepage_check.rs`) on the
HV creepage/clearance safety path of this mains-voltage board. A structural
scan (this change's new gate, `scripts/check_geometry_primitive_duplication.py`)
found **two more, previously unknown**, bringing the confirmed count to
**seven**. Measured empirically (Rust-backed, via the actual pyo3 bindings —
not a Python mirror) against board-scale (20-254mm) and near-degenerate
corpora:

- **Consolidated in this change**: `fixed_copper.rs`'s copy (renamed to
  `point_segment_distance`, per the task's own warning that a name-based
  search undercounts) is bit-identical to the canonical kernel on every
  finite input tested; it now delegates. The orphaned pure-Python copy in
  `temper-placer/physics/thermal_fdm.py` (dead code, zero callers) now
  delegates to the canonical Rust kernel too.
- **Measured and deliberately NOT consolidated**: `geometry_kernels.rs`
  (`len2 < 1e-12`) and `drc_constraints_geometry.rs` (`seg_len_sq < 1e-10`)
  disagree with the canonical contract on **~20-24% of near-degenerate
  segments** — a real decision-boundary difference, not 1-ulp rounding noise.
  Each is bit-pinned to its own already-shipped pre-migration Python oracle
  across a 20+ file blast radius including tests that pin the exact epsilon
  boundary. Forcing a merge in this change would repeat the #1136/#1137
  mistake the cross-arm rule exists to prevent.
- **Measured, decision-immune, deferred for scope reasons**:
  `temper-constraint-compiler/src/constraints/mod.rs`'s copy matches the
  canonical decision boundary exactly (`ab_len_sq == 0.0`, 0 catastrophic
  divergence measured) and differs only in final rounding (pow+sqrt vs
  hypot, ≤1-ulp, decision-immune by the same methodology issue #987 already
  established). Consolidating it needs a new cross-crate `temper-geometry`
  dependency on a wasm-target crate plus an oracle edit whose helper methods
  are shared by several other oracle computations in the same file — real
  scope, deferred rather than rushed.
- **Newly discovered, not yet triaged**: `temper-drc-rs/src/router_clearance.rs::point_to_segment_dist`
  (production; its own hybrid `len2 < 1e-12 || !len2.is_finite()`) and
  `temper-drc-rs/src/rules/drc/property_campaigns.rs::point_seg_closest`
  (test-support only; `len2 < 1e-30`). Neither was in the task's original
  5-copy inventory. Flagged here and allowlisted with a reason; not fixed in
  this change.

## The epsilon table

| # | Location | Degenerate test | Clamp | Final close | Pinned to |
|---|---|---|---|---|---|
| 1 | `temper-geometry/creepage_check.rs::point_to_segment_distance` (**canonical**) | `denom == 0.0 \|\| !denom.is_finite()` | `py_min(1,t)` → `py_max(0,t)` | `py_hypot` (CPython Dekker) | own oracle; HV creepage safety path |
| 2 | `temper-geometry/geometry_kernels.rs::point_to_segment_distance` | `len2 < 1e-12` | `py_max(0, py_min(1,t))` | `py_hypot` via `point_distance` | own oracle (`_geometry.py`, inline in `test_geometry_rust_differential.py`) |
| 3 | `temper-geometry/drc_constraints_geometry.rs::point_to_segment_distance` | `seg_len_sq < 1e-10` | `py_max(0, py_min(1,t))` | `py_hypot` | own oracle (`_constraints_geometry_py_oracle.py`, commit c5875adad) |
| 4 | `temper-geometry/fixed_copper.rs::point_segment_distance` **(renamed; now delegates)** | *was* `dx == 0.0 && dy == 0.0` (exact, no non-finite guard) | `py_max(0, py_min(1,t))` | `py_hypot` | own oracle (`_fixed_copper_py_oracle.py`, commit `1dd54e3f2`) |
| 5 | `temper-constraint-compiler/constraints/mod.rs::point_to_segment_distance` | `ab_len_sq == 0.0` | `py_max_0(py_min_1(t))` | `(pow(dx,2)+pow(dy,2)).sqrt()` — **not** hypot | own oracle (`_compiler_py_oracle.py`) |
| 6 | `temper-drc-rs/router_clearance.rs::point_to_segment_dist` (found by the new gate) | `len2 < 1e-12 \|\| !len2.is_finite()` | `py_max2(0, py_min2(1,t))` | `.sqrt()` on `dx²+dy²` | not yet triaged |
| 7 | `temper-drc-rs/rules/drc/property_campaigns.rs::point_seg_closest` (found by the new gate; test-support only) | `len2 < 1e-30` | `.clamp(0.0, 1.0)` | `.powi(2)` sum `.sqrt()` | not yet triaged; not a production caller |

(`temper-rust-router-core/pruning.rs::point_to_segment_distance` is a known,
pre-existing, non-Wave-4 router-encoding heuristic — `len_sq == 0.0`,
`.clamp()`, `.sqrt()` — already scoped out by issue #987's own execution
record as "not one of those copies"; it uses a `Point2D` type alias the new
gate's signature heuristic does not currently resolve, a known limitation
noted in the script's docstring.)

## Verified by direct measurement, not by citation

Ran all five originally-named implementations against each other through
their actual pyo3 bindings (`temper_geometry.{point_to_segment_distance_py,
geom_point_to_segment_distance_py, drc_point_to_segment_distance_py,
fixed_copper_point_segment_distance_py}`, `temper_constraint_compiler.constraint_point_to_segment_distance`)
— not a Python re-derivation — over four corpora:

| corpus | geometry_kernels vs canonical | drc_constraints_geometry vs canonical | fixed_copper vs canonical | constraint_compiler vs canonical |
|---|---|---|---|---|
| board-scale uniform [20,254]mm, 5000 cases | 0 mismatches | 0 mismatches | 0 mismatches | 834/5000 (all ≤1-ulp) |
| near-degenerate, length 1e-15..1mm, 3200 cases | 657/3200 **catastrophic**, 96 ≤1-ulp | 757/3200 **catastrophic**, 96 ≤1-ulp | 0 mismatches | 523/3200 (all ≤1-ulp) |
| exact zero-length segments, 500 cases | 0 mismatches | 0 mismatches | 0 mismatches | 87/500 (all ≤1-ulp) |
| non-finite / extreme coords, 6 cases | 4/6 differ (canonical stays finite) | 4/6 differ (canonical stays finite) | 4/6 differ (canonical stays finite) | 5/6 differ (canonical stays finite) |

"Catastrophic" here means relative difference `> 1e-15` — i.e. bounded by
the near-degenerate segment's own tiny length, not a rounding artifact.
`fixed_copper.rs` is the only one of the four that is bit-identical to
canonical on *every finite input tested*, including sub-nanometre segment
lengths — confirming it is safe to consolidate outright.

## The epsilon decision, on the merits

**Correct contract: `denom == 0.0 || !denom.is_finite()` — no arbitrary
epsilon threshold at all.**

Reasoning:

1. **What the degenerate check is actually protecting against** is division
   by (near-)zero when computing the projection parameter
   `t = dot / denom`. But `t` is immediately clamped into `[0, 1]` regardless
   — so even a tiny nonzero `denom` cannot produce a garbage projection; at
   worst `t` clamps to an endpoint, which is legitimate behaviour for a
   genuinely short segment (the true closest point to a 1nm-long segment
   *can* legitimately be nearer to its far endpoint than its near one — an
   epsilon-threshold version always returns distance-to-the-first-endpoint
   instead, discarding that distinction).
2. **The two threshold values in play (1e-12, 1e-10 on squared length, i.e.
   ~1nm and ~10nm on segment length) are both arbitrary picks inherited from
   two independently-written pre-migration Python modules**, not derived
   from anything about this board's coordinate system. Board coordinates are
   millimetres in the 20–254 range at f64; a single subtraction's rounding
   error at that magnitude is ~2^-52 × 254 ≈ 5.6e-14mm, and even several
   composed rotation/translation transforms should not push accumulated
   error past roughly 1e-11 to 1e-12mm in a realistic worst case. Both
   1e-12 and 1e-10 (squared) sit in the same "dead zone" between that noise
   floor and the smallest physically real trace feature on this board
   (~0.1mm / 4mil trace width, ~0.05mm etch tolerance) — a gap of 4-5 orders
   of magnitude. Neither threshold is wrong in the sense of catching noise
   it shouldn't, but neither is *needed* either: exact-zero already catches
   the only case that is actually dangerous (true division by zero), and
   anything with the "the segment endpoints are just not the same point in
   the last bit" character on realistic hardware is astronomically far from
   either threshold's boundary, not straddling it.
3. **Exact-zero is well-defined and catches the real hazard (`denom == 0.0`
   itself) without discarding real, if tiny, segment geometry.** It is
   strictly *more* informative than an epsilon threshold, not less: it
   answers "is this segment a single point" exactly, rather than "is this
   segment shorter than an arbitrary cutoff nobody derived from this
   board's tolerances."
4. **The non-finite guard is the one genuine correctness gap the
   epsilon-threshold and exact-zero-only variants share**, confirmed by the
   non-finite/extreme corpus above: all four alternatives diverge from
   canonical on 4-5 of 6 non-finite/overflow cases, propagating NaN/Inf
   where canonical stays finite. An overflowing/non-finite `denom` is
   exactly the scenario an early bailout should protect against, and
   `!denom.is_finite()` is the correct, general form of "protect against a
   ratio that cannot be trusted" — broader than exact-zero alone, and not
   reachable by any epsilon threshold on the *magnitude* of a finite
   `denom`.

This is exactly `creepage_check.rs`'s existing contract — already the
canonical kernel for the HV creepage/clearance safety path per issue #987 —
so no change was needed there. It is the target every other copy is being
measured against.

## What changed

- `packages/temper-geometry/src/fixed_copper.rs::point_segment_distance` now
  delegates to `creepage_check::point_to_segment_distance`. Verified
  decision-immune (bit-identical on every finite input in the corpora above,
  including this file's own 1000-case pinned differential
  `test_point_segment_distance_matches_oracle`, which passed unchanged). The
  file's own oracle (`_fixed_copper_py_oracle.py`) was **not** touched —
  no drift to re-pin, because the two contracts already coincide on every
  input that oracle exercises.
- `packages/temper-placer/src/temper_placer/physics/thermal_fdm.py::_point_to_segment_distance`
  (dead code — zero callers anywhere in the tree, zero test coverage, its
  own ad hoc `seg_len_sq < 1e-18` threshold and a plain `np.sqrt` close) now
  delegates to `temper_geometry.point_to_segment_distance_py` (the
  canonical kernel). No oracle existed to update.
- `scripts/check_geometry_primitive_duplication.py` (new): a fail-closed CI
  gate, registered in `gate_input_registry._CI_SCRIPT_SURVEY` and wired into
  `.github/workflows/python-tests.yml`. Structural detection (not
  name-based) so a renamed copy still matches; `.geometry-primitive-duplication-allowlist`
  records every currently-known copy with a reason.

## What was measured but deliberately not merged, and why

`geometry_kernels.rs` and `drc_constraints_geometry.rs` show real
decision-boundary divergence (~20-24% catastrophic on the near-degenerate
corpus), each pinned to an already-shipped pre-migration Python reference
across a 20+ file blast radius that includes tests explicitly pinning the
epsilon boundary (`_constraints_geometry_cases.py`: "AT the 1e-10 branch
boundary and one ulp either side of it"; `geometry_kernels.rs`'s own unit
tests probe `1e-6` vs `0.9e-6`). Issue #987's own spike
(`2026-08-11-point-to-segment-distance-dedupe-spike.md`) already
scoped these two out of its 4-copy ledger for the same reason ("out of
scope here; they are documented separate references") after measuring a
comparable divergence for what became copies A/B/C, then executing a
*dedicated* plan (new `pub` visibility, new Cargo dependencies, three
oracle re-pins, full differential+PBT re-verification) to land those three
safely. Repeating that scope for two more copies whose divergence is
*larger* than A/B/C's (a real decision-boundary difference, not a rounding
difference) is not something to rush inside a change whose primary
deliverable is the epsilon *decision*, not a second execution phase. They
remain a documented, evidence-based KEEP; a follow-up "own plan" (same
template as issue #987/#918) is the correct next step, not a forced merge
here.

`constraint-compiler/mod.rs`'s copy is decision-immune (matches canonical's
decision boundary exactly; only the final rounding differs, ≤1-ulp,
0 catastrophic in every corpus tested) — by issue #987's own established
bar this is safe to fold in. It is deferred here only for scope reasons: it
lives in a different, wasm-target crate with no current `temper-geometry`
dependency, and its pinned oracle's `_distance`/`_point_to_segment_distance`
helper methods are shared by several *other* oracle computations in the
same file (`_in_escape_zone`, etc.), widening the re-verification surface
beyond a same-crate, zero-new-dependency change like `fixed_copper.rs`'s.

## Newly discovered copies (follow-up, not fixed here)

The new structural gate found two Rust bodies matching the
point-to-segment-distance fingerprint that were **not** in the task's
original 5-copy inventory:

- `temper-drc-rs/src/router_clearance.rs::point_to_segment_dist` — production
  code (router clearance checks), its own hybrid threshold
  (`len2 < 1e-12 || !len2.is_finite()`, combining `geometry_kernels.rs`'s
  threshold with canonical's non-finite guard). Not yet triaged against a
  pinned oracle or this decision.
- `temper-drc-rs/src/rules/drc/property_campaigns.rs::point_seg_closest` —
  self-contained property-test-campaign support code (per the module's own
  docstring), only called from within that file's own campaigns, not a
  production caller. Lower priority.

Both are recorded in `.geometry-primitive-duplication-allowlist` with this
finding as the reason, so the new gate stays green while flagging them as
open work rather than silently absorbing them.
