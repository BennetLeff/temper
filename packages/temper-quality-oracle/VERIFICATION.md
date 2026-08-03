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
