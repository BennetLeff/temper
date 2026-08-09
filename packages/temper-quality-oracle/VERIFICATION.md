# temper-quality-oracle — Verification

Updated 2026-08-01: `routing_quality::routing_quality_score` added
(Wave 4 Phase A #1 — migration of
`temper_placer/metrics/routing_quality.py::evaluate_routing_quality`'s
composite 0-100 score to Rust; the Python module now delegates its
scoring arithmetic to `temper_quality_oracle.routing_quality_score_py`
through the existing pyo3 bridge).

Updated 2026-08-03: `quality_score::placement_score` /
`quality_score::drc_score` / `quality_score::overall_score` /
`quality_score::interpret_score` added (Wave 4 Phase A #5 — migration of
`temper_placer/metrics/quality_score.py`'s composite placement/DRC/
routing scoring to Rust; the Python module keeps its public API and
delegates to `temper_quality_oracle.{placement_score_py,drc_score_py,
overall_score_py,interpret_score_py}` through the same pyo3 bridge).

## Scope of this document

This crate implements the typed quality-oracle pipeline (net
classification → constraint derivation → config → thresholds →
pass/fail oracle) plus the IPC-2221 clearance function and, since
Wave 4 Phase A #1, the routing-quality composite score.  The induction
proofs below cover the module with computational structure; the
routing-quality and composite-quality scores are closed-form arithmetic
and carry the explicit non-applicability note required by the Wave 4
R1e gate (docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md).

## Routing-quality composite score — induction non-applicability note

`routing_quality::routing_quality_score(completion_rate, via_count,
drc_error_count, net_count) -> f64` is a **closed-form, loop-free and
recursion-free function of its four scalar inputs**:

```text
completion_score = completion_rate * 60.0
drc_score        = 20.0 if drc_error_count == 0 else 0.0
efficiency_score = 20.0 if net_count == 0 else
                   20.0 * (1.0 - clamp01((via_count / net_count - 2.0) / 8.0))
score            = (completion_score + drc_score) + efficiency_score
```

There is no iteration, no induction variable, and no data structure
whose size varies with the input — the kernel does exactly the same
finite sequence of correctly-rounded f64 operations for every input.
R1e's induction requirement applies to modules with recursive or
computational structure; for this module it is **not applicable**.
In its place we record the structural correctness argument below, which
is what the R1e note requires for data-only / closed-form modules.

### Structural correctness argument (bit-exact parity)

1. **Pure function of four inputs.** Every output bit depends only on
   the four scalar arguments and on correctly-rounded IEEE-754 f64
   arithmetic, which is deterministic and identical in CPython and
   Rust for the same operation sequence.  No IO, no global state, no
   nondeterminism enters the computation.

2. **Operation-order pinning.** The kernel reproduces the pre-migration
   Python's exact f64 operation order (pinned by the differential suite
   `packages/temper-placer/tests/metrics/test_routing_quality_rust_differential.py`,
   which embeds the verbatim pre-migration implementation as an oracle
   and asserts bit-identical equality):
   - `completion * 60` (float×int) ⇔ `completion * 60.0`
   - `vias / net_count` (int true-division) ⇔ `vias as f64 / net_count as f64`
   - `(vias_per_net - 2) / 8` ⇔ `(vias_per_net - 2.0) / 8.0`
   - `max(0.0, min(1.0, x))` ⇔ `x.min(1.0).max(0.0)` — agrees on every
     input including non-finite ones (CPython's comparison-based
     `min`/`max` keep the first non-NaN operand; Rust's `f64::min`/`max`
     ignore NaN the same way)
   - `20 * (1.0 - via_penalty)` (int×float) ⇔ `20.0 * (1.0 - via_penalty)`
   - left-associative `+` in Python ⇔ left-associative `+` in Rust:
     `(completion_score + drc_score) + efficiency_score`

3. **Branch equivalence.** The `net_count == 0` and
   `drc_error_count == 0` branches map one-to-one to the Python
   `if/else` structure; the closed-form decomposition is verified by
   the PBT suite's exact-boundary pins (P5:
   `score == 60*c + drc_part + 20.0` at ≤ 2 vias/net and
   `== 60*c + drc_part + 0.0` at ≥ 10 vias/net, bit-exact).

