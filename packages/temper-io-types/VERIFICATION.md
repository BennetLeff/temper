# Stackup validator — Verification

The stackup validator (`src/stackup_validator.rs`) is the Wave 4 Phase 4
leftovers slice's second migration: the `StackupValidationResult` /
`StackupValidationReport` pyclasses and the `validate_stackup` pyfunction,
ported from `temper_placer/manufacturing/stackup_validator.py` (the Python
module is now a pure-delegation re-export of the `temper_io_types`
pyclasses/functions). Home crate: `temper-io-types` — the validator
consumes the `LayerStackup` pyclass (the stackup primitives landed by the
Wave 4 Phase 3 parse-engine work, PR #723) as an opaque Python object
across the pyo3 boundary.

## Induction applicability

**Mathematical induction is not applicable to this module.** None of its
functions are recursive, and none iterate over a dimension whose
correctness depends on a size parameter:

- `check_copper_symmetry` / `check_copper_balance` iterate over the
  *fixed* set of stackup layers / fill entries; the per-element operation
  (weight × fill, max/min) is independent of the count and of the
  iteration order (verified by MR1 in `test_stackup_validator_pbt.py`).
- `check_return_path_adjacency` / `check_impedance_spec` are fixed branch
  tests over a constant argument surface.
- `neumaier_sum` is a bounded fold over the (≤ 4-layer) effective weights,
  not a size-parameterized recurrence whose correctness scales with n.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every public symbol, the pyclass /
pyfunction behaviour is bit-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/manufacturing/_stackup_validator_py_oracle.py`,
commit `6290942be`).

*Proof by structural cases.*

1. **Fill resolution.** The oracle's resolution chain is transcribed
   exactly: a truthy explicit dict wins (checked via CPython truthiness,
   so `{}` falls through); `routing_results is not None and board_dims is
   not None` invokes the Python call-back
   (`temper_placer.router_v6.copper_balance.analyze_copper_balance` stays
   Python — the KTD9 boundary) with the oracle's exact kwargs and builds
   the same `layer_name -> copper_percentage` dict; otherwise the
   `len(layers) == 4 and layers[0].name == "F.Cu"` default-estimate dict
   `{F.Cu: 35.0, In1.Cu: 95.0, In2.Cu: 95.0, B.Cu: 30.0}` is returned,
   else `{}`. The boundary reads `stackup.layers` / per-layer
   `name`/`copper_weight`/`layer_type` through Python attribute access on
   the SAME pyclass the oracle consumes, so the inputs are bit-identical
   by construction.

2. **Copper symmetry (R8).** Effective weight = `copper_weight * (pct/100)`
   transcribed verbatim (IEEE-754 double multiply is deterministic); the
   `total = sum(values)` uses `neumaier_sum` — a replica of CPython 3.12's
   compensated `sum()` (Neumaier with the compensation step skipped when
   `total + x` is non-finite), verified against CPython on 20,000 random
   finite arrays plus the inf/nan edge classes (0 mismatches). The
   imbalance formula `(max_eff - min_eff) / total`, the `0.25` threshold,
   the first-wins `max`/`min` (CPython's strict-comparison semantics —
   ties keep the earlier element; discriminated by the In1.Cu/In2.Cu tie
   case in the differential), and the argmax/argmin *name* selection all
   match. The warn message and `details` dict are byte/bit-identical
   (verified: `max_eff`/`min_eff`/`imbalance` float bits; `:.2`/`.1%`
   formatting verified identical to Python's on the module's value domain).

3. **Return-path adjacency (R9).** The `len(layers) >= 4` guard, the
   `layers[2].layer_type == "plane"` test (CPython's own `==` via
   `PyObject_RichCompareBool`, so a non-str `layer_type` compares False
   exactly as in Python), the stitching-vias suppression, and all three
   message strings match. The `layers[2]` index (not `layers[1]`) is
   discriminated by the mixed-type stackup case.

4. **Controlled impedance (R10).** The four branch tests (`empty nets`
   skip, `None` spec, `<= 0` invalid, `70..=120` pass, else out-of-range)
   match exactly; the `None`-spec message names the nets in `sorted()`
   order with CPython str-repr list rendering and the `{len}` count. The
   spec value in the messages is rendered from the ORIGINAL caller object
   via CPython's `str()` (`{90}` → "90", `{90.0}` → "90.0") — an int spec
   stays int in the message, exactly like the oracle's f-string. The
   branch comparisons use the extracted f64, so int and float specs take
   identical branches. The int-spec message parity is pinned by the
   differential matrix rows `impedance_spec_ohms=90` and `=-5` (added
   2026-08-05; RED before the fix: the f64 extraction rendered "90.0
   Omega"/"-5.0 Omega" where the oracle renders "90 Omega"/"-5 Omega").

5. **Copper balance (R11).** `min < 25 or max > 75` threshold, first-wins
   max/min over the dict values in insertion order, warn/pass messages and
   the `details` dict (`max_fill`/`min_fill` float bits) match.

6. **Report surface.** `all_passed` is the conjunction AND fails closed on
   an empty report (the oracle's anti-vacuity guard — `all()` over no
   results would be vacuously True); `warnings` returns exactly the
   non-passed results in order; `summary()` renders the `[PASS]`/`[WARN]`
   lines byte-identically.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `packages/temper-placer/tests/manufacturing/test_stackup_validator_rust_differential.py`
  (42 tests across a 22-case argument matrix; the RED state was
  demonstrated: the file fails to collect with
  `AttributeError: module 'temper_io_types' has no attribute
  'StackupValidationResult'` before the Rust landed). Includes the
  `routing_results` call-back arm (via a stub routing object), the two
  mutation-discriminating cases (tie-break, layer-index), and the two
  int-spec matrix rows (90, -5) added 2026-08-05 after an adversarial
  review found the int impedance messages diverged ("90.0 Omega" vs the
  oracle's "90 Omega").
- PBT (R1c): `test_stackup_validator_pbt.py` — 12 hypothesis properties
  (P1-P7 + MR1-MR4), each fail-capable.
- Metamorphic (R1d): `test_stackup_validator_pbt.py` — MR1 (fill-dict
  insertion-order permutation invariance), MR2 (impedance boundary
  closure), MR3 (differential-net set membership ⇒ identical sorted
  message), MR4 (default-fill equivalence: omitting the fill dict equals
  passing the Temper defaults explicitly).
- Anti-vacuity: 12 mutants, all caught by the differential/PBT suites:
  symmetry threshold `0.25→0.5`, balance min `25.0→30.0`, impedance range
  `70..=120→60..=120`, impedance invalid `<=0→<0`, all_passed empty-report
  flip, default fill `35.0→30.0`, `neumaier_sum→naive sum`, argmax
  first-wins→last-wins (caught by the tie case), adjacency index
  `2→1` (caught by the mixed-type case), adjacency `>=4→>4`, symmetry
  skip-arm removal, impedance message net-count off-by-one. **Re-verified
  2026-08-05 with an explicit revert verification** (each mutant applied to
  the Rust source, the rebuilt extension run against the suites, the
  failure confirmed, the source restored, and `git diff` confirmed EMPTY
  before the next mutant): 12/12 caught. Full log in
  `docs/evidence/2026-08-05-wave4-phase4-leftovers-adversarial-fixes.md`.
- Rust unit tests: `stackup_validator.rs::helper_tests` — the Neumaier
  replica against CPython's divergence classes, the repr helpers' B9/B10
  classes, and the first-wins max/min/argmax semantics.
- Rust practices (R1g): the `validate_stackup` boundary body is wrapped in
  `temper_py_bridge::catch_unwind` (panic → Python `RuntimeError`); no
  `unwrap`/`expect` outside tests; borrow-over-clone throughout;
  `cargo clippy --release` clean (0 warnings).
- Performance A/B (R1b): this is a validation surface with no compute
  kernel — the four checks are O(layers) constant-bounded passes over the
  stackup's four layers. Per the plan's R2 this is the **"no regression
  beyond noise"** comparison: the migrated validator calls back into the
  same Python `analyze_copper_balance` for the routing arm and performs
  the same bounded arithmetic otherwise; no speedup is claimed. (No
  `perf_ab` registration: the only consumers are the preflight pipeline
  hook and the tests, neither on a hot path.)
- R1h (physics discipline): NOT APPLICABLE. The stackup checks are
  advisory validation heuristics (warnings, not constraints): they encode
  no CP-SAT constraint gating a physics quantity, compute no quantity a
  post-solve audit could recompute from placement coordinates, and feed no
  solver. The R24 Chebyshev/BMC/post-solve obligations have no referent.

## Documented deviations (per R1, recorded here)

1. **Non-dict `copper_fill_percentages`.** The oracle's `fill_pct.get(...)`
   would `AttributeError` on a list/tuple fill value; the pyfunction raises
   `TypeError("copper fill percentages must be a dict")`. Different
   exception class, same failure class (the oracle is broken on such input;
   the differential drives dicts only).
2. **Non-float dict values.** A fill value that is not numeric raises a
   pyo3 `TypeError` from the f64 extraction where the oracle's arithmetic
   would raise a different-text `TypeError`. Not covered by the
   differential (the oracle itself fails there).
3. **`neumaier_sum` on a single value.** CPython's `sum` of a one-element
   iterable returns that element; the replica does too (the compensation
   stays 0.0). No divergence observed on any tested input; the replica is
   verified empirically rather than by source audit of CPython's fast
   paths.
