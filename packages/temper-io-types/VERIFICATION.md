# Report + explainability formatting — Verification

The report and explainability formatting slice (`report/formatter.py`,
`report/generator.py`, `report/summary.py`,
`explainability/{trace,decision,logger,markdown_report,serialization,
traced_loss,pipeline}.py`) is the Wave 4 Phase 5 migration into the
`temper-io-types` crate (`src/report.rs`, `src/explain.rs`, `src/pyfmt.rs`).
The Python modules are delegation shims re-exporting the Rust compute; the
pre-migration implementations are pinned verbatim as the differential
oracles (`tests/report/_*_py_oracle.py`, `tests/explainability/
explain_oracle/`). The TDD-RED commit is `ba3d857dd` (reachable on this
branch; oracles + differential/PBT suites, demonstrated failing to collect
until the Rust surface landed).

## Candidate scorecard (what stays Python, and why)

| Kernel | Python origin | Verdict |
|---|---|---|
| `format_text` / `format_html` rendering | `formatter.py` | migrated (byte-identical text/HTML; `str(value)` and Rich's `generate_text_report` are called back / not reimplemented) |
| `format_json` data shape (dict insertion order, concrete leaf types) | `formatter.py` | migrated — **`json.dumps(json_data)` stays Python stdlib** per the Phase-3 PyYAML/json ruling: re-tokenising JSON in Rust would change behaviour while the differential stays green. The Rust side returns the JSON data with pinned key order and **raw pass-through leaf types** (the oracle copies `total_elapsed_ms` / `elapsed_ms` / location attrs into the dict unchanged, so an int leaf stays an int); the shim renders it. |
| `calculate_benchmark_result` scoring kernel | `generator.py` | migrated; `BenchmarkResult` dataclass construction stays Python |
| `generate_summary` / key-metric extraction | `summary.py` | migrated; `BenchmarkSummary` dataclass stays Python |
| `Trace.why` NL generation | `trace.py` | migrated |
| `DecisionTrace` why/why_not/history/summary | `decision.py` | migrated; `Decision`/`DecisionTrace`/`Alternative` dataclasses + Enum members stay Python (Enum member identity, uuid/datetime defaults) |
| logger `should_log` / `significant_change` / `log_*` decision construction | `logger.py` | migrated; the `DecisionLogger` class shell and its `uuid`/`datetime` defaults stay Python |
| markdown renderers | `markdown_report.py` | migrated |
| `_serialize_value` recursion + dict shapes | `serialization.py` | migrated; `json.dumps`/`datetime.fromisoformat` stay Python |
| constraint subject/because introspection + threshold gate | `traced_loss.py` | migrated; the `@traced`/`@log_traced_loss` decorators themselves stay Python (they wrap arbitrary Python callables — a Rust decorator cannot wrap a Python closure without re-entrant pyo3 handles), `float()` and `sum()` on the loss stay Python |
| `compose_traces` monoid fold | `pipeline.py` | migrated |
| `str(value)` of arbitrary Python objects | all modules | **stays Python** — called back across the boundary; CPython's `str` is a Python runtime semantic (the guide's "library semantics are not reimplementable") |
| set iteration order (`unique_subjects`) | `markdown_report.py` / `trace.py` | **stays Python** — hash-randomized per process; sorting to stabilise would be a behaviour change no differential could catch (the guide's iteration-order trap). The Rust consumes the Python-ordered list. |
| `strftime` / `datetime` arithmetic | `markdown_report.py`, `decision.py`, `serialization.py` | **stays Python** — `datetime` is a Python stdlib type; durations are computed Python-side from `datetime` objects |

## Induction applicability

**Mathematical induction is not applicable to this slice.** Every migrated
kernel is a finite transcription: the renderers are fixed templates over
caller-provided collections (per-element work independent of collection
size), `_serialize_value` recursion is bounded by the input structure's
depth (the value domain is closed: tuples/lists/dicts of scalars, `None`,
`float`/`int`/`bool`/`str` — a structural recursion, not a size-parameterized
one), and `compose_traces`' fold is order-preserving concatenation whose
correctness is asserted for every composition arity by the monoid laws.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every migrated symbol, the Rust
behaviour is bit-identical to the pinned pre-migration Python
implementation for every input in the differential suites' domains, with
the documented Python-side seams below.

*Proof by structural cases.* Each kernel is a direct transcription of the
oracle body; the load-bearing equivalences, each pinned by the differential
or by construction:

1. **Float formatting (the `pyfmt` seam).** Every `f"{x:.Nf}"` site in all
   three Python modules routes through `py_float_fmt_N`. Rust's
   `format!("{x:.prec$}")` is correctly-rounded round-half-even, agreeing
   with CPython's `float.__format__` on every finite value, but renders
   NaN/inf as `NaN`/`inf` where CPython writes lowercase `nan`/`inf`/`-inf`
   — special-cased in `pyfmt.rs`. The half-even boundary itself is pinned
   on **both** surfaces (report `half_even` fixture: 8.25→"8.2"; trace
   `(9.5, 8.25)` pin), and the mutation sweep's M1 mutant (round-half-up)
   is caught by both. The `:.0f`/`:.2f`/`:.3f`/`:.4f` variants are the same
   seam with different precision.
2. **Dict insertion order.** `format_json_data_impl` builds `PyDict`s in
   the exact `data = {...}` literal order of the oracle; `test_json_key_order_pinned`
   pins the top-level and per-check key order and the metrics dict's
   insertion order (`["z", "a"]` — deliberately *not* sorted).
3. **Raw leaf pass-through.** Counts (`total_checks`, `passed_checks`,
   `failed_checks`, `total_issues`, `issue_count`) are set as Python `int`s;
   measured quantities (`elapsed_ms`, `runtime_ms`, location `x`/`y`/`layer`)
   pass through **raw** — `format_json_data_impl` copies
   `result.total_elapsed_ms`, `check_result.elapsed_ms` and the location
   attributes into the JSON untouched, exactly as the oracle's dict literal
   does, so an int leaf stays an int (`5` vs `5.0` both occur and must both
   survive; `test_json_int_elapsed_leaf_type_pinned` closes the pre-fix
   float coercion). `_run_json_key` carries each leaf's concrete type into
   the comparison key, so `5` vs `5.0` cannot hide behind numeric equality
   (M2 caught this class).
4. **Python `%` modulo.** `should_log` uses `epoch % interval == 0` with
   CPython semantics for negative epochs (`py_mod`: result takes the sign
   of the divisor); the differential pins negative-epoch and boundary
   cases, and Rust's `%` (truncated) differs from Python's (floored) for
   negative operands — hence the explicit `py_mod`.
5. **IEEE sqrt.** `significant_change` uses `(dx²+dy²).sqrt()` → `f64::sqrt`
   (correctly-rounded IEEE — identical to `math.sqrt`, measured 0
   mismatches in the Wave-3 HV-LV precedent).
6. **NaN-order-sensitive `min`.** The benchmark fallback preserves
   CPython's `min()` argument-order semantics around NaN via `py_min`
   (Python's `min(a,b)` returns `a` unless `b < a`; `f64::min` would
   discard NaN).
7. **String-level seams stay Python.** `str(value)` of arbitrary objects
   and `datetime.strftime` are called back; the Rust receives already-
   formatted strings and embeds them. `unique_subjects` ordering comes from
   the Python-side set iteration.
8. **Monoid fold.** `compose_traces` is order-preserving concatenation of
   entry lists; the monoid laws (associativity, identity, order
   preservation) are asserted as metamorphic relations and the fold is
   differentially driven over N traces including the empty case.
9. **Indexable-any-sequence positions.** `significant_change`, the markdown
   final-positions renderer and the clearance validator reach position
   elements through Python `__getitem__` (`seq_index`), matching the
   oracles' `new[0]`/`old[1]`, `pos[0]` and `ox, oy = comp["position"]` /
   `dx, dy = p["offset"]` — a list-typed (or numpy-typed) position behaves
   exactly like a tuple (review P3-3; the differential pins feed list-typed
   positions and pad offsets through all three surfaces). Tuple-only sites
   exist only where the oracle itself is tuple-only (`Trace.why`'s
   `isinstance(final.value, tuple)` and `_serialize_value`'s
   `isinstance(value, tuple)`).
10. **Truncation negative-stop.** `_truncate`'s `text[:max_len - 3]` is a
    negative slice for `max_len < 3`; the Rust reproduces CPython's clamp
    (max_len=2 → `text[:-1]`, 1 → `text[:-2]`, 0 → `text[:-3]`, floored at
    "") rather than `saturating_sub`'s "..." alone (review P3-4;
    unit-pinned, unreachable from the 60/40/50 call sites).