4. **Soundness of the closed-form bounds.** The PBT suite's global
   bound `0 ≤ score ≤ 100` holds exactly when `completion_rate ∈ [0,1]`
   (the kernel deliberately does not clamp completion; the bound is
   honestly scoped to that domain in the property's docstring).

## Composite quality score — induction non-applicability note

`quality_score::{placement_score, drc_score, overall_score,
interpret_score}` are **closed-form, loop-free and recursion-free
functions of their scalar inputs**:

```text
placement_score = clamp01x100(100 - 20·overlap - 15·boundary - 25·hvlv
                              - 10·keepout - 5·(clearance - hvlv)
                              - 10·zone - [avg_len > 50 ? min(10, (avg_len-50)/10) : 0])
drc_score       = clamp01x100(100 - 15·errors - 3·warnings)
overall_score   = routing.is_some() ? 0.4·ps + 0.4·ds + 0.2·rs
                                    : 0.5·ps + 0.5·ds
interpret_score = score ≥ 90 → "excellent" | ≥ 80 → "good"
                  | ≥ 60 → "ok" | "poor"
```

There is no iteration and no input-sized data structure — every input
runs the same finite sequence of correctly-rounded f64 operations.  R1e's
induction requirement is therefore **not applicable**; in its place we
record the structural correctness argument:

### Structural correctness argument (bit-exact parity)

1. **Pure functions of scalar inputs.** Every output bit depends only on
   the scalar arguments (violation counts, wirelength scalars, subscores)
   and correctly-rounded IEEE-754 f64 arithmetic — deterministic and
   identical in CPython and Rust for the same operation sequence.  No IO,
   no global state.

2. **Operation-order pinning.** The kernels reproduce the pre-migration
   Python's exact f64 operation order (pinned by the differential suite
   `packages/temper-placer/tests/metrics/test_quality_score_rust_differential.py`,
   which embeds the verbatim pre-migration implementation as an oracle
   and asserts bit-identical equality):
   - per-unit penalties are exact int arithmetic in Python, converted to
     f64 exactly at the subtraction: `score -= overlap_count * 20` ⇔
     `score -= overlap_count as f64 * 20.0` (identical for counts below
     2^53);
   - the wirelength penalty keeps the parenthesized `(avg_len - 50) / 10`
     before the `min(10, ·)` cap;
   - the clamp is `max(0.0, min(100.0, score))` ⇔
     `(100.0_f64.min(score)).max(0.0)` — constant-first, matching
     CPython's first-argument NaN semantics (B5);
   - the overall chains `0.5·ps + 0.5·ds` and
     `0.4·ps + 0.4·ds + 0.2·rs` are left-to-right with no reassociation.

3. **Branch equivalence.** The `total_wirelength > 0 && avg_len > 50`
   wirelength branch, the `routing_score.is_some()` overall branch, and
   the `>= 90 / >= 80 / >= 60` interpretation thresholds map one-to-one
   to the Python `if/else` structure (IEEE comparisons, identical on
   NaN).

4. **Soundness of the closed-form bounds.** `0 ≤ placement ≤ 100` and
   `0 ≤ drc ≤ 100` hold for ALL finite inputs because the clamp is the
   final operation; the interpretation vocabulary is closed (one of four
   strings).  The PBT suite pins the per-unit penalty weights via exact
   translation relations on a constrained (unclamped) input class.

### Base case / induction step for the crate's oracle module

The typed quality oracle (`oracle.rs`) does have computational
structure; its correctness argument follows the induction pattern
recorded for the crate's existing proptest suite (see
`proptest-regressions/oracle.txt`):

- **Base case:** an empty netlist produces an empty
  `QualityVerdict::Pass` with zero metrics — verified by the crate's
  unit tests.
- **Induction step:** classification (`classification.rs`) and
  derivation (`derivation.rs`) are per-net pure functions; adding the
  (n+1)-th net only adds its independent classification/derivation
  result to the aggregated verdict, so correctness for n nets implies
  correctness for n+1 nets.  The verdict aggregation is a fold with no
  cross-net coupling.

