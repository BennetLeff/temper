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
# DSN emitter — Verification

The SPECCTRA DSN emitter (`src/dsn_exporter.rs`, with the primitives in
`src/dsn_types.rs`) is Wave 4 Phase 3 candidate 6 of
`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`, ported from
`temper_placer/io/dsn_exporter.py` (559 LOC) and `temper_placer/io/dsn.py`
(131 LOC). Both Python modules are now pure-delegation shims; decision D6
("the DSN surface migrates onto the landed `temper-io-types` primitives and
`io/dsn.py`'s Python types retire") is what this entry closes.

Scope note on the candidate's measured 795 LOC: `io/dsn_schema.py` (39),
`io/dsn_validator.py` (49) and `io/dsn_normalizer.py` (17) were **already**
Rust delegation shims over the `temper-dsn` crate at `origin/main ebf9326ff`
— verified by reading the modules, not inferred. The remaining 690 LOC is what
moved here.

## R1h — state applicability

**N/A.** This is a serialization surface, not a physics-gated one: it reads a
`Board`/`Netlist` and emits text. No clearance, creepage, thermal, or
current-density margin is computed, asserted, or relied upon anywhere in the
module, so the R24 state gate has nothing to attach to.

## Induction applicability

**Mathematical induction is not applicable to this module.** Nothing here is
recursive over a size parameter whose correctness depends on that parameter:

- `dsn_expression_to_string` recurses over the expression *tree*, but the
  per-node rendering is a fixed concatenation independent of subtree depth and
  of sibling count; there is no size-parameterized invariant.
- `export_structure` / `export_library` / `export_placement` /
  `export_network` / `export_wiring` iterate caller-provided collections
  (layers, components, pins, nets, keepouts, traces). The per-element operation
  is independent of the collection's size. It is **not** independent of order
  — the emitter's whole determinism contract is an ordering contract — so
  order-independence is asserted where it holds (deterministic mode, distinct
  sort keys: E4/MR-family in `test_dsn_pbt.py`) and asserted against the oracle
  where it does not (non-deterministic mode, tied sort keys).
- `natural_sort_key` and `compute_center_offsets` are single linear passes.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (byte-identical parity).** For every public entry point, the Rust
emitter's output is byte-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/io/_dsn_exporter_py_oracle.py`
and `_dsn_py_oracle.py`, both pinned VERBATIM at `origin/main ebf9326ff`).

The claim is on **bytes**, not on structure. DSN output is a serialized
artifact: `io/dsn_schema.py` hashes the design into a `;schema-version:` header
that `io/dsn_validator.py` fails closed on, and `tests/io/test_dsn_kicad.py`
pins the emitted file as importable by KiCad's SPECCTRA importer. The
differential therefore asserts `str(rust) == str(python)` with no
normalization, and pairs it with a leaf-for-leaf structural assertion (floats
as `float.hex()`, every non-float leaf carrying its concrete `type`) so that an
int-vs-float drift cannot hide behind a rendering that trims `.0`.

*Proof by structural cases.*

1. **Numeric rendering.** Every coordinate reaches the output through one of
   two paths. Scaled-and-rounded coordinates go through `py_round_half_even`,
   which is CPython's `round(float)` — round-half-to-**even**, implemented as
   `f64::round_ties_even`. `f64::round` breaks ties **away from zero** and is
   therefore not a substitute; on a 5um design grid, exact `.5` ticks are
   common, so the naive port shifts geometry by one 10um unit routinely.
   Unrounded coordinates go through `format_dsn_arg`'s `{:.6}`-then-trim, which
   matches `f"{v:.6f}".rstrip("0").rstrip(".")`; both are correctly-rounded
   decimal conversions of the exact binary value.

2. **Float operation order.** The port preserves CPython's evaluation order
   where reassociation is observable: `-pad_width / 2 * S` is
   `((-pad_width) / 2) * S`, and `(min + max) / 2` is taken on the
   pad-inclusive bounding box after the half-extents. Reassociating the pad
   half-extent is bit-neutral for every *normal* f64 (verified numerically over
   2e5 samples) and differs only at subnormals — which is why the differential
   carries a subnormal pad width (`5e-324`), so the association order is pinned
   rather than merely believed.

3. **Ordering — the determinism contract.** Every sort is reproduced with its
   exact key and with `list.sort`'s **stability**:
   - keepouts sort on `str(k.args[0])`, a plain **string** sort, so `KO_10`
     precedes `KO_2`;
   - image pins sort **twice** — first on the natural key of the scaled X
     coordinate (`args[2]`), then, stably, on the natural key of the pin number
     (`args[1]`), so the X order survives as the tie-break;
   - `_natural_sort_key` splits on `(\d+)` and compares digit runs the way
     CPython compares `int()` of them: leading zeros insignificant, then
     numerically, and **unbounded** (Python's `int` has no width limit, so the
     port compares normalized digit strings by length-then-lexicographic rather
     than parsing into a fixed-width integer);
   - image/padstack/footprint-id sorts key on `py_lower`, a per-character
     lowercase. `str::to_lowercase` is NOT used: it applies the Greek
     final-sigma rule, which CPython's `str.lower()` does not, and the result
     is a sort key.

4. **Insertion order is pinned, not inherited.** `padstacks` and
   `components_by_fp` are Python `dict`s whose iteration order is insertion
   order by language guarantee, and the non-deterministic export path emits
   them in that order. `InsertionMap` reproduces it explicitly. A `HashMap`
   here would be the classic "ordering that happens to be stable today".

5. **Net classification.** The prefix list is transcribed verbatim. The
   voltage regex is `(?i)(_PLUS|VCC|VDD)\d+V?\d*\n?\z` — the `\n?\z` replaces
   Python's `$`, which (without `re.MULTILINE`) also matches immediately before
   a trailing newline whereas the `regex` crate's `$` is end-of-haystack only.
   `\d` is Unicode `Nd` on both sides.

6. **Truthiness.** Python truthiness is reproduced where it is load-bearing:
   an empty comment string emits **no** comment line (`if self.comment:`), an
   empty trace list emits **no** `(wiring)` section (`if traces:`), a falsy
   `layer_stackup` takes the two-layer fallback, and `pin.shape` being `""`
   falls through to `"rect"`.

7. **`bool` is not `int`.** At the pyo3 boundary a `PyBool` arm precedes the
   `PyInt` arm, because CPython's `bool` is an `int` subclass that
   `is_instance_of::<PyInt>()` accepts — the pinned Python falls through to
   `str(v)` and renders `True`, not `1`.

## Boundaries kept on the Python side (and why)

Applying PR #688's `yaml.safe_load` judgement: a kernel is kept across the
boundary when reimplementing it would be a *behaviour change* rather than a
port.

- **`np.argmax`** still derives rotation indices from a 2-D logits/one-hot
  array. Reimplementing it means re-deciding numpy's dtype promotion and
  tie-break on an array this crate cannot see without a numpy-interop
  dependency the phase plan explicitly declines to assume.
- **`pin_world_position`** still computes pad world geometry for the
  non-deterministic net ordering. It is the repo's SSOT for
  rotation-and-side-aware pad placement and it is `sin`/`cos` on `math.pi`;
  libm and Rust's intrinsics are not bit-identical across platforms for
  transcendentals, so porting it would inject a divergence into a *sort key*,
  where fixture differentials are least likely to catch it. The ordering logic
  built on those coordinates IS ported.
- **`compute_dsn_schema_hash`** is called, not reimplemented. It was already a
  Rust delegation shim (`temper-dsn`) before this migration, and
  `io/dsn_validator.py` fails closed on that hash — a second implementation
  would be exactly the drift the validator exists to catch.

## Documented deviations and bounds (per R1, recorded here)

1. **`DSNRect`/`DSNCircle`/`DSNPath` are pyclasses, not frozen dataclasses.**
   They are mutable, unhashable, compare by identity, no longer subclass
   `DSNShape`, and their `__repr__` differs. Measured consumers outside
   `io/dsn.py`: one test, which uses only `to_dsn()`.