## R24 determination — traced_loss.py and decision.py are NOT physics-gated

The dispatch brief asked for an R24 evaluation of `traced_loss.py` and
`decision.py` against `power_pcb_dataset/physics_soundness_register.yaml`
(KTD4 detection: AST reference to `thermal_fdm` / `heat_removal` /
`thermal_potential` / `ipc2152`, or an explicit `physics_gated: true`
marker).

**Determination: not physics-gated, no register entry.** Verified against
the pre-migration sources (the RED-commit oracle pins):
- neither module imports or AST-references any of the four physics
  modules (checked at `ba3d857dd` and at `origin/main`);
- neither module carries a `physics_gated: true` docstring marker;
- both are outside the register gate's scan set
  (`placer/cp_sat/handlers/*` register_handler encoders,
  `domain_clearance.generate_domain_clearance_constraints`,
  `router_v6/constraint_model.py` Constraint subclasses);
- the R24 discipline (Chebyshev-style soundness proof, BMC-exhaustive
  validation, post-solve audit) governs CP-SAT *constraint encoders that
  gate on physics quantities*; `traced_loss.py` and `decision.py` record
  and explain decisions after the fact — they constrain nothing.

`scripts/physics_soundness_register_gate.py` exits 0 on this branch
(the register and the scan set are consistent, with no gap).