## Placement metric analyzers — verification by induction

Added 2026-08-04 (Wave 4 Phase 4 — migration of the
`temper_placer/metrics/quality.py` analyzers to
`src/placement_metrics.rs`; the Python module keeps its public API and
delegates through `temper_quality_oracle.{thermal_score_py,
zone_compliance_score_py, hv_lv_clearance_score_py,
dual_rail_clearance_report_py, loop_area_score_py, compactness_score_py,
connectivity_clustering_score_py, quality_report_overall_py,
numpy_pairwise_sum_py}`).

Unlike the two closed-form scores above, these kernels **do** have
computational structure — every one is a fold over a variable-length
input — so R1e's induction requirement applies and is discharged here
rather than waived.

### Base case

For each aggregate the smallest meaningful input is the empty one, and
each has a pinned value (all `1.0`, the "nothing to measure is perfect"
default; `dual_rail_clearance_report` additionally pins integer `0`
counts):

| Kernel | Empty-input value | Pinned by |
|---|---|---|
| `thermal_score` | `1.0` | `every_aggregate_has_a_pinned_empty_input_value`, `test_thermal_score_empty_set_is_one` |
| `zone_compliance_score` | `1.0` | same + `test_zone_compliance_empty_is_one` |
| `hv_lv_clearance_score` | `1.0` | same + `test_hv_lv_clearance_empty_sides_are_one` |
| `dual_rail_clearance_report` | `(1.0, 1.0, 0, 0)` | same + `test_dual_rail_empty_sides_are_all_clear` |
| `loop_area_score` | `1.0` | same + `test_loop_area_empty_is_one` |
| `compactness_score` | `1.0` | same + `test_compactness_single_component_is_one` |
| `connectivity_clustering_score` | `1.0` | same + `test_connectivity_clustering_empty_is_one` |

The one-element case is likewise pinned bit-exactly against the oracle
(`test_p4_axis_aligned_loops_are_exactly_one`,
`compactness_score_single_component_is_one`).

### Induction hypothesis

For an input of `n` elements, the kernel's result is bit-identical to
the pinned Python oracle's result on the same `n` elements **in the same
order**.

### Induction step

Every kernel is a fold whose per-element contribution depends only on
that element and on loop-invariant scalars (board bounds, thresholds,
`max_distance`), never on other elements:

1. **`thermal_score` / `loop_area_score`** — `total += f(element)` with
   `count += 1`.  Adding an `(n+1)`-th element appends exactly one
   `f(element)` to the accumulation and one to the divisor; the first
   `n` operations are untouched.  Because the accumulation is a naive
   left-to-right f64 sum, *order* is part of the hypothesis, not an
   incidental detail — see "Ordering" below.
2. **`hv_lv_clearance_score` / `dual_rail_clearance_report`** — the fold
   is `min` over the HV×LV cross product plus integer counters.  Adding
   an element adds a row (or column) of independent pair evaluations;
   `min` and integer addition are associative and commutative over the
   finite values reachable here, so the result is independent of the
   order in which the new pairs are folded in.
3. **`zone_compliance_score`** — exact integer counting, then one
   division.  Per-element independence is immediate.
4. **`compactness_score` / `connectivity_clustering_score`** — the folds
   are `min`/`max` extrema plus a `sum`.  Extrema are order-independent
   and exact (they select an input value, introducing no rounding); the
   `sum` is CPython's compensated `sum()` and is reproduced operation for
   operation (class B12 below).

No kernel carries cross-element state beyond the accumulator, and none
short-circuits, so correctness for `n` implies correctness for `n+1`.

### Ordering is part of the contract, not an artifact

`thermal_score` accumulates over a Python `set`.  CPython randomises
`str` hashing per process, so the traversal order — and therefore the
low bits — already varied between processes before this migration.  The
delegation makes exactly one pass over the set and hands Rust the list in
that order; Rust folds it as given and never sorts.