2. **`DSNExpression.args` returns a fresh list** on each access rather than the
   stored sequence, so mutating the returned list does not mutate the
   expression.
3. **`DSNPoint` / `DSNShape` / `DSNPolygon` stay Python.** No Rust twin, and
   zero consumers repo-wide. Retiring them is an R8 residual decision.
4. **A short `positions` array now raises `IndexError` at construction**
   rather than at `export_placement`, because the shim materializes the array
   once. Same exception type and message (numpy's).
5. **`i64` coordinate bound.** `py_round_half_even` saturates where CPython's
   arbitrary-precision `int` would widen. A DSN coordinate is a board dimension
   in 10um units (reachable range ~1e6), so the bound is unreachable in
   practice; it is recorded rather than defended in code.
6. **Non-ASCII decimal digits in a natural-sort key.** Digit runs are compared
   as normalized digit strings, which is exact for ASCII. A run mixing scripts
   (e.g. Arabic-Indic digits) would compare by code point where CPython's
   `int()` compares by numeric value. Also unreached: CPython itself *raises*
   `ValueError` on a `str.isdigit()`-true-but-`\d`-false character such as `²`,
   which the port does not reproduce. Both are outside the generated input
   space by construction and named here rather than silently assumed away.
7. **NaN ordering** in the non-deterministic span sort falls back to
   `Ordering::Equal`; CPython's sort with NaN keys is itself
   implementation-defined. Not reachable from finite pad geometry.

## Evidence

- **R1a behavioral A/B** — `packages/temper-placer/tests/io/test_dsn_rust_differential.py`,
  42 tests: every section byte-compared against the pinned oracle plus a
  leaf-for-leaf structural compare; the shipped corpus (`power_pcb_dataset/corpus/`,
  both determinism modes) exported end to end; rounding-mode, natural-sort,
  lowercase-tie, quoting, shape/layer, footprint-separator, duplicate-ref,
  positions/rotations, and exclusion fixtures.
- **R1b performance A/B** — `benchmarks/perf_ab.py`, entry
  `("dsn-exporter", "export_pcb")`, wired to `scripts/pr_perf_compare.py`'s
  record shape and carrying an in-harness **byte**-parity assertion. Per R2
  this is the no-regression-beyond-noise arm; no speedup is claimed as the
  gate. The baseline row must be captured from CI (see the harness docstring on
  the measured ~11% darwin/linux platform bias), so the gate reports
  `NO_BASELINE` until it is.
- **R1c properties** — `packages/temper-placer/tests/io/test_dsn_pbt.py`:
  6 properties for `dsn_exporter` (E1-E6) and 6 for `dsn` (P1-P6), each with a
  G4 vacuity mutant asserting the property fails against a degenerate kernel.
- **R1d metamorphic relations** — MR1 (uniform pad translation absorbed by
  image self-centering, bounded to dyadic offsets), MR2 (sanitization
  idempotence, bounded to the emitted name), MR3 (keepout count monotonicity,
  bounded away from restating the sort), plus M1-M4 in the differential; a
  discriminating-check test proves the relations are breakable.
- **R1f TDD** — the differential was run before the extension carried the new
  class and failed to collect (`ImportError: cannot import name
  'DSNExporterCore' from 'temper_io_types'`); GREEN after the build.
- **R1g Rust practices** — no `unwrap`/`expect` outside tests and the two
  `#[expect]`-annotated literal-regex constructions; borrows preferred over
  clones on the hot path; every `#[pymethods]` body wrapped in `catch_unwind`
  at the boundary. `cargo clippy --all-features --all-targets -- -D warnings`
  clean.
- **Anti-vacuity** — 11 mutations applied to the Rust, rebuilt, and re-run;
  all 11 caught. Two initially survived (`(?i)` dropped from the voltage regex;
  the pad half-extent reassociated) and both were closed by *tightening the
  differential*, not by weakening the claim — the first needed a lower-case
  net name that no prefix rule already classifies, the second needed a
  subnormal pad width. See the PR body for the table.
# Verification: Wave-4 Phase 2 core contract layer

Scope: `src/placer_core/` — the Rust port of the placer's `core/`
CONTRACT layer (`Rect`, `PinInfo`, `PlacementViolation`, `FabPreset`,
plus the pure kernels of `units`, `net_classification`, `manufacturing`,
`placement_drc`, and `netlist.build_adjacency_matrix`).

This file carries the **R1e** obligation: a structural/inductive
soundness argument for each ported kernel, stating what is proved,
under what assumption, and where the assumption is checked. R1a (the
differential), R1b (perf), R1c (properties), R1d (metamorphic
relations) and the mutation corpus live in
`packages/temper-placer/tests/wave4_phase2/`.

---

## R1e-1 `net_classification`: the regex rewrite is a *language* identity

**Claim.** For every string `s` and every pattern `p` in the seven
declared sets, the Rust matcher accepts `s` iff CPython's
`re.search(rf"(?:^|_){re.escape(p)}(?:$|[\d_])", s.upper())` does.

**Proof (structural, on the position of a candidate match).**

Two rewrites separate the claim from the reference text.

1. `^` → `\A`. Without `re.MULTILINE`, CPython's `^` matches only at
   offset 0, which is `\A`'s definition. Identical, no assumption.

2. `$` → `\z`, with one trailing `\n` deleted from the haystack.
   CPython's `$` matches at exactly two positions: `len(s)`, and
   `len(s) - 1` when `s[-1] == '\n'`. Let `s'` be `s` with a single
   trailing `\n` removed if present.
   * If `s` has no trailing newline, `s' = s` and the two `$` positions
     collapse to one, `len(s) = len(s')`, which is `\z`. ∎
   * If `s` ends in `\n`, then `len(s') = len(s) - 1`, so `\z` on `s'`
     sits at the first `$` position; the second (`len(s)`) is
     unreachable for any pattern, because the character immediately
     before it is `\n`, and the only two things that can precede the
     tail alternation are the pattern's own final character (never `\n`
     — every pattern is ASCII alphanumeric, `+` or `-`) or a `[\d_]`
     match (`\n` is in neither class). ∎

   The deletion cannot destroy a match either: the only characters it
   removes is the final `\n`, which no pattern contains and no `[\d_]`
   accepts.

**Assumptions, and where they are checked.**
* *Every pattern is non-empty and ASCII* — checked by
  `netclass::tests::patterns_are_ascii_and_non_empty`, which fails at
  build time if a future pattern breaks it. (The emptiness case matters:
  the reference's guard is `if p and not p[-1].isalnum()`, so an empty
  pattern takes the *trailing-boundary* branch, not the leading-anchor
  one, and the two branches are **not** equivalent there. `pattern_source`
  reproduces that.)
* *`regex::escape` and `re.escape` describe the same language* — both
  escape a superset of the regex metacharacters and neither changes what
  the pattern matches. Only six patterns contain a metacharacter
  (`+3V3`, `+5V`, `+12V`, `+15V`, `DC_BUS+`, `DC_BUS-`), and all six are
  in the differential corpus.
* *`str.upper()` agrees between CPython and Rust* — both implement the
  full Unicode uppercase mapping including the length-changing cases.
  Checked on `ß` (→ `SS`) and `ı` (→ `I`) in
  `netclass::tests::unicode_case_folding` and across the differential's
  Unicode corpus. **Not proved in general**: see "Not verified" below.

**Order invariance.** `matches_any` is `Iterator::any` over the pattern
list, i.e. a disjunction with early exit. The value of a disjunction is
independent of evaluation order, so the reference's `frozenset`
iteration — whose order is `PYTHONHASHSEED`-dependent for `str` — cannot
change the answer. Not asserted, *measured*:
`test_witness_frozenset_iteration_order_is_hash_seed_dependent` runs the
reference under eight hash seeds, asserts the observed order really does
move (otherwise the test proves nothing) and that the classification
does not. The order is left alone; it is deliberately **not** sorted.

---

## R1e-2 `build_adjacency_matrix`: the update multiset is a permutation invariant

