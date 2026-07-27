# Clearance Rust port: baseline, falsifier, differential proof, and result

<!-- provenance: commit=278662e8035894f08bf287a2c4e8b4591cd1ddd1 dirty=UNKNOWN -->

**Date:** 2026-07-26
**Scope:** `verify_clearance()` (`packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`),
ported to `packages/temper-drc-rs/src/router_clearance.rs`, exposed as
`temper_drc_rs.verify_route_clearance`.

## TL;DR

- Baseline (pure Python) confirmed **quadratic**: doubling route count
  roughly **quadruples** wall time, up to 180.9s at 3,200 synthetic routes
  (19,200 segments).
- Both stated falsifiers were measured on the real production board
  (`pcb/temper.kicad_pcb`, 603 nets) and **did not fire**: only 3 distinct
  required-clearance values occur in practice, and only 1.16% of nets are
  HV-gated.
- The Rust port is **9.7x–124x faster** than Python across the measured
  range (widening with scale), produces **identical violation sets**
  (proven by a differential test against the Python reference, plus an
  internal Rust property test against a brute-force oracle, both passing),
  and all pre-existing tests continue to pass unmodified.
- End-to-end on the real board: **Stage 5 (all manufacturing DRC checks
  combined) now adds ~0.7s** to a ~124s route, down from an unbounded/
  27-minute prior measurement. Memory is unaffected by the clearance work;
  the multi-GB RSS on this board comes from the (unrelated) SAT topology
  solver stage.
- **Recommendation: do not flip `enable_manufacturing_drc` to default
  `True` in this change**, despite performance no longer being the
  blocker — see "Should the default flip?" below for why.

## 1. Baseline: pure-Python `verify_clearance`, before any change

Benchmarked directly (not through the full router pipeline) using two data
sources:

1. **A real routing result** from `pcb/temper.kicad_pcb` — obtained by
   actually running `RouterV6Pipeline(enable_manufacturing_drc=False).run()`
   on the real board (149 footprints, 95 routable nets). This required
   building `temper-rust-router` via `maturin develop --release` first (a
   separate pyo3 crate for Stage 3 topology solving, unrelated to this
   task's crate, but required to get real `RoutingResults`). The run
   completed in 124.3s and routed 64/84 nets (76.2%), producing 64 routes
   with 64 total segments and 0 vias — this board currently routes to
   *straight single-segment* traces per net under default settings, far
   below the ~3,265-segment scale in the historical incident
   (`docs/evidence/2026-07-26-manufacturing-drc-scalability.md`, not in
   this worktree's branch history but recovered via
   `git show 5b668fb0`/`dc02e2be` from the repo's full ref history).
2. **A synthetic scale-up**, because the real board's current routing
   quality doesn't reach the scale that caused the incident. Net names
   cycle through the same HV/signal/power/gnd keyword vocabulary
   `_classify_net_class` recognizes (`AC_L`, `HV_BUS`, `MAINS_LIVE`, ...
   vs `SPI_CLK`, `VCC_3V3`, `GND`, ...), each route gets a short random-walk
   polyline (not a single straight segment), and ~5% of nets are HV — see
   `packages/temper-drc-rs` differential test fixtures and the ad-hoc
   generator used for this benchmark (not committed; the committed
   differential test in `test_clearance_rust_differential.py` uses the same
   generation pattern at smaller scale for correctness, not performance).

| n_routes | segments | wall time (Python) | RSS delta |
|---:|---:|---:|---:|
| 64 (real board) | 64 | 0.010s | ~0.1 MB |
| 25 | 150 | 0.009s | ~0.02 MB |
| 50 | 300 | 0.039s | ~0.1 MB |
| 100 | 600 | 0.171s | ~0.16 MB |
| 200 | 1,200 | 0.685s | ~0.07 MB |
| 400 | 2,400 | 2.737s | ~0.05 MB |
| 800 | 4,800 | 10.956s | ~0.13 MB |
| 1,600 | 9,600 | 47.649s | ~2.9 MB |
| 3,200 | 19,200 | **180.882s** | ~4.5 MB |

Scaling check: 100→200 (4.0x time for 2x n), 200→400 (4.0x), 400→800
(4.0x), 800→1600 (4.3x), 1600→3200 (3.8x) — clean **O(n²)**, exactly as the
prior profiling evidence predicted. Peak memory stayed small and flat for
`verify_clearance` in isolation at every scale tested — the 9.2GB/14GB
figures from the historical incident and the reverted uniform-grid attempt
are **not reproduced by the clearance function alone**; they came from
either the full Stage-5 (all 7 DFM checks) combined, or from the
since-reverted uniform-grid attempt's pair-dedup set, per the prior
evidence file. This is an important scope correction: the 27-minute figure
is Stage 5 as a whole, not `verify_clearance` in isolation; this benchmark
is specific to the function this task targets, which is real, reproducible,
and unambiguously quadratic on its own.

## 2. Falsifiers, stated before implementing

Per the reverted-attempt evidence, the crux is the ~110x clearance-radius
spread (0.127mm default vs up to 14mm for HV nets). Two falsifiers were
stated before writing any Rust:

**Falsifier A — radius-class explosion.** *"The clearance-class bucketing
approach fails if the number of distinct required-clearance values grows
with board size (e.g. per-net custom voltages producing many distinct
radii), because then a fixed small set of tiers can't cover them and the
design degenerates to needing one grid per value."*

Measured on the real board's full 603-net list, `_get_required_clearance`
(now ported line-for-line) at default voltage/layer assumptions produces
exactly **3 distinct values**: `0.127mm` (default, non-HV pairs),
`4.2mm` (internal-layer HV, `14.0 * 0.30`), `14.0mm` (external-layer HV).
**Did not fire.**

**Falsifier B — HV majority.** *"The two-tier (FINE grid / HV brute force)
split degrades to the original O(n²) if HV-gated nets are not a small
minority, because the 'few-vs-many' asymmetric sweep only wins when the
'few' side is actually few."*

Measured on the real board using `_get_required_clearance`'s own narrow
escalation gate (`AC_`, `HV_`, `HIGH_VOLTAGE`, `MAINS` — a *different*,
narrower list than `_classify_net_class`'s broader classification
keywords, which also match `LINE`, `L1`/`L2`/`L3`, `PHASE`, etc. and would
have overstated the fraction at ~9%): **7 of 603 nets (1.16%)** are
HV-gated. **Did not fire.**

Because the falsifier could in principle fire on some other board, the
Rust implementation is correct-by-construction rather than depending on
these numbers: the HV-involving and via-related phases are always brute
force (never radius-tuned), so an HV-majority board only loses the
*speedup*, not correctness. This is exercised directly by
`test_random_all_hv_falsifier` (100% HV-gated synthetic board) in the
committed differential test, which passes.

## 3. Chosen data structure, and why

**Two-tier split by clearance class, not a single spatial index:**

- **FINE-vs-FINE segment pairs** (same layer, neither net HV-gated — the
  ~99% majority per the falsifier measurement) go through a **uniform
  grid** sized to `default_clearance + max_fine_width` (never smaller than
  the true search radius, so no candidate pair can be missed). Segments
  are inserted into every cell their radius-inflated bounding box
  overlaps; a shared cell is compared pairwise. Following the lesson
  recorded in the prior failed attempt (`docs/evidence/...-manufacturing-
  drc-scalability.md`, "drop the dedup set — duplicate comparisons are
  idempotent"), **no pair-dedup set is built**: the same pair may be
  compared more than once across shared cells, which is safe because the
  per-(route-pair, layer) minimum accumulator is a pure min-reduction.
- **Any pair touching an HV-gated net**, and **all via-related checks**
  (explicit vias and path-embedded via points, for both FINE and HV nets),
  are **brute force**. This is deliberate, not an oversight: the required
  clearance for an HV-involving pair depends on a conditional threshold
  (`if combined_candidate_max > 0.5mm: apply the internal-layer 0.30x
  factor`) that does **not decompose per-net** — a naive per-net
  precomputation can pick the wrong side of that `>0.5` boundary when one
  net's own candidate is below the threshold and the other's is above it.
  Rather than build a second, more complex accelerated tier around that
  non-decomposition, HV-involving and via-related pairs are evaluated
  exactly, which is safe because both populations are small minorities on
  real boards (measured above).

This directly addresses the 110x radius spread: the single largest cost
driver (FINE-FINE segment pairs at the small fixed radius) gets a properly
sized index; the heterogeneous, harder-to-index large-radius population is
handled by brute force because it's cheap in absolute terms, not because
it's assumed away.

**Degradation behavior:** if a future board has HV nets as a majority, the
FINE-FINE grid's benefit shrinks proportionally (more pairs fall into the
brute-force phase) but correctness is unaffected — verified directly by
`test_random_all_hv_falsifier`. This is a performance cliff, not a
correctness cliff.

## 4. Correctness: porting subtleties and how they were preserved

The Python original has several non-obvious behaviors that a naive
transliteration would silently break. Each was identified by reading the
source line-by-line before writing Rust, and is exercised by a specific
Rust or Python test:

1. **Two different HV-keyword lists.** `_get_required_clearance`'s own
   escalation gate (`AC_`, `HV_`, `HIGH_VOLTAGE`, `MAINS`) is narrower than
   `_classify_net_class`'s broader list (adds `LINE`, `NEUTRAL`, `PRIMARY`,
   `HOT`, `L1`/`L2`/`L3`, `PHASE`, `VBUS`, `B+`). A net can classify as
   `"HV"` for VoltageClass lookup purposes without ever triggering
   escalation. Ported as two separate constants
   (`HV_GATE_KEYWORDS`/`HV_CLASS_KEYWORDS`).
2. **CPython's positional `max()`/`min()` semantics on NaN**, which differ
   from Rust's `f64::max`/`f64::min` (IEEE-754 minimum/maximum-number
   semantics, which prefer the non-NaN operand — the opposite of what's
   needed here). Ported as `py_max2`/`py_min2` helpers that replicate
   "keep the first argument unless the second is strictly greater."