This is deliberate.  Sorting would make the result reproducible, which
looks like an improvement and is in fact a **behaviour change on shipped
inputs** that no differential against the current code could detect —
the same judgment PR #688 applied to the loader primitive it kept in
Python.  What is verified instead is the stronger, true statement:

- Rust reproduces Python for *every* permutation
  (`test_thermal_score_tracks_python_under_every_permutation`,
  `test_thermal_score_matches_python_for_each_discriminating_order`), and
- the permutation set is genuinely discriminating — five ordinary board
  coordinates produce two distinct bit patterns across their 120
  permutations (`test_thermal_score_is_genuinely_order_sensitive`), so
  the sweep is not vacuous.

The mutation "helpfully sort the thermal fold into a canonical order"
is caught by the differential (4 failures), which is what makes the
non-sorting a checked property rather than a comment.

### Three summation strategies, and why they are not interchangeable

The single largest source of divergence in this module is that the
oracle uses **three different summation algorithms**, and they disagree:

| Oracle expression | Algorithm | Rust helper |
|---|---|---|
| `np.sum(cross)` (shoelace) | numpy pairwise (class **B11**) | `numpy_pairwise_sum` |
| `sum(c.width * c.height for ...)` | CPython 3.12 Neumaier-compensated (class **B12**) | `py_builtin_sum` |
| `total_score += score` | naive left-to-right | `naive_sum` / inline fold |

Both B11 and B12 are **new catalog classes recorded by this migration**
and are now entered in `docs/wave4-discipline-contract.md` §2.  B12 was
found the hard way: `compactness_score` was 1 ulp off on random inputs
because the Rust used a naive fold where the oracle wrote `sum(...)`.

`numpy_pairwise_sum` is verified exact against `np.sum` across all three
of numpy's branches (n < 8 naive, n <= 128 eight-way unrolled,
n > 128 recursive halving) for n in 1..=40 plus
{63, 64, 127, 128, 129, 200, 256, 300, 1000}, and P6 fuzzes it to 400
elements.  The complementary anti-vacuity check
(`test_naive_summation_would_fail_the_pin`) proves numpy does *not* sum
naively, so the replication is load-bearing rather than ornamental.

### NEP 50 weak promotion — `connectivity_clustering_score`

This kernel never wraps its bbox extrema in `float()`, so they stay
numpy scalars.  Under NEP 50 (numpy >= 2.0) a Python float meeting a
numpy scalar is *weak*: it is cast to the scalar's dtype and the
operation runs in that dtype.  With a float32 placement array — which is
what `PlacementState.from_positions_dict`, and hence
`external_oracle.score_placement`, produces — the entire bbox → area →
ratio chain therefore runs in **f32**, not just the subtraction.

Two facts were measured rather than assumed:

1. NEP 50 casts the weak operand *first* and then operates.  Over 200k
   random `f32 op f64` triples, cast-then-operate reproduced numpy on
   every sample; compute-in-f64-then-round diverged on 57,055.  Rust's
   `as f32` followed by an f32 op is therefore the faithful shape.
2. `max(actual_area, min_possible_area)` has a **data-dependent return
   type**, because Python's `max` returns the object rather than a
   promoted value.  When the weak f64 wins the division is f64 (and the
   ratio is exactly `1.0`); when the strong f32 wins it is f32.  Both
   arms are reproduced.

The delegation passes the dtype explicitly.  Ignoring it is caught by
the differential (18 failures).

### libm `pow`, and a bug this caught

Catalog class B7 requires `x ** 2` / `x ** 0.5` to be libm `pow`, not
`x * x` / `sqrt`.  Measured here over 200k samples: `x ** 0.5` differs
from `math.sqrt(x)` on 263 and `x ** 2` from `x * x` on 256 — about one
input in 800.  `py_pow` resolves `pow` through `dlsym` per class B1.