**Claim.** The matrix is independent of the order of each net's pin
list, so the reference's `list(set(...))` — a hash-ordered sequence —
is deterministic despite appearances, and the Rust port's
first-occurrence order produces the same bits.

**Proof (induction on the number of nets).**

*Base.* Zero nets: both produce the all-zero `(n, n)` matrix.

*Step.* Assume the matrices agree after `k` nets. Net `k+1` contributes,
in both implementations, the set `S` of distinct in-range component
indices on that net (the reference by `set()`, the port by a `seen`
bitmap; both compute the same set, since both keep exactly the indices
that occur at least once). Both then enumerate ordered pairs `(a, b)`
with `a` before `b` in *their own* sequence order, and for each perform
two updates: `+= 1` at `(a, b)` and `+= 1` at `(b, a)`.

For any linear order on `S`, the enumeration `a < b` visits each
*unordered* pair `{i, j} ⊆ S, i ≠ j` exactly once. The two updates it
performs are `(i, j)` and `(j, i)` — a set that does not depend on which
of `i`, `j` came first. So the **multiset** of `(cell, +1)` updates
contributed by net `k+1` is `{ (i,j), (j,i) : {i,j} ⊆ S }`, identical
under any order. Distinct cells accumulate independently, and `f32`
addition on a single cell is applied the same number of times, so the
final bits agree. ∎

**Why `f32` and not a `u32` count.** The proof gives equality of the
*number* of `+= 1` applications, not of the value; `f32 += 1.0` stops
advancing at 2^24, so a `u32` count converted once would diverge above
that. Accumulating in `f32`, as the reference's `np.float32` array does,
makes the values agree by construction. Pinned by
`adjacency::tests::f32_accumulation_saturates_exactly_like_numpy`.

**Last-wins on duplicate refs.** `ref_to_idx` is a dict comprehension,
so a repeated `ref` maps to its final index. `HashMap::insert` in
enumeration order reproduces this. Pinned by
`duplicate_component_refs_resolve_to_the_last_index`.

**Empty netlist.** Deliberately *not* in Rust: `np.array([]).reshape(0, 0)`
is **float64**, unlike the float32 the populated branch returns. The
shim keeps that branch so the dtype contract survives; the differential
asserts it (`test_empty_netlist_dtype_is_float64_not_float32`).

---

## R1e-3 `validate_placement_drc`: the scan is a total function of unordered pairs

**Claim.** The port emits the same violations, in the same order, with
the same messages, and re-attaches the caller's own pin objects.

**Argument (structural).** The reference is a double loop over
`i < j` with no state carried between iterations other than the append
order. The port keeps the identical loop bounds and the identical
`continue` structure, so the emitted sequence is the same subsequence of
the same enumeration. Three float facts make the values bit-exact:

* `radius = diameter_mm / 2.0` — division by a power of two is exact for
  every finite input, and for infinities and NaN it is the identity/NaN.
  Never a rounding, so no libm involvement.
* `dist = sqrt(dx*dx + dy*dy)` — `sqrt` is required by IEEE-754 to be
  correctly rounded, so it is bit-identical to `math.sqrt` on any
  conforming libm; the two multiplies and the add are each single
  correctly-rounded operations in the same order. This is why `sqrt`
  does *not* need `temper-thermal`'s `dlsym` treatment while `exp`/`pow`
  do. Note the reference writes `dx * dx`, not `dx ** 2` — the latter is
  libm `pow` and is *not* reproducible by a multiply.
* the comparisons are `<` on raw `f64`, so a NaN operand makes every
  branch false and the pair yields nothing. Pinned as a witness
  (`nan_coordinate_yields_no_violation_witness`), not "fixed".

**Message formatting.** `f"{x:.3f}"` is `format_fixed`, not Rust's
`{:.3}`: they agree on the digits (both correctly rounded, ties to even)
but disagree on the non-finites (`nan`/`inf` vs `NaN`/`inf`). The
differential includes NaN and infinite coordinates, diameters and
clearances for exactly this reason.

**Object identity.** The pure kernel returns *indices*; the pyo3
boundary re-attaches `pins[i]`, so `violation.item_a is pins[i]` holds
as it did when the reference stored the objects directly. Checked by
`test_placement_drc_returns_the_callers_own_pin_objects`.

---

## R1e-4 `Rect`: the invariant is established at construction and never re-broken

**Claim.** Every reachable `Rect` satisfies `x_max > x_min` and
`y_max > y_min`, and every Python-visible operation reproduces the
frozen dataclass exactly.

**Argument (by construction + immutability).** There is exactly one
constructor path (`#[new]`), and it performs the two `__post_init__`
checks *before* the struct is built, at **Python** comparison level, so
the check is exact for large integers and honours any operand's own
`__gt__`. `from_xyxy`, `from_xywh` and `coerce` all funnel through
`cls(...)` (`coerce` via `cls.from_xyxy`, so a subclass override is
honoured as in the reference). The four fields have no setter and
`__setattr__`/`__delattr__` raise `dataclasses.FrozenInstanceError`, so
no reachable operation can invalidate the invariant afterwards. ∎

**Why the fields hold Python objects.** The reference does **no**
coercion in `__init__` — only `from_xyxy`/`from_xywh` call `float()`. So
`Rect(1, 2, 3, 4).x_min` is the `int` `1` and `.width` is the `int` `2`.
Storing `f64` would change both the value's type and the `repr`. The
struct therefore carries the four originals plus an `f64` view
(`PyRect::data`) for Rust consumers; the `f64` view is lossy above 2^53
and no Python-visible path reads it.

**Pickling — a regression this file initially missed.** A pyclass is
unpicklable by default and the dataclass was not, so `pickle.dumps(board)`
and `copy.deepcopy(zone)` both failed with `TypeError: cannot pickle
'temper_io_types.Rect' object` — reached through `Zone.bounds`. All four
contract types now implement `__reduce__` as `(type(self), (fields…))`,
which reconstructs through `type(self)` so a subclass stays a subclass,
re-runs the invariant check, and preserves field types exactly (an `int`
`Rect` round-trips as `int`). Covered by
`test_rect_survives_pickle_copy_and_deepcopy`,
`test_zone_and_board_survive_pickle_and_deepcopy`,
`test_contract_objects_survive_pickle_and_deepcopy` and
`test_rect_subclassing_still_works`, and by mutants M36–M39.

This is worth recording as a process point, not just a bug: the first
differential was green across 941 assertions while `pickle` was broken,
because nothing in it pickled anything. Behavioural coverage is only as
wide as the operations you think to perform.

**The one measured API delta.** `dataclasses.is_dataclass(Rect)` was
`True`, is now `False`. The visible consequence is that `asdict()` on a
dataclass *containing* a `Rect` no longer recurses into it — it
deep-copies the `Rect` instead of flattening it:

```text
before:  {'bounds': {'x_min': 0.0, 'y_min': 0.0, 'x_max': 1.0, 'y_max': 1.0}}
after:   {'bounds': Rect(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0)}
```

Grepped: the repo has four `asdict` call sites (`metrics/physics.py`,
`pipeline/dag_observability.py`, `testing/quarantine.py`,
`validation/results/battery_run.py`) and none is reachable from a
`Rect`. Both shapes are pinned by
`test_rect_is_no_longer_a_dataclass_and_asdict_changes_shape`.

---

## R1e-5 `units`: R24 physical-quantity discipline

Every function here converts or compares a **physical quantity**
(degrees, radians, millimetres, grid cells), so R24 applies.

**Conservative-bound classification.** None of these is an
approximation of a physical model; each is an exact unit conversion, so
the R24 requirement is not "the bound is conservative" but "the
conversion is the *same* conversion". The soundness statement is
therefore an identity, not an inequality, and it is discharged by
bit-exact agreement rather than by an error bound.

**Associativity is the whole content of the claim.** `deg_to_rad` is
`(x * π) / 180`, **not** `x * (π/180)`. Measured on this repo's
interpreter over 200 007 samples: the two disagree on **59 113**
(29.6 %), and `np.radians`/`math.radians` disagree with the reference on
the same 59 113. `rad_to_deg` = `(x * 180) / π` disagrees with
`np.degrees`/`to_degrees` on 51 688 / 200 000 (25.8 %). `to_radians()`
would have been a silent 1-ulp regression on a third of all inputs.
`std::f64::consts::PI` is bit-identical to `np.pi` (`0x1.921fb54442d18p+1`),
asserted in `units::tests::pi_constant_matches_numpy`.