## R1 gate status

| Gate | Status | Evidence |
|---|---|---|
| R1a behavioural A/B | PASS | 102 differential tests, bit-identical (strings byte-for-byte; floats via `float.hex()`; JSON via re-serialised `json.dumps` + concrete leaf types in the comparison key) |
| R1b no-regression arm | N/A, recorded | `pr_perf_compare` has **no benchmark rows for any Phase-5 surface** (its 11 arms are the Phase-2/3/4 kernels: board-netlist, bottleneck-geometry, config-loader, footprint-library, loaders, parse-engine, physics-*). These surfaces are report-time string builders invoked once per run — not hot loops — and their wall time is dominated by Python-side input marshalling, so a per-call A/B would measure the pyo3 boundary, not the kernel. The guide's Phase-4 warning ("a Rust kernel behind a per-call marshalling boundary can be net-negative") applies; no speedup claim is made. Adding harness rows is a follow-up if a caller of these surfaces ever becomes hot. |
| R1c ≥5 non-vacuous properties/module | PASS | see the per-module table below |
| R1d ≥3 MRs/module | PASS | see the per-module table below |
| R1e VERIFICATION.md | PASS | this file (structural proof; induction N/A, argued above) |
| R1f TDD | PASS | RED commit `ba3d857dd` — every differential fails to collect until the Rust surface lands (missing `temper_io_types.report_format_text` etc.); GREEN landed with the migration commits |
| R1g Rust practice | PASS | pyo3 boundaries wrapped in `temper_py_bridge_catch`/`catch` (`catch_unwind`), `?`-propagated `PyErr`, no `unwrap` outside `#[cfg(test)]`. The 7 `expect`s across `explain.rs` (4) and `req_safe_01.rs` (3) are each guarded by an immediately-preceding branch construction or early return: `filtered`/`decisions_vec` non-empty after an `is_empty()` early-return, `duration` present inside the `end_time`-derived branch, `best_pair` present when `best` is finite, and the two `owned_*` options assigned in the same match arm — an invariant violation would be a logic error caught by the differential before any production call |
| R1h R24 | N/A | determined not physics-gated above; no register entry required |

### R1c/R1d per module

Properties (R1c) and metamorphic relations (R1d) are counted across the
PBT and differential suites; every property has a vacuity guard (asserts
its fixture exercises it, G4-style).