The first implementation of that resolution was **wrong and silently
so**: it passed a null `RTLD_DEFAULT`, which is correct for glibc but not
for Darwin (`((void *) -2)`).  `dlsym` returned null, the code fell back
to `f64::powf`, and LLVM lowered `powf(x, 2.0)` to `x * x` and
`powf(x, 0.5)` to `sqrt(x)` — precisely the substitution B7 forbids.
The randomized differential cases did not catch it (0.13% hit rate); the
anti-vacuity mutation sweep did, by showing that swapping in `sqrt`
changed nothing.  Both the fix and a regression pin are in place:
`py_pow_resolves_to_host_libm_not_sqrt` (crate-side) and
`test_pow_diagonal_operands_that_sqrt_gets_wrong` (differential, using
search-found operands where the two really differ).

### Anti-vacuity: 10 mutations, 8 caught, 2 proven equivalent

| Mutation | Result |
|---|---|
| M1 compensated `sum()` -> naive (B12) | caught — 35 failures |
| M2 numpy pairwise -> naive (B11) | caught — 16 failures |
| M3 libm `pow` -> `sqrt`/`x*x` (B1/B7) | caught — 3 failures |
| M4 `py_max2` -> `f64::max`, thermal clamp (B5) | **not caught — provably equivalent** |
| M4b `py_max2` -> `f64::max`, `pair_clearance` (B5) | caught — 1 failure |
| M4c `py_min2` -> `f64::min`, clearance fold (B5) | **not caught — provably equivalent** |
| M5 ignore the float32 dtype flag (NEP 50) | caught — 18 failures |
| M6 sort the thermal fold | caught — 4 failures |
| M7 clearance ramp `>=` -> `>` | caught — 1 failure |
| M8 macOS `RTLD_DEFAULT` regression | caught — 3 failures |
| M9 compactness extrema fold -> first element only | caught — 107 failures |

The two survivors are reported as survivors rather than papered over,
because each is a *genuine* equivalence at its call site, not a testing
gap:

- **M4** — the divergent inputs for `py_max2(0.0, x)` vs `x.max(0.0)`
  are NaN and `-0.0`.  For NaN both yield `0.0`.  `-0.0` is unreachable:
  `1.0 - distance / max_distance` cannot produce `-0.0` under
  round-to-nearest (`a - b` is `-0.0` only for `a = b = -0.0`).
- **M4c** — `py_min2` and `f64::min` differ only once a NaN reaches the
  accumulator.  It cannot: the accumulator starts at `+inf`, and
  `py_min2(+inf, NaN)` keeps `+inf`, so NaN never becomes the running
  minimum.

Both uses are kept as the faithful mirror anyway — they cost nothing and
they stay correct if a future change makes those inputs reachable.

### Empty-input semantics (the vacuity class)

All seven aggregates default to a *passing* score on empty input.  That
is pre-migration behaviour and is preserved exactly, but preserving it
silently is how vacuous gates are born, so it is enumerated in
`TestEmptyInputSemantics` with the concrete type of each return value.

Two consequences are recorded explicitly rather than left latent:

- `compute_quality_report` calls the retired `total_wirelength`, which
  raises unless `context.net_pin_indices.shape[0] == 0`.  The report is
  therefore only callable with an empty pin table, which in turn forces
  `connectivity_clustering_score` to its vacuous `1.0` on every
  reachable call.  `test_report_raises_on_a_populated_context` pins that
  the delegation raises exactly where the oracle does.
- With an empty config, **six of the seven** subscores feeding
  `overall_score` are unconditional `1.0` (thermal, zone, clearance,
  loop, the retired `congestion_score` stub, and clustering).  Only
  `compactness_score` reads the placement.  So `overall_score >= 6/7`
  for any input, and a gate thresholding it below `0.857` is vacuous by
  construction —
  `test_report_of_an_empty_config_is_six_sevenths_vacuous` makes that
  ceiling visible.

`thermal_score` additionally has **no upper clamp**: a component placed
beyond the target edge scores above `1.0`
(`test_p1_domain_restriction_is_real` pins `2.0` for a part 1 mm past a
`max_distance = 1.0` edge).  This predates the migration; the Rust
reproduces it exactly and P1 is honestly scoped to on-board placements
rather than asserting a bound that does not hold.

### R1h — physics discipline: N/A