**BMC-exhaustive validation on small N.** `is_valid_layer` and
`is_valid_net_id` are total predicates over a small integer domain; the
differential enumerates `layer ∈ {-2, -1, 0, 1, 2, 3, 4, 5, 7, ±2^31,
2^53, 2^63}` against `max_layers ∈ {0, 1, 4, 8}` — every branch, both
outcomes, plus the unbounded-integer case that an `i64` extraction
cannot represent.

**Post-conversion audit.** `test_p7_mm_to_cell_agrees_and_truncates_toward_zero`
recomputes the quotient in Python and asserts the returned cell index
satisfies `|cell| <= |mm / size|` and `cell == int(mm / size)` — the
audit-after-the-fact that R24 asks for.

**Scope caveat (measured, not assumed).** Only the scalar path is in
Rust. `deg_to_rad`/`rad_to_deg` are annotated `float | Array`, and NEP 50
makes the array result dtype depend on the input dtype — a float32 array
stays float32 and is *computed* in float32 (measured:
`int32 -> float64`, `int64 -> float64`, `float32 -> float32`,
`float64 -> float64`). The shim routes non-scalars to the original,
untouched numpy expression. The scalar test is exact type identity, not
`isinstance`: `np.float64` **is** a subclass of `float`, and using
`isinstance` silently downgraded `np.float64` results to plain `float`
until the differential caught it.

---

## R1e-6 `manufacturing`: CPython's `max` is not `f64::max`

`inflated_clearance` is `max(0.0, nominal - tolerance)` with CPython's
*builtin* two-argument `max`, which keeps its left operand unless the
right compares strictly greater. Measured:

| call | CPython builtin | `f64::max` |
|------|-----------------|------------|
| `max(0.0, nan)`  | `0.0`  | `0.0`  |
| `max(nan, 0.0)`  | `nan`  | `0.0`  |
| `max(0.0, -0.0)` | `0.0`  | `0.0`  |
| `max(-0.0, 0.0)` | `-0.0` | `0.0`  |

With the constant `0.0` on the left the two agree *today*, so writing
`f64::max` would have passed the differential and left a landmine for the
first refactor that swaps the operands. `cpython_max2` spells the
semantics out instead, and `cpython_max_nan_is_left_biased` pins the
disagreement so the distinction cannot be optimised away later.

---

## Anti-vacuity: the mutation corpus

36 source mutants were applied to `src/placer_core/`, one at a time,
each followed by a full rebuild and a full gate run
(`cargo test --lib` + `pytest tests/wave4_phase2/`), then reverted. The
driver was a throwaway script (apply literal `(file, old, new)` edits;
rebuild; gate; revert) run outside the repo, so the durable record is
this section: every mutant is listed below by the exact behaviour it
reverts, which is enough to reconstruct the corpus.

**37 / 40 killed** (36 in the main corpus + 4 added for the `__reduce__`
path once pickling was fixed). The 3 survivors are each accounted for
below; none was closed by weakening a claim.

The four `__reduce__` mutants (M36–M39) all started as survivors and all
four were closed by new discriminating tests: reconstructing through the
concrete class instead of `type(self)` (needed a subclass `copy` test);
coercing the fields to `float`; swapping `PinInfo.x`/`.y`; and dropping
`FabPreset.drill_tolerance_mm` — the last of which survived because all
three named presets leave that field at its default, so the corpus now
includes a preset with every field non-default.