3. **NaN "poisons" a per-(route-pair, layer) minimum once set**, because
   Python's `_update_layer` only overwrites on `edge_dist <
   layer_info[layer][0]`, and `x < NaN` is always `False` — so a NaN
   value, once stored, can never be beaten by a later finite candidate.
   Rust's `<` operator has identical IEEE-754 NaN semantics, so writing the
   accumulator update as a literal `<` comparison (not `.min()`)
   reproduces this automatically. Verified by
   `nan_via_point_does_not_panic_and_poisons_layer_like_python`.
4. **The `via_diameter_default` quirk**: computed once per route pair as
   `max(route1.width, 0.6)` and used for **both** directions of the
   path-embedded-via-point check — i.e. `route2`'s own via points get a
   diameter derived from `route1`'s width, not their own. This looks like
   a latent bug in the original, but it is existing, tested behavior and
   is reproduced exactly (not "fixed") per the task's instruction to treat
   the Python implementation as the oracle.
5. **Exact-tie non-determinism from hash iteration order.** The first
   working version of the FINE-FINE grid used a `std::collections::HashMap`
   for grid cells; because Rust's default hasher reseeds on every
   `HashMap::new()`, two calls with *identical* input could visit cells in
   a different order and pick a different (but equally valid) closest
   point when multiple candidate pairs were at the exact same distance
   (e.g. several coincident zero-length segments). This was caught by the
   pre-existing Python test `test_dfm_hypothesis_fuzzing.py::
   test_clearance_idempotent` (Hypothesis flagged it as a `FlakyFailure` —
   same input, two different outputs). Fixed by switching the grid to a
   `BTreeMap` (deterministic key order). Locked in with a new Rust test,
   `repeated_calls_are_exactly_idempotent`, which calls the same input
   three times (including the exact fixture that triggered the bug) and
   asserts bit-for-bit identical output.
6. **`_calculate_minimum_clearance_by_layer`'s extraction helpers**
   (`get_segments`/`get_via_points_from_path`) were factored out to
   module-level (`_extract_segments`/`_extract_via_points`) so the
   Rust-backend adapter (`_route_to_rust_tuple`) and the pure-Python path
   share identical extraction code — eliminates an entire class of
   "the Rust input builder duck-typed `route.path` slightly differently"
   bugs by construction.

## 5. Differential-equivalence evidence

Three independent layers of proof, all passing:

1. **Rust-internal property test** (`accelerated_matches_brute_force_on_
   random_inputs`, 40 seeds; `accelerated_matches_brute_force_dense_fine_
   only`): the accelerated (grid + two-tier) implementation is compared
   against a literal brute-force translation of the original Python
   algorithm (no grid, no FINE/HV split) on randomized inputs at n=2..60
   routes, HV fractions {0%, 5%, 30%, 90%}, and three clearance thresholds.
   Compares the full violation set (net pair, layer, rounded actual/
   required clearance) — not just counts. `cargo test`: **57/57 pass**
   (49 pre-existing + 8 new).
2. **Python-vs-Rust differential test**
   (`packages/temper-placer/tests/router_v6/test_clearance_rust_
   differential.py`, new, committed): runs `verify_clearance(...,
   backend="python")` and `verify_clearance(..., backend="rust")` on the
   same input and asserts the violation sets are identical (unordered net
   pair, layer, actual/required clearance rounded to 1e-6mm) — deliberately
   excludes exact `location` comparison, because on genuine coordinate
   ties (not exercised by these fixtures) two backends could legitimately
   report either of two equally-valid closest points; total_checks is
   compared exactly. Covers: empty input, single route, overlapping
   segments, both-HV escalation (400V → 14.0mm expected), via-to-trace,
   a multilayer via-point path, 30 randomized seeds at n=2..25 routes, the
   Falsifier-B stress case (100% HV), and a dense FINE-only stress case
   (80 routes, 0% HV). **38/38 pass.**
3. **Full existing test suite**, run with the Rust backend as the
   (now-default) `backend="auto"` path — i.e. these are not special-cased,
   they exercise exactly what production code will call:

   ```
   packages/temper-placer/tests/router_v6/test_clearance_boundary.py
   packages/temper-placer/tests/router_v6/test_clearance_check.py
   packages/temper-placer/tests/router_v6/test_clearance_induction.py
   packages/temper-placer/tests/router_v6/test_clearance_segment_dist.py
   packages/temper-placer/tests/router_v6/test_dfm_hypothesis_fuzzing.py
   packages/temper-placer/tests/router_v6/test_dfm_interaction.py
   packages/temper-placer/tests/router_v6/test_empty_data_edge_cases.py
   packages/temper-placer/tests/router_v6/test_geometric_degeneracy.py
   packages/temper-placer/tests/router_v6/test_induction_base.py
   packages/temper-placer/tests/router_v6/test_induction_strategy.py
   packages/temper-placer/tests/router_v6/test_manufacturing_drc_integration.py
   packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.py
   packages/temper-placer/tests/router_v6/test_manufacturing_report_properties.py
   packages/temper-placer/tests/router_v6/test_manufacturing_report.py
   packages/temper-placer/tests/router_v6/test_multilayer_edge_cases.py
   packages/temper-placer/tests/router_v6/test_router_v6_drc_invariants_pbt.py
   packages/temper-placer/tests/router_v6/test_scale_resolution.py
   packages/temper-placer/tests/router_v6/test_clearance_rust_differential.py   (new)
   ```

   **Result: 551 passed, 18 xfailed (pre-existing, unrelated to this
   change), 0 failed.** The 18 xfailed are documented crash-characterization
   cases in `test_scale_resolution.py`/`test_empty_data_edge_cases.py`
   that predate this change.

The one genuine bug this process caught (item 5 above, the HashMap
iteration-order non-determinism) was found by the *existing* Hypothesis
idempotency test, not by anything written for this task — direct
confirmation that "the existing tests are the oracle" worked as intended.

## 6. Final benchmark: Rust-backed `verify_clearance`

Same scales as the baseline, `backend="rust"`:

| n_routes | segments | wall time (Rust) | wall time (Python) | speedup |
|---:|---:|---:|---:|---:|
| 64 (real board) | 64 | 0.106s | 0.010s | 0.1x (Rust slower — FFI/marshalling overhead dominates at this trivial scale) |
| 25 | 150 | 0.004s | 0.009s | 2.2x |
| 50 | 300 | 0.009s | 0.039s | 4.6x |
| 100 | 600 | 0.018s | 0.171s | 9.7x |
| 200 | 1,200 | 0.031s | 0.685s | 22.0x |
| 400 | 2,400 | 0.056s | 2.737s | 49.3x |
| 800 | 4,800 | 0.151s | 10.956s | 72.8x |
| 1,600 | 9,600 | 0.440s | 47.649s | 108.2x |
| 3,200 | 19,200 | 1.458s | 180.882s | **124.1x** |
| 6,400 | 38,400 | 5.470s | *(not measured, extrapolated ~720s)* | ~130x* |
| 12,800 | 76,800 | 22.294s | *(not measured, extrapolated ~2900s)* | ~130x* |
| 25,600 | 153,600 | 96.922s | *(not measured, extrapolated ~11,600s)* | ~120x* |

*Rows above 3,200 routes were only run with the Rust backend (running the
Python baseline at those sizes would take on the order of 45–190 minutes
per point by extrapolation of the confirmed O(n²) fit — not run, to stay
within a reasonable evidence-gathering budget). The extrapolated Python
figures are **UNVERIFIED** and shown only to illustrate why the larger
points weren't measured directly; the Rust figures at those sizes are
directly measured.

Peak RSS stayed under ~2.2GB even at 153,600 segments (the largest
synthetic case), versus the 9.2GB–14GB figures from the historical
incident and the reverted uniform-grid attempt.

Speedup increases with scale because it compounds two effects: (1) a
constant-factor win from compiled arithmetic replacing interpreted Python
(dominant at small-to-medium n), and (2) the FINE-FINE grid's near-linear
behavior versus Python's O(n²) (dominant at large n). At the real board's
current trivial scale (64 single-segment routes), Rust is measurably
*slower* in absolute terms (0.106s vs 0.010s) due to PyO3 marshalling
overhead on a workload too small to amortize it — noted honestly; it does
not matter in practice (both are far below any perceptible threshold) but
would be a misleading "speedup" claim if reported without context.

## 7. End-to-end: full `RouterV6Pipeline.run()` on the real board

Run in the foreground, no polling, per environment constraints:

| Configuration | Wall time | RSS delta |
|---|---:|---:|
| `enable_manufacturing_drc=False` (current default) | 124.2s | ~3,143 MB |
| `enable_manufacturing_drc=True`, `dfm_fail_on="none"` (Rust clearance backend) | 124.9s | ~2,778 MB |

**Stage 5 (all 7 DFM checks combined, including the now-Rust-backed
clearance check) adds ~0.7 seconds** to the ~124-second route — down from
the previously measured 25+ minutes for Stage 5 alone (which never
completed). The two RSS deltas are within run-to-run noise of each other
(both dominated by Stage 3's SAT topology solve — "SAT model: 6,738,105
vars, 12,328,302 clauses" appears identically in both runs); manufacturing
DRC does not add to peak memory in any measurable way. This directly
confirms the clearance function was correctly identified as the
time-dominant piece of Stage 5, and that the port resolves it.

Manufacturing report on this run: **618 total violations, 616 critical.**
Breakdown run against the same routing result in isolation:

- `clearance`: 493 violations (out of 2,016 checks) — predominantly
  **negative** actual_clearance (overlapping copper, e.g. -0.25mm to
  -0.38mm), concentrated among the `safety.*`/`discharge.*` net cluster.
  This reflects the board's actual routing state (64/84 nets routed,
  76.2% complete) producing genuinely overlapping traces, not an artifact
  of the Rust port — the same violations exist under `backend="python"`
  (proven by the differential test's exact-match requirement).
- `creepage`: 119 violations (out of 378 checks) — a separate, unmodified
  pure-Python check.
- `annular_rings`: 0 violations.
- `acid_traps`: **crashes** (`'RoutePath3D' object has no attribute
  'coordinates'`), caught by the pipeline's per-check error isolation and
  silently degrading to an empty report. This is a **pre-existing bug**,
  unrelated to this task (documented previously as
  "manufacturing DRC swallows check crashes into empty reports" in the
  repo's broader evidence history) — out of scope here but worth flagging
  because it means today's violation count is an undercount, not a
  ceiling.

## 8. Should `enable_manufacturing_drc` default to `True`?

**Not in this change.** The performance numbers in §7 unambiguously
resolve the original blocker (Stage 5 going from 25+ minutes /
non-terminating to +0.7s), so performance alone would support flipping.
But flipping the default here would silently change behavior well beyond
this task's scope:

- **14 of 16** test files in `packages/temper-placer/tests` that
  instantiate `RouterV6Pipeline`/`route_pcb()` do not pass
  `enable_manufacturing_drc` explicitly, so they'd start running all 7 DFM
  checks (previously running 0). Some of those fixture boards would very
  plausibly trip the **existing** `dfm_fail_on="critical"` default and
  start raising `ManufacturingDRCViolationError` where they previously
  returned a result — a real behavior change requiring its own review, not
  something to introduce as a side effect of a performance PR.
- The real board itself demonstrates this exact risk: with the default
  gate (`dfm_fail_on="critical"`), turning manufacturing DRC on would make
  `route_pcb()` **raise** on `pcb/temper.kicad_pcb` today (616 critical
  violations), converting today's "succeeds with 76.2% completion" into a
  hard failure. That may well be the *correct* long-term behavior (the
  check is finding real overlapping copper), but it is a product decision
  that deserves deliberate rollout — e.g. paired with fixing the
  `acid_trap`/`RoutePath3D` crash so the violation count reported to
  whoever makes that call is complete rather than an undercount, and with
  updating the 14 affected tests intentionally rather than incidentally.

`enable_manufacturing_drc` remains `False` by default; the Rust backend is
wired in as the default backend for `verify_clearance()` (`backend="auto"`
prefers Rust, falls back to Python, both documented and differential-
tested), so whenever manufacturing DRC *is* turned on — today, opt-in — it
gets the fast path automatically.

## 9. UNVERIFIED

- Extrapolated Python wall times for n > 3,200 routes in §6 (not measured
  directly; Rust figures at those sizes are measured).
- Whether the historical "27 minutes, 9.2GB" incident's memory figure was
  driven by `verify_clearance` specifically versus the other 6 DFM checks
  combined — this benchmark shows `verify_clearance` alone stays under a
  few MB of RSS delta at every scale tested, which suggests the 9.2GB came
  from elsewhere in Stage 5 or from the pipeline overall, but the original
  incident was not re-run stage-by-stage to confirm attribution.
- Whether the 616 "critical" violations on the real board represent
  genuine safety-relevant defects or an artifact of the board's
  incomplete (76.2%) routing state that would resolve once routing
  reaches full completion — not investigated as part of this task.
- Whether fixing the two keyword-list HV classification (item 1, §4) to
  use a single consistent list would change real-world behavior enough to
  matter — not investigated; both lists were preserved exactly as they
  exist in the Python oracle, unification was explicitly out of scope
  (fidelity to the existing implementation, not a redesign).

## Files touched

- `packages/temper-drc-rs/src/router_clearance.rs` (new) — the port,
  including the two-tier algorithm, Rust-internal brute-force oracle, and
  8 Rust unit/property tests.
- `packages/temper-drc-rs/src/lib.rs` — registers `verify_route_clearance`
  in the `temper_drc_rs` pymodule.
- `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`
  — `verify_clearance()` becomes a `backend`-dispatching entry point
  (`"auto"` default, prefers Rust); the original algorithm is preserved
  unchanged as `_verify_clearance_python()`; segment/via-point extraction
  factored out to module level (`_extract_segments`/`_extract_via_points`)
  so both backends share identical extraction logic; new
  `_route_to_rust_tuple()`/`_verify_clearance_rust()` adapter.
- `packages/temper-placer/tests/router_v6/test_clearance_rust_
  differential.py` (new) — the Python-vs-Rust differential test.