These are geometric and counting aggregates over already-computed
coordinates.  They encode no physical constraint, feed no solver, and
have no Chebyshev-style soundness obligation; the R24 physics gate does
not apply.

## Differential / property evidence

- `packages/temper-placer/tests/metrics/test_routing_quality_rust_differential.py`
  — bit-exact differential vs. the verbatim pre-migration oracle
  (direct kernel pins + full module-level delegation pins).
- `packages/temper-placer/tests/metrics/test_routing_quality_rust_pbt.py`
  — 5 vacuity-guarded invariants + 4 metamorphic relations.
- `src/routing_quality.rs` `#[cfg(test)]` unit tests — hand-computed
  values and a bounded exhaustive sweep asserting `score ≤ 100`.
- `packages/temper-placer/tests/metrics/test_quality_score_rust_differential.py`
  — bit-exact differential vs. the verbatim pre-migration oracle for the
  composite-quality kernels (placement/DRC subscores, overall, and
  interpretation; direct kernel pins + full module-level delegation
  pins, including NaN semantics, the adjacent-float wirelength boundary,
  and the no-routing vs routing weighted chains).
- `packages/temper-placer/tests/metrics/test_quality_score_rust_pbt.py`
  — 7 vacuity-guarded invariants + 4 metamorphic relations + 8 vacuity
  mutants.
- `src/quality_score.rs` `#[cfg(test)]` unit tests — hand-computed
  values, penalty/interpretation thresholds, and branch pins.
- `packages/temper-placer/tests/metrics/_quality_py_oracle.py` — the
  verbatim pre-migration copy of `metrics/quality.py` at `ebf9326ff`,
  pinned as the reference for the Phase 4 analyzer migration.
- `packages/temper-placer/tests/metrics/test_quality_rust_differential.py`
  — 479 bit-exact assertions vs. that oracle (floats compared through
  `float.hex()`, every non-float leaf carrying its concrete `type` in the
  comparison key so `0` and `0.0` cannot compare equal).  Covers all
  seven analyzers plus the report aggregate, both `float32` and
  `float64` placements, the `KeyError`-skip paths, the numpy pairwise
  branch boundaries, NaN positions, the ramp boundary at threshold `0`,
  and search-found operands where libm `pow` diverges from `sqrt`.
- `packages/temper-placer/tests/metrics/test_quality_rust_pbt.py` — 8
  vacuity-guarded properties (P1..P8, each with a `test_pN_fails_for_*`
  mutant) + 4 metamorphic relations (MR1 translation invariance, MR2
  power-of-two scale covariance, MR3a permutation invariance for the
  min/count reductions with MR3b honestly bounding the *non*-invariant
  float sum, MR4 point-reflection invariance).
- `src/placement_metrics.rs` `#[cfg(test)]` unit tests — 26 tests
  covering the B5 argument-order semantics, the B11 pairwise-sum branch
  structure, the B12 compensated-sum divergences, the `dlsym`
  resolution guard, and each kernel's empty-input value.

## Aesthetic metric kernel — verification by induction

Added 2026-08-08 (Wave 4 — migration of
`temper_placer/metrics/aesthetic.py::compute_aesthetic_score` to
`src/aesthetic.rs`; the Python module keeps its public API and delegates
through `temper_quality_oracle.aesthetic_score_py`).

### Recorded divergence (Wave-4 tie-break rule: report and record, do not fake)

The pre-migration module contains a **dead branch**: its `get_prefix_groups`
helper was retired with the JAX migration and now raises
`NotImplementedError`, so `compute_aesthetic_score` could never complete for
a non-empty placement.  Its only reachable pre-migration behavior was the
`n == 0` early return (`{"aesthetic_index": 1.0}`); the consumer
(`validation.human_reference_extractor`) swallows the exception and emits no
aesthetic metrics, which is why the module was never observed failing.