The first run used a pytest-only gate and reported 5 survivors. Two of
them (`M12` "cpython_max2 becomes f64::max" and `M11` "precedence: power
before ground") revealed real gaps rather than real equivalences:

* **M12** was killed by a Rust unit test that the pytest-only gate never
  ran. The gate was wrong, not the mutant — `cargo test --lib` is part
  of the R1 gate set and is now part of the mutation gate too.
* **M11** was a genuine coverage hole: the differential's name corpus
  contained no net name matching *two* pattern sets, so the precedence
  order (ground > power > hv) was never exercised. Ten such names
  (`GND_VCC`, `VCC_AC_L`, `AGND_VDD`, …) were added, plus
  `test_net_classification_corpus_is_not_degenerate`, which now fails if
  the corpus ever loses that property again. M11 is killed.
* **M24** (repr exponent threshold 16 → 17) was a second coverage hole:
  `pyrepr::repr_f64` is reached only through the Rust-built
  `__repr__`s, and no test had put a large-magnitude float into one.
  `test_contract_object_reprs_render_floats_exactly_like_cpython` now
  pushes every `EDGE_FLOAT` through `PinInfo` and `FabPreset`, and
  `test_placement_violation_repr_renders_extreme_floats` through
  `PlacementViolation`. M24 is killed.

### Survivors, with proofs

| mutant | verdict | evidence |
|--------|---------|----------|
| **M18** `radius`: `d / 2.0` → `d * 0.5` | **proved equivalent** | `2.0` and `0.5` are exact powers of two, so both spellings request the correctly-rounded `f64` nearest to the same exact real `d/2` — one rounding each, same result, including subnormals and non-finites. `placement_drc::tests::halving_is_exact_either_way` checks bit equality over every binade (`2^-1074 … 2^1023`, ±, ×1.5) plus 40 000 pseudo-random probes. |
| **M23b** `data[i] += 1.0` → `(data[i] as f64 + 1.0) as f32` | **proved equivalent** | For `x < 2^24` the `f64` sum is exact and the single `as f32` rounding is exactly what `f32` addition does. For `x >= 2^24` both yield `x`. No double-rounding window exists because the addend is exactly 1 and `f64` carries 53 bits against `f32`'s 24. |
| **M23c** count in `u32`, convert once at the end | **proved equivalent over the reachable domain** | The two agree for every cell whose final count is `< 2^24`; the first divergent count is `2^24 + 2 = 16 777 218` (`2^24 + 1` is a tie that `u32 as f32` also resolves down). Reaching it needs one *component pair* to co-occur on 16.7 M nets. The Temper board has **684 nets and 169 footprints** (measured from `pcb/temper.kicad_pcb`), ~4.5 orders of magnitude short, and a differential cannot construct the input — 16.7 M pin lists do not fit in memory. Boundary pinned in `adjacency::tests::f32_accumulation_saturates_exactly_like_numpy`. **This is a bounded claim, not an unconditional one.** |

Two mutants from the first run were withdrawn as invalid rather than
counted: an early `M23` added an unused `counts` vector (a no-op edit,
so "surviving" meant nothing) and was replaced by M23b/M23c above.

### What the corpus covers

Every trap this port is built around has a mutant that reverts it:
the `(x*π)/180` associativity (M01/M02), the fused multiply-add (M03),
Python's `$` before a trailing newline (M06), the leading/trailing regex
anchors (M07/M08/M09), case folding (M10), classifier precedence (M11),
CPython's left-biased `max` (M12/M13), the `<` vs `<=` DRC thresholds
(M15), `.3f` formatting (M16/M27), the SHORT-shadows-CLEARANCE control
flow (M17/M19), adjacency symmetry (M20), per-net dedup (M21), dict
last-wins (M22), the `repr` fixed/exponential threshold (M24/M28), the
`nan` spelling (M25), signed zero (M26), the `Rect` invariant (M29),
`coerce`-by-identity (M30), `isinstance`-vs-exact-type on `np.float64`
(M31), unhashability (M32), division by zero (M33), `float()`-vs-pyo3
coercion (M34), and `Rect` storing `f64` instead of the original objects
(M35).

---

## Not verified — read this before trusting anything above

* **Linux.** Every measurement in this file and in the test suite was
  taken on macOS/arm64 (Darwin 25.5.0, CPython 3.12.13, numpy 2.3.5).
  Nothing here was run on Linux. The kernels avoid the libm-sensitive
  operations (`exp`, `pow`, transcendentals) — only `sqrt` is used, and
  it is IEEE-mandated correctly-rounded — so there is no *known* source
  of cross-platform divergence, but that is an argument, not a
  measurement. Treat CI as the first Linux data point.
* **`str.upper()` in general.** Agreement between CPython's and Rust's
  full Unicode uppercase mappings is checked on a corpus, not proved.
  A locale-independent full mapping is specified by Unicode and both
  claim to implement it, but the two may track different Unicode
  versions.
* **`repr()` of a float across CPython versions.** `pyrepr::repr_f64`
  reimplements `format_float_short`'s decpt thresholds; those are stable
  CPython behaviour but are not a language guarantee.
* **`np.linalg.eigh`** (`compute_eigenvector_centrality`) is *not*
  ported and no parity is claimed for it — it is the host LAPACK, and
  bit-exactness would require linking the same LAPACK build.

---

# Placer non-cp_sat compute — Verification

The placer non-`cp_sat` compute slice (`placer/adjustment.py`,
`placer/deterministic.py`, `placer/template.py`; `placer/__init__.py`
stays untouched) is the Wave 4 **Phase 4** migration into the
`temper-io-types/placer_core` crate (`src/placer_compute.rs`, exposed
through the `placer_*` pyfunctions in `src/placer_core/pybridge.rs`).
The three Python modules are delegation shims; the pre-migration
implementations are pinned verbatim as the differential oracles
(`tests/placer/_placer_adjustment_py_oracle.py`,
`_placer_deterministic_py_oracle.py`, `_placer_template_py_oracle.py`,
each re-pinned from commit `17553437d` and registered in
`scripts/oracle_hashes.json`). The TDD-RED commit is `9d9e0197f`
(rebased from `ff156e1f3` onto current `origin/main`; oracles + differential
suites, demonstrated failing to collect until the Rust surface landed).

## Home-crate decision

`temper-io-types/placer_core` — the same home as #724's
`pybridge`/`pyrepr` and the Wave-4 Phase-2 contract layer. The kernels
consume nothing from `temper-design-bundle`; their Python-facing seams
(transcendentals, numpy `sqrt`/`**2`, `np.random.uniform`) are passed in
as callbacks, so no crate dependency on a Python-typed bundle is needed.
`placer_compute.rs` compiles for `wasm32-unknown-unknown` with no pyo3
dependency (the `#[cfg(feature = "python")]` pybridge is the only
Python-touching boundary), mirroring the crate's other kernels.

## Candidate scorecard (what stays Python, and why)

| Kernel | Python origin | Verdict |
|---|---|---|
| `ComponentTemplate.apply` geometry | `template.py` | migrated (`placer_apply_component_template`) |
| `ParametricTemplate.apply` geometry | `template.py` | migrated (`placer_apply_parametric_template`) |
| `place_power_stage_template` compute (zone-center template application + mapping loop) | `deterministic.py` | migrated (`placer_place_power_stage_template`) |
| `place_by_proximity` spiral (the #763 fix) | `deterministic.py` | migrated (`placer_place_by_proximity`) |
| `place_in_zone_center` grid distribution | `deterministic.py` | migrated (`placer_place_in_zone_center`) |
| `adjust_for_congestion` push loop (dtype-aware) | `adjustment.py` | migrated (`placer_adjust_for_congestion`) |
| template dataclasses + `create_*` data constructors | `template.py` | **stays Python** — data containers, not compute |
| `load_template_from_yaml` | `template.py` | **stays Python** — `yaml.safe_load` is a Python library seam (the Phase-3 PyYAML ruling) |
| `PlacementResult` dataclass | `deterministic.py` | **stays Python** |
| zone/netlist/bottleneck object navigation (`.zones`, `.bounds`, `.components[].ref/.fixed`, `n_components`, `bottleneck.overflow`, `bottleneck.to_coordinates(...)`) | all three | **stays Python** |
| `math.cos`/`math.sin` (template rotation, spiral angle) | all three | **stays Python, called back** — CPython's libm bits are the oracle's; Rust `f64::sin` is 1-ULP-divergent on this platform (measured 461/200k, 2026-08-05) |
| `np.sqrt(dx**2 + dy**2)` (numpy `**2` is libm `pow`, not `x*x`; numpy float32 `sqrt` is correctly-rounded f32) | `adjustment.py` | **stays Python, called back** (`dist` seam) |
| `np.random.uniform(0, 2*pi)` (the global numpy RNG, drawn in the oracle's iteration order) | `adjustment.py` | **stays Python, called back** (`uniform` seam) |
| `np.cos`/`np.sin` of the random push angle | `adjustment.py` | **stays Python, called back** |
| `math.radians` (`x*(pi/180)` ratio form) | `template.py` | reproduced in the kernel as `(r as f64) * (PI/180.0)` — bit-identical (both are the correctly-rounded double product of the same π double and 180.0) |
| Python `%` (floored) composite rotation | all | reproduced via `py_mod` |
| CPython `min`/`max` first-arg-on-tie + NaN semantics | `deterministic.py` | reproduced via `py_min`/`py_max` |

## Induction applicability

**Mathematical induction is not applicable to this slice.** Every migrated
kernel is a bounded transcription over caller-provided collections: the
per-component template/parametric geometry is a fixed per-element
transform independent of collection size; the spiral and grid loops apply
a per-element formula; the congestion push loop is a doubly-bounded
per-(bottleneck, component) pass whose per-element operation is independent
of the counts. Nothing recurses over a size-parameterized structure whose
correctness scales with n.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every migrated entry point, the Rust
kernel is bit-identical to the pinned pre-migration Python implementation
for every input in the differential suites' domains, with the documented
Python-side seams below (whose bits are preserved by construction because
the kernel calls back into the oracle's own library calls).

*Proof by structural cases.*

1. **Template rotation (R(-θ), the `if rotation != 0` bypass).** The
   oracle computes `rot_rad = math.radians(rotation)`, then
   `rotate_local_to_world(rel_x, rel_y, rot_rad)` = `(x*c + y*s, -x*s +
   y*c)` with `c, s = math.cos(rot_rad), math.sin(rot_rad)`, but **only**
   when `rotation != 0` (otherwise the rel offsets pass through). The
   kernel transcribes the same: `rotation_radians` is the ratio-form
   product (bit-identical to `math.radians`), the trig seam returns the
   oracle's libm bits, the formula and evaluation order match, and the
   `rotation != 0` bypass is preserved — pinned by the signed-zero test
   (`test_component_template_zero_rotation_signed_zero_pins_bypass`: at
   rotation=0 a `-0.0` rel offset must survive as `-0.0`, which an
   always-rotate kernel would turn into `+0.0`). `abs_rotation = (rotation
   + comp.rotation) % 360` is Python's floored modulo, reproduced by
   `py_mod` (negative composite rotations covered in the kernel tests and
   P3).
2. **Parametric scaling.** `rel_x = comp.x_ratio * target_width -
   anchor_off_x` where `anchor_off_x` is `anchor.x_ratio * target_width`
   or, for the missing-anchor fallback, `0.5 * target_width` — same
   products, same subtraction order. The anchor's own rel offset is
   `arx*w - arx*w == 0.0` bit-exactly (a value minus itself), so the
   anchor lands exactly at `(anchor_x, anchor_y)` for every dimension pair
   (MR3).
3. **`place_power_stage_template` mapping.** The oracle builds
   `placements = template.apply(zone_center_x, zone_center_y, rotation=0)`
   (a last-wins dict), `ref_to_idx = {comp.ref: i ...}` (last-wins on
   duplicate netlist refs), then iterates the netlist in order, placing
   each template-matched ref at its last index and appending to
   `placed_refs` per occurrence. The kernel reproduces both last-wins
   maps (`placements_by_ref` on the template side, `ref_to_idx` on the
   netlist side) and the same iteration order — pinned by
   `test_place_power_stage_template_duplicate_refs_last_wins` and the
   kernel test `power_stage_duplicate_template_ref_last_geometry_wins`.
   The `np.array(initial_positions, dtype=np.float32)` cast stays in the
   shim; the kernel receives the f32-widened values and reconstructs the
   exact f32 bits (`initial_float64_cast` differential pins the cast).
   `rotations[idx] = rot` and `positions[idx] = [x, y]` are f64→f32
   stores, transcribed as `as f32`.
4. **`place_by_proximity` spiral (the #763 fix).** `angle_step =
   2*math.pi / max(len(refs), 4)` (int max; `2*math.pi` and the division
   are single correctly-rounded doubles, identical in the kernel);
   `angle = i * angle_step`; `distance = 8.0 + (i // 4) * 3.0`; `x =
   base_x + distance * cos(angle)` (trig seam); zone clamp `max(b0,
   min(b2, x))` via `py_max`/`py_min` (first-arg-on-tie = CPython's
   semantics). The #763 contract — the spiral runs at function level
   regardless of `zone_name` — is preserved by construction (the loop
   never sits inside the `zone` branch) and pinned by the no-zone arms
   (`test_place_by_proximity_no_zone`: `"C1" in placed_refs`). The
   oracle's `max_distance` branch is a literal no-op (`if distance >
   max_distance: pass`); the differential drives `max_distance` across
   values and asserts the shim is invariant, pinning the dead parameter.
5. **`place_in_zone_center` grid.** `grid_size = ceil(sqrt(len))` is
   IEEE correctly-rounded sqrt/ceil (bit-identical to `math.sqrt`/
   `math.ceil`); `x = center_x + (col - grid_size/2) * spacing` with
   `spacing = 8.0`; zone clamp via `py_max`/`py_min`. The refs→indices
   `None` for unknown refs lands them in `unplaced_refs` exactly like the
   oracle's `continue`.
6. **`adjust_for_congestion` dtype awareness.** The oracle operates on
   `result = positions.copy()` in the array's own dtype. Under numpy 2.x
   NEP-50 a float32 array's normalized-push chain stays in float32
   (`dx = px - bx` computed in f32, `force` in f32, the in-place add in
   f32), while the exact-spot random push (`dist < 1e-3`) adds the f64
   random delta to the widened f32 element and rounds only on store. The
   kernel reproduces both paths op-for-op (`is_f32` branch); the f32
   `1e-3` spot threshold is bit-equivalent to the f64 comparison for all
   f32 dist values (no f32 lies strictly between `1e-3` and its f32
   rounding), pinned by `test_float32_normalized_chain` and
   `test_float32_exact_spot_store_semantics`. The distance is the numpy
   `sqrt(dx**2 + dy**2)` seam (numpy `**2` is libm `pow`, not `x*x`, and
   numpy's float32 sqrt is a correctly-rounded f32 sqrt — measured
   divergence on both dtypes 2026-08-05), and the random angle comes from
   the seeded `np.random.uniform` seam in the kernel's exact
   bottleneck-major/component-minor iteration order, so seeding reproduces
   the oracle's angle sequence. `influence_radius` is the oracle's literal
   `10.0`; `bottleneck.to_coordinates` and the `overflow <= 0` skip stay
   in the shim.
7. **Int/float and iteration-order traps.** Integer `refs.len().max(4)`,
   `i // 4`, `i // grid_size`, `i % grid_size`, `col`/`row` arithmetic and
   `(rotation + comp.rotation)` are integer operations on both sides;
   every `int * float` widens the int exactly (both arms are correctly
   rounded). Iteration order is netlist order / template insertion order
   / refs order on both sides — never a HashMap iteration.

## R1 gate status

| Gate | Status | Evidence |
|---|---|---|
| R1a behavioural A/B | PASS | 75 differential tests (adjustment 19, deterministic 27, template 29), bit-identical: numpy arrays via `tobytes()` (dtype included), floats via `float.hex()`, placements dicts on (keys, order, typed values) |
| R1b no-regression arm | N/A, recorded | `pr_perf_compare` has no benchmark rows for these surfaces (its arms are the Phase-2/3/4 kernels). `place_by_proximity`/`place_in_zone_center`/`adjust_for_congestion` are single-shot heuristics invoked once per placement run; the template `apply` methods are called a handful of times per board. Their wall time is dominated by the Python-side object navigation and marshalling that deliberately stays in the shims, so a per-call A/B would measure the pyo3 boundary, not the kernel. The prior-phase guide's "a Rust kernel behind a per-call marshalling boundary can be net-negative" applies; no speedup claim is made, and the migration's purpose is the single-implementation / no-reimplementation goal of Wave 4, not speed. Existing callers (`mcu_subsystem`, the pipeline stages, the integration loop) are unchanged in behaviour and remain green (97 tests incl. `test_mcu_subsystem`). |
| R1c ≥5 non-vacuous properties/module | PASS | 5 properties + 3 MRs over `template.py` in `test_placer_template_pbt.py`; the migrated deterministic/adjustment surfaces are driven by the differential suites' non-vacuous assertions (each with an explicit discriminating fixture, e.g. the no-zone #763 arm, the exact-boundary `dist == 10.0` arm). See the per-module table below. |
| R1d ≥3 MRs/module | PASS | 3 metamorphic relations over the template apply compute (MR1 scaling-by-power-of-two, MR2 full-turn rotation periodicity, MR3 parametric anchor invariance), each with a vacuity guard and each asserting *bit-level* equalities only over IEEE-exact transforms. |
| R1e VERIFICATION.md | PASS | this file |
| R1f TDD | PASS | RED commit `9d9e0197f` (rebased from `ff156e1f3`) — every differential file imports the to-be-added `temper_io_types.placer_*` symbol at module level, so RED is a collection failure (`AttributeError`) verified against the RED tree (no `placer_*` registration, no `placer_compute` module); GREEN landed with this migration commit (91 differential/PBT tests pass) |
| R1g Rust practice | PASS | pyo3 boundaries wrapped in `guard` (`temper_py_bridge::catch_unwind` → Python `RuntimeError`, G7); `?`-propagated `PyErr`; no `unwrap`/`expect` outside `#[cfg(test)]` (the test module carries `#![allow(clippy::unwrap_used)]` with a comment); borrow-over-clone throughout (the string clones are per-component output refs); `cargo clippy --all-features --all-targets -- -D warnings` clean |
| R1h R24 | N/A | determined **not physics-gated** below; no register entry required |

### R1c/R1d per module

| Module | Properties (R1c) | Metamorphic relations (R1d) |
|---|---|---|
| `placer/template.py` | 5 in `test_placer_template_pbt.py` — P1 bit-identical-to-oracle (anchor component **not** excluded), P2 anchor lands bit-exactly at the anchor point, P3 composite rotation is floored modulo 360, P4 zero-rotation is translation-only (trig seam bypassed), P5 parametric ratios scale linearly; each with a vacuity guard proving the claim is breakable | 3 — MR1 template-coordinate power-of-two scaling (bit-exact relation vs the anchor+scale·rel arithmetic), MR2 full-turn (360k) composite-rotation periodicity + differential at the shifted rotation, MR3 parametric dimension-rescaling anchor invariance |
| `placer/deterministic.py` | the differential suite's non-vacuous assertions: the #763 no-zone spiral arm, exact-boundary `dist == 10.0` not-pushed vs `just inside` pushed, board-center base, unknown-ref → `unplaced_refs`, empty-refs, duplicate-ref last-wins, initial-position f64→f32 cast pin | MRs are the metamorphic *arguments* encoded in the differential: `max_distance` invariance across `[1, 8, 15, 100]` (the dead parameter), refs-count scaling (`angle_step` = 2π/max(len,4) across 1/5/9 refs), grid-size scaling (1/2/3/5/9 refs), clamping kick-in when the grid spills beyond the zone |
| `placer/adjustment.py` | differential assertions over dtype (f64/f32), fixed/not-fixed, overflow skip, `dist < 1e-3` exact-spot vs normalized push, boundary `dist == 10.0`, multiple bottlenecks accumulating in order, empty positions | RNG-sequence relation (5 seeds, both arms re-seeded → identical draws), push-strength scaling (`2.0/0.5/1.0`), bottleneck-count ordering (2-bottleneck accumulation) |

### place_by_proximity #763 preservation note

The #763 fix (commit `9c7d58412`) dedented the spiral loop out of the
`zone_name` block — the placement must run even when `zone_name=None`.
The kernel's `place_by_proximity` keeps the loop at function level with
the zone clamp conditional, and the base position comes from the zone
center when a zone is given, else the board center — exactly the oracle's
`if zone:` / `else:` split. The no-zone arms of the differential
(`test_place_by_proximity_no_zone`, parametrized over `max_distance`)
assert `"C1" in placed_refs` — a non-vacuous pin that the spiral ran.

## R24 determination — NOT physics-gated

The dispatch brief asked for an R24 evaluation of the placer non-cp_sat
slice against `power_pcb_dataset/physics_soundness_register.yaml`.

**Determination: not physics-gated, no register entry.** Verified against
the pre-migration sources (the RED-commit oracle pins):
- none of `adjustment.py` / `deterministic.py` / `template.py` imports or
  AST-references any physics module (`thermal_fdm`, `heat_removal`,
  `thermal_potential`, `ipc2152` — none appear);
- none carries a `physics_gated: true` docstring marker;
- all three are outside the register gate's scan set
  (`placer/cp_sat/handlers/*` register_handler encoders,
  `domain_clearance.generate_domain_clearance_constraints`,
  `router_v6/constraint_model.py` Constraint subclasses);
- they place components (spiral/grid/template/anti-congestion geometry);
  they compute no physics quantity a post-solve audit could recompute from
  placement coordinates, and they feed no CP-SAT solver. The R24
  Chebyshev/BMC/post-solve obligations have no referent.

`scripts/physics_soundness_register_gate.py` exits 0 on this branch.

## RED-test corrections

No RED-commit test was changed in semantics. The oracle files were
**renamed** from `_placer_py_oracle/{adjustment,deterministic,template}.py`
(a directory layout) to the flat `_placer_*_py_oracle.py` convention so
`scripts/check_oracle_hashes.py`'s `_*_py_oracle.py` glob covers them
(verified: the renames are content-identical `git mv`s, and the registry
now pins all three). The test-file imports were updated to match
(`from tests.placer import _placer_*_py_oracle as oracle`). One
verbatim-copy defect in the RED commit was corrected: the adjustment
oracle carried a duplicate `from __future__ import annotations` (the
pinned source has one); removed, and the registry pin regenerated (see the
mutation-sweep evidence). Two differential fixtures were **added**
(not edited): the clamp-firing arms `test_place_by_proximity_zone_clamp_fires`
and `test_place_in_zone_center_grid_clamp_fires`, closing the vacuous-clamp
gap the mutation sweep found.

## Documented deviations (per R1, recorded here)

1. **`place_power_stage_template` anchor-missing raise.** The oracle
   reaches the raise through `template.apply()`; the shim raises the same
   `ValueError("Anchor point ... not found in template")` before the
   kernel is reached. Same class, same message, same failure point.
2. **Short `positions` in `adjust_for_congestion`.** If the positions
   array has fewer rows than `netlist.components`, the oracle raises
   `IndexError` on `result[i]`; the kernel's out-of-bounds access is
   caught by the `guard` boundary and surfaces as `RuntimeError`. Same
   failure class (the input is invalid on both sides); the differential
   drives valid inputs plus the empty case only.
3. **Duplicate template refs in `apply`.** The oracle's dict and the
   kernel's `placements_by_ref` both resolve duplicates to the LAST
   geometry; the shim's dict comprehension keeps the last row. Verified
   identical and pinned by the kernel unit test
   `power_stage_duplicate_template_ref_last_geometry_wins` (the
   differential's template fixtures use unique refs, as all `create_*`
   templates do).
4. **`adjust_for_congestion` int-dtype inputs.** The oracle would raise on
   `result[i] += [float, float]` for an int array (numpy's in-place cast
   rule); the shim passes an f64 view and writes back through
   `np.asarray(out, dtype=result.dtype)`, which truncates. Real callers
   pass float arrays (the differential drives f32/f64 only); the int case
   is a pre-existing broken input, recorded rather than reproduced.

## Evidence

- Differential (R1a/R1f, TDD red→green):
  `test_placer_adjustment_rust_differential.py` (19), 
  `test_placer_deterministic_rust_differential.py` (27),
  `test_placer_template_rust_differential.py` (29). RED state
  demonstrated: the files fail to collect with `AttributeError: module
  'temper_io_types' has no attribute 'placer_...'` before the Rust
  landed.
- PBT (R1c/R1d): `test_placer_template_pbt.py` — 5 properties + 3 MRs,
  each with a vacuity guard.
- Rust unit tests: `placer_compute.rs::tests` — floored `py_mod` on
  negative rotations, first-arg-on-tie `py_min`/`py_max` including NaN,
  the rotation=0 identity bypass, the #763 no-zone spiral, unknown-ref
  unplaced, the zone-center grid, the f32 vs f64 congestion chains, and
  duplicate template-ref last-wins.
- Rust practice (R1g): `guard` catches panics at every pyo3 boundary; no
  `unwrap`/`expect` outside `#[cfg(test)]`; `cargo clippy --all-features
  --all-targets -- -D warnings` clean.
- Raw-trig gate: `scripts/check_no_raw_rotation_trig.py` now exempts
  `placer/template.py::_cos_sin` — the seam contains only
  `math.cos`/`math.sin` calls (no rel/abs arithmetic; the R(-θ) formula
  the gate guards against lives only in the pinned Rust kernel). The
  gate passes (17 guarded files).
- Oracle pins: `scripts/oracle_hashes.json` registers the three placer
  oracles; `scripts/check_oracle_hashes.py` passes (82/82).

## Anti-vacuity (mutation sweep)

See `docs/evidence/2026-08-06-wave4-phase4-placer-mutation-sweep.md` for the
mutation campaign: 10 mutants applied to the Rust kernels, rebuilt, run
against the differential/PBT suites, failure confirmed, source restored,
and `git diff` confirmed EMPTY before the next mutant. 9/10 were caught by
the suites; the 10th (M9, the influence-radius `<`→`<=` boundary) is
recorded as bit-equivalent — the boundary push is an exact-zero
displacement, so the distinction is IEEE-invisible — with the reasoning in
the evidence doc. One gap was found and closed: the RED-committed
differential had no fixture that actually fired the zone-clamp path, so
two clamp-firing fixtures were added (and a clamp-dropping mutant is now
caught by them). The sweep also found and corrected a verbatim-copy defect
in the RED adjustment oracle (a duplicate `from __future__` import; the
registry was regenerated).

# Kicad-write geometry — Verification

The kicad-write geometry kernels (`src/kicad_write_geometry.rs`) are the
Wave-4 migration of the deterministic write/export surface:
`temper_placer/io/_write_tracks.py`, `_write_zones.py`, `_write_modules.py`
and `placement_exporter.py`. The four Python modules are now delegation
shims keeping their public entry points (which stay Python because they are
kiutils board I/O — the KiCad-format boundary is a documented
JUSTIFIED-KEEP) and forwarding every pure kernel here. The pre-migration
implementations are pinned VERBATIM as `_oracle_*` blocks inside
`packages/temper-placer/tests/io/test_write_geometry_rust_differential.py`
(origin/main `47349a50`); the TDD-RED state was demonstrated (the file
failed to collect with `AttributeError: module 'temper_io_types' has no
attribute 'kicad_write_geometry'` before the Rust landed).

## R1h — state applicability

**N/A.** This is a serialization/ordering surface: it derives deterministic
object IDs and canonical emission order for the written board, computes
axis-aligned pad bounds, and resolves net indices. No clearance, creepage,
thermal, or current-density margin is computed or asserted anywhere, so the
R24 physics-gate discipline has nothing to attach to.

## Induction applicability

**Mathematical induction is not applicable to this module.** No kernel is
recursive, and none iterates over a dimension whose correctness depends on
a size parameter:

- `stable_tstamp` is a fixed sha256 + UUIDv4 derivation, independent of the
  input size.
- `trace_emission_key` / `via_emission_key` build a constant-shaped tuple
  from a bounded attribute read (net, layer, one start/end/position pair,
  width, layers, is_diff_pair) — the via layers tuple is the only
  size-varying piece and it is a literal `tuple(str(x) for x in ...)`
  transcription.
- `component_bounds` is a min/max reduction whose per-pad operation is
  independent of the pad count; order-independence is asserted (MR1), not
  assumed.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every ported symbol, the Rust behaviour
is bit-identical to the pinned pre-migration Python implementation.

*Proof by structural cases.*

1. **`stable_tstamp`.** `_stable_tstamp` is
   `uuid.UUID(bytes=sha256(f"{kind}\0{key!r}".encode())[:16], version=4)`.
   `key!r` is CPython's `repr` — a Python runtime semantic (the B9 repr
   class) — so the repr is CALLED BACK via `key.repr()` rather than
   reimplemented; the payload bytes are therefore identical by construction.
   `sha2`'s sha256 is byte-identical to `hashlib`'s (verified by the existing
   `provenance.rs` pins). The UUIDv4 bit surgery replicates CPython's
   `UUID(..., version=4)` exactly: `int &= ~(0xc000<<48); int |= 0x8000<<48`
   (variant) and `int &= ~(0xf000<<64); int |= 4<<76` (version), which in
   big-endian byte terms is `b[6] = (b[6] & 0x0f) | 0x40` and
   `b[8] = (b[8] & 0x3f) | 0x80`, then the canonical 8-4-4-4-12 lowercase-hex
   rendering. Unit-tested and differentially pinned (including keys whose
   reprs contain quotes/escapes and floats whose reprs are repr-sensitive).
2. **Emission keys.** Both keys read the route/via fields through Python's
   object protocol (`str()` via `.str()`, `float()` via `__float__()`,
   `start[0]` via `.get_item(0)`, `net or ""` via truthiness), so numpy-typed
   geometry widens exactly as the oracle's `float(route.start[0])` does —
   the same `from_py_object` boundary `dsn_exporter.rs` established. Net
   index resolution is the truthiness-guarded `net and net in map` (a
   missing or falsy net is 0), and layer rank is `LAYER_NAME_TO_IDX.get(name,
   len(STANDARD_LAYER_ORDER))` with the map passed in from the Python SSOT.
   The returned Python tuple compares and — load-bearing — reprs identically,
   because repr is CPython's. The differential asserts BOTH the value tree
   (floats as `float.hex()`) and the repr string; the determinism suite
   (`test_write_tracks_determinism.py`) re-writes a real board under 32 hash
   seeds and asserts byte-identical output.
3. **`component_bounds`.** The KiCad rotation (`rotate_local_to_world`) stays
   on the Python side and is passed pre-rotated, because it is `sin`/`cos` on
   `math.pi` — B1: libm and Rust intrinsics are not bit-identical across
   platforms for transcendentals, so porting it would inject a divergence
   into geometry the differential would not reliably catch (the same
   judgement as `dsn_exporter.rs`'s `pin_world_position`). The reduction is
   ported with the two float facts that matter: the operation order
   (`abs_x - pad_w / 2` groups as `abs_x - (pad_w / 2)`; B7) and CPython
   builtin `min`/`max` first-argument NaN semantics (B5, `py_min`/`py_max`).
   The differential drives angles at/below/above the `0.1` rotation
   threshold, a NaN pad position, an empty pad list, and a missing
   `position`/`size` (defaults 0.0/1.0 — handled Python-side).
4. **Net-index map / resolution.** `build_net_name_to_index_map`'s loop
   (`hasattr(net, "name") and hasattr(net, "number")` → `net_map[net.name] =
   net.number`, last-wins) is transcribed with `getattr(...).ok()` — which,
   like CPython's `hasattr`, swallows any exception, not only AttributeError.
   The zones writer's bare `dict.get(net_name, 0)` and the truthiness-guarded
   `_resolve_net_index` are the two resolution kernels.
5. **Placement exporter.** `float(idx) * 90.0` and `x + origin_x` /
   `y + origin_y` are single correctly-rounded f64 operations, identical to
   CPython's. `np.argmax` (soft rotations → indices) deliberately stays
   Python — reimplementing numpy's dtype promotion and tie-break would be a
   behaviour change (the `dsn_exporter` precedent).

## Boundaries kept on the Python side (and why)

- **kiutils board I/O** (load, mutate, write `.kicad_pcb`) stays Python — the
  KiCad-format boundary is a recorded JUSTIFIED-KEEP; there is no kernel to
  extract from `KiBoard.from_file`/`to_file`.
- **`rotate_local_to_world`** stays Python (B1, see above); the reduction
  built on its output is ported.
- **`np.argmax`** stays Python (numpy tie-break/dtype judgement, `dsn_exporter`
  precedent).
- **Zone `tstamp`** (`write_zones_to_pcb`'s `uuid.uuid4()`) is NOT determinized:
  it is random in the pre-migration code, so determinizing it would be a
  behaviour change no bit-identical differential could pin; the zone writer
  has no live caller. Recorded, not silently changed.

## Documented deviations and bounds (per R1, recorded here)

1. **`i64` net-index bound.** `_resolve_net_index` returns `i64`; Python's
   `int` is arbitrary precision. A net index beyond `i64` saturates at
   extraction. KiCad net numbers are small integers (~1e3); unreachable in
   practice, recorded rather than defended.
2. **Emission keys on non-str net objects.** The kernels read `net` via
   `str(net)` and `map[str(net)]`; the oracle's `net in map` hashes the raw
   object. For the str/None domain `Trace.net` declares (and the differential
   drives), these coincide.
3. **`i64` rotation index in `rotation_index_to_degrees`.** Same width note;
   indices are 0..3 in the only caller.
4. **`component_bounds` inputs are pre-rotated world pads.** The kernel
   signature is not a drop-in for the full oracle loop; the shim
   (`_component_bounds`) owns the rotation-threshold branch and the SSOT call.
   Pinned end-to-end by the delegation tests (monkeypatched Rust symbols
   raise through the shipped entry points).

## Evidence

- **R1a behavioural A/B** — `test_write_geometry_rust_differential.py`: 56
  tests. Bit-exact comparisons (floats via `float.hex()`), emission keys
  additionally repr-compared, `_stable_tstamp` diffed against CPython
  `hashlib`/`uuid` directly, numpy-typed route/via geometry, duck-typed
  route/via objects, rotation-threshold and NaN pad cases, and six
  delegation tests proving the shipped modules reach the Rust kernels
  (monkeypatch-to-raise).
- **R1c properties** — `test_write_geometry_pbt.py`: 9 properties (P1–P9),
  one per cluster module, each with a G4 vacuity mutant that demonstrably
  fails against a degenerate kernel.
- **R1d metamorphic relations** — MR1 (bounds size-growth monotonicity,
  exact), MR2 (emission-key permutation invariance, exact), MR3 (tstamp is a
  1:1 function of the repr), MR4 (placement-origin associativity, exact for
  dyadic halves), MR5 (net-index map order independence, bounded to distinct
  names), each with a breakability test.
- **R1f TDD** — the differential failed to collect
  (`AttributeError: module 'temper_io_types' has no attribute
  'kicad_write_geometry'`) before the Rust module landed; GREEN after the
  build.
- **R1g Rust practices** — `cargo clippy --features python --all-targets`
  clean (0 warnings); no `unwrap`/`expect` outside `#[cfg(test)]`; every
  pyfunction body wrapped in `temper_py_bridge::catch_panic` at the boundary;
  borrows over clones.
- **Regression sweep** — the end-to-end determinism suite
  (`test_write_tracks_determinism.py`, 32 hash-seed subprocesses) still
  produces byte-identical boards, and the existing
  `test_placement_exporter`, `test_kicad_writer`, `test_rotation_handling`,
  `test_integration`, `test_pad_orientation_roundtrip` and
  `test_strip_routing_consolidation` suites stay green on the rewired shims.
