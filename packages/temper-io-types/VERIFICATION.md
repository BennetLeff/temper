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
| `format_json` data shape (dict insertion order, concrete leaf types) | `formatter.py` | migrated — **`json.dumps(json_data)` stays Python stdlib** per the Phase-3 PyYAML/json ruling: re-tokenising JSON in Rust would change behaviour while the differential stays green. The Rust side returns the JSON data with pinned key order and int-vs-float leaf types; the shim renders it. |
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
3. **int-vs-float leaf types.** Counts (`total_checks`, `passed_checks`,
   `failed_checks`, `total_issues`, `issue_count`) are set as Python `int`s;
   measured quantities (`elapsed_ms`, `runtime_ms`, locations) as `float`s.
   `_run_json_key` carries each leaf's concrete type into the comparison
   key, so `5` vs `5.0` cannot hide behind numeric equality (M2 caught this
   class).
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
| R1a behavioural A/B | PASS | 97 differential tests, bit-identical (strings byte-for-byte; floats via `float.hex()`; JSON via re-serialised `json.dumps` + concrete leaf types in the comparison key) |
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