Parity on non-empty inputs therefore **cannot** be pinned against the
verbatim oracle (it raises) — G1/G2 are honest for the empty case and are
recorded as a deliberate divergence elsewhere.  The migration resolves the
dead call to the module's **own specified consequence**: with no prefix
groups, the module's `else` branch makes `prefix_alignment_score` its
vacuous `1.0` default.  The differential suite pins both halves: the verbatim
oracle's empty-case output is asserted bit-identical, the verbatim oracle's
non-empty raise is asserted (so the divergence is a measured fact), and the
Rust kernel is pinned bit-for-bit against the module's own formulas
(`_module_formula_reference`, numpy) for the grid/orientation/aggregate
compute.  The observable change on the consumer is that a real board now
produces four aesthetic metrics instead of none — the state the module was
designed for (see
`docs/solutions/architecture-patterns/quality-metrics-built-but-never-connected-2026-07-01.md`).

### Base case

The smallest meaningful input is the empty placement: the oracle returns only
`{"aesthetic_index": 1.0}`.  The Rust kernel returns `None` and the
pyfunction emits exactly that dict — pinned bit-identical by
`test_empty_input_bit_identical_to_oracle` (both the pyfunction and the
public shim) and `empty_placement_is_none`.

### Induction hypothesis

For `n` components, the Rust kernel's result is bit-identical to the module
formulas (`_module_formula_reference`) on the same `n` components, in the
same order, in both the float32 and float64 chains.

### Induction step

The kernel has no cross-element state: the grid-snap factor aggregates a
count of per-component booleans (each a pure function of that component's
coordinates and the loop-invariant `grid_size`), and the orientation factor
aggregates a fixed 4-bin histogram of per-component `argmax` indices.  Adding
an `(n+1)`-th component appends one independent boolean to the count and one
independent histogram increment; neither operation reads or writes any other
component's contribution, and the aggregate is a closed-form weighted sum of
the two order-free totals (plus the constant alignment factor).  Correctness
for `n` therefore implies correctness for `n+1`.  Unlike `thermal_score`,
this kernel is genuinely permutation-invariant (no float sum over components
exists), which MR2 asserts as a bit-exact property.

### Empirical verification

- Differential:
  `packages/temper-placer/tests/metrics/test_aesthetic_rust_differential.py`
  — verbatim `_oracle_*` block pinned; empty case asserted bit-identical;
  the oracle's non-empty `NotImplementedError` asserted (the recorded
  divergence); 300 randomized + 5 crafted cases per dtype asserted
  bit-identical to `_module_formula_reference` (NaN/inf positions, negative
  and huge coordinates, all-equal and NaN logits, single component); the
  f32-vs-f64 dtype flags pinned load-bearing (grid-snap discriminator
  `x = 578.5099839972382`, argmax discriminator rows).
- PBT: `packages/temper-placer/tests/metrics/test_aesthetic_rust_pbt.py` —
  five vacuity-guarded properties (P1 bounds, P2 grid fraction, P3
  split-extremeness ordering, P4 weighted-sum aggregate, P5 argmax-multiset
  independence) each with a `test_pN_fails_for_<mutant>`, plus three
  bit-exact metamorphic relations (MR1 grid-aligned translation on dyadic
  coordinates, MR2 component permutation, MR3 coordinate reflection), each
  with its exactness bound stated.  Reachability companions record that the
  generated inputs genuinely reach discriminating values.
- `src/aesthetic.rs` `#[cfg(test)]` unit tests — B12 `np.minimum`/`np_clip`
  semantics (signed-zero tie and NaN propagation), floored `np.mod` bits,
  measured `numpy_argmax` behavior (first-max, NaN-wins, dtype flag), the
  `dlsym` log resolution, and both dtype-flag discriminators.
- **Bit-exactness classes exercised:** B1 (host libm `log` via `dlsym`,
  measured identical to `np.log` on 200k samples), B7 (aggregate expression
  shape preserved left-to-right), B11 (the 4-term entropy `np.sum` is numpy's
  naive sub-8 path), B12 (`np.minimum`/`np.clip` NaN propagation and tie
  semantics), NEP 50 (f32 grid-snap and argmax chains).

### R1h — physics discipline: N/A

This is a counting/entropy aggregate over already-computed coordinates and
rotation logits.  It encodes no physical constraint, feeds no solver, and
has no Chebyshev-style soundness obligation.
