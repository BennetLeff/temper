# Wave 4 Phase 4 — regression slice: anti-vacuity mutation sweep — 2026-08-05

<!-- provenance: commit=dc603230b dirty=true; updated 2026-08-05 (pass 2) to add the kernel-only scope disclosure -->

**Base commit:** `dc603230b` (the TDD-GREEN commit — kernels + delegation
shims) + uncommitted working-tree changes (the VERIFICATION.md entries, the
ledger carve-out). `dirty=true` because this document is committed together
with the migration it verifies.

## Why this sweep exists

The R1 gate set requires anti-vacuity evidence for every migration: mutate
the Rust, confirm the differential **fails**, revert, and record every
mutation and what caught it. A differential never shown to fail is not
evidence. Landed migrations ran 6–11 mutants per module; two found surviving
mutants that were closed by adding discriminating cases.

## Method

For each mutant: apply a single behavior-changing edit to one Rust kernel in
`packages/temper-drc-rs/src/` or `packages/temper-design-bundle/src/`,
rebuild the owning extension (`uv run --no-sync maturin develop --release`),
run that module's differential/PBT suite from `packages/temper-placer`, and
record the result. A mutant is counted **caught** only when the suite
genuinely failed (pytest exit 1); a rebuild/infra failure (`BUILD_FAILED`,
`APPLY_FAILED`) is recorded as such and never counted as a kill. Every
mutant was reverted immediately after its test run, and the campaign ended
with a **PRISTINE rebuild of both extensions from the final clean sources**
(the `#766`/`#762` lesson — per-mutant revert alone leaves the last
mutant's `.so` installed). The driver is `/tmp/mutate_regression.py`.

## Results — 45 mutants across the seven kernels, all caught

### temper-drc-rs

| # | Kernel | Mutation | Suite | Result |
|---|---|---|---|---|
| drc_ratchet M1 | `ratchet_check` | removed the current-rules sort | drc_ratchet | **caught** (order-dependent messages) |
| drc_ratchet M2 | `ratchet_check` | `count > allowed` → `>=` | drc_ratchet | **caught** (implicit-zero boundary) |
| drc_ratchet M3 | `ratchet_check` | `error_delta > 0` → `>= 0` | drc_ratchet | **caught** (pass at zero delta) |
| drc_ratchet M4 | `ratchet_check` | fail predicate `\|\|` → `&&` | drc_ratchet | **caught** (aggregate masked per-type) |
| drc_ratchet M5 | `ratchet_check` | slack `> 0` → `>= 0` | drc_ratchet | **caught** (slack note text) |
| drc_ratchet M6 | `detect_ceiling_raise` | per-type violations loop dropped | drc_ratchet | **caught** (per-type raise undetected) |
| drc_ratchet M7 | `detect_ceiling_raise` | approval check inverted | drc_ratchet | **caught** (unapproved raise passes) |
| drc_ratchet M8 | `ratchet_check` | version note not trimmed on pass | drc_ratchet | **caught** (message text) |
| closure_test M1 | `closure_validate` | `<= 0` → `< 0` | closure_test | **caught** (zero iterations) |
| closure_test M2 | `closure_validate` | `<= 0.0` → `< 0.0` | closure_test | **caught** (zero pct) |
| closure_test M3 | `closure_validate` | `< 2` → `<= 2` | closure_test | **caught** (stages == 2) |
| closure_test M4 | `closure_validate` | zero-results `&&` → `\|\|` | closure_test | **caught** (half-zero runs) |
| closure_test M5 | `closure_summary` | PASS/FAIL inverted | closure_test | **caught** (Status line) |
| closure_test M6 | `closure_summary` | `:.1` → `:.2` | closure_test | **caught** (report text) |
| physics M1 | `compute_oracle_margins` | `- 1.0` → `+ 1.0` | physics_oracle | **caught** (margin value) |
| physics M2 | `compute_oracle_margins` | `*` → `/` | physics_oracle | **caught** (margin value) |
| physics M3 | `overall_score` | Neumaier branch disabled (plain `+=`) | physics_oracle | **caught** (last-bit divergence) |
| physics M4 | `overall_score` | empty → `1.0` | physics_oracle | **caught** (empty-input semantics) |
| physics M5 | `clearance_passed` | `>=` → `>` | physics_oracle | **caught** (threshold boundary) |
| physics M6 | `compute_oracle_margins` | missing-key default `1.0` → `0.0` | physics_oracle | **caught** (default semantics) |

### temper-design-bundle

| # | Kernel | Mutation | Suite | Result |
|---|---|---|---|---|
| measure M1 | `compute_drc_clearance_pass_pct` | `>= 4` → `> 4` | measure_closure | **caught** (stages boundary) |
| measure M2 | `compute_drc_clearance_pass_pct` | `== 0` → `<= 0` | measure_closure | **caught** (errors boundary) |
| measure M3 | `compute_drc_clearance_pass_pct` | `10.0` factor → `5.0` | measure_closure | **caught** (linear step) |
| measure M4 | `compute_drc_clearance_pass_pct` | clamp removed | measure_closure | **caught** (negative pct) |
| measure M5 | `compute_drc_clearance_pass_pct` | else branch `0.0` → `50.0` | measure_closure | **caught** (degraded stages) |
| measure M6 | `compute_drc_clearance_pass_pct` | full-pass `100.0` → `90.0` | measure_closure | **caught** (full-pass) |
| cp_sat M1 | `compare_metric_dicts` | `- 1e-9` epsilon dropped | cp_sat | **caught** (epsilon boundary) |
| cp_sat M2 | `compare_metric_dicts` | wirelength `<= 0.0` → `< 0.0` | cp_sat | **caught** (`-0.0` baseline) |
| cp_sat M2b | `compare_metric_dicts` | wirelength ratio inverted | cp_sat | **caught** (ratio detail) |
| cp_sat M3 | `compare_metric_dicts` | summary prefix changed | cp_sat | **caught** (summary text) |
| cp_sat M4 | `compare_metric_dicts` | failing list separator `, ` → `,` | cp_sat | **caught** (summary text) |
| cp_sat M5 | `compare_metric_dicts` | detail precision `:.4` → `:.2` | cp_sat | **caught** (detail text) |
| cp_sat M6 | `compare_metric_dicts` | bool render `True` → `true` | cp_sat | **caught** (detail text) |
| fingerprint M1 | `input_fingerprint` | seed/epochs update order swapped | fingerprint | **caught** (digest) |
| fingerprint M2 | `input_fingerprint` | missing-path contributes nothing | fingerprint | **caught** (digest) |
| fingerprint M3 | `source_fingerprint` | join `"\n"` → `","` | fingerprint | **caught** (digest) |
| fingerprint M4 | `should_skip` | empty-entry check disabled | fingerprint | **caught** (skip on empty entry) |
| fingerprint M5 | `should_skip` | `&&` → `\|\|` | fingerprint | **caught** (either-match skips) |
| fingerprint M6 | `input_fingerprint` | seed suffix dropped | fingerprint | **caught** (digest) |
| schema M1 | `validate_schema` | pass-1 unknown sweep disabled | schema_validator | **caught** (unknown field passes) |
| schema M2 | `validate_schema` | `value < min` → `<=` | schema_validator | **caught** (min boundary) |
| schema M3 | `validate_schema` | `value > max` → `>=` | schema_validator | **caught** (max boundary) |
| schema M4 | `validate_schema` | `== 0.0` → `!= 0.0` | schema_validator | **caught** (zero rule) |
| schema M5 | `validate_schema` | min check disabled | schema_validator | **caught** (below-min passes) |
| schema M6 | `validate_schema` | reason code `below_min` → `minimum_violated` | schema_validator | **caught** (message) |

**No surviving mutants.** Every mutation was caught by at least one
differential assertion; no discriminating-case additions were required.

## Scope — kernel-only (disclosed pass 2)

This sweep mutated ONLY the Rust kernels in `packages/temper-drc-rs/src/`
and `packages/temper-design-bundle/src/`. The Python-side shim marshalling
layer was deliberately NOT mutant-tested:

- `drc_ratchet.py`'s `_marshal` (the `int()` coercion boundary),
- `drc_ratchet.py`'s lazy `temper_drc_rs` import boundary,
- `fingerprint.py`'s cache-entry lookup and `_tdb()` boundary,
- the cp_sat/fingerprint delegation argument assembly.

The adversarial review (2026-08-05) proved this scope matters with a
concrete fail-open: **P1-1** — the shim's `int()` marshal truncated a
float-valued ceiling (`100.5` → `100`), making a raise invisible to
`detect_ceiling_raise` and failing the #575 approval gate OPEN. A
kernel-only sweep cannot see that class. It is now closed by fail-loudly
int-validation at the marshal boundary (the shim raises `CeilingMarshalError`
instead of truncating), and the `should_skip` null/non-dict entry class by
the kernel fix in `fingerprint.rs` — both landed in the same pass-2 review
round. Two kernel-boundary pins were also added because the sweep's mutant
set did not cover them: the cp_sat `str-number`/`bool` leaf class (pins
`py_builtin_float`; a mutant to `extract::<f64>()` fails on `'1.5'`) and the
drc_ratchet exact `'; '`-separator message (a `','` mutant fails).

## Notes

- The physics M3 mutant (Neumaier → plain `+=`) is the load-bearing one for
  the `overall_score` kernel: CPython 3.12's `sum()` is Neumaier-compensated
  (measured: plain accumulation diverges on 4640/20000 random inputs on this
  platform), so a naive Rust accumulation would pass a `sum()`-free review
  and still be a real kernel bug. The differential caught it.
- Two of the campaign's early harness bugs were TEST bugs (fixed before the
  sweep, not counted): the schema oracle-vs-shim exception-class mismatch
  (each arm's `SchemaValidationError` is a different class; the tests now
  catch `Exception` on each arm), and several assertion targets that were
  numerically wrong against the oracle's actual arithmetic (`0.2 * 6.5` is
  `1.2999999999999998`, the sorted path order normalizes argument order in
  `compute_input_fingerprint`, the below-min check precedes zero_is_valid in
  the oracle's check order).
- Every mutant was reverted; the campaign ended with a pristine rebuild of
  both extensions and a full `tests/regression/` run (256 passed) from the
  clean sources.