| Module | Properties | Metamorphic relations |
|---|---|---|
| `report/formatter.py` | 5 (text band structure; JSON counts agree with input; UTF-8/escape validity; severity-line presence; runtime-line presence) | 3 (more issues ⇒ `total_issues` grows and text grows; JSON parse→fields round-trip stability; `json.dumps` re-parse of shim output is valid + shape-stable) |
| `report/generator.py` | 5 (scores in [0,1]; FAIL ⇒ violations non-empty; thermal score strictly monotone inverse; balanced weighted formula; wirelength-ratio status classification) | 3 (monotone-inverse thermal score over increasing penalty; status monotonicity FAIL→PASS as violations clear; formula agrees with hand-computed value) |
| `report/summary.py` | 5 (component/net/check counts in text; passed+failed == checks; empty result ⇒ zeros; key-metric extraction pins; runtime line) | 3 (counts consistent under growing inputs; empty placement/result ⇒ zeroed summary; per-check pass/fail split == input tally) |
| `explainability/trace.py` | 5 (why filters to subject; truncation is a prefix; final value wins; reason list order; empty-trace why) | 3 (monoid laws: associativity, identity, order preservation — the strongest form, since they hold for every trace triple) |
| `explainability/decision.py` | 7 (why shape; constraint refs appended; why_not list/tuple matching; loss at 4dp; history chronological subject filter; summary aggregation; duration none/after-finalize) | 3 (history order == insertion order per subject; summary aggregates == underlying decisions; why includes refs iff present) |
| `explainability/logger.py` | 5 (periodicity; boundary; negative-epoch modulo; zero-interval raises; significant-change commutativity + threshold boundary) | 3 (distance symmetry (a,b)↔(b,a); periodicity `should_log(e+i)==should_log(e)`; threshold monotonicity — exactly-at-threshold flips) |
| `explainability/markdown_report.py` | 6 (byte-identical render; header lines; duration line; value formatting; truncation pins; table indexing + ordered tables) | 3 (component report contains only subject decisions; 50-cap: 60 decisions ⇒ capped + "earlier decisions omitted" + last present; section order fixed) |
| `explainability/serialization.py` | 5 (dict shapes; `_serialize_value` recursion on nested tuples/lists/dicts; round-trip stability; ids/metrics preserved; leaf type pins) | 3 (serialize→deserialize→serialize idempotent; recursion mirrors input nesting; re-serialised dict shape == original) |
| `explainability/traced_loss.py` | 6 (subject/because introspection over 6 constraint shapes; threshold gate; float conversion accepts strings; non-float records raw; defaults; context mode) | 3 (threshold monotonicity — below/at/above gate; wrapper returns same loss value as undecorated callable; context enter/exit restores prior state) |
| `explainability/pipeline.py` | 5 (monoid associativity; identity/empty compose; order preservation; N-way compose; oracle equality on random trace lists) | 3 (the three monoid laws, per-module) |

## RED-test corrections

All corrections to the RED commit's tests were verified to fail
oracle-vs-oracle (i.e. the two arms agree and only the literal assertion
was wrong) before being made; see the migration commit messages:
- dropped the uuid `id`-equality assertion in `_assert_traces_equal`
  (uuid defaults are Python-side construction, per the scorecard);
- corrected the `8.25 -> 8.2` round-half-even pin (initially `8.25 ->
  8.3` — CPython's `float.__format__` is round-half-even);
- split the component-report indexing pins at the 50-cap boundary;
- corrected the nested-tuple dict expectation;
- raised the constraint-subject `loss_fn` above the 1e-6 threshold so the
  fixture actually exercises the gate (vacuity);
- pinned each arm's own `func.__name__` default.

## Mutation campaign

`docs/evidence/2026-08-05-wave4-phase5-mutation-sweep.md` records 13
mutants across the two home crates; all 13 were caught by the
differential/PBT suites, one (M1, the pyfmt rounding seam) only after the
report arm gained the `half_even` fixture — the gap it exposed, closed
rather than accepted.

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
  (44 tests collected — 21 test functions + the 21-case argument matrix
  of `test_validate_stackup_full_report_parity`; the RED state was
  demonstrated: the file fails to collect with
  `AttributeError: module 'temper_io_types' has no attribute
  'StackupValidationResult'` before the Rust landed). Includes the
  `routing_results` call-back arm (via a stub routing object), the two
  mutation-discriminating cases (tie-break, layer-index), and the two
  int-spec matrix rows (90, -5) added 2026-08-05 after an adversarial
  review found the int impedance messages diverged ("90.0 Omega" vs the
  oracle's "90 Omega"), and the two duplicate-layer-name cases
  (dict-collapse and last-wins-value) added 2026-08-05 after the same
  review found the Vec-push kernel doubled `total` on duplicate names.
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