# temper-orchestration — Verification

The Phase-5 cli/adapters/temper-workflow slice (`feat/wave4-phase5-cli-adapters-workflow-rust`)
migrates the **compute** of the orchestration surfaces to Rust. This crate is
its home. Each migrated module keeps its full Python CLI/script surface
(flags, help, exit codes, output text) and delegates the compute across the
pyo3 boundary; the pre-migration implementations are pinned VERBATIM as the
differential oracles.

## Home-crate decisions

| Python module | LOC | Compute migrated | Home (module in this crate) | Verdict |
|---|---:|---|---|---|
| `temper_placer/cli/timing.py` | 832 | `compare_stage` (the `timing_check` delta/pct/effective-baseline/threshold/passed block), `p95` (the `wall_ms_p95` expression) | `timing.rs` | MIGRATE (compute) — the click surface, YAML manifest I/O, `git` subprocess calls and the `profiling.timing_gate` / `regression.metrics_recorder` call-backs stay Python (surfaces owned by other Phase-4/5 slices) |
| `temper_placer/cli/trace_commands.py` | 107 | `filter_decisions` (the `why` subject filter), `find_rejected_alternative` (the `why_not` nested scan) | `trace_filter.rs` | MIGRATE (compute) — the click surface stays Python; the `report` command stays Python (reconstructs `core.decision` objects, calls `pipeline.explainability` — other slices) |
| `temper_workflow/routing/route_and_measure.py` | 96 | `measure_copper_length` (per-trace Euclidean accumulation) | `copper_length.rs` | MIGRATE (compute) — the `parse_kicad_pcb` call (Phase-3 `io/` surface) and the script `main()` (argparse, exit codes, file handling) stay Python |
| `temper_placer/pipeline/convergence.py` | 391 | Wave-4 (feasibility): `record_loss`, `check_success`, `is_converged`, `check_routability_regression` (the net-set decision + state update). Phase-1 (orchestration engine): the four classes — `TerminationReason`, `ConvergenceCriteria`, `ConvergenceState`, `ConvergenceChecker` — as pyclasses | Wave-4: `feasibility.rs`; Phase-1: `convergence.rs` (+ `stage.rs`/`pipeline.rs`/`board_state.rs` engine scaffolding) | MIGRATE (full). Wave-4 moved the compute with the dataclasses/class orchestration staying Python; Phase-1 (plan 2026-08-09-001, U1) moved the classes themselves: `convergence.py` is now a delegation shim re-exporting the four Rust pyclasses + the module-level `is_converged` helper (public API unchanged; `test_convergence.py` passes through the shim). |
| `temper_placer/pipeline/preflight.py` | 286 | `component_area_ratio`, `proximity_rule_impossible`, `zone_over_capacity`, `loop_area_violation`, `isolation_barrier_too_large` (the compensated product sum is the internal `py_builtin_sum`/`sum_product_areas_impl`, deliberately NOT a standalone export) | `feasibility.rs` | MIGRATE (compute) — `PreflightChecker.run` orchestration, the `len(k) == 4` / zone-name / ref-membership marshalling, the `PreflightReport` rendering and the constant/stub checks stay Python |
| `temper_placer/pipeline/derivation.py` | 118 | `derive_emi_max_dist`, `derive_thermal_clearance`, `derive_si_max_placement_dist`, `mains_voltage_to_class_code`, `extract_min_clearance` | `feasibility.rs` | MIGRATE (compute) — the dict assembly, the code-to-`VoltageClass` mapping and the PCL `SeparatedConstraint` construction stay Python |
| `temper_placer/pipeline/state.py` | 117 | U4 (orchestration engine): the data model — `PipelinePhase`, `PipelineConfig`, `PipelineState` — as pyclasses (plan 2026-08-09-001, U4); `PipelineError` stays Python | `pipeline_state.rs` | MIGRATE (full, minus `PipelineError`): `state.py` is now a delegation shim re-exporting the three Rust pyclasses + the Python exception (public API unchanged; `test_pipeline_state_rust_differential.py` + `test_pipeline_state_pbt.py` pin parity). `PipelineConfig` is the plan's U4 "PipelineState→Rust config" migration. |
| `temper_placer/router_v6/stage_ledger.py` | 193 | `snapshot_cardinality` (the `_snapshot` cardinality counting), `diff_cardinality` (the `_diff` five-field compare), `CardinalitySnapshot` (the `_CardinalitySnapshot` dataclass) — the final portable router_v6 orchestration module | `stage_ledger.rs` | MIGRATE (compute) — the stateful `StageLedger` orchestration (`_pre`/`_post` storage, the `checkin`/`checkout`/`verify` flow, the `fail_on_imbalance` raise decision, the logger emission), `LedgerReport` + `__str__`, the checkout message rendering (presentation of the diff list) and `StageLedgerImbalanceError` stay Python (see the slice section below) |
| `temper_placer/cli/drc_cli.py` | 319 | — | — | R3-style record (below) |
| `temper_placer/cli/watch_commands.py` | 115 | — | — | R3-style record (below) |
| `temper_placer/cli/andon_commands.py` | 26 | — | — | R3-style record (below) |
| `temper_placer/cli/version.py` | 17 | — | — | R3-style record (below) |
| `temper_placer/adapters/*.py` (4 modules) | 368 | — | — | R3-style record (below) |
| `temper_workflow/metrics/*.py` (3 modules) | 280 | — | — | R3-style record (below) |
| `temper_workflow/routing/steiner_sweep.py` | 86 | — | — | R3-style record (below) |
| `temper_workflow/utils/__init__.py` | 1 | — | — | R3-style record (below) |

## R3-style records — pure dispatch/glue surfaces

Wave-4 R3 (residual decision procedure): a surface that is pure dispatch or
glue — its only behavior is call-backs into not-yet-migrated Python owned by
other slices, static data, or a documented `NotImplementedError` stub — is
recorded here with its named blocker instead of receiving a differential it
could not discriminate. "Consolidation alone" is never the justification
(D6); the blocker is concrete in every case. All are re-decidable when their
call-back targets migrate.

| Module | Blocker (named) |
|---|---|
| `cli/drc_cli.py` | Orchestration over the Phase-4 `validation/` surface (`Placement.from_yaml`, `ConstraintSet.from_yaml`, `CheckRunner`, all 13 check classes) and `report/` (`format_text/json/html`, `generate_summary`) — both owned by other slices. The remaining content is static template data (`list_checks`, `init_placement`, `init_constraints`) and click wiring; zero standalone compute exists to migrate. |
| `cli/watch_commands.py` | `_watch_replay` is marshalling over `pipeline/dag_observability.StageEvent` + `pipeline/terminal_dashboard.TerminalDashboardObserver` (the Phase-5 `pipeline/` slice owns both). The only non-call-back logic is JSON field defaulting (`e.get("name", "")` etc.) whose semantics are Python dict-`.get` — the same boundary the migrated `trace_filter` keeps Python-side. Zero standalone compute. |
| `cli/andon_commands.py` | The module's entire behavior is a documented `raise NotImplementedError` ("Andon board not yet migrated to DAG engine"). Migrating a stub is vacuous; the R1 battery has nothing to pin. The command's click surface stays as-is. |
| `cli/version.py` | Prints a version string + a one-line notice through the rich console. Zero compute; consumers rely on the click wiring in `cli/__init__.py`. |
| `adapters/router_v6_stage_adapter.py` | All five stage `run()` bodies are 100% call-backs into `io/kicad_parser` (Phase 3) and `router_v6/pipeline` (Phase 5 `router_v6` slice) — the task brief explicitly directs keeping those call-backs Python-side. The stage classes are data (`name`/`requires`/`provides`/`contract`) plus dispatch; the registration side-effect calls `strategy_registry` (Phase 5, other slice). Zero standalone compute. |
| `adapters/register_strategies.py` | `PlacementStage`/`RoutingStage` are `@dataclass` `PipelineStage` subclasses whose `run()` bodies call `strategy_registry.register` and `router_v6.route_pcb` (Python call-backs). `PipelineStage` is a `@runtime_checkable` Protocol with no pyclass mapping (the `protocol.py` R3 record, already decided); `dataclasses.replace()`-style surface is relied on by consumers. Zero standalone compute. |
| `adapters/deterministic_adapter.py` | `_WrappedDeterministicStage` is a protocol-compat wrapper whose `run()` calls the wrapped `deterministic.stages.Stage` (the `deterministic/` slice owns the stages). Zero standalone compute; the wrapper is data + one call-back. |
| `adapters/placement_adapter.py` | A deprecated stub whose `run()` raises `NotImplementedError` (JAX retirement) plus a registration side-effect. Nothing to migrate. |
| `temper_workflow/metrics/aesthetic_turing_test.py` | A standalone study script whose compute is one-hot rotation encoding (6 lines) plus call-backs into `io/kicad_parser` (Phase 3), `core/state.PlacementState` (Phase 2), `metrics/aesthetic` (Phase 4) and the retired JAX stack (`jax.numpy` — the module already carries a documented undeclared-import finding; `scripts/check_undeclared_imports.py` reports it as needing an owner decision). Migrating 6 lines of logit-encoding behind a JAX boundary is net-negative marshalling. |
| `temper_workflow/metrics/compare_refinement.py` | Study-script glue: `losses`/`optimizer` (Phase 4) call-backs plus a `time.time()` wall-clock study loop. Zero standalone compute beyond the retired-JAX `PlacementState` construction. |
| `temper_workflow/metrics/measure_displacement.py` | Study-script glue: `optimizer.analytical`/`initialization`/`legalization` (Phase 4) and `jax` call-backs; the `run_legalization_study` body is a `jnp.linalg.norm` + `float()` reduction over the JAX boundary. The 4 reductions are numpy-library semantics not reimplementable bit-exactly outside numpy (the guide's "library semantics" trap). |
| `temper_workflow/routing/steiner_sweep.py` | Study-script glue: `losses.wirelength` (Phase 4) call-backs + `measure_copper_length` (now Rust). The `hpwl_error`/`steiner_error` ratios are 3 lines of guarded division. |
| `temper_workflow/utils/__init__.py` | Docstring-only module (`"""Utility modules for GPBM workflow."""`); nothing to migrate. |
| `temper_placer/strategy_registry.py` | Pure import-time registry of Python stage factories (`register`/`get`/`list_stages`/`register_composite`/`get_composite`). Every operation is a dict membership/insert with Python semantics (idempotent register, KeyError raise, `f"{p}/{n}"` key assembly) or a call-back into the stored `Callable[[], PipelineStage]` factory; stored values are live Python callables and resolved objects are `@runtime_checkable` Protocol instances (no pyclass mapping — the `protocol.py` record above). It is the shared import-time seam the adapter modules above register into and `runner.py` resolves from (`get_composite`/`get` in `resolve_and_run`); migrating it would make that seam — and both sides of it — import the pyo3 boundary for zero compute (D6: registry-surface independence). Ledger verdict flips MIGRATE phase 5 → JUSTIFIED-KEEP on 2026-08-06 (`docs/wave4-verdicts.yaml`); re-decidable if a consumer migrates and carries the registry with it. |

## Panic safety at the boundary (R1g)

pyo3's `#[pyfunction]` expansion wraps every exported body in `catch_unwind`
and converts a Rust panic into `PyPanicException`; the crate sets
`profile.release.panic = "unwind"` so that catch is what runs. No `unwrap`
outside tests (clippy `unwrap_used`/`expect_used` = deny); no unsafe outside
`host_math.rs`, which carries the dlsym safety-doc allow + rationale.

## Physics gating (R1h)

**Not physics-gated.** None of the migrated surfaces gates on a physics
quantity (no clearance, temperature, loop-area or thermal constraint
involvement). The R24 discipline (Chebyshev proof, BMC-exhaustive small-N
validation, post-solve audit) is therefore not applicable; this note records
that explicitly.

## Induction applicability

**Mathematical induction is not applicable to any migrated kernel.** None is
recursive, and none iterates over a dimension whose correctness depends on a
size parameter:

- `compare_stage` is a fixed sequence of arithmetic steps.
- `p95` sorts and indexes; the per-index operation is size-independent and
  the empty-input error path is a constant.
- `filter_decisions` / `find_rejected_alternative` iterate caller-provided
  collections; each element's comparison is independent of collection size.
- `measure_copper_length` accumulates per-segment; the accumulation order is
  load-bearing (naive summation) but each step is the same IEEE add
  regardless of length.
- The pipeline-feasibility kernels are fixed-step arithmetic (`record_loss`,
  `check_success`, the derivation scalars, `component_area_ratio`), indexed
  decisions (`mains_voltage_to_class_code`), or finite loops whose per-step
  operation is size-independent — the compensated `sum`/`sum_product_areas`
  iterate caller-provided collections with each step the same IEEE
  add-and-compensate regardless of length (order is load-bearing, pinned by
  the differential's dict-order cases). `check_routability_regression` is a
  bounded state machine with no size parameter.

Per R1e, a **structural proof** is recorded instead (bit-exactness is
verified by the differential suites and the mutation campaign).

## Structural proof

**Claim (bit-identical parity).** For every migrated kernel, the Rust
behaviour is bit-identical to the pinned pre-migration Python for every
input in the differential suites' domains, with the documented boundary
choices below.

*Proof by structural cases.* Each kernel is a direct transcription of the
oracle's inline expression with the following load-bearing equivalences,
each pinned by measurement or by identity:

1. **Decimal rounding (p95).** CPython `round(x, 3)` is David Gay dtoa
   mode-1 decimal round-half-to-even — measured 494/2M mismatches vs
   `(x * 1000).round() / 1000` on uniform samples plus every exact `.xxx5`
   tick. `p95` therefore calls Python's `round` for the final step
   (bit-identical by identity); the sort and index selection are Rust. The
   selected element is handed to `round` as its ORIGINAL Python object, so
   the result carries its type (int in → int out, exactly like the oracle —
   review P2-6: the shim writes the result into the YAML manifest, where
   `100` vs `100.0` render differently). Elements with `|x| >= 2**53` sort
   by their f64 approximation (the pre-migration extraction had the same
   boundary; not claimed).
2. **Stable `<`-sort (p95).** CPython `sorted()` on floats is a stable sort
   under `<`, where `-0.0 < 0.0` is False and every NaN comparison is
   False. `py_cmp` maps non-comparable pairs to `Equal`, reproducing
   CPython's placement for finite values, `-0.0`/`+0.0` ties and NaN alike.
   `int(len * 0.95)` truncates; the Rust `(len as f64 * 0.95) as usize` is
   the same IEEE multiply + truncation.
3. **CPython `max` (compare_stage).** `max(baseline, floor)` is asymmetric
   on NaN (`max(nan, 1.0)` → nan; `max(1.0, nan)` → 1.0); `py_max`
   (`if b > a { b } else { a }`) reproduces it, unlike `f64::max`. The
   `baseline_ms > 0` guard short-circuits the division for zero/`-0.0`/NaN
   baselines, so there is no float-division-by-zero divergence path.
4. **Python value semantics (trace_filter).** The filter comparisons are
   `dict.get` defaulting to `None` (missing → `None`, `None == x`),
   `str()` of arbitrary JSON leaves, and `==` — preserved by calling back
   into Python for each leaf (`call_method1("get", ...)` raises the same
   `AttributeError` a non-dict would; `PyAny::str()` is Python `str()`;
   `PyAny::eq` is Python `==`; non-iterable `decisions` → `TypeError` via
   `PyObject_GetIter`, by identity). The control flow (iteration, subject
   equality, the nested scan, first-match return) is Rust.
5. **libm `pow` via dlsym (copper_length).** `dx ** 2` is CPython
   `float ** float` — libm `pow`, NOT `x * x` (measured 229-389/200k-300k
   mismatches of `x*x` vs `**2` in this slice's own environment).
   `host_math::pow` resolves `dlsym(RTLD_DEFAULT, "pow")` — the NULL
   handle (== `RTLD_DEFAULT` on ELF; NOT on Darwin, where it is -2) — to
   the exact libm the host CPython loads, with `f64::powf` as the
   fallback. On macOS the NULL handle fails ('invalid handle': it only
   searches the main image plus `RTLD_GLOBAL`-loaded images, and CPython
   loads extension bundles `RTLD_LOCAL`), so the fallback is the LIVE
   route there; it is sound by accident, exactly as documented for
   temper-constraint-compiler (`constraints/mod.rs`, with the
   `nm`-verified `U _pow` and the 200k-sample A/B): the runtime exponent
   defeats LLVM's `x*x` folding and the lowered call resolves to libSystem
   `pow`, the same function CPython's `float_pow` calls. `math.sqrt` is
   the correctly-rounded IEEE sqrt → `f64::sqrt`.
6. **Naive accumulation (copper_length).** `total_length += length` and
   `net_lengths.get(net, 0.0) + length` are non-compensated; the Rust uses
   plain f64 `+=` / add in the same per-segment order (the differential
   permutes segments to pin the order-sensitivity). First-seen net order is
   preserved (Vec + `dict(pairs)` assembly on the shim side).
7. **Falsy-net skip (copper_length).** `if not trace.net` skips `None` AND
   `""` (flattened as `Option<String>`; empty string skipped explicitly).
   The shim applies the skip BEFORE the `start[0]`/`end[0]` index accesses
   (its flatten comprehension carries `if trace.net`), matching the
   oracle's statement order — a falsy-net trace whose `start`/`end` are not
   indexable is skipped rather than raised on (ordering fix from review
   2026-08-05).

**Documented boundary choices** (kept Python, argued in-source and above):
PyYAML manifest I/O (`timing.py` — the loaders precedent), the `git`
subprocess calls, `profiling.timing_gate`/`regression` call-backs, the
`io/kicad_parser` parse call, click/argparse surfaces, and the
`timing_tighten` empty-`qualifying_runs` `else 0.0` guard (the bare p95
expression raises `IndexError` on empty; the guard is a call-site policy,
not part of the kernel contract — pinned as such by the differential).

## Pipeline-feasibility slice (Wave 4, cluster)

The feasibility/check compute of `temper_placer.pipeline.{convergence,preflight,derivation}`
(795 LOC combined) is migrated to `feasibility.rs`. The three Python modules
keep their full public API (dataclasses, enums, the
`ConvergenceChecker`/`PreflightChecker` classes and the module-level
functions) and delegate the compute across the pyo3 boundary. The
pre-migration modules are pinned VERBATIM as the oracle
(`tests/pipeline/_pipeline_feasibility_py_oracle.py`, content-hashed below
its PINNED BODY marker; the only documented rewrite is derivation.py's
future-import hoist).

### Structural proof

**Claim (bit-identical parity).** For every migrated kernel, the Rust
behaviour is bit-identical to the pinned pre-migration Python for every input
in the differential suites' domains. The load-bearing equivalences, each
pinned by measurement or identity:

1. **Compensated builtin `sum` (B12).** CPython 3.12's `sum()` over floats is
   the improved Kahan-Babuska (Neumaier) algorithm. `py_builtin_sum`
   transcribes `builtin_sum_impl` in `bltinmodule.c` (v3.12.13) INCLUDING two
   details the quality-oracle copy omits: (a) the seed is `0 + first`
   (`PyNumber_Add(0, first)`), which makes `sum([-0.0])` equal **+0.0** — IEEE
   round-to-nearest — not the first element's `-0.0`; and (b) the final flush
   guard is `if (c != 0.0 && c.is_finite()) hi + c else hi`, matching the C
   `if (c && Py_IS_FINITE(c))`, so an overflowed/NaN compensation is dropped
   rather than producing `inf + -inf = NaN`. The preflight keepout sum mixes
   int `0` entries with float products; in the C float fast path those hit the
   `f_result += (double)0` no-op branch, so the mixed sequence sums exactly
   like the float products alone in order — pinned by the module-level
   `PreflightChecker.run` differential with a real mixed-length keepout list,
   and by `test_compensated_summation_matches_python_sum` (the
   `1e16 + 1 - 1e16` naive-vs-compensated discriminator plus 120 randomized
   is_converged pairs against a Python `sum()`-based reference). The helper
   is internal (`py_builtin_sum`) rather than an exported pyfunction — no
   production path needs a raw sum exposed, and the unwired-kernel gate
   rejects inert exports; its unit tests pin the `-0.0` seed and the
   non-finite compensation guard directly.
2. **CPython `min`/`max` positional semantics.** `py_min` is
   `if b < a { b } else { a }`, keeping the first argument on ties and NaN
   (proximity min-spacing, isolation `min(w, h)`), never `f64::min`.
3. **`record_loss` zero-best raises.** `(best_loss - loss) / best_loss` with
   `best_loss == 0.0` (incl. `-0.0`) raises `ZeroDivisionError("float division
   by zero")` in Python where IEEE division returns ±inf; the kernel raises
   the identical exception (message parity pinned via `canon_call`).
4. **`check_routability_regression` state parity.** The kernel is pure and
   returns the post-call best/stall state; the shim writes it back. Attribute
   reads replicate the oracle exactly: `_best_routed_nets` is always read
   (AttributeError parity on a fresh state), `_best_routability` only on the
   non-first-call path, `_stall_count` only on the identical-net-set path.
   Net sets are deduped + sorted into `BTreeSet`s (set semantics for `len`/
   `==`/difference; `lost_nets` comes out sorted); the claimed domain is the
   oracle's own `frozenset[str]` contract. The rendered `failure_message`s use
   the shim's original f-strings on the kernel-returned values (same IEEE
   bits → identical text).
5. **`is_converged` order-sensitive compensated lengths.** The success count
   is exact int arithmetic; the length sums are compensated and therefore
   element-order-sensitive — the shim preserves dict insertion order.
6. **Derivation scalars.** `sqrt(area) * 0.8` (IEEE sqrt), `power * 2.0` and
   `max_len / 1.5` are direct transcriptions; the voltage-class boundary chain
   and the `str.replace`-all-occurrence `_min_clearance` extraction are
   reproduced exactly (`str::replace`, not `removesuffix`).

**Documented boundary choices** (kept Python, argued in-source and above):
`ConvergenceChecker`'s time-based checks (`check_timeout`,
`get_elapsed_seconds`) and `check_iteration_limit`/`check_stagnation` are
trivial comparisons with no float math; `PreflightChecker.run` orchestration
and the `_check_layer_count`/`_check_stackup_quality`/stub checks are
marshalling or call-backs into the manufacturing surface; the preflight
message f-strings (`Fill ratio {ratio:.1%}`, `{min_d:.1f}`) and the
`PreflightReport.summary()` rendering stay Python (Python-format exactness
would not be reproducible in Rust's `{:.N}`); the PCL `SeparatedConstraint`
construction is Python IR marshalling. A `max_distance_mm=None` proximity rule
raises `TypeError` in both arms but with different messages (pinned as a
witnessed divergence).

### Differential suites

| Suite | Location | Count |
|---|---|---|
| timing differential | `packages/temper-placer/tests/cli/test_timing_rust_differential.py` | 14 |
| trace_commands differential (incl. CLI-surface A/B) | `packages/temper-placer/tests/cli/test_trace_commands_rust_differential.py` | 18 |
| route_and_measure differential | `packages/temper-workflow/tests/test_route_and_measure_rust_differential.py` | 19 |
| pipeline-feasibility differential (cluster: convergence + preflight + derivation) | `packages/temper-placer/tests/pipeline/test_pipeline_feasibility_rust_differential.py` | 69 |
| timing PBT (+G4 mutants) | `packages/temper-placer/tests/cli/test_timing_pbt.py` | 16 |
| trace_commands PBT (+G4 mutants) | `packages/temper-placer/tests/cli/test_trace_commands_pbt.py` | 15 |
| route_and_measure PBT (+G4 mutants) | `packages/temper-workflow/tests/test_route_and_measure_pbt.py` | 13 |
| pipeline-feasibility PBT + metamorphic (P1..P6 with mutation guards, MR1..MR4) | `packages/temper-placer/tests/pipeline/test_pipeline_feasibility_pbt.py` | 24 |

Oracles (VERBATIM pre-migration copies, byte-verified):
`tests/cli/_timing_py_oracle.py`, `tests/cli/_trace_commands_py_oracle.py`,
`tests/_route_and_measure_py_oracle.py`, and — for this slice —
`tests/pipeline/_pipeline_feasibility_py_oracle.py` (content-hash-pinned by
`test_oracle_body_matches_pinned_digest`; byte-verified section-by-section
against the three modules at origin/main `68ea250f`). The timing oracle's
relative import `from ._io import console` is rewritten to its absolute form
(document in its header) so it is importable from the test tree; the trace
oracle had no module docstring and gains one; everything else is
byte-identical to the pinned commit (origin/main `15110fecc`).

### G4 / G5 status for the pipeline-feasibility cluster

The verification unit is the CLUSTER (per the 2026-08-05 G4 ruling: one
pinned oracle, one shared corpus). Six non-vacuous properties (P1..P6) reach
all three modules — convergence.py via P1/P2/P3, preflight.py via P4/P5,
derivation.py via P6 — each with a degenerate-kernel mutation guard
(`test_pN_fails_for_<mutant>` via `hypothesis.inner_test`) and a reachability
witness test. Four metamorphic relations (MR1..MR4) cover all three modules
and are claimed BIT-EXACT: MR1 record_loss power-of-two scale invariance, MR2
zone zero-product append no-op (a `0.0 * h` product enters the compensated
sum without changing hi or the compensation), MR3 component-area-ratio
power-of-two scaling, MR4 thermal-clearance output doubling.

## Rust orchestration engine — U0 scaffolding + U1 convergence (Phase-1)

The Rust Orchestration Engine plan (2026-08-09-001) ships its Phase-1
deliverable here: the engine scaffolding (U0: `stage.rs`, `pipeline.rs`,
`board_state.rs`) and the first migrated pipeline module on it (U1:
`convergence.rs` — `TerminationReason`, `ConvergenceCriteria`,
`ConvergenceState`, `ConvergenceChecker` as pyclasses, bit-exact with the
pre-migration `pipeline/convergence.py`).

### What changed vs. the Wave-4 feasibility slice

Wave-4 migrated only the *compute* of convergence (the `record_loss` /
`check_success` / `is_converged` / `check_routability_regression` kernels in
`feasibility.rs`), keeping the dataclasses/class orchestration in Python.
Phase-1 migrates the classes themselves: the shim now re-exports the four
Rust pyclasses from `temper-orchestration` and keeps the module-level
`is_converged` helper (delegating to the Wave-4 kernel). The `ConvergenceChecker`
pyclass additionally implements `Stage<BoardState>` — the first concrete
`Stage` on the new engine (a Phase-1 stub: reads nothing, returns the state
unchanged; full `BoardState` integration is Phase C).

### G1 — differential oracle before Rust (TDD)

The differential suite `test_convergence_rust_differential.py` and its
VERBATIM oracle `_convergence_py_oracle.py` were committed first (RED:
`5cfe4880` — the anti-vacuity `__module__` assertions failed, the port was
not Rust), then the implementation landed GREEN (`571c84ca`). The oracle is
the pre-migration `convergence.py` at `68ea250f`, byte-identical to the
convergence section of the already content-hash-pinned
`_pipeline_feasibility_py_oracle.py` (verified via `diff` against
`git show 68ea250f:.../convergence.py`), pinned by sha256.

### G2 — behavioural A/B (bit-exact)

The differential drives BOTH arms with identical inputs and compares every
return value and every post-op state snapshot bit-exact (floats via
`float.hex()` via `canon`, error parity via `canon_call`): termination-member
values, criteria defaults and 40 randomized kwargs sets, deterministic
`record_loss` / `check_success` / `check_routability_regression` /
termination-flag sequences, the three rendered `failure_message` scenarios,
`ZeroDivisionError` parity on a zero best, and **120 randomized trials**
(random criteria + random state + random op sequences — the G2 100+
randomized-input arm). 15/15 green.

### G3 — performance

Pure-delegation carve-out: the convergence checker is <1ms per check; the
only overhead added is the FFI crossing + pyclass construction for the four
classes. No regression beyond noise is possible or claimed.

### G4 / G5 — PBT + metamorphic (`test_convergence_pbt.py`)

Six non-vacuous properties (P1 iteration-limit threshold, P2 timeout budget,
P3 success thresholds, P4 stagnation needs history AND epochs, P5
record_loss epoch monotonicity, P6 check_all preserves an existing reason),
each with a reachability witness and TWO mutation guards via
`hypothesis.inner_test`; four metamorphic relations (MR1 monotonic iteration,
MR2 loss-improvement resets stall, MR3 criteria permutation invariance of
the stagnation decision, MR4 routability stall increment/reset), each with a
mutation guard. MR1/MR4 claimed bit-exact; MR2/MR3 boolean parity over
bit-exact state. 27/27 green.

The plan's example property table is re-expressed over the real pre-migration
API: the plan's invented `check()` method never existed in the module (the
real surface is `check_all`/`check_iteration_limit`/`check_success`/
`check_stagnation`/`record_loss`/`check_routability_regression`), so the
properties target that surface; the plan's intent (monotonicity, priority
order, no-stagnation-without-history, NaN never panics) is preserved.

### G6 — induction

Not applicable — the convergence module is data-only (fixed-step arithmetic
and bounded state transitions); no recursive computation. A structural proof
is recorded below instead (per R1e).

### G7 — Rust bar

`cargo test` 65/65 green; `cargo clippy --all-features --all-targets --
-D warnings` clean. No `unwrap`/`expect` anywhere (crate denies both). No
`catch_unwind` needed at the pyo3 boundary for the pyclasses: pyo3's
`#[pyclass]`/`#[pymethod]` expansion wraps every exported body in
`catch_unwind` and converts a Rust panic into `PyPanicException` (the crate
sets `profile.release.panic = "unwind"` so that catch is what runs) — the
same mechanism the module docstring already documents for `#[pyfunction]`.

Two Cargo.toml notes, both deliberate:
- `pyo3/py-clone` is enabled — the plan's `BoardState` `#[derive(Clone)]`
  over `Option<Py<PyAny>>` fields is impossible without it (`Clone for Py<T>`
  is cfg-gated behind it). The generated `clone()` panics only when a
  NON-EMPTY `Py<T>` field is cloned from a non-attached thread; `BoardState`
  instances with populated fields only exist inside the Python-driven
  pipeline (GIL held), and the all-None clones in pure-Rust unit tests never
  touch the interpreter. Unreachable for the Phase-1 scope.
- `pyo3/extension-module` was REMOVED from the Cargo features (it stays in
  pyproject.toml's `[tool.maturin] features`, so the maturin-produced cdylib
  is unchanged) — with it in Cargo features, `cargo test`/`cargo clippy
  --all-targets` link the test binary against an unlinked-libpython pyo3 and
  fail on toolchains whose CGU partitioning pulls pyo3 code into the test
  binary (measured: rustc 1.97.1 — the pristine crate at `main` fails the
  same way). Without it, the test build links libpython normally. This
  fixes a latent CI gap (the `cargo test` step would fail on newer
  toolchains).

### G8 — R24 physics discipline

Not applicable — convergence is pure data (no clearance, temperature,
loop-area or thermal involvement). Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every method and state transition of
the four pyclasses, the Rust behaviour is bit-identical to the pinned
pre-migration Python for every input in the differential suite's domains,
with the documented boundary choices below.

1. **`record_loss` zero-best raises (ZeroDivisionError).** `(best - loss) /
   best` with `best == 0.0` (incl. `-0.0`) raises
   `ZeroDivisionError("float division by zero")` in CPython where IEEE
   division returns ±inf; the pyclass raises the identical exception, and
   the loss is appended to `loss_history` BEFORE the raise on both sides
   (pinned by `test_record_loss_zero_best_error_parity`).
2. **`check_success` dict-defaulting and NaN semantics.** `metrics.get(key,
   default)` resolves missing keys to the oracle's defaults (`inf` for
   overlap/boundary, `0.0` for routing/margin); NaN values never FAIL a
   comparison (`NaN > x`/`NaN < x` are both False) — pinned by the metric
   sets incl. NaN cases. A Python int metric coerces exactly like the
   pre-migration shim's `float(...)`.
3. **Rendered `failure_message` parity is by identity.** The regression /
   convergence f-strings format floats with `:.3f` (David-Gay-dtoa semantics
   that Rust's `{:.3}` does not reproduce bit-for-bit in general) and render
   `sorted(lost_nets)` via Python list-`str`; the pyclass calls CPython's
   `format()` builtin and `str(list)`, so parity is by identity, not by
   coincidence of formatter implementations.
4. **`check_routability_regression` reuses the Wave-4 kernel.** The net-set
   decision + best/stall state update is the exported `feasibility.rs`
   kernel (BTreeSet set semantics; `lost_nets` sorted); the post-call state
   is written back onto `self.state` exactly as the Wave-4 shim did.
5. **Time checks are wall-clock.** `start_time` is a float-seconds epoch
   timestamp (the plan's Rust API — documented deviation from the Python
   `datetime` field); `get_elapsed_seconds`/`check_timeout` compare the same
   quantity. The differential pins `timeout_seconds` to `{0.0}` (always
   fires: elapsed >= 0) or `>= 60` (never fires: elapsed is milliseconds),
   so both arms agree deterministically.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above):
- `ConvergenceState.start_time` is a float-seconds timestamp, not a Python
  `datetime` (the plan's Rust API; nothing in the Phase-1 surface constructs
  `ConvergenceState` from a datetime).
- `_best_routed_nets` / `_best_routability` / `_stall_count` are DECLARED
  optional fields (None/0 defaults) rather than the oracle's lazily-created
  dynamic attributes. A truly-fresh oracle state raises AttributeError on the
  first `check_routability_regression` call; the Rust state treats it as a
  first call. Every caller pre-initializes these attributes (the differential's
  `_preinit` mirrors the callers), so the divergence is unreachable on
  exercised paths — recorded, not hidden.
- `ConvergenceChecker`'s `reset()` drops the lazily-created `_best_*` attrs
  on the oracle; the differential re-initializes after every `reset`
  exactly like the callers do.
- The four classes keep the pre-migration method surface exactly; the plan
  sketch's invented `check(state)` method is NOT added (it never existed in
  the module — see the G4 note).

### Differential suites (Phase-1)

| Suite | Location | Count |
|---|---|---|
| convergence differential (oracle: `_convergence_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/pipeline/test_convergence_rust_differential.py` | 15 |
| convergence PBT + metamorphic (P1..P6 + MR1..MR4, mutation-guarded) | `packages/temper-placer/tests/pipeline/test_convergence_pbt.py` | 27 |
| existing shim surface (`test_convergence.py` through the delegation shim) | `packages/temper-placer/tests/pipeline/test_convergence.py` | 32 |
| pipeline-feasibility suites (still green against the shim) | `tests/pipeline/test_pipeline_feasibility_*.py` | 93 |

## Differential suites

| Suite | Location | Count |
|---|---|---|
| timing differential | `packages/temper-placer/tests/cli/test_timing_rust_differential.py` | 14 |
| trace_commands differential (incl. CLI-surface A/B) | `packages/temper-placer/tests/cli/test_trace_commands_rust_differential.py` | 18 |
| route_and_measure differential | `packages/temper-workflow/tests/test_route_and_measure_rust_differential.py` | 19 |
| timing PBT (+G4 mutants) | `packages/temper-placer/tests/cli/test_timing_pbt.py` | 16 |
| trace_commands PBT (+G4 mutants) | `packages/temper-placer/tests/cli/test_trace_commands_pbt.py` | 15 |
| route_and_measure PBT (+G4 mutants) | `packages/temper-workflow/tests/test_route_and_measure_pbt.py` | 13 |

Oracles (VERBATIM pre-migration copies, byte-verified):
`tests/cli/_timing_py_oracle.py`, `tests/cli/_trace_commands_py_oracle.py`,
`tests/_route_and_measure_py_oracle.py`. The timing oracle's relative import
`from ._io import console` is rewritten to its absolute form (documented in
its header) so it is importable from the test tree; the trace oracle had no
module docstring and gains one; everything else is byte-identical to the
pinned commit (origin/main `15110fecc`).

### Oracle drift — status and named follow-up (review P2-2, 2026-08-05)

- **(a) The byte-identity claim above is a ONE-TIME verification**, performed
  at migration time against the pinned commit. Nothing in CI re-checks that
  a `_*_py_oracle.py` file still matches the module it was copied from, so a
  future edit to either side can silently invalidate the claim.
- **(b) Named follow-up (program-level decision, NOT built here):** a
  committed content-hash gate for the `_*_py_oracle.py` files — e.g. a
  checksum manifest checked by CI (`check_vacuous_gates`-style) that fails
  when an oracle file changes without an accompanying
  re-verification-and-repin step. This requires a new CI gate, which is a
  program decision (the same class of decision as adding any gate), so it is
  recorded here rather than built in this PR.
- **(c) Current pin:** the oracles are pinned against the pre-migration
  module versions at origin/main `15110fecc` (the dispatch base this slice
  rebased onto). Byte-verified 2026-08-05 on this branch: each oracle was
  diffed against `git show 15110fecc:<module>` and differs ONLY by its
  documented header/import rewrites (the timing oracle's docstring +
  relative-import rewrite; the trace oracle's added docstring + two leading
  blank lines; the ram oracle's docstring replacement) — every other
  statement is byte-identical.

## Mutation campaign (anti-vacuity)

`scripts/phase5_cli_adapters_workflow_mutations.py` — 11 mutations applied
to the Rust kernels, each rebuilt and re-run through the six suites,
expecting failure, then reverted (source), with a post-campaign rebuild so
the installed extension is always left correct.

| Mutant | Kernel | What it changed | Killed by |
|---|---|---|---|
| M1 | compare_stage | `<=` → `<` for `passed` | differential (boundary case) |
| M2 | compare_stage | unguarded delta_pct division | differential (zero-baseline guard) |
| M3 | compare_stage | `f64::max` instead of `py_max` | differential (NaN asymmetry) |
| M4 | compare_stage | dropped `* 100.0` | differential (fixed: the first run hit the docstring copy, not the code) |
| M5 | p95 | multiply-divide rounding instead of Python `round` | differential (decimal discriminators) |
| M6 | p95 | `f64::total_cmp` sort instead of `py_cmp` | differential (NaN / -0.0 placement) |
| M7 | p95 | empty list returns 0.0 | differential (IndexError parity) |
| M8 | filter_decisions | `d["subject"]` instead of `d.get("subject")` | differential (missing-key None semantics) |
| M9 | find_rejected | dropped the subject check | differential (first-match subject scope) |
| M10 | copper_length | `dx*dx` instead of libm `pow` | differential — **survived round 1**; closed by adding full-precision discriminating segments (`test_measure_pow_vs_multiply_discriminators` — 4 cases, each asserted to genuinely discriminate pow-vs-multiply; the original 4th case was found inert in review 2026-08-05 and replaced by a searched successor; review 2026-08-05 round 2 found 3 of the 4 successors ALSO inert under Ubuntu CI — glibc 2.39 — where `pow(x, 2.0) == x*x` for most inputs, so the cases were re-searched to bite on BOTH darwin and glibc and re-verified byte-for-byte in the CI container); killed round 2 |
| M11 | copper_length | empty-string nets pass through | differential (falsy-net skip) |

M10 is the campaign's honest survivor-turned-kill: the initial randomized
differential used 6-decimal-rounded coordinates whose squares never landed
on a `pow`-vs-multiply ulp boundary; the mutation sweep (exactly as the
Wave-4 guide predicts for the dlsym trap) found it, and the fix was a
**discriminating case** — full-precision deltas — not a weakened claim.
9 of 11 mutants were killed by the differentials alone; the PBT suites
provide the G4 vacuity-mutant belt (each property has a degenerate-kernel
test that must fail).

## R1 gate status

- **R1a** — bit-identical differentials vs verbatim oracles: green (120
  differential assertions across 4 modules/clusters; floats via
  `float.hex()`, type carried on every leaf, error parity via `canon_call`).
  Phase-1 convergence adds the 15-assertion differential suite (120
  randomized ConvergenceState trials plus explicit deterministic sequences)
  with the anti-vacuity port-is-Rust tripwire.
- **R1b** — performance/no-regression arm: the migrated compute is invoked
  per CLI command (once per stage-entry), not in any hot loop; per the
  guide, this is the no-regression-beyond-noise arm. The rust kernels are
  trivially faster or equal for the per-call work; no speedup claim is
  made. (The pr-perf-check baseline covers the CLI surfaces' wall time via
  the timing-gate itself.) The pipeline-feasibility compute is preflight /
  convergence / derivation — invoked once per pipeline run, never hot.
  Phase-1 convergence is a pure-delegation carve-out (<1ms per check; FFI
  crossing + pyclass construction is the only added overhead).
- **R1c** — >= 5 non-vacuous properties per verification unit: timing 6,
  trace_commands 6, route_and_measure 5, pipeline-feasibility CLUSTER 6
  (P1..P6, all G4-vacuity-guarded with reachability witnesses),
  Phase-1 convergence 6 (P1..P6, each with two mutation guards + witnesses),
  U4 pipeline-state 8 (P1..P8, each with mutation guards).
- **R1d** — >= 3 metamorphic relations/unit: timing 4, trace_commands 3,
  route_and_measure 3, pipeline-feasibility cluster 4 (MR1..MR4, all
  bit-exact claims), Phase-1 convergence 4 (MR1..MR4, mutation-guarded).
  U4: metamorphic relations are not claimed — the migrated surface is pure
  data (dataclass semantics); the G4 properties and the randomized
  differential arm cover it (recorded in the U4 section below).
- **R1e** — this document: structural proof + explicit non-applicability
  note for induction.
- **R1f** — TDD: the four differentials were written first and demonstrated
  RED (collection failure — `temper_orchestration` did not exist / the shims
  did not delegate), then GREEN. The pipeline-feasibility differential's RED
  commit (ede48808) predates its kernels' GREEN commit (6cc75679) in git
  history. The Phase-1 convergence differential's RED commit (5cfe4880)
  predates its port's GREEN commit (571c84ca). The U4 pipeline-state
  differential's RED commit (0ba59658 — oracle + differential) predates its
  port's GREEN commit (9a817982 — pyclasses + shim) in git history.
- **R1g** — borrow over clone; no `unwrap` outside tests; `catch_unwind`
  at every pyo3 boundary (pyo3's `#[pyfunction]`/`#[pyclass]` expansion);
  clippy `unwrap_used`/`expect_used` denied. U4 adds an explicit
  `catch_unwind` stage guard (`stage_guard` in `derivation_stage.rs`): a
  panic inside a stage body is converted to `StageError { kind: Fatal }`
  rather than unwinding through the `Python::attach` frame (the plan's error
  model; the runner test's panic path is covered by the stage error report).
- **R1h** — not physics-gated (recorded above).

## Rust orchestration engine — U4 (pipeline state + Stage wiring)

The Rust Orchestration Engine plan (2026-08-09-001) ships its U4 unit here
(depends on U0/U1 + the U2/U3 feasibility kernels): the
`pipeline/state.py` data model migrates to `pipeline_state.rs` (the plan's
Phase C row "PipelineState→Rust config"), and the Wave-4 feasibility
kernels get their `Stage<BoardState>` wrappers (`derivation_stage.rs` +
`preflight_stage.rs`).

### What migrated

- `PipelinePhase`, `PipelineConfig`, `PipelineState` — Rust pyclasses
  bit-exact with the pre-migration `pipeline/state.py` (dataclass defaults,
  field get/set, `__eq__`/`__repr__`, unhashability, per-instance
  `default_factory` containers). `PipelineError` stays a Python exception
  (the plan's U4 row names only `PipelineConfig`/`PipelinePhase` for the
  Rust side; exceptions have no bit-exact pyclass mapping in scope).
  `pipeline/state.py` is now a delegation shim (public API unchanged; the
  four names re-exported by `temper_placer.pipeline` resolve identically).
- `DerivationStage` — wraps the `derive_emi_max_dist` /
  `derive_thermal_clearance` / `derive_si_max_placement_dist` /
  `mains_voltage_to_class_code` kernels as `Stage<BoardState>` (mirroring
  `derive_constraints_from_spec`).
- `PreflightStage` — wraps `component_area_ratio` /
  `proximity_rule_impossible` / `zone_over_capacity` /
  `loop_area_violation` / `isolation_barrier_too_large` as
  `Stage<BoardState>` (mirroring `PreflightChecker.run`'s five
  kernel-backed checks).

### G1 — differential oracle before Rust (TDD)

The differential suite `test_pipeline_state_rust_differential.py` and its
VERBATIM oracle `_pipeline_state_py_oracle.py` were committed first (RED:
`0ba59658` — the anti-vacuity `__module__` assertions failed), then the
implementation landed GREEN (`9a817982`). The oracle is the pre-migration
`state.py` at `57c083c0` (the last commit touching the module was
`0712b669`; the tree at the pin is byte-identical), pinned by sha256
(`182239b2…`). The oracle body was diffed against the module and is
byte-identical below the marker.

### G2 — behavioural A/B (bit-exact)

The differential drives BOTH arms with identical inputs and compares
`repr()` of every whole object and every per-field signature bit-exact
(repr is the exactest discriminator for Paths, Enum members, dicts with
Enum keys and floats — `canon` cannot represent Path/Enum leaves). 18/18
green: 16 phase members (value/name/repr/str/eq/hash), config defaults +
40 randomized kwargs sets + eq + mutation + unhashability, state defaults +
40 randomized kwargs sets + eq (incl. deep nested-config equality) +
mutation + default-factory independence, `PipelineError` phase retention.

### G3 — performance

Pure-delegation carve-out: the pipeline-state classes are constructed once
per pipeline run; the stage wrappers add a single FFI crossing per stage.
No regression beyond noise is possible or claimed.

### G4 — PBT (`test_pipeline_state_pbt.py`)

Eight non-vacuous properties (P1 config defaults, P2 kwargs round-trip, P3
repr self-describes, P4 eq symmetric + reflexive, P5 mutation observable,
P6 state defaults, P7 default-factory independence, P8 phase members
unique and self-equal), each with mutation guards via
`hypothesis.inner_test` (degenerate stand-ins swapped through the `_IMPL`
indirection). 22/22 green.

### G5 — metamorphic relations

Not claimed. The migrated surface is pure data (dataclass construction /
equality / repr / mutation); there is no computation to relate. The G4
properties plus the randomized differential arm cover the surface. (The
Wave-4 feasibility cluster already carries MR1..MR4 for the kernels the
stages delegate to.)

### G6 — induction

Not applicable — data-only module, no recursive computation. Structural
proof below.

### G7 — Rust bar

`cargo test` 71/71 green (incl. the 4-test runner suite
`tests/stages_runner.rs` sequencing both stages through
`PipelineRunner<BoardState>`); `cargo clippy --all-features --all-targets --
-D warnings` clean. No `unwrap`/`expect` in non-test code. Panic safety:
pyo3's `#[pyclass]` expansion wraps the pyclass boundaries; the stage
bodies additionally wrap `run()` in `stage_guard` (catch_unwind -> 
`StageError::Fatal`).

### G8 — R24 physics discipline

Not applicable — the pipeline-state data model and the stage wrappers gate
on no physics quantity (the kernels they delegate to are the Wave-4
feasibility cluster, already recorded not-physics-gated).

### Structural proof

**Claim (bit-identical parity).** For every field, constructor default and
method of the three pyclasses, the Rust behaviour is bit-identical to the
pinned pre-migration Python for every input in the differential suite's
domains, with the documented boundary choices below.

1. **repr by identity.** The dataclass `__repr__` renders every leaf via
   CPython's repr engine; the Rust `__repr__` calls CPython `repr()` on
   each field value (`format!`'s `{:.?}` diverges for float exponent
   notation and `{:?}` uses double quotes for strings). Parity is by
   identity, not by coincidence of formatter implementations.
2. **eq by identity.** Dataclass equality is exact-class + field-wise `==`.
   The Rust `__eq__` type-checks the other operand's type identity first,
   then compares each field with Python `==` (object fields) or Rust `==`
   (scalars; NaN != NaN and -0.0 == 0.0 behave identically in both).
3. **Unhashability.** Dataclasses are unhashable (`eq=True`,
   `frozen=False`); the Rust `__hash__` raises
   `TypeError("unhashable type: '...'")`. `PipelinePhase` members stay
   hashable (Enum singletons; equal members hash equally).
4. **Per-instance default factories.** `loops` and `phase_timings` get a
   FRESH `PyList`/`PyDict` per construction (the dataclass
   `field(default_factory=...)`), pinned by the differential's
   independence test.
5. **Stage message parity by identity.** The preflight message f-strings
   (`Fill ratio {ratio:.1%}`, `{min_d:.1f}`, `{max_d}`) are rendered by
   calling CPython's `format()` / `str()` (David-Gay semantics Rust's
   `{:.N}` does not reproduce bit-for-bit) — the documented boundary the
   Wave-4 cluster already records.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above):
- `PipelineError` stays a Python exception on the shim.
- The typed scalar fields (`epochs: i64`, `skip_*: bool`,
  `max_movement_mm: f64`, …) reject type-unsafe assignment (e.g. setting a
  `bool` field to an `int` raises TypeError) where the dataclass would
  store it. The PBT's mutation property draws type-appropriate values.
- An EXPLICIT `None` passed for `current_phase` / `loops` /
  `phase_timings` is treated as the omitted sentinel (dataclass default)
  rather than stored: all three fields are type-annotated containers/enums,
  so a caller passing `None` is outside the declared type. The differential
  never passes explicit `None` for them.
- `PipelineState.config` / `current_phase` / `failed_phase` are stored as
  `Py<PyAny>` (the dataclass does not type-enforce); the constructor
  supplies the dataclass defaults.
- The Stage wrappers' BoardState field mapping is a **Phase-C-pending
  placeholder contract** (D2 — no field is tightened speculatively):
  `DerivationStage` reads the `PcbSpecification` from `BoardState.config`
  and writes the derived constraints dict back to `BoardState.config`;
  `PreflightStage` reads board/netlist/constraints from
  `BoardState.{board,netlist,config}` and writes a plain-data report dict
  (the `PreflightReport` shape: `checks` + `overall` + `total_time_ms`)
  into `BoardState.violations`. The Python `PreflightCheck`/`PreflightReport`
  object construction is marshalling the Phase-C Python `run()` shim
  performs (the plan's boundary: Rust stages write typed results, the
  Python layer converts).
- `PreflightStage` returns `Ok(state)` with the FAIL **in** the report
  (matching `PreflightChecker.run`'s actual semantics). The plan's
  `StageErrorKind::Infeasible` sketch for "the preflight checker's FAIL
  result" is NOT adopted: it would diverge from the module's behaviour
  (Python returns the report; it does not raise). Missing BoardState fields
  are the stage's hard-error path (`Err(Fatal)` — exercised by the runner
  test's halt case).
- The derivation stage's `hv_lv_isolation_mm` safety-present path imports
  `temper_placer.core.net_types` (always importable in the real pipeline);
  the runner test exercises the no-safety 6.5mm fallback so the embedded
  interpreter needs no venv site-packages. `mains_voltage_to_class_code`
  is still exercised by the stage's safety path and by the Wave-4 kernel
  unit tests. The Python `warnings.warn` on the fallback is observability,
  not part of the derived dict, and is not reproduced.

### Differential / PBT / runner suites (U4)

| Suite | Location | Count |
|---|---|---|
| pipeline-state differential (oracle: `_pipeline_state_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/pipeline/test_pipeline_state_rust_differential.py` | 18 |
| pipeline-state PBT (P1..P8, mutation-guarded) | `packages/temper-placer/tests/pipeline/test_pipeline_state_pbt.py` | 22 |
| stage runner (sequences DerivationStage + PreflightStage through `PipelineRunner<BoardState>`) | `packages/temper-orchestration/tests/stages_runner.rs` | 4 |
| existing shim surface (all `tests/pipeline/*`, incl. convergence + feasibility differentials/PBT) | `packages/temper-placer/tests/pipeline/` | 506 |

## Rust orchestration engine — D1 (deterministic setup stages)

Phase D batch D1 of the Rust Orchestration Engine plan (2026-08-09-001):
the orchestration of the three deterministic setup stages
(`deterministic/stages/{setup,net_ordering,config_attach}.py`, ~330 LOC)
moves to `temper-orchestration` as `Stage<BoardState>` implementors
(`setup_stage.rs` + `net_ordering_stage.rs` + `config_attach_stage.rs`, with
the Python↔Rust BoardState conversion seam in `d1_bridge.rs`).

### What migrated

| Python stage | Rust stage | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `config_attach.py` (36) | `ConfigAttachStage` | `config` | `config` (only when absent) |
| `net_ordering.py` (47) | `NetOrderingStage` | `netlist`, `loops` | `net_order` |
| `setup.py` (250) | `DrcOracleSetupStage` + `NetClassSetupStage` | `board`, `netlist`, `placements` | `drc_oracle` (netlist mutated in place by NetClassSetupStage) |

The stages read the `Py<PyAny>` BoardState fields via py.getattr (D2: no
field is tightened speculatively — the conversion in `d1_bridge.rs` is a
pure Py pass-through, `net_order` being the one owned `tuple[str, ...] ↔
Vec<String>` field) and write the changed fields back through
`dataclasses.replace` from Rust. The Python shims stay thin: `run(state)`
crosses the FFI once per stage through the exported pyfunctions
(`run_drc_oracle_setup` / `run_net_class_setup` / `run_net_ordering` /
`run_config_attach`).

**What stays Python (evidence)**: the leaf objects the stages construct —
`ClearanceMatrix`, `DRCOracle`, `Pad`, `Point`, `NetClassRules`, and the
`order_nets` wire-marshalling shim — are Python classes whose numeric
bodies are already Rust kernels (temper-drc-rs / temper-geometry /
temper-rust-router); they are called from the Rust stage as thin delegation
(bit-exactness of that delegation is exactly what the differential pins).
The `Netlist.apply_net_class_mapping` call is the already-Rust pyclass
method. No new Python API is invented.

### G1 — differential oracle before Rust (TDD)

The three pre-migration modules are pinned VERBATIM as
`tests/deterministic/_setup_py_oracle.py`, `_net_ordering_py_oracle.py`,
`_config_attach_py_oracle.py` (only relative imports rewritten to absolute
paths — the compute bodies are byte-identical; each body's sha256 is pinned
in the differential, which fails on any drift).

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d1_rust_differential.py`: 20 tests
drive both arms with identical BoardState inputs and compare every
observable output bit-exactly — `state.config` (identity-preserving attach
semantics), `state.net_order`, the DRCOracle's registered-pad list and the
ClearanceMatrix state (defaults, `_net_class_rules`, `_net_to_class`,
`_differential_pairs`) across all branches (default / board-parse /
netlist-fallback / placements / duck-typed config / DesignRules /
differential-pairs / parsed-pads layer+PTH+shape+net-sentinel mapping), and
the per-net class after `NetClassSetupStage` (mutate + no-op paths).
Notable pinned semantics: the empty-net sentinel `__UNCONNECTED__`, the
layer mapping (`B.Cu`→3 / `In1.Cu`→1 / `In2.Cu`→2 / else→0), PTH detection
(drill > 0 or `.diameter`), unknown-shape normalization to `rect`, the
`R(-theta)` rotation convention, and the identity-preserving no-op paths.

### G3 — performance

Pure-delegation carve-out: each stage crosses the FFI once per `run()`; the
compute is unchanged (already-Rust kernels). No regression beyond the single
FFI crossing is possible or claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d1_pbt.py`)

Six non-vacuous properties (P1 config-None no-op, P2 config identity-attach,
P3 net-order permutation, P4 no-netlist preservation, P5 parsed-pad order +
layer mapping, P6 mapping-only-touches-named-nets), each with a
fails-for-mutant companion re-running the same body against a degenerate
stand-in and asserting the property trips — the established U4 PBT
vacuity-guard pattern.

### G5 — metamorphic

Not claimed: the D1 stages are orchestration over stateful Python objects,
not pure functions; the differential and PBT arms already pin the
behavioural surface. Recorded as N/A per the plan's per-module G5
discretion.

### G6 — induction

Non-applicability note: the stages are finite loops over caller-provided
collections (design_rules dicts, PadData lists, netlist components/pins);
no recursive or size-parameterized computation. Structural proof instead:
bit-exactness verified by the differential and the mutation campaign.

### G7 — Rust bar

No `unwrap` outside tests (clippy `unwrap_used`/`expect_used` = deny in the
lib target; the runner test file carries the tests-only allow). Every stage
body is wrapped in `stage_guard` (`catch_unwind` → `StageError::Fatal`).
Clippy clean on `--all-targets`.

### G8 — R24 physics

N/A — the stages gate on no physics quantity; the ClearanceMatrix/DRCOracle
numeric bodies they delegate to are already-differential-tested kernels.

### Differential / PBT / runner suites (D1)

| Suite | Location | Count |
|---|---|---|
| D1 differential (oracles: `_*_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d1_rust_differential.py` | 20 |
| D1 PBT (P1..P6, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d1_pbt.py` | 12 |
| D1 stage runner (sequences ConfigAttachStage + NetOrderingStage + DrcOracleSetupStage + NetClassSetupStage through `PipelineRunner<BoardState>`, with sys.modules-registered fakes for the venv-only Python modules) | `packages/temper-orchestration/tests/d1_stages_runner.rs` | 5 |

## Rust orchestration engine — D2 (deterministic zone stages)

Phase D batch D2 of the Rust Orchestration Engine plan (2026-08-09-001):
the orchestration of the three deterministic zone stages
(`deterministic/stages/{zone_geometry,zone_assignment,slot_generation}.py`,
~213 LOC) moves to `temper-orchestration` as `Stage<BoardState>` implementors
(`zone_geometry_stage.rs` + `zone_assignment_stage.rs` +
`slot_generation_stage.rs`, with the Python↔Rust BoardState conversion seam
extended in `d1_bridge.rs`). Depends on D1 (the same conversion seam and
Stage pattern).

### What migrated

| Python stage | Rust stage | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `zone_geometry.py` (105) | `ZoneGeometryStage` | `board` (width/height) | `zones` (frozenset of `Zone`) |
| `zone_assignment.py` (54) | `ZoneAssignmentStage` | `netlist` | `component_zone_map` (frozenset of `(ref, zone)`) |
| `slot_generation.py` (54) | `SlotGenerationStage` | `zones` | `zone_slots` (frozenset of `(zone_name, slots_tuple)`) |

The stages read the `Py<PyAny>` BoardState fields via py.getattr (D2: no
field is tightened speculatively — the `d1_bridge.rs` conversion stays a
pure Py pass-through) and write the changed fields back through
`dataclasses.replace` from Rust. The Python shims stay thin: `run(state)`
crosses the FFI once per stage through the exported pyfunctions
(`run_zone_geometry` / `run_zone_assignment` / `run_slot_generation`).
The `Zone` dataclass stays Python (kept by the shim; the stage constructs
its `Zone` objects by importing it) and `SlotGenerationStage.
_generate_slots_for_zone` stays as a leaf-delegation helper because
`ZoneAwareSlotGenerationStage` subclasses `SlotGenerationStage` and calls it
from its own `run` (a real consumer that bypasses this stage's `run`).

**What stays Python (evidence)**: the leaf kernels
(`temper_design_bundle_python.deterministic_stages.define_zone_layout` /
`scale_zone_bounds` / `assign_component_zones` / `generate_slots_for_zone`)
are the already-migrated Phase-5 first-slice kernels, called from the Rust
stages as thin delegation (bit-exactness of that delegation is exactly what
the differential pins). The `Zone` dataclass and the subclass-visible
`_generate_slots_for_zone` helper stay Python. No new Python API is
invented.

### G1 — differential oracle before Rust (TDD)

The three pre-migration modules are pinned VERBATIM as
`tests/deterministic/_zone_geometry_py_oracle.py`,
`_zone_assignment_py_oracle.py`, `_slot_generation_py_oracle.py` (only
relative imports rewritten to absolute paths; each body's sha256 is pinned
in the differential, which fails on any drift — the bodies were diffed
against `git show origin/main:<module>` and are byte-identical below the
marker).

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d2_rust_differential.py`: 21 tests
drive both arms with identical BoardState inputs and compare every
observable output bit-exactly — `state.zones` (projected to `(name,
bounds)` and canoned with `float.hex()`, keeping int-vs-float distinct),
`state.component_zone_map`, and `state.zone_slots` across the guards, the
default 4-zone layout (int and float boards), dict configs (with and
without `bounds_ratio`), CopperZone objects (flat 4-tuple Rect bounds
nested), mixed configs incl. the unknown-format `print` warning (stdout
captured and compared byte-for-byte), empty configs, the empty-zones
no-clobber path, spacing that produces the naive `+=` drift (0.1mm), and a
zone→assignment→slots chain. Notable pinned semantics: the identity-
preserving guards (both arms return the state object unchanged on a guard
hit, including the `frozenset()` BoardState defaults — the truthiness guard
fires on an EMPTY `zones` too, so pre-populated `zone_slots` survive an
empty-zones pass), the dict-branch default `[0, 0, 1, 1]`, the int-vs-float
type-carrying bounds, and the `dict(pairs)` → `frozenset(dict.items())`
insertion-order-preserving wrap.

### G3 — performance

Pure-delegation carve-out: each stage crosses the FFI once per `run()`; the
compute is unchanged (already-Rust kernels). No regression beyond the single
FFI crossing is possible or claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d2_pbt.py`)

Seven non-vacuous properties (P1 zone-geometry no-board guard, P2 the
4-zone layout covering the full board, P3 dict-config ratio scaling, P4
zone-assignment coverage with valid zones, P5 no-netlist guard, P6
slot-grids strictly inside their bounds with the half-cell anchor, P7
no-zones guard), each with a fails-for-mutant companion re-running the same
body against a degenerate stand-in and asserting the property trips — the
established U4 PBT vacuity-guard pattern. 14 tests green.

### G5 — metamorphic

Not claimed: the D2 stages are orchestration over stateful Python objects
(and their leaf compute is already metamorphic-covered by the Phase-5
kernels), not pure functions; the differential and PBT arms pin the
behavioural surface. Recorded as N/A per the plan's per-module G5
discretion (same ruling as D1).

### G6 — induction

Non-applicability note: the stages are finite loops over caller-provided
collections (zone configs, netlist components, zone frozensets); no
recursive or size-parameterized computation. Structural proof instead:
bit-exactness verified by the differential and the PBT vacuity mutants.

### G7 — Rust bar

No `unwrap` outside tests (clippy `unwrap_used`/`expect_used` = deny in the
lib target; the runner test file carries the tests-only allow). Every stage
body is wrapped in `stage_guard` (`catch_unwind` → `StageError::Fatal`).
Clippy clean on `--all-targets -- -D warnings`; `cargo test` 85/85 green
(71 lib + 5 D1 runner + 5 D2 runner + 4 U4 runner).

### G8 — R24 physics

N/A — the stages gate on no physics quantity; the leaf kernels they delegate
to are already-differential-tested Phase-5 kernels.

### Differential / PBT / runner suites (D2)

| Suite | Location | Count |
|---|---|---|
| D2 differential (oracles: `_*_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d2_rust_differential.py` | 21 |
| D2 PBT (P1..P7, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d2_pbt.py` | 14 |
| D2 stage runner (sequences ZoneGeometryStage + ZoneAssignmentStage + SlotGenerationStage through `PipelineRunner<BoardState>`, with sys.modules-registered fakes for the venv-only Python modules) | `packages/temper-orchestration/tests/d2_stages_runner.rs` | 5 |

## Rust orchestration engine — D3 (deterministic clearance-grid stages)

Phase D batch D3 of the Rust Orchestration Engine plan (2026-08-09-001):
the clearance-grid batch (`deterministic/stages/_grid_stage.py`, 416 LOC, is
the migrated stage; the differential oracles also pin
`_grid_{core,hv,fence}.py` — 747 LOC of helper/data surface — verbatim so
the whole batch is behaviourally anchored) moves to `temper-orchestration`
as a `Stage<BoardState>` implementor (`grid_stage.rs`, with the `_grid_hv`
and `_grid_fence` helper orchestrations as Rust kernels in `grid_hv.rs` /
`grid_fence.rs` and the Python↔Rust BoardState conversion seam extended in
`d1_bridge.rs`). Depends on D1 (the conversion seam + Stage pattern).

### What migrated

| Python module | Rust entity | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `_grid_stage.py` (416) | `ClearanceGridStage` (Stage impl) | `board` (width/height), `netlist`, `placements` | `grid` (a `ClearanceGrid` Python object) |
| `_grid_hv.py` (126) | `run_hv_pad_set` (grid_hv.rs) | — (called by the stage; returns the HV-pad `(ref, pin)` set) | — |
| `_grid_fence.py` (139) | `run_grid_fence_check` + `run_grid_perf_budget` (grid_fence.rs) | — (called by the stage / public shims) | — |
| `_grid_core.py` (482) | — | the `ClearanceGrid` DATA TYPE stays Python (see below) | — |

The Rust stage transcribes `_grid_stage.py`'s `run()` orchestration: the
pad-collection loop (net → pads mapping, per-pad geometry via
`pin_world_position` + `pad_sizes`), the per-net blocking pass
(net-class-aware clearance with the inner-layer cap), the pre-route HV
creepage-expansion pass (HV-pad resolution via `_grid_hv.hv_pad_set`,
per-layer `effective_creepage`, rect/circle Minkowski expansion,
`_grid_fence._EXPANSION_LOG` append), the U3 fence invocation and the EXP-13
exclusion-zone blocking (direct `arr[row, col] = -2` numpy writes). The
stage reads the `Py<PyAny>` BoardState fields via py.getattr (D2: no field
is tightened speculatively) and writes the `grid` field back through the
`d1_bridge.rs` write-back (identity-based: the dataclass `==` compares only
the four constructor dims, so a fresh equal-dims grid would otherwise be
skipped; the stage either produces a NEW grid object or returns the state
unchanged on the guard). The Python shim stays thin: `run(state)` crosses
the FFI once per stage through `run_clearance_grid_stage`.

**What stays Python (evidence)**: the `ClearanceGrid` data type
(`_grid_core.py`, 482 LOC) is NOT orchestration — it is the numpy-backed
grid container whose cell-rasterisation compute (`block_circle_into_grid_py`
/ `block_segment_into_grid_py` / `block_rect_into_grid_py` /
`clear_circle_from_grid_py` / `occupancy_bitmap_row_py`) is already Rust
in temper-geometry's `grid_raster.rs`, plus the matplotlib
`export_visualization` and `export_stats`. It is the marshalling-pending
type of `BoardState.grid`, consumed by downstream Python routing code; it
stays Python exactly like `board.py`/`netlist.py` (Phase 2 residual
decisions). The `ConfigError` / `FenceViolation` exception classes stay
Python (raised from the Rust kernels via the Python classes; the FFI
wrapper re-raises the ORIGINAL exception type, so `pytest.raises(FenceViolation)`
and callers that catch `ConfigError` see the real class, not a RuntimeError
wrapper — the D3-only refinement: `run_clearance_grid_stage` calls
`run_guarded` which threads the raw `PyErr` instead of `stage_guard`'s
StageError conversion). The `_EXPANSION_LOG` module-level list stays Python
(the stage clears+appends it via FFI so the U3 tests and the U4a closure
test can inspect it). `effective_creepage` / `_layer_index_to_name` /
`_STANDARD_LAYER_NAMES` / `OUTER_COPPER_LAYERS` stay Python (leaf helpers
and board constants). No new Python API is invented.

### G1 — differential oracle before Rust (TDD)

The four pre-migration modules are pinned VERBATIM as
`tests/deterministic/_grid_core_py_oracle.py`, `_grid_hv_py_oracle.py`,
`_grid_fence_py_oracle.py`, `_grid_stage_py_oracle.py` (only relative
imports rewritten to absolute paths so the oracle stage uses the oracle
helpers; each body's sha256 is pinned in the differential, which fails on
any drift). The RED commit (`af630131`) landed the oracles + differential +
PBT with the anti-vacuity tripwire failing (the shims did not yet delegate);
the GREEN commit (`68d37377`) landed the port.

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d3_rust_differential.py`: 23 tests
drive both arms with identical BoardState inputs and compare the FULL grid
internal state bit-exactly — the int32 trace and pad net-id arrays (via
`numpy.ndarray.tolist()`), the net registration maps (pinning the net-id
ASSIGNMENT ORDER), the dimensions, the `_EXPANSION_LOG` side effect
entry-for-entry, and every exclusion-zone print (stdout captured and
compared byte-for-byte). Notable pinned semantics: the identity-preserving
no-board guard; the placements gate (a component present in `placements`
with `initial_position=None` is processed, an absent one is skipped — the
pad position itself comes from `pin_world_position`, not the placement);
PTH all-layer vs layer-mapped target layers; rect-blocking rotation 0/90
swaps; the mechanical (empty-net) zero-clearance blocking; the HV expansion
circle/rect branches, the inner-layer 0.30 factor and the spatial
zone→component fallback; `ConfigError` parity on both unresolvable-zone
messages; `FenceViolation` parity via a patched fence on BOTH arms; the
fence violation dicts (reasons with `:.3f` rendered via CPython
`__format__` — bit-exact by construction); and a zone→assignment→slots→grid
pipeline chain.

### G3 — performance

Pure-delegation carve-out: the stage crosses the FFI once per `run()`; the
grid rasterisation and creepage compute are unchanged (already-Rust
kernels). No regression beyond the single FFI crossing is possible or
claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d3_pbt.py`)

Eight non-vacuous properties (P1 no-board guard, P2 empty-netlist empty
grid, P3 pads block their own location, P4 cross-net mutual blocking with
own-net transparency, P5 net ids assigned in pin-first-seen order 1..N, P6
`hv_pad_set` explicit-refdes resolution, P7 perf-budget floor exemption +
overrun message, P8 the HV expansion strictly grows the blocked count), each
with a fails-for-mutant companion re-running the same body against a
degenerate stand-in and asserting the property trips — the established U4
PBT vacuity-guard pattern. 16 tests green.

### G5 — metamorphic

Not claimed: the D3 surface is orchestration over stateful Python objects
(and the leaf kernels it delegates to are already metamorphic-covered), not
pure functions; the differential and PBT arms pin the behavioural surface.
Recorded as N/A per the plan's per-module G5 discretion (same ruling as D1/D2).

### G6 — induction

Non-applicability note: the stage is a finite loop over caller-provided
collections (netlist components/pins, pad layers, HV zones, expansion-log
entries); no recursive or size-parameterized computation. Structural proof
instead: bit-exactness verified by the differential and the PBT vacuity
mutants.

### G7 — Rust bar

No `unwrap`/`expect` outside tests (clippy `unwrap_used`/`expect_used` =
deny in the lib target; the runner test file carries the tests-only allow).
`cargo test` 90/90 green (71 lib + 5 D1 + 5 D2 + 5 D3 + 4 U4 runner);
`cargo clippy --all-features --all-targets -- -D warnings` clean. Panic
safety: `run_guarded` wraps the stage body in `catch_unwind` (a Rust panic
becomes a Python RuntimeError instead of unwinding through the pyo3 frame),
and pyo3's `#[pyfunction]` expansion additionally wraps every exported body.

### G8 — R24 physics

N/A — the stage gates on no physics quantity; the creepage clearances it
applies are configuration constants threaded through the already-tested
temper-geometry kernels. Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every input in the differential
suites' domains, the Rust stage produces a `BoardState.grid` bit-identical
to the pinned pre-migration oracle's. The load-bearing equivalences:

1. **Net-id registration order.** The grid's `get_net_id` calls happen in
   blocking-call order; the Rust stage reproduces the exact iteration order
   (components → pins → nets in first-seen order → exclusion-zone nets in
   zone order), pinned by the canon's net-map projection.
2. **`int(round(rotation)) % 180` is CPython's `round`** (banker's rounding)
   applied to the ORIGINAL rotation object — Rust `f64::round` is
   half-away-from-zero and diverges on `.5` boundaries.
3. **`max(size.X, size.Y)` is CPython `max`** (first-arg-wins on NaN/ties),
   not `f64::max`.
4. **F-string messages by identity.** The fence `reason` (`:.3f`) and perf
   warning (`:.1f`) render via CPython `__format__` on the exact sample /
   f64 values (David-Gay dtoa is not reproducible from Rust `{:.N}`); the
   `ConfigError` messages render via CPython `str()` on the original
   objects (int-vs-float type-carrying preserved); the exclusion-zone
   prints via `str()` of the original zone attributes.
5. **Exception type propagation.** `FenceViolation` / `ConfigError` are
   raised through their Python classes and re-raised by the FFI wrapper with
   the original type (`run_guarded` threads the raw `PyErr`), matching the
   oracle's raise — pinned by the error-parity tests and the existing
   `test_fence_pipeline_halts_on_violation` (which monkey-patches the fence
   module and expects `pytest.raises(FenceViolation)`).
6. **Fence called through the Python module at runtime.** The stage invokes
   `_grid_fence.check_clearance_grid_conservatism` / `_grid_fence`'s
   `_EXPANSION_LOG` / `_grid_hv.hv_pad_set` via `PyModule::import` at
   runtime — the monkey-patch seam the U3 tests depend on, and the reason
   the temper-geometry leaf kernels `closest_component_for_zone_py` /
   `fence_samples_py` are ledgered as wired-but-scan-invisible in
   `.unwired-kernel-inventory` (the Python AST scan cannot see
   cross-extension Rust→Python calls).

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above): `_grid_core.py`'s `ClearanceGrid` data type
stays Python (JUSTIFIED-KEEP data type, like `board.py`/`netlist.py`); the
exception classes and `_EXPANSION_LOG` stay Python; the exclusion-zone
writes reproduce the oracle's missing `_invalidate_cache()` (the stage does
not invalidate either — a faithful wart).

### Differential / PBT / runner suites (D3)

| Suite | Location | Count |
|---|---|---|
| D3 differential (oracles: `_grid_{core,hv,fence,stage}_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d3_rust_differential.py` | 23 |
| D3 PBT (P1..P8, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d3_pbt.py` | 16 |
| D3 stage runner (ClearanceGridStage alone and in a zone→grid chain through `PipelineRunner<BoardState>`, with sys.modules-registered fakes for the venv-only Python modules incl. a tuple-indexable fake grid) | `packages/temper-orchestration/tests/d3_stages_runner.rs` | 5 |
| pre-existing grid suites (leaf-kernel differentials/PBT, `test_clearance_grid.py` incl. the fence monkey-patch test, `test_clearance_expansion_regression.py`, the njit-fallback test) | `packages/temper-placer/tests/deterministic/` | 172 |

## Rust orchestration engine — D4 (deterministic assignment stages)

Phase D batch D4 of the Rust Orchestration Engine plan (2026-08-09-001):
the deterministic assignment batch (`deterministic/stages/component_assignment.py`,
247 LOC, and the DRC fence validator of
`phased_component_assignment_validator.py`, 353 LOC) moves to
`temper-orchestration`. `ComponentAssignmentStage` becomes a
`Stage<BoardState>` implementor (`component_assignment_stage.rs`); the
validator's coverage / non-over-claim compute becomes a Rust kernel
(`run_phased_validator_hv` in `phased_component_assignment_validator_stage.rs`)
returning `(field, value, reason)` triples that the Python shim wraps in the
router_v6 `StageDRCFailure`. `phased_component_assignment.py` (49 LOC) is a
mixin aggregation with zero standalone orchestration — its `run()` lives in
the D5 mixins, so D4 leaves it as the D5 carrier and migrates its
D4-visible consumer, the validator. Depends on D1 (the conversion seam +
Stage pattern), D2/D3 (the populated `component_zone_map` / `zone_slots`
fields the stage reads).

### What migrated

| Python module | Rust entity | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `component_assignment.py` (247) | `ComponentAssignmentStage` (Stage impl) + `run_component_assignment` / `run_component_assignment_kernel` pyfunctions | `netlist`, `component_zone_map`, `zone_slots`, `component_domain_map`, `domain_regions` (+ the stage-config `slot_spacing` / `fixed_placements`) | `placements` (frozenset of `(ref, (x, y))`) |
| `phased_component_assignment_validator.py` (353) | `run_phased_validator_hv` / `phased_validator_hv` (coverage + non-over-claim scans; `(field, value, reason)` triples) | `netlist`, `design_rules`, `placements`, `used_slots`, `zone_slots` | — (DRC-fence validator; the shim wraps the triples in `StageDRCFailure`) |
| `phased_component_assignment.py` (49) | — | the class aggregation stays Python as the D5 carrier (see below) | — |

The Rust stage transcribes `component_assignment.py`'s `run()` orchestration:
the identity-preserving state guards, `_domain_lookups` (the per-ref domain
map + the HV_edge/LV_interior region dict), the GEOS domain filter
PRECOMPUTED into the per-ref `domain_ok` slot set (the loop structure, the
netlist-order `seen_refs` de-duplication and the `region.covers(Point(x, y))`
predicate all driven Rust-side through the shapely objects at runtime), the
sheetpath-first/ref-fallback fixed-placement resolution, the greedy-kernel
call (`temper_design_bundle_python.deterministic_leaves.assign_components_to_slots`
via runtime `PyModule::import`), the `dict(...)` wrap and the
`frozenset(placements.items())` write. The validator kernel reproduces the
whole `validate_phased_component_assignment_hv` orchestration: `_creepage_mm`
(max across HV/AC net classes, CPython `max` first-arg-wins), `_absolute_hv_pins`
(the net-class + safety resolution and the absolute `placed + pin_relative`
positions), `_flatten_slots`, the saturation short-circuit (`math.hypot`
called via the math module), the fallback `used_slots` recompute AND the
legitimate-origin set through the D5 mixin helpers (`_get_footprint_radius` /
`_effective_ghost_pad_radius` called on a `PhasedComponentAssignmentStage`
instance constructed via `__new__` exactly like the oracle), and the two
failure scans. The bucketed slot-index kernels (`infer_slot_spacing_py` /
`build_slot_index_py` / `slots_within_radius_py`) stay single-source in
`temper-design-bundle` and are called through it. The stage reads the
`Py<PyAny>` BoardState fields via py.getattr (D2: no field is tightened
speculatively) and writes the `placements` field back through the
`d1_bridge.rs` write-back (frozenset `==`-comparison: an unchanged stage on
the guard returns the ORIGINAL state object — identity preserved).

**What stays Python (evidence)**: the shapely/GEOS domain filter itself
(`region.covers(Point)`) — the Rust stage drives the predicate through the
shapely objects, the same calls in the same order as the oracle; the greedy
kernel and the slot-grid kernels stay single-source in design-bundle. In the
validator, the router_v6 `StageDRCFailure` construction stays Python (the
kernel returns plain triples — the shim's `validate_phased_component_assignment_hv`
wraps them), and the D5 mixin methods `_get_footprint_radius` /
`_effective_ghost_pad_radius` (and the `PhasedComponentAssignmentStage`
aggregation in `phased_component_assignment.py` — its `run()` orchestration
is the D5 `_phase_*` mixins, out of scope for D4) stay Python. The small
state-extraction bindings `_absolute_hv_pins` / `_creepage_mm` stay Python
(public module API exercised by `tests/property/test_ghost_pad_injection.py`);
the Rust kernel inlines the same computation, so the two are kept honest by
the differential. `phased_component_assignment.py` (49 LOC) is a mixin
aggregation with zero standalone orchestration — migrating it would mean
moving the D5 mixin `run()`; D4 records it as the D5 carrier. The
`math.hypot` saturation check and the failure reason f-strings render via
CPython (the `str.format` calls and the math module), so David-Gay float
repr / tuple str / hypot semantics are identical by construction.

### G1 — differential oracle before Rust (TDD)

The two pre-migration modules are pinned VERBATIM as
`tests/deterministic/_component_assignment_py_oracle.py` and
`_phased_component_assignment_validator_py_oracle.py` (only the two relative
imports of `component_assignment.py` rewritten to absolute paths so the
oracle imports from the test tree; each body's sha256 is pinned in the
differential, which fails on any drift). The RED commit (`2546d5e9`) landed
the oracles + differential + PBT with the anti-vacuity tripwire failing (the
shims did not yet delegate); the GREEN commit (`81f4c19e`) landed the port.

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d4_rust_differential.py`: 25 tests
drive both arms with identical BoardState inputs and compare bit-exactly —
the `placements` frozenset through `float.hex()` (content; the ordering
semantics pinned through who-won-the-best-slot), the identity-preserving
guards, the sheetpath-first fixed-placement resolution (dict and list forms,
unknown keys skipped), the cross-zone fallback, the GEOS domain filter
(confinement, the empty-covered-set-unfiltered semantics, the
`covers`-keeps-boundary case), and — for the validator — the `StageDRCFailure`
lists projected to `(field, value.hex, reason)` IN ORDER with the reason
strings byte-for-byte (coverage failures in pin order then slot order,
over-claim failures in the `used_slots` set-iteration order reproduced by
building the same Python `set`), the degenerate paths (no netlist, zero
creepage, saturation creepage, empty zone slots), the fallback recompute
path, the used_slots-attr precedence, and a full end-to-end run of the D5
Python phased placer whose output both validator arms must judge identically.
A zone→assignment→slots→component-assignment pipeline chain closes the batch.

### G3 — performance

Pure-delegation carve-out: the stage crosses the FFI once per `run()`; the
greedy assignment, the GEOS filter and the slot-grid kernels are unchanged.
No regression beyond the single FFI crossing is possible or claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d4_pbt.py`)

Eight non-vacuous properties (P1 no-netlist guard identity, P2 every
component placed on a generous grid, P3 unique slots + determinism, P4
domain-filter confinement, P5 no-netlist no-failures, P6 zero-creepage
no-failures, P7 saturation-creepage no-failures, P8 a coverage gap is
reported), each with a fails-for-mutant companion re-running the SAME body
against a degenerate stand-in and asserting the property trips — the
established U4/D2/D3 PBT vacuity-guard pattern. Every migrated surface is
reached by at least one property. 16 tests green.

### G5 — metamorphic

Not claimed: the D4 surface is orchestration over stateful Python objects
(and the leaf kernels it delegates to are already metamorphic-covered), not
pure functions; the differential and PBT arms pin the behavioural surface.
Recorded as N/A per the plan's per-module G5 discretion (same ruling as D1/D2/D3).

### G6 — induction

Non-applicability note: the stage and the validator kernel are finite loops
over caller-provided collections (netlist components/pins, zone slots,
fixed-placement entries, HV pins); no recursive or size-parameterized
computation. Structural proof instead: bit-exactness verified by the
differential and the PBT vacuity mutants.

### G7 — Rust bar

No `unwrap`/`expect` outside tests (clippy `unwrap_used`/`expect_used` =
deny in the lib target; the runner test file carries the tests-only allow).
`cargo test` 95/95 green (71 lib + 5 D1 + 5 D2 + 5 D3 + 5 D4 + 4 U4 runner);
`cargo clippy --all-features --all-targets -- -D warnings` clean. Panic
safety: the stage's `Stage::run` wraps its body in `stage_guard`
(`catch_unwind` — a Rust panic becomes a Python RuntimeError instead of
unwinding through the pyo3 frame), and pyo3's `#[pyfunction]` expansion
additionally wraps every exported body (the validator kernel returns
`PyResult` directly).

### G8 — R24 physics

N/A — the stage and the validator kernel gate on no physics quantity; the
creepage clearances are configuration constants threaded through the
already-tested design-bundle kernels. Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every input in the differential
suites' domains, the Rust stage / validator kernel produce outputs
bit-identical to the pinned pre-migration oracle's. The load-bearing
equivalences:

1. **Zone-dict insertion order.** `dict(state.component_zone_map)` /
   `dict(state.zone_slots)` are built via the builtins `dict()` over the
   ORIGINAL frozenset objects, so the dict insertion order is the
   frozenset's iteration order exactly like the oracle — order is load-bearing
   for the kernel's cross-zone fallback (first non-empty other zone wins).
2. **`domain_ok` keying.** Keyed in netlist component order with explicit
   `seen_refs` de-duplication; each entry's covered slot set is built by
   iterating `zone_slots.items()` in dict order and calling the SAME
   `region.covers(Point(x, y))` predicate — the GEOS filter stays Python and
   the Rust stage drives it, so parity is by construction. The empty-covered
   set leaves a ref out of `domain_ok`, which the kernel treats as unfiltered
   (the migrated semantics, pinned by the Phase-5 differential too).
3. **Fixed-placement resolution.** sheetpath-first then ref fallback, both
   the dict (`{"position": [...]}`) and bare list/tuple forms, `float()`
   conversions via pyo3 f64 extraction (int→float exact); unknown keys are
   skipped — pinned by the sheetpath-first and unknown-key tests.
4. **Failure reasons by identity.** The f-strings render via CPython
   `str.format` on the ORIGINAL slot / creepage / pin objects (David-Gay
   float repr and tuple str semantics); the `field` prefixes are plain str
   concatenation. The `math.hypot` saturation check is called through the
   math module, not reimplemented in Rust.
5. **Failure ORDER.** Coverage failures in pin order then per-pin slot-list
   order; over-claim failures in the `used_slots` Python-set iteration order.
   The Rust kernel builds `used_slots` / `legitimate_origin` as real Python
   `set`s with the same insertion sequence as the oracle, then iterates them
   via FFI — identical table order by construction.
6. **`max(max_creepage, candidate)` is CPython `max`** (first-arg-wins on
   NaN/ties), never `f64::max`.
7. **The mixin helpers are called, not reimplemented.** `_get_footprint_radius`
   / `_effective_ghost_pad_radius` are invoked on a
   `PhasedComponentAssignmentStage` instance built via `__new__` with
   `use_isolation_slots = False` — the identical construction the oracle
   uses, so the D5-surface helpers (and the `use_isolation_slots = False ⇒
   ring = creepage` invariant) stay single-source.
8. **The `_effective_ghost_pad_radius` creepage argument is a fresh Python
   float** of the computed `_creepage_mm` value (bit-identical to the
   oracle's `creepage`), and the pin centers `(cx, cy)` are rebuilt tuples
   of the extracted values, exactly like the oracle's unpack-and-rebuild.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above): shapely/GEOS stays Python (driven through FFI);
the slot-grid and greedy kernels stay single-source in design-bundle; the
router_v6 `StageDRCFailure` construction stays Python; the D5 mixin methods
and the `phased_component_assignment.py` class aggregation stay Python (the
D5 carrier); `_absolute_hv_pins` / `_creepage_mm` stay Python module API
(the kernel inlines the same computation).

### Differential / PBT / runner suites (D4)

| Suite | Location | Count |
|---|---|---|
| D4 differential (oracles: `_component_assignment_py_oracle.py` + `_phased_component_assignment_validator_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d4_rust_differential.py` | 25 |
| D4 PBT (P1..P8, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d4_pbt.py` | 16 |
| D4 stage runner (ComponentAssignmentStage alone, with fixed placements, with a domain filter, and the `phased_validator_hv` kernel, through `PipelineRunner<BoardState>` / the Rust-callable kernel with sys.modules-registered fakes incl. a fake greedy kernel + shapely stub) | `packages/temper-orchestration/tests/d4_stages_runner.rs` | 5 |
| pre-existing assignment/validator/ghost-pad suites (the Phase-5 kernel differentials/PBT, the U3 validator scenarios, the phased-placer suites, the ghost-pad property) | `packages/temper-placer/tests/deterministic/stages/` + `tests/property/` | 84 |

## Rust orchestration engine — Phase D batch D5 (zone-aware slot generation + phased component assignment)

Phase D batch D5 of the Rust Orchestration Engine plan (2026-08-09-001): the
deterministic zone-aware batch (`deterministic/stages/zone_aware_slot_generation.py`,
567 LOC, and the phased-component-assignment mixins `_phase_core.py` 326 +
`_phase_zones.py` 410 + `_phase_rotation.py` 259 + `_phase_validation.py` 195,
~1,757 LOC) moves to `temper-orchestration`. `ZoneAwareSlotGenerationStage`
becomes a `Stage<BoardState>` implementor (`zone_aware_slot_generation_stage.rs`);
`PhasedAssignmentStage` (`phased_assignment_stage.rs`) transcribes the
`PhasedComponentAssignmentStage` run() orchestration that the D4 note flagged
as living in the D5 mixins. Depends on D1 (the conversion seam + Stage
pattern), D2/D3 (the populated `zones` / `zone_slots` fields) and D4 (the
`placements`/`used_slots` write-back surface).

### What migrated

| Python module | Rust entity | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `zone_aware_slot_generation.py` (567) | `ZoneAwareSlotGenerationStage` (Stage impl) + `run_zone_aware_slot_generation` pyfunction | `zones`, `board`, `netlist` (+ the stage-config `slot_spacing_mm` / `copper_zone_margin` / `yaml_copper_zones` / `yaml_isolation_slots` / `net_class_rules`) | `zone_slots` (frozenset), `reclaim_by_pin_pair` (K4 reclaim dict or None) |
| `_phase_core.py` (326) | `PhasedAssignmentStage` (Stage impl) `run()` body: guards, `compiler.validate` warnings, design-rules attach, `_domain_lookups`, phase dispatch, frozenset writes | `netlist`, `component_zone_map`, `zone_slots`, `board`, `design_rules`, `component_domain_map`, `domain_regions` (+ the Python stage instance as the config carrier) | `design_rules`, `placements`, `used_slots` |
| `_phase_zones.py` (410) | `_place_template` / `_place_proximity` / `_place_optimize` / `_simple_greedy_placement` / `_filter_by_domain` / the `_select_best_slot` scoring loop (+ `run_phase_select_best_slot` FFI) | — | — |
| `_phase_rotation.py` (259) | `_reserve_slots_with_hv` / `_reserve_slots` (footprint + HV creepage rings) | — | — |
| `_phase_validation.py` (195) | `_apply_bottleneck_filter` is CALLED back on the stage (seed-filter surface stays Python) | — | — |

The Rust stages transcribe the pre-migration orchestration wholesale:
`zone_aware` runs the isolation-slot filter (netlist `comp_pos`/`comp_by_ref`,
the K4 reclaim formula with `_hv_clearance_overrides` driven through CPython
`re` and the pow-arithmetic pin pitch), `_get_copper_zones` (YAML +
`board.copper_zones` + the `board.zones` net-class scan over
`POWER_NET_NAMES`), the no-filter plain-generation branch, the per-zone slot
walk with the copper + isolation-cutout filters, the F.Cu / statistics log
lines (CPython `str.format`) and the `zone_slots` / `reclaim_by_pin_pair`
writes. `phased` drives the state guards (identity-preserving), the phase
dispatch over `constraints.placement_priority`, the three placement methods,
the footprint-size sort (CPython tuple-key semantics), the cross-zone
fallback, the seed-filter call-back, the shapely domain filter, the best-slot
scoring (CPython `min` first-minimum-wins) and the footprint + HV ghost-pad
reservation (with the nearest-other-HV-pin reduction through
`_effective_ghost_pad_radius`). The `d1_bridge.rs` write-back gains the
`reclaim_by_pin_pair` field and the `used_slots` / `design_rules` candidates,
with a faithful clear-a-field write-back (a changed field whose Rust value is
None writes Python None).

**What stays Python (evidence)**: the design-bundle leaf kernels — the
slot-grid walk (`generate_slots_for_zone`), the ray casting
(`point_in_polygon_py`), the AABB test (`slot_intersects_iso_py`), the HPWL
kernel (`compute_wirelength_py`), the U2 reduction
(`effective_ghost_pad_radius_py`) and the bottleneck kernel
(`find_critical_bottleneck_violations_py`) — stay single-source and are
driven through FFI (the D2–D5 delegation boundary). `isolation_slot_aabb`
(`temper_placer.io.isolation_slot_geometry`, re-exported from
temper-io-types) stays Python. The `POWER_NET_NAMES` classification set stays
a module constant (the Rust stage reads it through FFI). The constraint
compiler (`self.slot_filter` / `self.slot_scorer`), the shapely
`_filter_by_domain` predicate, `routability_penalty` and the `_hv_clearance_overrides`
regex all stay single-source and are driven from Rust. The mixin helpers
`_get_footprint_radius` / `_effective_ghost_pad_radius` /
`_compute_wirelength` / `_apply_bottleneck_filter` / `_is_hv_ref` stay Python
methods (public API, directly exercised by the pre-existing suites) and are
called back on the stage — the D4 `__new__`-construction pattern. The
router_v6 DRC-fence call-back (`register_validator` / `run_validators`) stays
Python in the shim's `run()` (router_v6 surface, the D4 `StageDRCFailure`
convention), and `_check_critical_bottlenecks` / `find_critical_bottleneck_violations`
stay Python (the `is_drc_fence_fail_enabled` SSOT source test
`test_phased_drc_fence_flip.py` requires the former's body). All interpolated
log messages render through CPython `str.format` (David-Gay `:.1f`/`:.2f` and
list reprs).

### G1 — differential oracle before Rust (TDD)

The pre-migration modules are pinned VERBATIM as
`tests/deterministic/_zone_aware_slot_generation_run_py_oracle.py` (the run
orchestration, isolation filter, copper-zone collection, K4 helpers) and
`tests/deterministic/_phased_assignment_py_oracle.py` (the four `_phase_*`
mixins + the `phased_component_assignment.py` aggregation, concatenated into
one module; only relative imports rewritten to absolute paths); each body's
sha256 is pinned in the differential, which fails on any drift. The RED
commit (`4333e62d`) landed the oracles + differential + PBT with the
anti-vacuity tripwire failing (the shims did not yet delegate); the GREEN
commits (`274b7cd4` zone-aware, `5dec4ca7` phased) landed the ports.

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d5_rust_differential.py`: 24 tests
drive both arms with identical BoardState inputs and stage constructor args
and compare bit-exactly — `zone_slots` and `reclaim_by_pin_pair` projected
through `float.hex()`, `placements` + `used_slots` through the same canon, the
identity-preserving guards, the no-zones reclaim write, the copper-zone
polygon / bounds-margin / wrong-layer filtering, the isolation-cutout + K4
reclaim (with the net-class override and the per-slot pin pitch), the phased
template / proximity / optimize / domain-filter / no-phases-fallback paths,
the HV ghost-pad rings, the design-rules attach, the unknown-phase-method
warning path, the D2→D5 pipeline chain and a cross-batch zone-aware→phased
run. `float.hex()` pins the libm-`pow` squares and `f64::sqrt` distances
bit-for-bit.

### G3 — performance

Pure-delegation carve-out: each stage crosses the FFI once per `run()`; the
slot-grid / ray-casting / AABB / wirelength / reduction / bottleneck kernels,
the constraint compiler and shapely are unchanged. No regression beyond the
single FFI crossing is possible or claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d5_pbt.py`)

Seven non-vacuous properties (P1 no-zones path writes the reclaim, P2 copper
filter + determinism, P3 K4 reclaim clamp, P4 no-netlist guard identity, P5
every component placed on a generous grid with unique slots + determinism, P6
HV creepage rings land in `used_slots` when the ring overlaps the grid, P7
cross-run determinism), each with a fails-for-mutant companion re-running the
SAME body against a degenerate stand-in — the established U4/D1-D4 PBT
vacuity-guard pattern. 14 tests green.

### G5 — metamorphic

Not claimed: the D5 surface is orchestration over stateful Python objects
(and the leaf kernels it delegates to are already metamorphic-covered), not
pure functions; the differential and PBT arms pin the behavioural surface.
Recorded as N/A per the plan's per-module G5 discretion (same ruling as D1–D4).

### G6 — induction

Non-applicability note: the stages are finite loops over caller-provided
collections (zones, slots, netlist components/pins, phases); no recursive or
size-parameterized computation. Structural proof instead: bit-exactness
verified by the differential and the PBT vacuity mutants.

### G7 — Rust bar

No `unwrap`/`expect` outside tests (clippy `unwrap_used`/`expect_used` = deny
in the lib target; the runner test file carries the tests-only allow).
`cargo test` 100/100 green (71 lib + 5 D1 + 5 D2 + 5 D3 + 5 D4 + 5 D5 + 4 U4
runner); `cargo clippy --all-features --all-targets -- -D warnings` clean.
Panic safety: both stages wrap their bodies in `stage_guard`
(`catch_unwind` — a Rust panic becomes a Python RuntimeError instead of
unwinding through the pyo3 frame), and pyo3's `#[pyfunction]` expansion
additionally wraps every exported body.

### G8 — R24 physics

N/A — the stages gate on no physics quantity; the creepage clearances are
configuration constants threaded through the already-tested design-bundle
kernels. Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every input in the differential
suites' domains, the Rust stages produce outputs bit-identical to the pinned
pre-migration oracle's. The load-bearing equivalences:

1. **libm `pow` squares.** `(a - b) ** 2` in `_reserve_slots`,
   `_distance`, `_resolve_pin_pitch_mm` and the nearest-HV-pin scan is
   CPython `float ** float` = libm `pow` — routed through `host_math::pow`
   (the same dlsym-resolved host libm `copper_length` uses); `** 0.5` in the
   K4 pin pitch is `pow(x, 0.5)`, not `sqrt`. `math.sqrt` is the
   correctly-rounded IEEE sqrt == `f64::sqrt`.
2. **CPython `max`/`min`.** `py_max`/`py_min` reproduce first-arg-wins on
   ties/NaN; the best-slot and nearest-HV-pin `min` scans keep the first
   element on ties (strict `<`).
3. **Sort key semantics.** The footprint-size sort is CPython `sorted` on
   `(-size, ref)` tuple keys: stable, with the first element compared by
   Python `<`-then-`==` (so `-0.0`/`0.0` ties and NaN fall through to the
   ref string exactly like CPython tuple comparison).
4. **Dict/list insertion order.** The phase-dispatch order, the cumulative
   `{**a, **b}` placement merges, the `net_pins`/`zone_slots`/`all_slots`
   orders and the reclaim dict's insertion order are reproduced by building
   the same Python dicts/lists through FFI in the same sequence.
5. **Mixin helpers are called, not reimplemented.** `_get_footprint_radius`,
   `_effective_ghost_pad_radius`, `_compute_wirelength`,
   `_apply_bottleneck_filter` and `_is_hv_ref` are invoked on the Python
   stage instance (the D4 `__new__`-construction pattern), so the constraint
   compiler, the design-bundle wirelength/reduction kernels and the R6
   seed-filter logging stay single-source.
6. **Leaf kernels via FFI.** The slot-grid walk, the ray casting, the AABB
   test and `isolation_slot_aabb` are called through the design-bundle /
   io-types / Python modules — identical calls, identical order, so parity is
   by construction.
7. **CPython rendering.** Every log line's interpolated message renders
   through CPython `str.format` (David-Gay `:.1f`/`:.2f`, list reprs), and the
   `_hv_clearance_overrides` regex runs through CPython `re`.
8. **Write-back fidelity.** `d1_bridge.rs` writes a candidate field only when
   it actually changed (equality on the original Python objects), returning
   the ORIGINAL state object when nothing changed (identity preserved on the
   guard paths); a changed field whose Rust value is None writes an explicit
   Python None — matching the Python stages' `dataclasses.replace(field=None)`.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above): the constraint compiler, shapely, the router_v6
DRC-fence call-back, the seed-filter surface, the directly-tested mixin
helpers and the design-bundle/io-types leaf kernels stay single-source; the
pre-populated-reclaim clear path (a state that already carries a reclaim dict
when the stage computes an empty one) is value-identical through the faithful
None write-back.

### Differential / PBT / runner suites (D5)

| Suite | Location | Count |
|---|---|---|
| D5 differential (oracles: `_zone_aware_slot_generation_run_py_oracle.py` + `_phased_assignment_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d5_rust_differential.py` | 24 |
| D5 PBT (P1..P7, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d5_pbt.py` | 14 |
| D5 stage runner (ZoneAwareSlotGenerationStage no-zones/with-zones + PhasedAssignmentStage guard/end-to-end/HV rings through `PipelineRunner<BoardState>` with sys.modules-registered fakes incl. fake design-bundle + channels modules) | `packages/temper-orchestration/tests/d5_stages_runner.rs` | 5 |
| pre-existing zone-aware / phase / phased / ghost-pad suites (the Phase-5 kernel differentials + PBT, the phased-placer scenarios, the seed-filter integration, the DRC-fence flip, the ghost-pad property, the channel-integration tests) | `packages/temper-placer/tests/deterministic/` + `tests/property/` + `tests/parity/` | 1335+ |

## Rust orchestration engine — Phase D batch D6 (deterministic validation stages)

Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001): the
deterministic validation batch (`deterministic/stages/{placement_validation,
via_validation,drc_sweep,drc_validation,connectivity_validation,
courtyard_check}.py`, ~1,220 LOC) moves to `temper-orchestration` as nine
`Stage<BoardState>` implementors. Depends on D4+D5 (placements populated).

### What migrated

| Python module | Rust entity | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `placement_validation.py` (293) | `PlacementValidationStage` (Stage impl) + `run_placement_validation` pyfunction | `board` (+ the Python stage instance: `constraints` / `fail_on_hard_violations` / `parsed_pads`) | `placement_violations` (tuple) |
| `via_validation.py` (261) | `ViaValidationStage` + `ViaDeduplicationStage` + `run_via_validation` / `run_via_deduplication` | `vias`, `routes`, `netlist`, `placements` | `vias` (frozenset) |
| `drc_sweep.py` (257) | `DRCSweepStage` + `TrackDeduplicationStage` + `ShortCircuitDetectionStage` + `run_drc_sweep` / `run_track_deduplication` / `run_short_circuit_detection` | `drc_oracle`, `routes`, `vias`, `netlist`, `placements` | `routes` (frozenset), `vias` (frozenset) |
| `drc_validation.py` (72) | `DRCValidationStage` + `run_drc_validation` | `drc_oracle` | `drc_violations` (tuple) |
| `connectivity_validation.py` (145) | `ConnectivityValidationStage` + `run_connectivity_validation` | `drc_oracle`, `layer_assignments` | `connectivity_violations` (tuple) |
| `courtyard_check.py` (192) | `CourtyardCheckStage` + `run_courtyard_check` | `placements` (+ the Python stage instance: `max_iterations` / `nudge_step`) | `placements` (frozenset) |

The Rust stages transcribe the pre-migration orchestration wholesale:
`placement_validation` runs the no-board guard, the component-position
extraction, the proximity / signal-HV sweeps, the hard-violation filter, the
raise message and the write; `via_validation` builds the trace-endpoint index
(with the 0.5mm mid-trace sampling via libm-`pow` squares and `** 0.5`) and
the pin-position index (PTH all-layers registration), runs the per-via
validity sweep (diff-pair skip, plane-net special case) and the print
messages; `drc_sweep` runs the oracle track/via sweep with the non-Trace
pass-through, the Trace-only dedup marshalling + remap, and the pin_net_map
build with CPython-`round(x, 2)` keys + endpoint short sweep; `drc_validation`
runs the `validate_all` + summary + `threshold_decision_py` raise decision;
`connectivity_validation` runs the geometry extraction + per-net grouping +
plane/empty-net skips + UnionFind marshalling; `courtyard_check` runs the
iterative nudge loop (libm-`pow` distance, the coincident-center branch, the
`_clamp_position` call-backs). The `d1_bridge.rs` write-back gains the
`routes` / `vias` / `drc_violations` / `placement_violations` /
`connectivity_violations` candidates, and `stage.rs` gains a
`From<PyErr> for StageError` conversion so stage bodies use `?` on `PyResult`
values directly.

**What stays Python (evidence)**: the temper-drc-rs leaf kernels
(`validate_proximity_py`, `validate_signal_hv_py`, `count_connected_layers_py`,
`dedup_via_positions_py`, `deduplicate_traces_py`, `threshold_decision_py`,
`summarize_violations_py`, `connectivity_validate_net_py`, `clamp_position_py`)
stay single-source and are driven through FFI. The DRCOracle methods
(`validate_all`, `can_place_track_segment`, `get_valid_via_sites`, `.geometry`)
and the `LAYER_NAME_TO_IDX` constant stay Python call-backs. The
`pin_world_position` / `pin_world_position_at` geometry, the `is_ground_net` /
`is_power_net` net-classification predicates and the `Trace` / `Via`
pyclasses + `core.board` layer constants stay Python (driven through FFI). The
`PlacementViolation` / `ConnectivityViolation` dataclasses, the router_v6
`Point` class and the `PlacementValidationError` / `DRCValidationError` /
`ConnectivityValidationError` exception classes stay Python: the raising
stages return `Err(StageErrorKind::Infeasible)` and the shared
`write_back_or_raise` channel hands `(state, message)` to the shim, which
raises its module's exception type with the Rust-decided message text. The
shapely/GEOS STRtree courtyard collision detection (`_find_collisions`) and
the CPython `random.random()` nudge noise stay single-source and are called
back on the Python stage instance (the D4/D5 mixin boundary); `_validate_proximity`
/ `_validate_signal_hv` / `_get_pin_position` / `_get_component_positions` /
`_get_proximity_constraints` / `_get_signal_hv_constraints` /
`_point_to_segment_distance` / `_log_summary` stay Python methods directly
exercised by `test_drc_leaf_rust_differential.py`, and the Rust run() calls
the two validation helpers back. All interpolated log/print messages render
through CPython (`print`, `str.format`, `sorted`, `round`, `logging`) -- the
David-Gay `:.1f`, tuple-repr and round-half-to-even semantics stay CPython.

### G1 — differential oracle before Rust (TDD)

The pre-migration modules are pinned VERBATIM as
`tests/deterministic/_<module>_run_py_oracle.py` (six oracles, only relative
imports rewritten to absolute paths); each body's sha256 is pinned in the
differential, which fails on any drift. The RED commit (`4a52a0fb`) landed the
oracles + differential with the anti-vacuity tripwire failing (the shims did
not yet delegate); the GREEN commits (`bcd089f0` drc/connectivity,
`8cd8b651` via/drc-sweep, `acc9451a` placement/courtyard) landed the ports.

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d6_rust_differential.py`: 54 tests
drive both arms with identical BoardState inputs and stage constructor args
and compare bit-exactly — `placement_violations` / `drc_violations` /
`connectivity_violations` tuples projected through `float.hex()`, the
`routes` / `vias` / `placements` frozensets through the same canon, the
identity-preserving guards (no board / no vias-or-routes / no oracle / no
placements), the `PlacementValidationError` / `DRCValidationError` /
`ConnectivityValidationError` raise parity (message equality), the parsed-pads
offset, the via-connectivity / plane-via / diff-pair / dedup sweeps, the
drc-sweep / track-dedup / short-circuit filters, the connectivity net skips,
and the courtyard nudge trajectories (the CPython `random` module seeded
identically before each arm, so both consume the identical noise sequence;
captured stdout compared bit-exact on every print-emitting stage).
`float.hex()` pins the libm-`pow` squares and `** 0.5` distances bit-for-bit.

### G3 — performance

Pure-delegation carve-out: each stage crosses the FFI once per `run()`; the
leaf kernels, the DRCOracle methods, shapely and `random` are unchanged. No
regression beyond the single FFI crossing is possible or claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d6_pbt.py`)

Nine non-vacuous properties (P1 placement-violation invariants, P2 anchored
via kept, P3 via-dedup separation, P4 track-dedup collapse, P5
drc-violation preservation, P6 connectivity plane/empty-net skip, P7
courtyard clean-layout preservation, P8 drc-sweep bad-geometry removal + non-
Trace pass-through, P9 short-circuit wrong-net removal), each with a
fails-for-mutant companion re-running the SAME body against a degenerate
stand-in — the established U4/D1-D5 PBT vacuity-guard pattern. Every D6
module is reached by at least one property. 18 tests green.

### G5 — metamorphic

Not claimed: the D6 surface is orchestration over stateful Python objects
(and the leaf kernels it delegates to are already metamorphic-covered), not
pure functions; the differential and PBT arms pin the behavioural surface.
Recorded as N/A per the plan's per-module G5 discretion (same ruling as D1–D5).

### G6 — induction

Non-applicability note: the stages are finite loops over caller-provided
collections (constraints, vias, routes, nets, iterations); no recursive or
size-parameterized computation. Structural proof instead: bit-exactness
verified by the differential and the PBT vacuity mutants.

### G7 — Rust bar

No `unwrap`/`expect` outside tests (clippy `unwrap_used`/`expect_used` = deny
in the lib target; the runner test files carry the tests-only allow).
`cargo test` 125/125 green (91 lib + d1..d6 runner suites, 5 d6 runner
tests); `cargo clippy --all-features --all-targets -- -D warnings` clean.
Panic safety: every stage body wraps in `stage_guard` (`catch_unwind`), and
pyo3's `#[pyfunction]` expansion additionally wraps every exported body.

### G8 — R24 physics

N/A — the stages gate on no physics quantity; the creepage clearances and
required distances are constraint/configuration values threaded through the
already-tested temper-drc-rs kernels. Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every input in the differential suites'
domains, the Rust stages produce outputs bit-identical to the pinned
pre-migration oracle's. The load-bearing equivalences:

1. **libm `pow` squares and roots.** `(a - b) ** 2` in the via trace sampling,
   the courtyard `dx**2 + dy**2` and the placement distances is CPython
   `float ** float` = libm `pow` — routed through `host_math::pow`; `** 0.5`
   is `pow(x, 0.5)`, NOT `sqrt`.
2. **CPython `round(x, 2)` keys.** The short-circuit pin_net_map keys round
   through CPython's `round` builtin (round-half-to-even) via FFI; the
   `{px:.1f}` message rendering goes through CPython `__format__`.
3. **CPython rendering.** Every log line and `print` message renders through
   CPython `print` / `str.format` / `str.join` / `sorted` (David-Gay `:.1f`,
   tuple reprs, removed-net previews) — parity by identity, not by coincidence
   of formatter implementations.
4. **Mixin helpers are called, not reimplemented.** `_validate_proximity` /
   `_validate_signal_hv` (placement) and `_find_collisions` / `_clamp_position`
   (courtyard) are invoked on the Python stage instance, so the constraint
   kernels, the shapely/GEOS collision detection and the CPython
   `random.random()` noise stay single-source. The courtyard differential
   seeds `random` identically per arm, so both consume the identical noise
   sequence.
5. **Leaf kernels / oracle methods via FFI.** The temper-drc-rs kernels, the
   DRCOracle methods and the geometry / classification helpers are called
   through their Python modules — identical calls, identical order, so parity
   is by construction.
6. **Set/dict insertion order.** The via/drc-sweep removed-net accounting, the
   connectivity per-net grouping (first-seen net order) and the courtyard
   placements dict are built through CPython in the same sequence as the
   oracle; the descending-count summary sort is a stable Rust sort keyed by
   `Reverse(count)`, matching Python's `sorted(..., reverse=True)` tie order.
7. **Write-back fidelity.** `d1_bridge.rs` writes a candidate field only when
   it actually changed (equality on the original Python objects), returning
   the ORIGINAL state object when nothing changed (identity preserved on the
   guard paths); the `(state, message)` raise channel writes nothing back on
   the raise path — the Python oracle raises before `dataclasses.replace`.

**Documented boundary choices** (kept Python / deliberately different, argued
in-source and above): the raising stages surface their decision through the
shared `write_back_or_raise` channel (the shim raises the module's exception
class; a non-raise internal PyErr becomes a `RuntimeError` from the
pyfunction, exactly the D1-D5 `to_pyerr` convention). The placement /
connectivity violation dataclasses and the courtyard/geometry objects stay
Python single-source (constructed through FFI). The `_get_component_positions`
component-position dict is built in Rust rather than called back (the method
stays as directly-exercised public API); the differential pins the two agree.

### Differential / PBT / runner suites (D6)

| Suite | Location | Count |
|---|---|---|
| D6 differential (oracles: the six `tests/deterministic/_*_run_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d6_rust_differential.py` | 54 |
| D6 PBT (P1..P9, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d6_pbt.py` | 18 |
| D6 stage runner (DRCSweep / ViaDedup / DRCValidation / Courtyard / ConnectivityValidation through `PipelineRunner<BoardState>` with sys.modules-registered fakes incl. fake temper-drc-rs + core.board + pin_geometry + net_classification modules) | `packages/temper-orchestration/tests/d6_stages_runner.rs` | 5 |
| pre-existing deterministic suites (the stage kernels differentials + PBT, the D1-D5 differentials, the coverage paydown, the phase/ghost-pad/channel suites) | `packages/temper-placer/tests/deterministic/` | 1389 |

## Rust orchestration engine — Phase D batch D7 (routing-adjacent stages + Phase D completion)

Phase D batch D7 of the Rust Orchestration Engine plan (2026-08-09-001) is
the **FINAL Phase D batch**: the deterministic routing-adjacent batch
(`deterministic/stages/{fine_pitch_escape,hv_lv_partition,power_plane,
layer_assignment,apply_placements}.py`, ~830 LOC) moves to
`temper-orchestration` as five `Stage<BoardState>` implementors, `base.py` is
retired as the D7 stage base (kept as a minimal shim — evidence below), and
`clearance_grid.py` is recorded as already shim-only (D3 migrated
`_grid_stage`). Depends on D1-D6 (the conversion seam, the Stage pattern, and
the populated `netlist`/`placements`/`vias`/`layer_assignments` fields).

### What migrated

| Python module | Rust entity | Reads from BoardState | Writes to BoardState |
|---|---|---|---|
| `fine_pitch_escape.py` (319) | `FinePitchEscapeStage` (Stage impl) + `run_fine_pitch_escape` | `netlist`, `placements`, `vias` (+ the stage instance as the config carrier) | `vias` (frozenset) |
| `hv_lv_partition.py` (181) | `HvLvPartitionStage` (Stage impl) + `run_hv_lv_partition` | `config`, `board`, `netlist`, `drc_oracle` | `component_domain_map`, `routing_corridors`, `domain_regions` |
| `power_plane.py` (148) | `PowerPlaneStage` (Stage impl) + `run_power_plane` | `netlist`, `layer_assignments` (+ stage config) | `layer_assignments` (frozenset) |
| `layer_assignment.py` (79) | `LayerAssignmentStage` (Stage impl) + `run_layer_assignment` | `netlist` (+ stage config) | `layer_assignments` (frozenset) |
| `apply_placements.py` (33) | `ApplyPlacementsStage` (Stage impl) + `run_apply_placements` | `netlist`, `placements` | `netlist` |
| `base.py` | RETIRED as the D7 stage base; kept as a minimal shim (the Python `Stage` ABC is still subclassed by 15 `router_v6/*` stage classes, `adapters/deterministic_adapter.py`, the `deterministic`/`deterministic.stages` re-export seams and the D1-D7 Python shims) | — | — |
| `clearance_grid.py` | already shim-only (D3 migrated `_grid_stage`); D7 records the shim-only status | — | — |

The Rust stages transcribe the pre-migration orchestration wholesale:
`fine_pitch_escape` runs the fine-pitch detection passes (the
`min_pin_pitch_py` kernel, the net collection), the escape-via placement loop
(the `placements.get(ref, initial_position)` resolution, the
CPython-`round(x, 3)` via-position dedup, the `escape_layer_for_net_py`
layer selection, the `Via` construction), the debug prints and the Phase-5
escape validation + auto-generation; `hv_lv_partition` runs the config load +
guards, the `_rules_by_net` reading (INLINED — the D6
`_get_component_positions` precedent; the duck-typed read cannot be called
back without the Python state, and the differential pins the two agree), the
`rules_marshalled` / `components_nets` marshalling, the design-bundle
`hv_lv_classify` / `hv_lv_area_check` calls, the decision dispatch and the
domain/corridor/region write; `power_plane` / `layer_assignment` run their
guards, the design-bundle kernel calls and the frozenset writes;
`apply_placements` runs the guards and the per-component
`dataclasses.replace(initial_position=...)` reconstruction through FFI. The
`d1_bridge.rs` write-back gains the `netlist` / `layer_assignments` /
`component_domain_map` / `routing_corridors` / `domain_regions` candidates.

**What stays Python (evidence)**: the design-bundle leaf kernels
(`min_pin_pitch_py` / `escape_layer_for_net_py` / `assign_layers` /
`recompute_plane_assignments` / `hv_lv_classify` / `hv_lv_area_check`), the
`LayerAssignment` / `Via` pyclasses and `pin_world_position_at` stay
single-source and are driven through FFI. The pydantic `HvLvGuardConfig` +
`load_guard_config`, the shapely `_outline` + `compute_guard_strip` GEOS
surface and the duck-typed `_nets` / `_area` readers stay Python call-backs.
The `PartitionError` exception class stays Python (the raise decisions
construct it through the module class, so the `{:.2f}` message is bit-exact
by identity and `pytest.raises(PartitionError)` sees the real class —
`run_guarded` threads the raw `PyErr`, the D3 pattern). The module-level
`TEMPER_PLANE_NETS` / `TEMPER_PLANE_LAYERS` tables (data, not compute) and
the directly-exercised `_calculate_min_pin_pitch` /
`_get_escape_layer_for_net` / `_assign_layer_by_net_class` helpers stay
Python. No new Python API is invented.

### G1 — differential oracle before Rust (TDD)

The five pre-migration modules are pinned VERBATIM as
`tests/deterministic/_<module>_run_py_oracle.py` (only relative imports
rewritten to absolute paths); each body's sha256 is pinned in the
differential, which fails on any drift. The RED commit (`f5625f98`) landed
the oracles + differential + PBT with the anti-vacuity tripwire failing (the
shims did not yet delegate); the GREEN commits (`6a25c3cc` Rust ports +
runner) landed the ports.

### G2 — behavioural A/B (bit-exact)

`tests/deterministic/test_deterministic_d7_rust_differential.py`: 30 tests
drive both arms with identical BoardState inputs and stage constructor args
and compare bit-exactly — `state.vias` frozensets (via `float.hex()`) and the
captured stdout (the fine-pitch detection / layer-distribution / no-detection
messages byte-for-byte), `state.component_domain_map` / `routing_corridors` /
`domain_regions` (shapely compared by `wkt`), the `PartitionError` raise
(message equality), the log messages (`caplog`), `state.layer_assignments`
frozensets and `state.netlist`'s replaced-component positions. The identity
preserving guards (no netlist / no placements / disabled config / skip_empty /
skip_zero / fallback) assert `out is state` on both arms.

### G3 — performance

Pure-delegation carve-out: each stage crosses the FFI once per `run()`; the
leaf kernels, the pin geometry, the shapely/GEOS surface and the
`dataclasses.replace` calls are unchanged. No regression beyond the single
FFI crossing is possible or claimed.

### G4 — PBT (`tests/deterministic/test_deterministic_d7_pbt.py`)

Seven non-vacuous properties (P1 fine-pitch escape-via coverage of every
netted fine-pitch pin + determinism, P2 no vias for a non-fine-pitch-only
layout, P3 layer-assignment coverage of every net + valid layers, P4 plane
nets marked `is_plane` + one assignment per net, P5 apply-placements applied
+ unplaced preserved, P6 hv_lv guards preserve identity + the ok path writes
exactly one domain per component, P7 fine-pitch vias unique per rounded
position), each with a fails-for-mutant companion re-running the SAME body
against a degenerate stand-in — the established U4/D1-D6 PBT vacuity-guard
pattern. Every D7 module is reached by at least one property. 16 tests green.

### G5 — metamorphic

Not claimed: the D7 surface is orchestration over stateful Python objects
(and the leaf kernels it delegates to are already metamorphic-covered), not
pure functions; the differential and PBT arms pin the behavioural surface.
Recorded as N/A per the plan's per-module G5 discretion (same ruling as D1–D6).

### G6 — induction

Non-applicability note: the stages are finite loops over caller-provided
collections (components, pins, nets, zone configs, placements); no recursive
or size-parameterized computation. Structural proof instead: bit-exactness
verified by the differential and the PBT vacuity mutants.

### G7 — Rust bar

No `unwrap`/`expect` outside tests (clippy `unwrap_used`/`expect_used` = deny
in the lib target; the runner test files carry the tests-only allow).
`cargo test` 130/130 green (91 lib + d1..d7 runner suites, 5 d7 runner
tests); `cargo clippy --all-features --all-targets -- -D warnings` clean.
Panic safety: every stage body wraps in `stage_guard` / `run_guarded`
(`catch_unwind` — a Rust panic becomes a `StageError::Fatal` / Python
RuntimeError instead of unwinding through the pyo3 frame), and pyo3's
`#[pyfunction]` expansion additionally wraps every exported body.

### G8 — R24 physics

N/A — the stages gate on no physics quantity; the clearances are
configuration constants threaded through the already-tested design-bundle
kernels. Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every input in the differential suites'
domains, the Rust stages produce outputs bit-identical to the pinned
pre-migration oracle's. The load-bearing equivalences:

1. **CPython `round(x, 3)` keys.** The fine-pitch via-position dedup keys
   round through CPython's `round` builtin (round-half-to-even) via FFI —
   never Rust `f64::round`. The same applies to the escape-validation /
   auto-generation position keys.
2. **CPython rendering.** Every fine-pitch `print` message renders through
   CPython `str.format` (David-Gay `:.2f`, float `str()`, `sorted()` list
   reprs); the hv_lv `logger` messages render through CPython `str.format`
   for the interpolated text (`%s` of a float == `{}` of a float) and CPython
   `logging` for the record. Parity by identity, not by coincidence of
   formatter implementations.
3. **The `PartitionError` message is by identity.** Both raise points
   construct the ORIGINAL exception through the module class (its `__init__`
   renders `{:.2f}` via CPython) — bit-exact by construction; the `PyErr`
   threads through `run_guarded` so the class survives the FFI (the D3
   `FenceViolation`/`ConfigError` pattern).
4. **Duck-typed reads are called back or pinned.** `_outline` /
   `compute_guard_strip` / `load_guard_config` / `_nets` / `_area` are
   invoked through their Python modules in the same order as the oracle;
   `_rules_by_net` is inlined (the D6 `_get_component_positions` precedent)
   and the differential pins the two agree.
5. **Kernels via FFI.** `min_pin_pitch_py` / `escape_layer_for_net_py` /
   `assign_layers` / `recompute_plane_assignments` / `hv_lv_classify` /
   `hv_lv_area_check` and `pin_world_position_at` are called through their
   Python modules — identical calls, identical order, so parity is by
   construction.
6. **`dataclasses.replace` by identity.** The apply-placements component /
   netlist reconstruction calls the Python `dataclasses.replace` on the
   pyclass objects via FFI — the exact operation the oracle performs. The
   `placements.get(ref, initial_position)` resolution is `dict.get` with the
   eagerly-evaluated default, exactly like the oracle's two-argument call.
7. **Write-back fidelity.** `d1_bridge.rs` writes a candidate field only when
   it actually changed (equality on the original Python objects), returning
   the ORIGINAL state object when nothing changed (identity preserved on the
   guard paths); the raise path writes nothing back (the oracle raises before
   `dataclasses.replace`).

**Documented boundary choices** (kept Python / deliberately different, argued
in-source and above): the fine-pitch Phase-5 missing-escape auto-generation
path is transcribed faithfully but is unreachable in the differential's
domain (every fine-pitch pin's rounded key is covered by the pass-2 dedup —
a latent wart the oracle shares); the `_rules_by_net` helper stays Python as
directly-pinned module API while the port inlines the same computation.

### base.py retirement evidence

`git grep 'deterministic.stages.base import Stage'` at the D7 base
(`3a7dd1d9`): the `Stage` ABC is imported by the 15 `router_v6/*` stage
modules, `adapters/deterministic_adapter.py`, `temper_placer.deterministic`
(public re-export), `temper_placer.deterministic.stages` (public re-export)
and every D1-D7 stage shim. The Rust `Stage` trait (`stage.rs`) replaces the
ABC **for the migrated deterministic batch** — the D7 stage classes no longer
carry any run() logic in their Python bodies — but the Python class cannot be
deleted while the router_v6 stage classes subclass it (Phase E). The module
stays as a minimal shim whose class surface is unchanged; its header records
this decision and the consumer evidence.

### Differential / PBT / runner suites (D7)

| Suite | Location | Count |
|---|---|---|
| D7 differential (oracles: the five `tests/deterministic/_*_run_py_oracle.py`, sha256-pinned) | `packages/temper-placer/tests/deterministic/test_deterministic_d7_rust_differential.py` | 30 |
| D7 PBT (P1..P7, mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_d7_pbt.py` | 16 |
| D7 stage runner (FinePitchEscape / HvLvPartition / PowerPlane / LayerAssignment / ApplyPlacements through `PipelineRunner<BoardState>` with sys.modules-registered fakes incl. fake design-bundle + pin_geometry + hv_lv_partition modules) | `packages/temper-orchestration/tests/d7_stages_runner.rs` | 5 |
| pre-existing deterministic suites (the stage kernels differentials + PBT, the D1-D6 differentials/PBT, the phase/ghost-pad/channel suites) | `packages/temper-placer/tests/deterministic/` | 1389 |

With D7 landed, **Phase D is complete** per the plan: all seven batches
(D1 setup → D7 routing-adjacent) are migrated, and the plan's Phase D table
rows (27 stage files, ~7,800 LOC) are exhausted.

## Rust orchestration engine — U8 (explainability data contracts + MarkdownReport)

The Rust Orchestration Engine plan (2026-08-09-001) ships its Phase-A U8 unit
here: the `explainability/{decision,trace,serialization,markdown_report}.py`
row (886 LOC) — the explainability **data contracts** migrate to
`explainability.rs` pyclasses (`Decision`, `Alternative`, `DecisionTrace`,
`Entry`, `Trace`) and the **markdown report generation** becomes the
`MarkdownReport` pyfunctions (`render_markdown_report` /
`render_component_report`). The three Python shims collapse to re-exports.
`DecisionPhase` / `DecisionType` stay Python `Enum` classes; the
NL-generation kernels (`why` / `why_not` / `history` / `summary`) stay
single-source in `temper-io-types` and are called back from the pyclasses.

### What migrated

- `decision.py` — the `Alternative` / `Decision` / `DecisionTrace`
  dataclasses become pyclasses (field get/set, per-instance
  `default_factory` containers, `uuid`/`datetime` defaults invoked from the
  Rust constructors, `to_dict` / `query_*` / `finalize` / `add` /
  `__len__` / `__iter__` / `__eq__` / `__repr__`). `DecisionPhase` /
  `DecisionType` stay Python Enums (redefined in the shim).
- `trace.py` — the `Entry` / `Trace` frozen dataclasses become pyclasses
  (the immutable monoid: `empty` / `add` / `__add__` / `for_subject` /
  `__len__` / `__bool__` / `__eq__` / `__hash__` / `__repr__`).
- `markdown_report.py` — the renderers are the `MarkdownReport` deliverable
  ported into `explainability.rs` (byte-pinned against the verbatim oracle);
  the shim keeps only the `strftime` timestamp pre-formatting, the
  `duration` datetime arithmetic and `save_markdown_report` file I/O.
- `logger.py`, `pipeline.py`, `traced_loss.py`, `serialization.py` stay
  Python unchanged (orchestration over Python callables / stdlib file-I/O /
  numpy; the logger's `explain_log_*`, `explain_should_log`,
  `explain_significant_change`, `explain_compose_traces`,
  `explain_constraint_subject`, `explain_trace_threshold` and the
  serialize/deserialize dict-shapes stay wired in `temper-io-types`).

### Boundaries (argued in `explainability.rs` and here)

- **Enums stay Python.** `DecisionPhase` / `DecisionType` keep their Enum
  identity, value construction (`DecisionPhase(x)`) and class iteration
  (`list(DecisionPhase)`) — Python runtime semantics that pyo3 cannot
  reproduce (no metaclass hook for class iteration). The pyclass fields hold
  the Python enum members as `Py<PyAny>`.
- **`uuid` / `datetime` defaults stay Python runtime semantics.** The pyclass
  constructors call Python's `uuid.uuid4()` / `datetime.now()` for the
  defaults (never reimplemented); the differential pins the SHAPE (8-char /
  12-char ids, `datetime` instances), not the values.
- **NL-generation stays single-source in `temper-io-types`.** `why` /
  `why_not` / `history` / `summary` / `Trace.why` call the io-types kernels
  back across the boundary (the pyclass instances expose the exact attribute
  surface those kernels read). The five io-types kernels are ledgered as
  wired-but-invisible-to-the-Python-AST-scan (the gate cannot see
  cross-extension Rust→Python `PyModule::import` calls). The two markdown
  renderers ARE ported (the plan's `MarkdownReport` deliverable) and are
  ledgered as orphaned/superseded.
- **Per-instance default factories.** `constraint_refs` / `alternatives` /
  `config_snapshot` / `decisions` / `final_positions` / `final_metrics` get a
  FRESH `PyList`/`PyDict` per construction (the dataclass
  `field(default_factory=...)`), pinned by the differential's independence
  test.
- **`loss_contribution` is `Py<PyAny>`.** An int stays an int (the logger
  differential's `test_log_heuristic_int_confidence_type_preserved` pins it);
  the dataclass does not type-enforce.
- **`subject` / `reason` / `id` are typed `String`** — a non-str argument
  raises TypeError where the dataclass would store it (the U4 typed-boundary
  precedent; no caller in the differential/PBT corpora passes non-str).

### G1 — differential oracle before Rust (TDD)

The U8 differential `test_explainability_contracts_rust_differential.py`
(23 tests) and its RED arm were committed first (`4a603144` — the
`__module__ == "temper_orchestration"` assertions failed, the shims were not
collapsed), then the implementation landed GREEN (`438352c1`). The oracle is
the verbatim pre-migration module copies in
`tests/explainability/explain_oracle/` (already byte-pinned by the Wave-4
suites).

### G2 — behavioural A/B (bit-exact)

The 23-test differential drives BOTH arms with identical inputs and compares
every observable bit-exact: construction defaults (uuid/datetime shapes),
`to_dict` shapes (repr-compared), `query_*` results (Decision reprs),
`finalize`, `summary`/`why`/`why_not`/`history` (via the delegated kernels),
the Trace monoid (`empty`/`add`/`+`/`for_subject`/`why`/repr) and the
markdown reports byte-identical across 15 randomized fixtures × the
include_config/include_positions matrix. The pre-existing Wave-4 suites
(`test_decision_rust_differential.py`, `test_trace_rust_differential.py`,
`test_serialization_rust_differential.py`, `test_markdown_rust_differential.py`,
`test_logger_rust_differential.py`, `test_traced_loss_pipeline_rust_differential.py`,
`test_explainability_pbt.py`, `test_*_extra.py`) now drive the **pyclasses**
through the collapsed shims and stay green — 138 explainability tests.

### G3 — performance

Pure-delegation carve-out: the data contracts are constructed once per
decision, the renderers run once per report; the only overhead added is the
pyclass construction / FFI crossing. No regression beyond noise is possible
or claimed.

### G4 / G5 — PBT + metamorphic (`test_explainability_contracts_pbt.py`)

Six non-vacuous properties (P1 Trace monoid identity, P2 `add` appends
exactly one entry, P3 `Decision.to_dict`→`deserialize_decision` round-trip,
P4 `summary` aggregation consistency, P5 `query_subject` chronological
filter, P6 markdown determinism), each with a degenerate-kernel mutation
guard via `hypothesis.inner_test`. Four metamorphic relations (MR1
composition order-preservation, MR2 monoid identity invisible to `why` output,
MR3 component report monotone in the appended final value, MR4 summary scale
invariance under decision duplication), each mutation-guarded. 20/20 green.

### G6 — induction

Not applicable — the migrated surface is data contracts plus fixed-sequence
rendering; no recursive computation. A structural proof is recorded below.

### G7 — Rust bar

`cargo test` 75/75 green (71 lib + 4 runner; the 4 new
`explainability.rs` unit tests pin `truncate`'s negative-stop clamp,
`py_title`, and the `py_float_fmt` NaN/inf/round-half-even seam);
`cargo clippy --all-features --all-targets -- -D warnings` clean. No
`unwrap`/`expect` anywhere (crate denies both). Panic safety: pyo3's
`#[pyclass]`/`#[pyfunction]` expansion wraps every exported body in
`catch_unwind` (the crate sets `profile.release.panic = "unwind"` so that
catch is what runs).

### G8 — R24 physics discipline

Not applicable — the explainability surface gates on no physics quantity
(data records + text rendering). Recorded explicitly.

### Structural proof

**Claim (bit-identical parity).** For every constructor, field, method and
renderer of the migrated pyclasses, the Rust behaviour is bit-identical to
the pinned pre-migration Python for every input in the differential suites'
domains, with the documented boundary choices above.

1. **repr by identity.** The dataclass `__repr__` renders every leaf via
   CPython's repr engine (Enums as `<DecisionPhase.GEOMETRIC: 'geometric'>`,
   datetimes as `datetime.datetime(...)`, floats with David-Gay semantics);
   the Rust `__repr__` calls CPython `repr()` on each field value. Parity by
   identity, not by coincidence of formatter implementations (U4 precedent).
2. **eq by identity.** Dataclass equality is exact-class + field-wise `==`.
   The Rust `__eq__` type-checks the other operand's type first, then
   compares every field with Python `==` — the enum members, datetimes,
   tuples, numpy leaves and nested `Alternative`/`Decision` lists all compare
   with Python equality, exactly like the dataclass.
3. **Unhashability / hashability.** `Decision` / `DecisionTrace` are
   unhashable (`eq=True`, `frozen=False` — `__hash__` raises TypeError);
   `Entry` / `Trace` are frozen dataclasses and hashable (hash of the field
   tuple / entries tuple).
4. **Per-instance default factories.** Fresh `PyList`/`PyDict` per
   construction, pinned by the differential's independence test.
5. **Markdown float/truncation seams.** The renderers go through the ported
   `py_float_fmt` seam (NaN/inf lowercase, round-half-even) and `truncate`
   (CPython negative-stop slicing clamp for max_len < 3) — the same seams
   io-types pins, re-pinned here by unit tests and the byte-identical
   differential (incl. the deterministic-string golden test).
6. **`finalize` truthiness.** `if positions:` / `if metrics:` skip empty
   (`falsy`) dicts exactly like the oracle (pinned by the differential).
7. **Delegated NL-generation by single-source.** `why` / `why_not` /
   `history` / `summary` / `Trace.why` call the same io-types kernels the
   pre-migration shims called, so parity is by construction (the kernels
   read the pyclass attribute surface, which matches the dataclass surface
   bit-for-bit).

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above):
- `DecisionPhase` / `DecisionType` stay Python Enum classes.
- `uuid` / `datetime` defaults are Python runtime semantics invoked from the
  constructors (shape-pinned, never value-pinned).
- The `subject` / `reason` / `id` / `rejection_reason` fields are typed
  `String` (reject type-unsafe assignment where the dataclass would store
  it).
- The NL-generation compute stays in `temper-io-types` (single-source;
  ledgered as wired-but-scan-invisible); the two superseded io-types markdown
  renderers are ledgered as orphaned.

### Differential / PBT suites (U8)

| Suite | Location | Count |
|---|---|---|
| U8 contracts differential (oracle: `explain_oracle/{decision,trace,markdown_report}_oracle.py`) | `packages/temper-placer/tests/explainability/test_explainability_contracts_rust_differential.py` | 23 |
| U8 PBT + metamorphic (P1..P6, MR1..MR4, mutation-guarded) | `packages/temper-placer/tests/explainability/test_explainability_contracts_pbt.py` | 20 |
| pre-existing explainability suites (Wave-4 differentials/PBT/extra, now driving the pyclasses) | `packages/temper-placer/tests/explainability/` | 138 |

## Rust orchestration engine — Phase E batch E3 (clearance-family stages)

Rust Orchestration Engine plan 2026-08-09-001 Phase E E3: the five
clearance-family modules' ORCHESTRATION moves to `src/clearance.rs` as
`Stage<BoardState>` impls plus the pyfunction FFI surface the router_v6 /
cp_sat shims delegate to. The pre-migration orchestration is pinned VERBATIM
as `tests/router_v6/_clearance_family_py_oracle.py` (byte-exact snapshot at
the dispatch base, content-hash pinned in `scripts/oracle_hashes.json` AND
by the differential's own body digest).

### The Python-side split (what stays, with evidence)

- **`clearance_engine.get_clearance`** — `clearance::get_clearance_py`: the
  five-standard candidates, the conservative max and the IEC 60664-1
  internal-layer reduction. The leaf tables stay single-source in
  temper-geometry (`safety_distances_py` / `net_class_to_voltage_class_py` /
  `calculate_required_creepage_py`) and the `VoltageClass`
  `get_clearance_mm`/`get_creepage_mm` methods stay on the design-bundle
  pyclass, all driven through FFI; `calculate_safety_distances`,
  `SafetyDistances`, the `VoltageClass` enum mapping and the private
  keyword/class helpers stay Python.
- **`creepage_check.verify_creepage`** — `clearance::run_creepage_check`:
  the HV-net pair loop, the required-distance decision (default override or
  the IPC-2221 kernel) and the per-pair min-clearance sweep. The duck-typed
  route extraction (`_extract_segments`) and the report construction stay
  Python; the shim preserves the pre-migration LAZY contract — a board with
  no HV net reports zero checks without inspecting any route (pinned by
  `test_empty_data_edge_cases`). `_find_clearance_violations` and the
  geometry delegations stay (differential-test API).
- **`clearance_check.verify_clearance`** — `clearance::run_clearance_check`:
  the production rust path (min-clearance validation with CPython float
  repr, the temper-drc-rs `verify_route_clearance` delegation, the
  `total_checks` accounting). The pure-Python reference
  (`_verify_clearance_python` + its geometry helpers) stays Python as the
  `backend="python"` oracle; `_route_to_rust_tuple`/`_all_routes`
  marshalling and the report construction stay.
- **`isolation_barrier`** — `clearance::classify_domain_partition_py` /
  `project_onto_barrier_axis_py` / `evaluate_isolator_feasibility_py`: the
  component partition (exact-name pin-net membership, never substring), the
  integer 4-rotation table (out-of-range rotation raises KeyError exactly
  like the pre-migration dict) and the isolator feasibility assembly over
  the temper-geometry axis-gap / best-rotation kernels. The ortools
  `add_isolation_barrier_to_model` wiring stays Python untouched (plan D4
  boundary); `compute_pad_groups`, the `Pad`/`IsolatorPadGroups` dataclasses
  and `_pad_tuple` marshalling stay.
- **`domain_clearance`** — `clearance::domain_clearance_constraints_py` /
  `keepaway_constraints_py` / `intra_footprint_conflicts_py` /
  `audit_domain_clearance_py`: the IEC60335_REQUIREMENTS matrix walk, the
  (a, b) canonicalization + margin/reason dedup, the sorted emission, the
  keep-away and intra-footprint walks and the R24 post-solve audit. The
  matrix stays the Python SSOT (marshalled once per call via the shim's
  `_matrix_rows`); the pairing/domain kernels stay single-source in
  temper-drc-rs (`req_safe_01_*`); the `SeparatedConstraint` construction
  and the logging stay Python (pcl is Python-owned; the `because` reason
  strings render through CPython `str.format` from Rust, bit-exact).

### Structural proof (bit-identical parity)

- **Kernel reuse**: every geometry/table/margin kernel is the pinned
  temper-geometry / temper-drc-rs / temper-constraints function driven
  through FFI — the same kernels the oracle calls, so the orchestration
  differential inherits the existing bit-exact kernel proofs.
- **Reason-string fidelity**: `because` strings embed floats (`{margin}mm`,
  `clearance={...}mm`); Rust renders them via CPython `str.format` (the
  `py_format` helper), so `4.0` renders `"4.0"` — Rust `format!("{}")`
  would render `"4"`.
- **Python-max semantics**: `get_clearance`'s conservative max is a
  first-maximum fold (`x > best`), never Rust `f64::max` (NaN semantics
  differ); a NaN-voltage board degrades to the 0.5 mm safe default exactly
  like the Python `if not candidates`.
- **Eager/lazy fidelity**: `run_creepage_check` receives segments only for
  the routes the pre-migration pair loop would have touched (the shim
  marshals lazily when no HV net exists), and `run_clearance_check` keeps
  the `min_clearance` NaN/inf `ValueError` message byte-identical (CPython
  `repr`).
- **KeyError table**: `project_onto_barrier_axis_py` raises `KeyError` for a
  rotation outside 0..=3 (the pre-migration `{...}[rot]` dict), pinned by
  the metamorphic companion and the Rust unit tests.

### Empirical Verification

- **Differential suite**: `test_clearance_family_rust_differential.py` (72
  tests, all green) — the oracle is content-hash-pinned; the shims bind to
  `temper_orchestration` pyfunctions (anti-vacuity assert), the oracle stays
  pure Python. `get_clearance` is compared bit-exact (`float.hex()`) over
  25x40 randomized net-class/voltage/layer/design-rule cases incl. NaN;
  `verify_creepage` field-by-field over deterministic + 15 randomized route
  sets incl. the default-creepage override; `verify_clearance`'s rust path
  against the pure-Python reference over deterministic + 10 randomized
  route sets; isolation-barrier partition/feasibility/rotation table
  field-by-field; domain-clearance generator/keep-away/conflicts/audit
  field-by-field incl. the `component_refs` filter, exempt pairs and the
  missing-position NaN case.
- **PBT suite**: `test_clearance_family_rust_pbt.py` (14 tests, all green) —
  seven non-vacuous properties (P1 design-rule-candidate absorption, P2
  internal-layer exact factor, P3 creepage lazy contract, P4 creepage
  threshold monotonicity, P5 clearance C(n,2) pair accounting, P6 partition
  totals/disjointness, P7 audit soundness), each with a discriminating
  vacuity guard.
- **Metamorphic suite**: `test_clearance_family_rust_metamorphic.py` (11
  tests, all green) — five relations (MR1 engine symmetry, MR2 threshold
  superset, MR3 partition ref covariance, MR4 audit monotone in separation,
  MR5 rotation table in-domain + out-of-domain KeyError), each with a
  discriminating companion.
- **Runner suite**: `tests/e3_stages_runner.rs` (4 tests, all green) — the
  five E3 stages sequence through `PipelineRunner<BoardState>` in
  declaration order, every `run()` completes without panicking (guarded
  identity on empty payloads; the FFI kernels are exercised by the Python
  differential), and the read-only stages preserve the state.
- **Consumer suites**: the full pre-existing clearance-family surface stays
  green with the delegating shims — `test_clearance_check.py`,
  `test_creepage_check.py`, `test_isolation_barrier.py`,
  `test_domain_clearance.py`, the rust-kernel differentials
  (`test_clearance_rust_differential.py`,
  `test_creepage_check_rust_differential.py`,
  `test_isolation_barrier_rust_differential.py`,
  `test_domain_clearance_dist_rust_differential.py`),
  `test_via_clearance_tier2_rust_differential.py` / `_pbt.py`,
  `test_clearance_boundary.py` / `test_creepage_boundary.py`,
  `test_creepage_properties.py` / `test_creepage_geometry_pbt.py`,
  `test_empty_data_edge_cases.py` (the lazy-contract pin),
  `test_manufacturing_report*.py` / `test_manufacturing_drc_integration.py`,
  `test_validator_audit.py`, `test_router_v6_drc_invariants_pbt.py`,
  `test_encoder_rust_differential.py` — all green.
- **Rust unit tests**: `clearance.rs` carries `#[cfg(test)]` unit tests
  (the rotation table + out-of-range, the partition buckets + substring
  anti-match); like every pyo3-gated module here they compile under
  `--features python` only, so the Python differential is the authoritative
  gate.
- **Clippy**: `cargo clippy --all-features --all-targets -- -D warnings` —
  clean.
- **Wiring**: `check_unwired_kernels.py` reports no new unwired kernel
  (`dist_py` is ledgered as wired-from-Rust-FFI, the E3 delegation boundary;
  every other kernel's Python delegation wrapper stays).
- **G6 induction** — N/A: every migrated orchestration is a bounded loop
  nest over board/route/component inputs with size-independent per-step
  operations; the R24 post-solve audit is a linear scan with a fixed
  comparison.
- **G8 physics discipline** — N/A for the migrated orchestration: it
  assembles/counts/computes from already-physics-gated values (the
  clearance/creepage requirement tables were physics-gated when the kernels
  landed; their R24 proofs live with the kernels and the validator). The
  `domain_clearance` soundness proof is unchanged and lives in the module
  docstring (R24 item 1) — the encoded `SeparatedConstraint` margin is the
  matrix value, only the walk moved to Rust.
- **R1g Rust bar**: every `#[pyfunction]` body is wrapped in `catch_unwind`
  by pyo3's macro expansion (the crate sets `profile.release.panic =
  "unwind"`); the `Stage` run() bodies run under `stage_guard`; no
  `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

## Rust orchestration engine — Phase E batch E4 (channel operations)

Rust Orchestration Engine plan 2026-08-09-001 Phase E E4: the channel
operations' ORCHESTRATION moves to `src/channel_mapping.rs` as
`Stage<BoardState>` impls plus the pyfunction FFI surface the
`router_v6/channel_mapping.py` and `router_v6/channel_widths.py` shims
delegate to. The pre-migration orchestration is pinned VERBATIM as
`tests/router_v6/_channel_ops_py_oracle.py` (byte-exact snapshot of the two
modules' orchestration bodies at the dispatch base, origin/main d1b330b90;
content-hash pinned in `scripts/oracle_hashes.json` AND by the differential's
own body digest; the oracle bodies were AST-verified byte-identical to the
committed modules).

### What migrated

| Python module | Rust entity | Migrated orchestration |
|---|---|---|
| `router_v6/channel_mapping.py` (639) | `channel_mapping.rs` | `map_topology_to_channels` / `_map_net_to_channels` / `_extract_waypoints` / `_parse_channel_coordinate` / `_skeleton_nodes_in_coordinate_order` / `_assign_layer` / `_ssot_layer_for_net` / `_validated_two_pad_terminals` / `expand_channel_path_terminals` / `fallback_channel_path` |
| `router_v6/channel_widths.py` (694, shapely-blocked portions stay Python) | `channel_mapping.rs` | `compute_channel_widths`'s EDT production path: the per-edge interior sampling, the all-points assembly, the batched `edt_width_lookup_batch` dispatch, the node/edge-width assembly and the min/max/avg statistics |

**What stays Python (evidence)** — the shapely-blocked channel_widths
portions have no Rust equivalent (argued in the `channel_widths.py` shim
header): `_rasterize_boundary_mask` (`shapely.contains_xy` — the module
docstring's boundary-semantics proof depends on shapely's exact predicate),
`_compute_width_at_point` (prepared-geometry `Point.distance` to the
exterior/interior rings — the per-point reference path, `use_edt=False`),
`_compute_board_fingerprint` (the routing polygon's WKB serialization hashed
for the EDT disk cache), `_build_edt` / `_atomic_write_npz` /
`_evict_if_over_budget` (the rasterise + npz disk-cache lifecycle), the
`available_area.is_empty` guard and the `MultiPolygon` decomposition /
prepared-geometry caches. The `ChannelWidthsStage` pipeline stage and the
`validate_channel_widths` DRC-fence validator stay Python unchanged
(BoardState orchestration + the `StageDRCFailure` convention). The
channel-ID coordinate parsing calls CPython `float()` (Python float accepts
whitespace / `inf` / underscore forms Rust's `f64::from_str` does not); the
path-graph node fallback strings (`str(node)`) and their exception
swallowing stay Python (CPython str semantics); the net-classification
predicates are driven through the Python module at runtime (single-layer-mode
is process-local mutable state). No new Python API is invented.

### Structural proof (bit-identical parity)

The differential drives both arms with identical inputs and compares every
return value bit-exact (`float.hex()` via `canon`). The load-bearing
equivalences:

- **Kernel reuse**: every geometry kernel (`channel_path_length_py` /
  `is_near_skeleton_py` / `nearest_skeleton_node_py` /
  `nearest_terminal_order_py` / `edt_width_lookup_batch` in
  temper-geometry) is the pinned function driven through FFI — the same
  kernel the oracle calls, so the orchestration differential inherits the
  existing bit-exact kernel proofs.
- **The paren-group scan is the regex**: `re.findall(r"\(([^)]+)\)",
  channel_id)` is leftmost-non-overlapping with `[^)]+` requiring at least
  one non-`)` character; `find_paren_groups` reproduces it exactly (pinned
  by the Rust unit tests: `"((a))"` → `["(a"]`, `"(a(b)c)"` → `["a(b"]`,
  `"()"` → `[]`). The `match.split(",")` → `float()` → `(x, y)` parse goes
  through CPython `float()`, matching the oracle's `ValueError` swallowing
  (both parts must parse for the point to be emitted).
- **Python tuple ordering**: the `sorted()` sorts (the skeleton
  coordinate-order fallback and `fallback_channel_path -> sorted(pads)`) and
  the `min()` over tuple lists (`min(missing)`) replicate CPython's
  `==`-falls-through-`<` tuple comparison exactly — `-0.0`/`0.0` ties and
  NaN compare equal and keep input order (stable), so the results are pure
  functions of the node/pad SET, never of insertion order (the H1/H2
  determinism hazards).
- **`_assign_layer` via the Python module**: `get_single_layer_mode()` and
  the `is_power_net`/`is_ground_net`/`is_hv_net` predicates are called back
  through `temper_placer.router_v6.net_classification` (single-layer-mode
  short-circuit semantics stay single-source); the single-layer early return
  skips the SSOT lookup exactly like the oracle. `_ssot_layer_for_net`
  reads `reason`/`primary_layer` via `getattr` with the `""` default, and
  the `_LAYER_ENUM_TO_KICAD` lookup uses Python `eq` (so `1`/`1.0`/`True`
  keys match, a `"1"` string does not — dict semantics, not i64 casting).
- **`_validated_two_pad_terminals`**: the identity/swap displacement
  decision uses libm `pow` for `(dx**2 + dy**2) ** 0.5` (host_math), the
  `<=` tie-break is identity-preferring, and `corrected == waypoints` (float
  equality) selects the identity return — the shim returns the ORIGINAL
  object, preserving `terminal_tree`/`terminals` (identity parity is pinned
  by the differential).
- **The all-pad-tree `total_length` wart**: the length is recomputed over
  `[*waypoints, *missing]` where `missing` is the pad-INPUT-order list (not
  the deterministic `ordered_missing`) — a faithful reproduction of the
  reference's quirk, pinned by a dedicated differential case that permutes
  the pads and asserts the waypoints stay deterministic while the lengths
  differ on both arms identically.
- **EDT-branch statistics**: the reference's `sum(all_widths)` operates on a
  list whose FIRST element is always `np.float64` (node widths come first),
  so CPython's float-compensation fast path never engages — every add is
  numpy-scalar arithmetic = plain naive IEEE accumulation in dict order; the
  Rust replicates it as a naive f64 fold (`min`/`max` are the iterable
  first-minimum/first-maximum semantics; a NaN never displaces the
  incumbent). The edge sampling uses `pow` squares + `int(edge_length /
  sample_distance)` truncation + `i / num_samples` true division in the
  exact reference order; the batch lookup is called once with the same
  byte-identical EDT/mask inputs.
- **numpy-scalar normalisation in the differential**: the oracle's width
  values are `np.float64` (numpy indexing) while the Rust path returns
  Python floats; the differential compares `float(v).hex()` (exact
  conversion), documenting that the IEEE bits are the contract, the numpy
  wrapper is not.

### Empirical Verification

- **Differential suite**: `test_channel_ops_rust_differential.py` (87 tests,
  all green) — the oracle is content-hash-pinned; the shims bind to
  `temper_orchestration` pyfunctions (anti-vacuity assert), the oracle stays
  pure Python. `map_topology_to_channels` is compared bit-exact over the
  empty/None topologies, SAT channel sequences (coordinate / edge-ID /
  underscore / plain IDs), the path-graph fallback, the layer-constraint
  overrides (SimpleNamespace + `.value` enums + bare-string shims) and 20
  randomized net/skeleton/constraint cases; `fallback_channel_path` /
  `expand_channel_path_terminals` over the two-pad identity/swap/wrong-
  endpoint/short-path/interior-preserved cases, the all-pad-tree append /
  no-op / disabled / duplicates / empty-path cases and 10+10 randomized
  cases (incl. the pad-input-order total_length wart); `compute_channel_widths`
  over the EDT path (box, multipolygon, sample-distance sweep, diagonal
  edges, empty skeleton, empty area, 8 randomized skeletons) and the
  per-point reference path (`use_edt=False`).
- **PBT suite**: `test_channel_ops_rust_pbt.py` (12 tests, all green) — six
  non-vacuous properties (P1 SAT sequence authoritative, P2 path-graph
  fallback, P3 fallback_channel_path determinism, P4 two-pad endpoint
  correction, P5 width-stats consistency with the naive-sum reference, P6
  edge-width bounded by its endpoints), each with a discriminating vacuity
  guard.
- **Metamorphic suite**: `test_channel_ops_rust_metamorphic.py` (8 tests,
  all green) — four relations (MR1 two-pad expansion idempotence, MR2
  pad-order endpoint closure + interior preservation with the exact-tie
  identity-preference companion, MR3 all-pad-tree waypoint permutation
  invariance, MR4 edge-width upper bound), each with a discriminating
  companion.
- **Runner suite**: `tests/e4_stages_runner.rs` (4 tests, all green) — the
  two E4 stages sequence through `PipelineRunner<BoardState>` in declaration
  order, every `run()` completes without panicking (guarded identity on
  empty payloads; the FFI kernels are exercised by the Python differential),
  and the read-only stages preserve the state.
- **Consumer suites**: the full pre-existing channel surface stays green with
  the delegating shims — `test_channel_mapping.py`,
  `test_channel_widths.py`, `test_channel_mapping_pbt.py`,
  `test_channel_mapping_rust_differential.py` (the four temper-geometry
  kernels), `test_channel_mapping_terminal_validation.py`,
  `test_channel_widths_pbt.py`, `test_channel_widths_edt.py`,
  `test_astar_heuristics_rust_differential.py` (incl. the one-batch-call
  pin), `test_all_pad_tree_routing.py`, `test_adapter.py`,
  `test_wave3_skip_sat.py`, `test_astar_nlayer.py`,
  `test_astar_pathfinding.py`, `test_astar_route_multilayer_via_fallback.py`,
  `test_decline_reason_contract.py`, `test_demand_budget_pbt.py`,
  `test_tree_grid_layer_mismatch.py` — all green (228 passed, 1 skipped on
  the batch; identical pass/fail signature to origin/main).
- **Rust unit tests**: `channel_mapping.rs` carries `#[cfg(test)]` unit
  tests (the paren-group scan semantics, the CPython tuple `<` / stable
  coordinate sort, the first-min/first-max iterable semantics, the two-pad
  identity/swap decision and interior preservation).
- **Clippy**: `cargo clippy --all-features --all-targets -- -D warnings` —
  clean.
- **Wiring**: `check_unwired_kernels.py` reports no new unwired kernel — the
  temper-geometry kernels the Rust orchestration drives (`channel_path_length_py`
  / `is_near_skeleton_py` / `nearest_skeleton_node_py` /
  `nearest_terminal_order_py` / `edt_width_lookup_batch`) are still wired by
  their Python delegation wrappers in the shims, so the Python AST scan sees
  them wired.
- **G6 induction** — N/A: every migrated orchestration is a bounded loop
  nest over nets/skeleton nodes/edges/pads with size-independent per-step
  operations; the sampling loop's arithmetic is per-sample fixed-step.
  Structural proof above.
- **G8 physics discipline** — N/A for the migrated orchestration: it maps /
  measures from already-physics-gated inputs (the width/clearance values
  come from the pinned temper-geometry kernels); no new physics quantity is
  gated. The channel-width measurement itself is data (2x EDT distance), not
  a constraint the solver optimises against.
- **R1g Rust bar**: every `#[pyfunction]` body is wrapped in `catch_unwind`
  by pyo3's macro expansion (the crate sets `profile.release.panic =
  "unwind"`); the `Stage` run() bodies run under `stage_guard`; no
  `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

**Pre-existing finding (not introduced by E4)**: two tests in
`test_channel_widths_rust_differential.py`
(`test_compute_channel_widths_batch_matches_per_point` /
`test_compute_channel_widths_multipolygon_batch_matches_per_point`) fail
IDENTICALLY on origin/main — the pre-migration `_per_point_rebuild` oracle
calls `skeleton.graph.nodes()` / `.edges()` as methods, but the SkeletonGraph
pyclass exposes them as properties; the failure predates E4 (the CI-uncovered
registry's `_PASSING_LOCALLY` entry is stale). E4 leaves the file untouched
(not in scope) and records the rot here.

## Rust orchestration engine — Phase E batch E6 (pipeline route + adapter)

Rust Orchestration Engine plan 2026-08-09-001 Phase E E6: the pipeline-route
ORCHESTRATION moves to `src/pipeline_route.rs` as the pyfunction FFI surface
the `router_v6/_pipeline_route.py` and `router_v6/_adapter_convert.py` shims
delegate to, plus the `PipelineRouteStage` `Stage<BoardState>` impl. The
pre-migration orchestration is pinned VERBATIM as
`tests/router_v6/_pipeline_route_py_oracle.py` and
`tests/router_v6/_adapter_convert_py_oracle.py` (AST-extracted byte-identical
bodies at the dispatch base, origin/main cfc9415c1; content-hash pinned in
`scripts/oracle_hashes.json` AND by the differential's own per-body digest).

### The Python-side split (what stays, with evidence)

- **`_pipeline_route._select_sat_nets`** — `run_select_sat_nets`: the top-N
  nets by ascending pin count (the dict first-insertion-order / last-writer-
  wins semantics and the stable `sorted(..., key=)` replicate CPython
  exactly). The shim marshals `[(net.name, len(net.pins))]`.
- **`_pipeline_route._build_clause_origin`** — `run_build_clause_origin`: the
  CNF clause-index -> constraint-name registry (the terms /
  group_a_indices / p_var priority with `max(1, n*3)` clause counts). The
  `ConstraintModel` is passed through; the duck-typed `hasattr` /
  truthiness / `len` walk mirrors the oracle.
- **`_pipeline_route.select_routing_grids`** — `run_select_routing_grids`:
  the (primary, alternate) occupancy-grid pick (the `or` truthiness
  fallback — pinned by a falsy-grid differential case — and the
  alternate-excludes-the-PRIMARY-layer rule that fixed the plane-outer-board
  double-primary bug). The original grid objects are returned.
- **`_adapter_convert._next_tstamp`** — `run_next_tstamp`: the deterministic
  KiCad `tstamp` UUIDv5 sequence. The RFC 4122 version-5 UUID is
  `sha1(namespace.bytes + name)[..16]` — CPython 3.12's `uuid.uuid5` is the
  SHA-1-based UUID (a first cut ported RFC 1321 MD5, which is UUIDv3's
  algorithm, and the differential caught the divergence immediately); the
  SHA-1 is hand-rolled (RFC 3174, pinned by the RFC test vectors + the
  multiblock padding vectors) so the crate adds no digest dependency. The
  shared counter list is mutated in place (`counter[0] = n+1` before the
  UUID renders), preserving the single sequence across the Rust emission
  core and the Python zone-pour emission.
- **`_adapter_convert._to_stage0_netclass_rules`** — 
  `run_to_stage0_netclass_rules`: the netclass SSOT->stage0 conversion
  boundary (explicit alias checking with the TypeError message rendered
  through CPython `str.format` — `{!r}` of the type name, `{}` of the alias
  list — byte-identical; the unrepresented-field warnings through the
  ORIGINAL module's logger, so `caplog` sees the same records). The
  `_UNREPRESENTED_WARN` table stays the Python SSOT and is marshalled once
  per call (the E3 `_matrix_rows` precedent); the shim wraps the returned
  values in the `stage0_data.NetClassRules` dataclass (Python
  single-source).
- **`_adapter_convert._write_routes_to_content`'s emission core** —
  `run_write_route_segments`: the collinear-step merge (the 1e-12 epsilon
  comparison, the layer-change / coincident-point skips — "no zero-length
  segment is emitted" holds outright) and the `(segment ...)` / `(via ...)`
  s-expression rendering with CPython `{:.4f}` floats (David-Gay by identity,
  not by formatter coincidence) and the shared tstamp counter. The shim
  drives ONE payload per compiled route so the counter's increment order
  relative to the (Python) tree-route branch stays byte-identical.

**What stays Python (evidence)** — `_run_stage3` / `_run_stage4` /
`_run_stage5` / `_augment_with_pcl_constraints` stay: they are the ortools /
CP-SAT-boundary glue (the net-batching branch is batch E5's owner, the
`temper_rust_router` solve invocation is that package's surface, the
`ModelBuilder` / `BundleAnalyzer` / `TopologicalSolution` /
`TopologyGraph` / `Stage4Orchestrator` wiring is dataclass-construction glue
whose kernels are already Rust). `route_pcb` / `_build_routing_result` /
`_apply_placements_to_pcb` / `_reorient_pads_in_footprint_block` stay: the
pipeline-invocation glue, the failure-extraction assembly and the `re`-based
s-expression text rewriting — the crate has no regex engine and the
`_PAD_AT_RE` pad-reorientation rewrite is a Perl-5-flavoured regex state
machine (backreferences, optional angle groups) that a hand-rolled parser
would risk silently mis-porting. The chamfer (`_chamfer_path_points`), the
tree-route folding (`TreeRouteGeometry.iter_segments`), the zone-pour
emission (`_emit_zone_pours`), the s-expression injection and the net-number
regex parsing stay Python single-source. No new Python API is invented; the
two modules' public surfaces (`adapter.py` re-exports, the patched
`RouterV6Pipeline._run_stage{3,4,5}` methods) are unchanged.

### Structural proof (bit-identical parity)

The differential drives both arms with identical inputs and compares every
return value bit-exact (routed content byte-for-byte, `float.hex()` via
`canon`, tstamp sequences as emitted). The load-bearing equivalences:

- **uuid5 by algorithm, pinned by the differential.** CPython 3.12's
  `uuid.uuid5(ns, name)` = SHA-1 of `namespace.bytes + name.utf-8`, first 16
  bytes with the version-5 / variant bits, rendered as the lowercase
  8-4-4-4-12 hex string. The ported SHA-1 is pinned by the RFC 3174 vectors,
  the multiblock padding vectors (55/56/57-byte inputs crossing the block
  boundary) and — decisively — by the differential's byte-exact tstamp
  comparisons against the oracle's `uuid5` calls.
- **CPython rendering.** The `{:.4f}` segment/via floats render through
  CPython `str.format` (`py_fmt4`), the TypeError message through CPython
  `str.format` (`{!r}` / `{}` conversions) and the unrepresented-field
  warnings through CPython `logging` with the original module's logger — the
  `%s`/`%r` formatting is CPython's. Parity by identity.
- **Dict/`or`/len semantics.** `_select_sat_nets` replicates the dict
  comprehension's first-insertion order / last-writer-wins and the stable
  sort; `select_routing_grids`' `or` is a truthiness test (a falsy grid
  object falls through, pinned), `dict.get` missing-key -> None, and the
  alternate's key comparison is against the PRIMARY's layer name (never the
  literal `"F.Cu"`).
- **The emission merge is a straight transcription.** The inner `while j`
  loop's `(abs(dx_cur - dx_prev) < 1e-12 ...)` epsilon comparisons and the
  layer/coincident skips map 1:1; the `i = j - 1` advance is identical. The
  width snap (`if not width or width <= 0.0`) reproduces Python's NaN
  survival (NaN is truthy and never `<= 0.0`).
- **The via loop is outside the path guard in both arms.** The oracle's
  `net_num` is defined before the guard, so vias emit for every non-tree
  route regardless of `path_length`; the Rust port resolves `net_num` per
  route and does the same (the differential's randomized routes include
  zero-length paths with vias).
- **Per-route FFI preserves the counter order.** One `run_write_route_segments`
  call per compiled route means the shared tstamp counter increments exactly
  where the pre-migration loop did, interleaved with the Python tree-route
  emission and followed by the Python zone-pour emission.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above): the s-expression text rewriting
(`_apply_placements_to_pcb` / `_reorient_pads_in_footprint_block`), the
tree-route branch, the chamfer and the zone-pour path stay Python (no regex
engine / shapely single-source / `TreeRouteGeometry.iter_segments` duck-
typing); the Stage3/Stage4/Stage5 dispatch and the `route_pcb` pipeline
invocation stay Python (the ortools / temper-rust-router boundary).

### Empirical Verification

- **Differential suite**: `test_pipeline_route_rust_differential.py` (41
  tests, all green) — the oracles are content-hash-pinned (per-body digests
  in the differential AND the registry); the shims bind to the
  `temper_orchestration` pyfunctions (anti-vacuity assert), the oracles stay
  pure Python. `_select_sat_nets` over the None/unbounded/bound/ties/
  duplicates/max==len edges + 30 randomized; `_build_clause_origin` over the
  terms / group / p_var / plain priority, the empty-terms fall-through and 30
  randomized constraint sets; `select_routing_grids` over the F.Cu/B.Cu
  preference, the plane-outer fallback, the alternate-excludes-layer rule,
  the single-grid no-alternate case, a falsy grid and 30 randomized dicts;
  `_next_tstamp` sequences (shared counters, nonzero start); 
  `_to_stage0_netclass_rules` over full/alias/default/None-safety shapes, the
  TypeError (bit-identical message), the unrepresented warnings (same logger,
  same records) and 25 randomized real `NetClassRules` instances;
  `_write_routes_to_content` over the no-routes / no-routing-results /
  merged-segment / staircase+via / layer-change-split / coordinates-branch /
  zero-length / single-pad / unknown-net / nonpositive-width edges and 20
  randomized route sets — byte-identical content and pad_positions.
- **PBT suite**: `test_pipeline_route_rust_pbt.py` (14 tests, all green) —
  seven non-vacuous properties (P1 selection ordering + bound, P2
  determinism + last-writer-wins, P3 clause-origin accounting, P4 grid-pick
  contract, P5 tstamp determinism + UUIDv5 validity, P6 netclass totality,
  P7 emission well-formedness — no zero-length formatted segment), each with
  a discriminating vacuity guard.
- **Metamorphic suite**: `test_pipeline_route_rust_metamorphic.py` (8 tests,
  all green) — four relations (MR1 selection order-invariance, MR2 alias
  equivalence, MR3 collinear sub-division invariance — the grid-staircase
  collapse, MR4 B.Cu-removal covariance), each with a discriminating
  companion.
- **Runner suite**: `tests/e6_stages_runner.rs` (4 tests, all green) — the
  `PipelineRouteStage` sequences through `PipelineRunner<BoardState>`,
  completes without panicking (guarded identity on `None` payload), and the
  read-only stage preserves the state.
- **Consumer suites**: the full pre-existing pipeline-route + adapter surface
  stays green with the delegating shims — `test_adapter.py` (97 passed, 1
  skipped), `test_stage4_golden_parity.py`, `test_stage4_monolith_parity.py`,
  `test_wave2_structural_small.py`, `test_astar_nlayer.py`,
  `test_tree_grid_layer_mismatch.py`, `test_zero_length_segments.py` (131
  passed, 3 skipped across those seven) — identical pass/fail signature to
  the origin/main baseline. `test_bundled_full_pipeline.py`'s single failure
  (`test_bundled_pipeline_reaches_rust_solve_boundary`, an
  `edges_with_data` AttributeError) is pre-existing on origin/main
  (reproduced in the main checkout before this batch).
- **Rust unit tests**: `pipeline_route.rs` carries `#[cfg(test)]` unit tests
  (the SHA-1 RFC 3174 vectors, the multiblock padding vectors, the uuid5
  shape/determinism, the select-sat-nets bounds + stable order + duplicate
  last-writer-wins). `cargo test` 141/141 lib green (+ the E1..E7 runner
  suites); `cargo clippy --all-features --all-targets -- -D warnings` clean.
- **Wiring**: `check_unwired_kernels.py` reports no new unwired kernel — the
  six pyfunctions are referenced by the delegating shims, so the Python AST
  scan sees them wired; `make regen-check` reports all derived artifacts
  consistent (incl. the two new oracle pins).
- **G6 induction** — N/A: every migrated orchestration is a bounded loop nest
  over nets/constraints/grids/routes with size-independent per-step
  operations; the merge loop advances monotonically. Structural proof above.
- **G8 physics discipline** — N/A for the migrated orchestration: it
  selects/counts/formats from already-physics-gated inputs; no new physics
  quantity is gated.
- **R1g Rust bar**: every `#[pyfunction]` body is wrapped in `catch_unwind`
  by pyo3's macro expansion (the crate sets `profile.release.panic =
  "unwind"`); the `Stage` run() body runs under `stage_guard`; no
  `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

## Rust orchestration engine — Phase E unit U-H (adapter marshalling residual)

Rust Orchestration Engine plan 2026-08-09-001 Phase E E6 follow-on (unit
U-H): the residual deterministic wire-format construction of
`router_v6/_adapter_convert.py` — the part of the adapter that builds the
router's input/output wire formats around the already-ported E6 kernels —
moves to `src/pipeline_route.rs` (append-only, next to the E6 kernels).
The shim delegates; the public API is unchanged.

### What migrated

| `_adapter_convert.py` block | Rust kernel (pipeline_route.rs) | Wire format |
|---|---|---|
| `_write_routes_to_content`'s pad-positions block | `run_collect_pad_positions` | board → `pad_positions` dict/vector assembly (its per-net length feeds `run_write_route_segments`' pad count, the zone-pour emission and the connectivity preflight) |
| `_write_routes_to_content`'s per-route payload block | `run_build_route_payload` | route → `RouteEmission` payload tuple fed to `run_write_route_segments` (the E6 emission core) |
| `_build_routing_result`'s failure-extraction assembly | `run_build_routing_result` | result → plain-data extraction (`unrouted_nets`, `forced_segment_nets`, DRC violations, congestion regions, `topology_solved_nets`) |

**What stays Python (evidence)**: `route_pcb` (pipeline invocation,
`tempfile`/subprocess boundary, the `RouterV6Pipeline` / `_apply_placements_to_pcb`
call-backs), `_apply_placements_to_pcb` / `_reorient_pads_in_footprint_block`
and the net-name→number regex mapping (the `re`-based s-expression handling —
the crate has no regex engine, the E6 boundary), the tree-route folding
(`TreeRouteGeometry.iter_segments` call-back), the s-expression injection,
the zone-pour emission (`_emit_zone_pours` / `strip_existing_zones`) and the
`connectivity_preflight` call-back (the shim drives the whole
`_build_routing_result` with `enable_connectivity_verifier=False` in the
differential; the call-back stays Python single-source, exercised by
`test_adapter.py`). `_chamfer_path_points` stays Python single-source and is
CALLED BACK from `run_build_route_payload` through the
`temper_placer.router_v6._zone_pour_stitch` module at runtime (the D4/D5
mixin-call-back pattern — parity by construction). No new Python API is
invented.

### Structural proof (bit-identical parity)

The differential drives both arms with identical inputs and compares every
observable bit-exact (dicts/lists through the `_canon` walker with
`float.hex()`, dataclass equality on the wrapped `RoutingResult`, routed
content byte-for-byte against the E6 oracle). The load-bearing equivalences:

- **The pad-positions walk is a straight transcription.** `comp_by_ref`
  last-writer-wins (the dict comprehension), the `getattr(net, "pins", [])`
  default, the `comp.get_pin(pin_name)` conditional call (missing method or
  `None` pin → `comp.initial_position`, default `(0.0, 0.0)`), the
  `float(comp_pos[0]) + float(px)` sums and the first-seen net order /
  empty-positions omission all map 1:1.
- **The payload guard and branches.** `path_length > 0 and pad_count >= 2`
  gates the points; the segments branch (`(s[0], s[1], s[2])`) and the
  coordinates branch (`(c[0], c[1], default_layer)` with
  `getattr(path, "layer_name", "F.Cu")`) reproduce the oracle's duck-typed
  reads; the chamfer runs INSIDE the kernel through the Python module
  (identity of call + arguments ⇒ bit-identical chamfered points); vias are
  extracted OUTSIDE the guard exactly like the oracle.
- **The width snap.** `not width or width <= 0.0` is a truthiness check
  (None/0/0.0 snap to 0.2; NaN is truthy and never `<= 0.0`, so it
  survives) — the Rust port checks truthiness before extraction and then
  applies the same `== 0.0 || <= 0.0` snap `run_write_route_segments`'
  emission core already uses (idempotent).
- **Dict iteration semantics.** `compiled_routes` is walked via
  `PyDict.iter()` for the (key, value) pairs the oracle's `.items()` yields
  (`PyObject_GetIter` would yield keys — a real divergence the differential
  caught and the port documents); `net_topologies` keys are iterated as keys
  (`list(dict.keys())`).
- **CPython `> 0` and `in` membership.** The `drc_count > 0` /
  `forced_segment_count > 0` guards and the
  `pair_kind in ("component_edge", "component_keepout")` membership go
  through CPython comparison/equality (`Bound::gt` / `Bound::eq`), matching
  the oracle for ints, floats, `None` and duck-typed values alike.
- **Violation ordering.** Report violations append first (in `net_reports`
  order), manufacturing-report violations after — the oracle's two-loop
  order, pinned by the differential's combined case.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above): the `re`-based net-number parsing, the
s-expression injection, the tree-route branch, the zone pours, the chamfer
source and the `connectivity_preflight` call-back stay Python; the
`DrcViolation` / `CongestionRegion` dataclass construction stays Python (the
kernel returns plain tuples — the D4 `StageDRCFailure` precedent).

### Empirical verification (U-H)

- **Differential suite**: `test_adapter_convert_marshal_rust_differential.py`
  (28 tests, all green) — the three pre-migration blocks are pinned VERBATIM
  as inline `_oracle_*` functions (per-body SHA-256, `test_oracle_bodies_match_pinned_digests`
  fails on any drift); the anti-vacuity tripwire asserts the shims bind to
  the `temper_orchestration` pyfunctions. Coverage: None/empty pcbs, the
  get_pin resolution / `None`-pin fallback / missing-attr defaults, the
  duplicate-ref last-writer-wins, 30 randomized pcbs, zero-length / single-
  pad / chamfered-corner / coordinates-with-and-without-layer payloads, the
  width snap (0, negative, missing, NaN-survival), the via extraction order,
  30 + 10 randomized payloads, the empty/forced-segment/report/mfg/
  congestion/topology routing-result cases (incl. missing stage3 /
  topology_graph / net_topologies) and 30 randomized results, plus two
  full-shim byte-for-byte comparisons of `_write_routes_to_content` against
  the pre-E6 oracle (the E6 differential's `_adapter_convert_py_oracle.py`).
- **PBT suite**: `test_adapter_convert_marshal_pbt.py` (12 tests, all
  green) — six non-vacuous properties (P1 pad-positions totality + order, P2
  determinism + first-seen order, P3 the payload guard with vias kept, P4
  the width snap, P5 unrouted/forced-segment extraction, P6 violation /
  congestion extraction), each with a discriminating vacuity guard.
- **Metamorphic suite**: `test_adapter_convert_marshal_metamorphic.py`
  (8 tests, all green) — four relations claimed BIT-EXACT (MR1
  unresolvable-pin content invariance, MR2 pin-order permutation invariance,
  MR3 zero-violation-report invariance, MR4 non-collected-bottleneck
  invariance), each with a discriminating companion.
- **Runner suite**: `tests/uh_marshal_runner.rs` (2 tests, all green) — the
  three kernels driven THROUGH the registered pyfunctions (the exact seam
  the shims use) in the collect → payload → emit → result sequence, with a
  sys.modules fake for the chamfer call-back seam and the degenerate-input
  no-panic guards.
- **Consumer suites**: the full pre-existing adapter + pipeline-route
  surface stays green with the delegating shims —
  `test_adapter_convert_rust_differential.py`,
  `test_pipeline_route_rust_differential.py`,
  `test_pipeline_route_rust_pbt.py`,
  `test_pipeline_route_rust_metamorphic.py`, `test_adapter.py` (177 passed,
  1 skipped across those five), plus
  `test_stage4_golden_parity.py` / `test_stage4_monolith_parity.py` /
  `test_wave2_structural_small.py` / `test_tree_grid_layer_mismatch.py` /
  `test_zero_length_segments.py` / `test_adapter_repair_verification.py`
  (29 passed, 2 skipped) — identical pass/fail signature to the origin/main
  baseline.
- **Rust bar**: `cargo test` 1071 lib green (1069 + the 2 U-H runner tests;
  all D1-D7 / U4 / E6 runner suites green); `cargo clippy --all-features
  --all-targets -- -D warnings` clean; the `--no-default-features` lib
  (host_math dlsym) and the `wasm-test-registry` check build both pass. No
  `unwrap`/`expect` outside tests (crate denies both); every `#[pyfunction]`
  body is wrapped in `catch_unwind` by pyo3's expansion
  (`profile.release.panic = "unwind"`).
- **Wiring / gates**: `check_unwired_kernels.py` reports the three new
  kernels wired (the delegating shims reference them); `make regen-check`
  reports all derived artifacts consistent (no new oracle files, no lib-test
  registry changes); `import_linter_gate.py` PASSED (no new violations).
- **G6 induction** — N/A: every migrated block is a bounded loop over
  components/nets/pins/routes/reports with size-independent per-step
  operations; no recursive computation. Structural proof above.
- **G8 physics discipline** — N/A: the marshalling converts/selects/formats
  already-physics-gated inputs; no new physics quantity is gated.

## Rust orchestration engine — Phase C residual (pipeline contract tail)

The plan's Phase C "What Python is removed: ~1,550 LOC of pipeline
orchestration" is nearly complete (U1–U4 landed); this section records the
residual tail — the four pipeline-contract modules — migrated as pyclasses,
each with a differential against a VERBATIM pre-migration oracle in the
temper-placer test tree:

| Python module | Home (module in this crate) | Migrated | Kept Python |
|---|---|---|---|
| `pipeline/dag_types.py` | `dag_types.rs` | `StageResult` (dataclass contract) | `DAGError` hierarchy (incl. `DAGExprError`/`DAGExprSyntaxError`), `DataContext` alias, `PipelineState`/`StageHandler` Protocols |
| `pipeline/dag_observability.py` | `dag.rs` | `StageEvent`, `PipelineExecutionLog` (incl. the asdict `to_dict` serialization) | `ProgressObserver` Protocol, `write_execution_log_json` (stdlib I/O + `json.dump` over the Rust `to_dict()`) |
| `pipeline/bottleneck_report.py` | `bottleneck.rs` | `BottleneckNetEntry`, `BottleneckRegion`, `CongestionHeatmapData`, `BottleneckReport`, `DeclaredArtifact` (full serialization surface) | nothing |
| `pipeline/metrics_observer.py` | `metrics.rs` | `MetricsObserver` (the cross-validation + canary decisions), `CanaryCheckError`, `CrossValidationError` (pyo3 exceptions subclassing `ValueError`) | `SchemaValidator` + `PipelineMetricsRecord`/`record_metrics` call-backs (owned by `regression/`), `time.monotonic()`/`time.time()` runtime semantics |

`dag_expr.py`'s predicate parser already lives in `temper-io-types`
(out of scope); the DAG exception classes that module's shim needs stay on
the Python `dag_types` shim, so no parser logic was duplicated.

### Boundaries (argued in the module headers, reproduced here)

- **Exceptions**: `DAGError`/`DAGExprError`/`DAGExprSyntaxError` stay Python
  (the U4 `PipelineError` precedent — no bit-exact pyclass mapping for
  exception hierarchies in scope). The metrics exceptions are the ONE
  exception: the plan's Phase C table explicitly names `CanaryCheckError` /
  `CrossValidationError` in the migrated column, so they are pyo3 exceptions
  subclassing `ValueError` (the `issubclass(e, ValueError)` contract holds;
  `__module__ == "temper_orchestration"`).
- **Protocols/type aliases** (`ProgressObserver`, `PipelineState`,
  `StageHandler`, `DataContext`): typing-only constructs — pyo3 has no
  Protocol/typing-only mapping, so there is no runtime value to migrate.
- **`dataclasses.asdict` semantics**: `PipelineExecutionLog.to_dict()`'s
  event transform is a 1:1 port of CPython's `dataclasses._asdict_inner`
  (dataclass instances → dicts in definition order, namedtuples keep their
  type, list/tuple/dict recurse element-wise, every other leaf via
  `copy.deepcopy`). The deepcopy leaf is a stdlib library semantic and is
  delegated to CPython — reimplementing `copy.deepcopy` bit-exactly is the
  "library semantics" trap the R3 records name. `asdict` cannot run on the
  pyclasses themselves (`__dataclass_fields__` requirement), which is why the
  algorithm is ported rather than called. ClassVar-bearing user dataclasses
  and dict/list subclasses are a documented boundary (the declared types are
  plain containers).
- **Type identity is load-bearing in bottleneck_report**: the dataclasses
  store EXACTLY the value passed to the constructor (int stays int, repr
  `0`), so the numeric-ish fields are `Py<PyAny>` raw, NOT Rust scalars.
  `BottleneckReport.from_dict` coerces `float()`/`int()` exactly where the
  oracle does; the differential pins the int-vs-float cases explicitly.
- **Rendered strings go through CPython**: `to_json` uses `json.dumps(...,
  indent=2)`, `write` delegates to the path's `write_text`, the metrics
  exception messages render floats through the `py_float_fmt` seam and every
  other leaf through CPython `str()` — David-Gay formatting parity by
  identity, the d6_util precedent. `wall_time_ms = int(duration_s * 1000)`
  computes through CPython `int()` (Python raises `OverflowError` for
  non-finite / out-of-range, Rust casts saturate — delegated, not
  reimplemented).
- **`time.time()`/`time.monotonic()`** stay CPython runtime semantics (never
  reimplemented in Rust; the U8 default-factory precedent).
- **Documented constructor boundaries** (exercised by the differential, which
  drives the declared types only): an EXPLICIT `None` passed to a
  container-typed constructor argument is treated as the omitted sentinel
  (fresh container); `StageEvent.timestamp` / `MetricsObserver.canary_value`
  explicit `None` is treated as the omitted default; scalar fields coerce to
  `f64` on assignment (`5` → `5.0`); `StageResult` / `BottleneckReport`
  constructors substitute their dataclass defaults for an omitted argument.
- **The mock seam is preserved**: `MetricsObserver.on_stage_complete`
  dispatches `_validate_schema` / `_cross_validate_against` / `_check_canary`
  / `_write` through Python attribute lookup on the instance
  (`#[pyclass(dict)]`), so the pre-existing `test_metrics_observer.py`
  `mock.patch.object` tests intercept exactly as they did on the pure-Python
  class; `_stage_start_times` is a real Python dict.
- **No duplication of the dag_expr parser**: the DAG `dag_types` shim keeps
  the exception classes and the type alias only; the parser/evaluator stays
  single-source in `temper-io-types::dag_expr` (pinned by the existing
  `test_dag_expr_rust_differential.py`).

### Differential / PBT / metamorphic suite

`tests/pipeline/test_phase_c_tail_rust_differential.py` (52 tests): the four
oracle bodies are content-hash pinned (sha256 in the suite + registered in
`scripts/oracle_hashes.json`), the port is proven distinct from the shim
(`__module__`), every differential assertion is bit-exact (`repr()` equality
for whole objects and per-field signatures, JSONL byte-equality for the
metrics write path under a frozen metrics timestamp, exception-message
equality for the cross-validation/canary failure paths). Six non-vacuous PBT
properties (each with a `test_pN_fails_for_*_mutant` guard) and four
metamorphic relations. The 37 pre-existing pipeline tests
(`test_dag_types`, `test_dag_observability`, `test_bottleneck_report`,
`test_metrics_observer`) pass unchanged through the delegating shims.

### Structural proof (bit-identical parity)

Bit-exactness is established by the differential suites (G4-companion):
every migrated surface either (a) delegates the stdlib formatting / deep-copy
/ time / json / int-coercion leaves to CPython so parity is by identity, or
(b) is a finite, order-preserving recursion over caller-provided containers
whose per-step operation is size-independent (`asdict_inner`, the
`to_dict`/`from_dict` walks), pinned across the input shapes the differential
drives.

### G8 physics discipline

Not physics-gated (R1h): none of the migrated surfaces gates on a physics
quantity. The R24 discipline does not apply; the canary/timing checks are
pipeline-integrity invariants, not physics bounds.

### Gates

- `cargo test -p temper-orchestration` — 141 lib + runner suites green.
- `cargo clippy --all-features --all-targets -- -D warnings` clean.
- `import_linter_gate.py` — PASSED, 0 new violations.
- `make regen-check` — oracle registry 158/158 OK; the only `regen-check`
  REFUSE is the pre-existing `loop_area.py:108` hash-order NEW_SITE on
  origin/main (unrelated to this slice; not touched here).
- `check_unwired_kernels.py` — no new unwired kernel: every new pyclass is
  referenced by its delegating shim, so the Python AST scan sees it wired.

## Rust orchestration engine — stage_ledger (the final portable router_v6 module)

Rust Orchestration Engine plan 2026-08-09-001, the last router_v6
ORCHESTRATION slice: the `router_v6/stage_ledger.py` cardinality compute moves
to `src/stage_ledger.rs` as the `snapshot_cardinality` (the pre-migration
`_snapshot` counting over duck-typed BoardState / ParsedPCB / routing-result
shapes) and `diff_cardinality` (the pre-migration `_diff` five-field compare)
pyfunctions plus the `CardinalitySnapshot` pyclass (the `_CardinalitySnapshot`
dataclass). The pre-migration module is pinned VERBATIM as
`tests/router_v6/_stage_ledger_py_oracle.py` (content-hash registered in
`scripts/oracle_hashes.json` AND by the differential's own per-body digest for
`_snapshot`/`_diff`). The production caller (`_pipeline_core.py`'s
`StageLedger(fail_on_imbalance=False)`, wired at
`_pipeline_core.py:259`) is untouched.

### The Python-side split (what stays, with evidence)

- **The stateful orchestration** — `StageLedger` itself: the `_pre`/`_post`
  snapshot storage, the `checkin`/`checkout`/`verify` flow, the
  `fail_on_imbalance` raise decision and the `_logger` emission. This is
  state plus side effects (logging, raising the module's own exception type);
  exceptions stay Python per the crate-wide convention.
- **The presentation** — `LedgerReport` + its `__str__`, and the checkout
  message rendering (`Stage '{stage}' introduced cardinality imbalance:` plus
  the `  field: before -> after` lines). This is the human-readable rendering
  of the diff list, the same family as `LedgerReport.__str__` — presentation,
  not compute. The differential pins it bit-exactly anyway, because the shim
  keeps the oracle's exact orchestration over the Rust-returned diff.
- **`StageLedgerImbalanceError`** — the exception class.

The migrated compute feeds the shim through three wired symbols
(`CardinalitySnapshot` is stored in `_pre`/`_post`; `snapshot_cardinality` is
called by `checkin`/`checkout`; `diff_cardinality` by `checkout`), so the
unwired-kernel gate sees every new export referenced by production Python.

### Bit-exactness traps pinned in the module

- `hasattr` swallows only `AttributeError` — `has_attr` propagates every other
  exception exactly like CPython's `hasattr` (pinned by the `len(object())`
  TypeError differential case).
- `if state_or_pcb.channel_skeletons:` and `getattr(..., None) or ()` are
  TRUTHINESS tests — replicated with `PyAny::is_truthy()`, so a custom
  `__bool__` behaves identically.
- The three dict-shaped walks (`channel_skeletons`, `routing_spaces`,
  `compiled_routes`) iterate `.values()` exactly like the oracle — the first
  cut iterated dict keys and the differential caught it immediately.
- `isinstance(val, dict)` is subtype-aware (`PyObject_TypeCheck`), so a dict
  subclass in `routing_spaces` is still counted.
- `max(0, len(coordinates) - 1)` for an empty coordinates list is
  `len().saturating_sub(1)`.

### Differential / PBT / metamorphic suite

`tests/router_v6/test_stage_ledger_rust_differential.py` (25 tests): the two
oracle bodies are content-hash pinned (sha256 in the suite + registered in
`scripts/oracle_hashes.json`); the port is proven distinct from the shim
(`__module__` binding, recording-stub delegation proofs for both pyfunctions);
every differential assertion is bit-exact (`repr()` equality for snapshots —
the Rust `__repr__` reproduces the `_CardinalitySnapshot` dataclass string —
field-level equality, exact `_diff` list/tuple equality, `LedgerReport`
field/`str()` equality across the shim-vs-oracle arms, exception-message
equality). Seven non-vacuous Hypothesis properties (differential over random
count vectors for both kernels and both report paths, self-diff emptiness,
exactly-the-changed-fields, common-shift delta preservation) and five
metamorphic relations (swap-flips-before-after, common-shift, balance
transitivity, verify idempotence, snapshot purity). The 7 pre-existing
`test_stage_ledger.py` tests pass unchanged through the delegating shim.

### Structural proof (bit-identical parity)

The migrated compute is a direct transcription of the oracle's two functions
with the load-bearing equivalences above, each pinned by the differential.
Wherever the oracle's semantics are Python value semantics (`hasattr`,
`len()`, `isinstance`, truthiness, `__bool__`, exceptions), the Rust side
calls back into CPython (`PyObject_Size` for `len`, `PyObject_TypeCheck` for
`isinstance`, `is_truthy`, AttributeError-scoped probing) so parity is by
identity; the control flow (branching, the fixed five-field iteration order,
the counting) is Rust.

### G8 physics discipline

Not physics-gated (R1h): cardinality counting and comparison gates on no
physics quantity. The R24 discipline does not apply.

### Gates

- `cargo test -p temper-orchestration` — lib suite green (incl. the
  python-gated `stage_ledger::tests` unit tests: pure `diff_counts` pins +
  the repr/eq dataclass-shape pins).
- `cargo clippy --all-features --all-targets -- -D warnings` clean.
- `cargo build --no-default-features` and `--features wasm-test-registry`
  clean (the `stage_ledger::tests` module is census-classified
  `[python-gated]`, so no registry regeneration is needed).
- `import_linter_gate.py` — PASSED, 0 new violations.
- `make regen-check` — oracle registry 159/159 OK; all derived artifacts
  consistent.
- `check_unwired_kernels.py` — no new unwired kernel: every new pyclass /
  pyfunction is referenced by its delegating shim, so the Python AST scan
  sees it wired.

# Regression reporter (`reporter.rs`) — Verification

The Wave-4 tail-tooling migration of `temper_placer/regression/reporter.py`
(152 LOC): all four classes move to `src/reporter.rs` as pyclasses —
`MetricDelta` (the `delta_display`/`message()` delta computation),
`BoardResult`, `BatteryVerdictReport` and `RegressionReporter` (the
`total`/`passed`/`failed`/`skipped`/`has_failures` counting and the
`summary()`/`battery_report()` verdict/result formatting). The pre-migration
module is pinned VERBATIM as
`packages/temper-placer/tests/regression/_reporter_py_oracle.py`
(content-hash registered in `scripts/oracle_hashes.json`); the shim
(`regression/reporter.py`) re-exports the pyclasses by identity (public API
unchanged — `runner.py`, `cli.py` and the existing suites construct them
identically).

## Home-crate decision

The reporter is a *reporting* surface — the task's per-module home decision
places reporting in `temper-orchestration` (vs `temper-io-types` for
hashing/manifest, where quarantine and the golden-manifest live). The
classes are data + formatting; the formatting (delta rendering, summary /
battery-report renderers) and the counting are the portable compute.

## What migrated vs stayed Python

| Piece | Verdict |
|---|---|
| `MetricDelta.delta_display` / `message()` (the sign-prefixed delta rendering, the `name: current vs baseline (delta)` line) | migrated (pyclass methods; floats rendered through CPython `str`, David-Gay decimal stays Python) |
| `MetricDelta`/`BoardResult`/`BatteryVerdictReport`/`RegressionReporter` dataclass semantics (fields, defaults, `repr`/`str`/`eq`) | migrated (pyclasses with CPython-`repr`-built dataclass strings and type-strict `__eq__`) |
| `RegressionReporter` counting + `summary()`/`battery_report()` renderers | migrated (Rust iteration + key-sorted `board_shape` join; `:.1f` cost via `d6_util::py_format`, verdict `upper()` via CPython) |
| the helps-battery *decision* (verdicts, `budget_exceeded`, the verdict thresholds) | stays Python in `validation/_thermal_battery.py` (out of this module's scope — the reporter only renders what it is handed) |

## Induction applicability

**Mathematical induction is not applicable.** Rendering and counting are
single-pass loops over the results/verdicts lists with no recursion or size
parameter. A **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every input in the differential
domains (documented cases + Hypothesis-generated metric values, result
mixes, board shapes, verdict sets), the four pyclasses produce values
bit-identical to the pinned oracle's dataclasses (`delta_display`,
`message`, `repr`/`str`, field values, counts, `summary()`,
`battery_report()`).

*Proof by structural cases.*

1. **`delta_display`.** `"+" if delta > 0 else ""` is `delta_sign`; the float
   rendering is CPython `str(float)` (`PyFloat::str`), so exponent-range and
   signed-zero values (`-0.0` → `"-0.0"`) are bit-identical by construction.
2. **`message()`.** The `"name: current vs baseline (delta_display)"` line
   is assembled from the same CPython-rendered floats.
3. **Counting.** `total`/`passed`/`failed`/`skipped`/`has_failures` are the
   oracle's `sum(1 for r in results if ...)` predicates over the stored
   `BoardResult` fields (`failed` = not passed and not skipped).
4. **`summary()`.** The renderer reproduces the oracle line-for-line: the
   header block, per-result `[SKIP]/[PASS]/[FAIL]` lines, the `board_shape`
   line via a Rust key-sorted `k=v` join (keys are ASCII identifiers, so
   byte order == code-point order), skip reasons, `REGRESSION:` lines for
   regression-flagged deltas (via each delta's `message()`), warnings,
   errors, and the battery-verdicts section (`verdict.upper()` and the
   `:.1f` cost column routed through CPython).
5. **Dataclass semantics.** `repr`/`str` build `Class(field=..., ...)`
   strings from CPython `repr()` of every field (single-quoted strings,
   `repr(float)`, `True`/`False`); `eq` is type-strict with field-wise
   comparison (containers via CPython `==`), exactly like dataclass `__eq__`.

## R1 gate status

| Gate | Status | Evidence |
|---|---|---|
| R1a behavioural A/B | PASS | `tests/regression/test_reporter_rust_differential.py` (25 tests): delta display/message/repr/str/eq over 6 documented metric shapes, BoardResult/BatteryVerdictReport repr/eq/defaults, counts + summary + battery_report over 6 result sets incl. the richest full-shape report, `repr` of the reporter, and the oracle class bodies content-hash pinned in-suite and in `scripts/oracle_hashes.json`. |
| R1b no-regression arm | N/A, recorded | the reporter runs once per regression-suite invocation on a sub-second surface; no speedup is claimed. |
| R1c ≥5 non-vacuous properties | PASS | 7 hypothesis properties (delta_display differential, message+repr differential, counts differential over random mixes, board-shape-line differential, battery_report differential, sign invariant — each pins a distinct branch against a distinct implementation). |
| R1d ≥3 MRs | PASS | 4 metamorphic relations (adding a failure flips `has_failures` and moves the counters in lockstep; only regression-flagged deltas emit REGRESSION lines; summary is the ordered concatenation of per-result blocks; battery_report is empty-exact then populated). |
| R1e VERIFICATION.md | PASS | this section |
| R1f TDD | PASS | the differential file was authored against the not-yet-registered surface; the shim re-export is proven by identity (`shim_cls is pyo3_cls`) |
| R1g Rust practice | PASS | no `unwrap`/`expect` outside `#[cfg(test)]`; the pyo3 boundary is catch_unwind-wrapped by pyo3's pymethod expansion (the crate sets `profile.release.panic = "unwind"`); `cargo clippy --all-features --all-targets -- -D warnings` clean. |
| R1h R24 | N/A | no physics quantity is computed, asserted, or gated. |

## Documented bounds (per R1, recorded here)

1. **Verdict thresholds stay Python.** The reporter renders `verdict` /
   `budget_exceeded` / `verdict_details` as handed in; the helps-battery
   decision lives in `validation/_thermal_battery.py`. This is the task's
   documented pure-Python-orchestration boundary for this module.
2. **Float rendering is CPython-routed.** `str(float)` (via `PyFloat::str`)
   and `:.1f` (via `str.format`) are not reimplemented in Rust — the
   repo-wide David-Gay convention (same as `d6_util`) keeps parity by
   construction; the differential still pins it end-to-end.
3. **`board_shape` keys are ASCII.** The summary's `sorted(...)` join uses
   Rust byte-order string sort; Python's sort is code-point order. Board
   shape keys are ASCII identifiers (`component_count`, `net_count`), so the
   orders coincide; the PBT constrains keys accordingly.

## Rust orchestration engine — U-E (the deterministic pipeline loop + factory)

Orchestration-port unit U-E of the Rust Orchestration Engine plan
(2026-08-09-001): the SEQUENCING of `DeterministicPipeline.run()` and the
ORDER of the `create_drc_aware_pipeline()` stage factory move to
`deterministic_pipeline.rs` as the `DeterministicPipeline` pyclass; the
Python `deterministic/__init__.py` keeps its public API and delegates.

### What migrated

| Python surface | Rust surface | Notes |
|---|---|---|
| `DeterministicPipeline.run()` (the `state = stage.run(state)` loop + the per-stage fence invocation) | `DeterministicPipeline::run` → `run_pipeline` | drives the stages through `PipelineRunner<BoardState>` via a `PythonStageShim` (one per Python stage object); the Python `BoardState` threads through a shared side-channel so untouched fields keep OBJECT IDENTITY; a raising stage halts the runner and the ORIGINAL exception is re-raised |
| `create_drc_aware_pipeline()`'s ordered stage-list construction | `DeterministicPipeline::create_drc_aware_pipeline_stages` (static method) → `build_drc_aware_python_stages` | the D1→D7 order of the 23 shim stages (exposed as `drc_aware_stage_order`), the zone-aware / standard slot-stage selection, the phased / standard component-stage selection (the `config_has_phased_rules` / `config_use_isolation_slots` getattr decisions), the `metadata is None` TypeError, and the R4c sidecar injection (`channel_map` into the phased stage when it has a grid) |

### What stays Python (the U-E boundary, argued in the shim headers and here)

- The config / design_rules parameter EXTRACTION: the `getattr(config, …)`
  chains assembling plain dicts/lists, the `max(...) + 0.3` clearance
  margin, the `DesignRules`/`NetClassRules` conversion and the `PadInfo`
  anonymous-class pad conversion — Python-object marshalling into stage
  constructor kwargs, not ordering or sequencing.
- `load_channel_map_from_sidecar` (file I/O, WARNING logging, the
  `ChannelMap` parse and the `cell_size_um` hard error) and the
  `SidecarAwarePipeline` wrapper + `record_sidecar_load` counter (the
  sidecar-orchestration tests assert these).
- The fence's call-backs: `_board_state_to_drc_input` and
  `_issue_fingerprint` (imported at runtime by the shim), and
  `DRCFence.check` itself (the validation-slice differential already records
  it as kept Python).
- `create_legacy_pipeline` (a different, legacy order; the task's scope is
  the DRC-aware factory) and the `DeterministicPipeline` class shell
  (`.stages` / `.fence` attributes — the isolation-slots, phased-integration
  and instrumentation tests iterate and re-wrap `.stages`, which must remain
  the real Python stage objects).

### Structural proof

**Claim (bit-identical parity).** For every stage list and initial state,
the Rust loop produces the same final Python `BoardState` — same call order,
same per-field values, same object identity for untouched fields — as the
pinned pre-migration Python loop, with the documented boundary choices below.

1. **The loop is a pure left fold over the same stage objects.** Both arms
   call `stage.run(state)` in declaration order on the same Python stage
   instances (the per-stage compute is pinned by the D1..D7 differentials);
   the Rust loop additionally marshals the state through
   `d1_bridge::from_python` per stage (a read-only pass-through; `net_order`
   is the one owned `tuple[str, …] ↔ Vec<String>` field). The final Python
   state is the LAST stage's returned object, threaded through the shared
   context — untouched fields keep identity because no arm copies them.
2. **Exception identity by value.** A stage raising mid-loop halts the
   runner (`StageErrorKind::Fatal` from the shim's PyErr conversion) and the
   ORIGINAL exception is re-raised from the run-loop (its value object is
   captured in the shared context; `PyErr::from_value` re-raises it) — the
   exception type and message are preserved, not re-wrapped.
3. **The fence block is a direct transcription.** `if self.fence and
   stage.invariants:` (truthiness, not len), `stage_time_ms` wall-clock via
   `Instant` (the loop's nondeterminism is preserved by design — the fence
   only observes it), the `fence.check` keyword call, and the
   `previous_violations` frozenset threading (`_issue_fingerprint` per
   violation) — all call-backs stay Python (identity parity for the
   call-back results by construction).
4. **Empty stage list identity.** `stages=None`/`[]` returns the initial
   state unchanged (object identity) — the oracle's
   `DeterministicPipeline(stages=[]).run(state)` semantics.
5. **`initial_state or BoardState()`.** A `None` initial state constructs a
   fresh Python `BoardState()` through the module import; a non-None initial
   state is used as-is (BoardState is always truthy; a falsy custom
   initial-state object is outside the declared domain — recorded).

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above):
- The parameter EXTRACTION stays Python (see above); the factory receives
  the extracted values and returns the constructed stage list — the ORDER
  and the selections are Rust, the marshalling is Python.
- The report produced by the internal `PipelineRunner` is not surfaced: the
  Python API is `run() -> BoardState` (raises on stage failure), so the
  runner's report is consumed internally (halted-early → re-raise).
- The differential compares per-field state by `repr`, not `==`: the
  DRCOracle field holds numpy-array members whose `==` raises
  `ValueError: truth value of an array is ambiguous`; `repr` is total and
  deterministic (the U4 convention).

### Correctness-verification sweep (2026-08-12)

A dedicated correctness-verification pass re-audited the two migrated kernels
against the wave-4 bit-exactness catalog (B1–B13) with the loop's specifics in
mind. Findings — each either pinned by an existing test or recorded as
not-applicable with a reason:

- **Stage sequencing is declaration order, not HashMap order.** The run loop
  collects the Python stage objects into a `Vec<Py<PyAny>>` (list order) and
  the runner iterates `Vec<Box<dyn Stage>>` in insertion order; the factory's
  `drc_aware_stage_order` projects a `const` slice through `.iter().map().collect()`
  — no `HashMap`/`HashSet` in either path. Pinned by the ORDER proptests
  (which hardcode the differential's `_ORDER_DEFAULT`) and the differential's
  `test_stage_order_matches_oracle_*`.
- **No float accumulation across stages (B7 N/A).** The loop threads Python
  objects; the only float it touches is `stage_wall_time_ms` (wall-clock,
  nondeterministic by design, not compared bit-exactly). `max(...) + 0.3`
  (the one `max` in the factory) stays in the Python parameter-extraction
  shim, unchanged.
- **B5 min/max NaN, B3 rounding, int overflow in counters/timeouts — N/A in
  this surface.** The factory emits literal constructor constants (0.25, 4,
  2.0, 3.0, 0.65, 5.0, 1) and truthiness decisions; no rounding, no `min`/`max`
  on the Rust side, and `stage_wall_time_ms` is an `f64` (no integer counter
  to overflow).
- **Stage-failure semantics: abort (never continue/record).** A raising stage
  becomes `StageErrorKind::Fatal` (the shim only ever produces Fatal), which
  halts the default `halt_on_error` runner; the original exception is re-raised
  by value. `Warning`/`Infeasible`/`continue-on-error` are runner features the
  shim never emits — the Python loop has no continue path either. Pinned by the
  differential's exception-parity tests and the `single_fatal_halts_with_prefix_state`
  proptest.
- **Factory kwargs match the oracle constructor signatures.** Every stage is
  constructed with the same kwargs as the oracle (`SlotGenerationStage(slot_spacing)`
  is the one positional call and binds to the stage's single `slot_spacing_mm`
  parameter; `ZoneAwareSlotGenerationStage` / `ComponentAssignmentStage` /
  `PhasedComponentAssignmentStage` / `NetClassSetupStage` / `ConfigAttachStage`
  / `DRCOracleSetupStage` all keyword-construct identically). The phased stage's
  `use_isolation_slots=bool(placer_cfg.get(...))` truthiness matches
  `config_use_isolation_slots`; the `config if config else design_rules` oracle
  fallback matches the `oracle_design_rules` match.
- **`initial_state or BoardState()` truthiness.** A `None` initial state
  constructs a fresh `BoardState()`; a non-None (BoardState is always truthy)
  is used as-is. A falsy non-`None` object (e.g. `run(False)`) would diverge —
  Python returns a fresh state, Rust raises on the first field read — but that
  is outside the declared `BoardState | None` domain and recorded here rather
  than silently "fixed" (the structural-proof item 5 already records it).
- **Fence attribute access.** `if self.fence and stage.invariants:` short-circuit
  matches the Rust `if let Some(fence)` + `invariants.is_truthy()`; `fence` is a
  `DRCFence` (always truthy) or `None`, so the `Some`-vs-truthiness distinction
  is unreachable. `stage.invariants` / `stage.name` / `stage.last_modified_regions`
  are plain attributes on real stages, so Rust reading them once (vs Python's
  re-read in the fence block) is indistinguishable.

No kernel bug was found in the migrated run loop or factory on this sweep; the
four prior-wave catches (py_hypot NaN, py_repr_float, py_builtin_sum) live in
the per-stage compute, which is pinned by the D1..D7 differentials, not in this
loop.

### Differential / PBT / runner suites (U-E)

| Suite | Location | Count |
|---|---|---|
| pipeline differential (oracle: `_deterministic_pipeline_py_oracle.py`, sha256-pinned; stage order, per-prefix state threading, fence sequence, exception parity, real 23-stage end-to-end) | `packages/temper-placer/tests/deterministic/test_deterministic_pipeline_rust_differential.py` | 17 |
| pipeline PBT (P1..P6, each mutation-guarded) | `packages/temper-placer/tests/deterministic/test_deterministic_pipeline_pbt.py` | 12 |
| U-E runner (the canonical D1→D7 order through the pyclass loop + real Rust stages through `PipelineRunner<BoardState>`) | `packages/temper-orchestration/tests/ue_pipeline_runner.rs` | 3 |
| native Rust proptests — the factory ORDER (`drc_aware_stage_order` P1..P5: 23-stage length, declaration-table base, pinned-default match with the two substitutions, only-substitution-slots change, non-interference) | `packages/temper-orchestration/src/deterministic_pipeline.rs` `mod proptests` | 5 |
| native Rust proptests — the loop's pure core (`PipelineRunner<u32>` P1..P4: pure left-fold in declaration order, determinism, single-fatal halt preserves the prefix state, inactive stages skip in place) | `packages/temper-orchestration/src/pipeline.rs` `mod proptests` | 4 |
| existing shim surface (all `tests/deterministic/*` through the delegation shim) | `packages/temper-placer/tests/deterministic/` | 1517 passed, 1 skipped |

The native proptests pin the two migrated kernels the Python suites can only
reach through the pyclass boundary: the factory's stage ORDER
(`drc_aware_stage_order`) and the sequencing loop's pure core
(`PipelineRunner`). The ORDER properties hardcode the differential's
`_ORDER_DEFAULT` so a HashMap-order regression — the classic determinism bug
this port exists to prevent — fails on the exact canonical sequence, not
merely on length. The runner properties express the loop's left-fold /
halt-at-fatal / skip semantics over random stage lists (`PROPTEST_CASES`
bumped to 10 000 in verification sweeps).

### R1 gate status (U-E)

- **R1a** — behavioural A/B vs the verbatim oracle: 17/17 (stage ORDER on
  every selection axis; per-prefix state threading; fence-check sequence
  parity with a recording fence; exception parity; a full real D1→D7
  end-to-end run on a minimal board, compared field-by-field by repr).
- **R1b** — performance: the loop is invoked once per pipeline run; the
  added cost is one `from_python` marshalling pass per stage plus the shim
  call (each stage already crossed the FFI once); no regression beyond noise
  is possible or claimed.
- **R1c** — 6 non-vacuous properties (P1..P6), each with a degenerate-mutant
  guard that must trip. Plus 9 native Rust proptests on the two migrated
  kernels (5 on the factory ORDER in `deterministic_pipeline.rs`, 4 on the
  loop's `PipelineRunner<u32>` core in `pipeline.rs`), each re-run at
  `PROPTEST_CASES=10000` in the verification sweep — the ORDER properties are
  the Rust-side analogue of the Python P1 (call order) with the pinned
  canonical sequence hardcoded.
- **R1d** — metamorphic relations not claimed: the loop is a pure left fold
  whose relations (prefix composition) are already pinned as property P5.
- **R1e** — this section.
- **R1f** — TDD: the differential + oracle were committed first (RED —
  `temper_orchestration.DeterministicPipeline` did not exist, 6 failed),
  then the Rust pyclass + shim landed GREEN.
- **R1g** — no `unwrap`/`expect` outside tests (crate denies both); the shim
  `run()` bodies are `catch_unwind`-guarded (panic → `StageError::Fatal`),
  the pyclass methods by pyo3's own expansion; `cargo clippy --all-features
  --all-targets -- -D warnings` clean; `cargo test` 1120/1120 green; the
  wasm tier (`--no-default-features`) compiles.
- **R1h** — not physics-gated (recorded explicitly: the loop sequences
  stages; no physics quantity is computed, asserted or gated).

## Rust orchestration engine — U-G (the RouterV6 run-loop)

Orchestration-port unit U-G of the Rust Orchestration Engine plan
(2026-08-09-001): the SEQUENCING of `RouterV6Pipeline.run()` moves to
`router_pipeline.rs` as the `RouterPipeline` pyclass; the Python
`router_v6/_pipeline_core.py` keeps its public API and delegates.

### What migrated

| Python surface | Rust surface | Notes |
|---|---|---|
| `RouterV6Pipeline.run()` — the fixed stage sequence (Stage 0 load → Stage 0.5 legalization → Stage 1 escape vias → Stage 2 channel analysis → Stage 3 topological routing → Stage 4 geometric realization → Stage 5 manufacturing DRC → result assembly) | `RouterPipeline::run` → `run_router_pipeline` | one shim per step driven through `PipelineRunner<BoardState>`; the Python objects (pcb, escape_vias, stage2/3/4, manufacturing_report) thread through the shared `RunContext` so untouched objects keep OBJECT IDENTITY; a raising stage halts the runner and the ORIGINAL exception is re-raised |
| the CONDITIONALS | Rust | legalization on/off (shim added conditionally), manufacturing DRC on/off + the `dfm_fail_on` raise decision (`dfm_should_fail`), fence presence (stage-0.5/1 gates inside the validate/escape shims; a dedicated fence-4 shim), ERC on/off (shim added conditionally) |
| the verbose print orchestration | Rust | every run()-level print renders through CPython `print`/`str.format` (David-Gay `:.1f`/`{}` semantics stay CPython), byte-identical to the oracle (pinned by the differential, modulo the wall-clock runtime line) |
| the wall-clock runtime | Rust | `std::time::Instant` (same semantics as `time.time()` deltas) |
| the exception propagation | Rust | ValueError on validation failure, ManufacturingDRCViolationError on a DFM fail (type + message pinned), a stage exception re-raised as the ORIGINAL value |
| the result assembly | Rust | `RouterV6Result` construction (with `batch_results=list(self.last_batch_results)`), the final `ledger.checkout("routing_complete", result)` |

### What stays Python (the U-G boundary, argued in the shim headers and here)

- The leaf compute call-backs, invoked by the driver in oracle order:
  `parse_kicad_pcb_v6` (through the `temper_placer.io.kicad_parser` module
  attribute seam, so the plane-condemnation monkeypatch test
  `test_plane_condemnation_pipeline_wiring.py` keeps working;
  `use_declared_layer_roles=True` passes as a keyword), the Stage-0 setup
  marshalling (`_run_stage0_setup`: the pcb_override swap, the
  netclass/assignment injection with the 0.15mm default clearance, and the
  CPython `list.sort` with the `_net_sort_key` callable — the U-E
  "parameter EXTRACTION" category, pinned by the injection/order
  differential), the `Legalizer` methods, `identify_dense_packages` /
  `generate_escape_vias` (the subprocess-free escape-via compute), the
  `pcb.validate_placement` method, `_run_stage2` /
  `_compute_resource_bound`, `_run_stage3` (the ortools / CP-SAT solve —
  the E6 boundary already records it), `_run_stage4` / `_run_stage5` (the
  A* geometric realization and post-processing), `_run_manufacturing_drc`
  (the DFM checks), `_run_fence` (the DRCFence orchestration), the
  `StageLedger` orchestration (checkin/checkout — the ledger shim's own
  boundary), the `ErcGate` gate and the `RouterV6Result` dataclass.
- The R7 skip_stage3 DECISION and the "SKIPPED" verbose print stay in the
  shim's `run()`: `test_wave3_skip_sat.py` inspects the run() source text
  (`if self.skip_stage3:` + `"SKIPPED"`), so the branch must execute there;
  the driver consumes the resolved empty `Stage3Output` (or None to run
  stage 3 normally). Consequence: on a verbose skip run the "SKIPPED" line
  lands before the delegation instead of after Stage 2 — a documented
  positional divergence. The differential therefore compares verbose
  stdout on the NON-skip path (where the driver prints "Stage 3:
  Topological routing..." at the oracle position) and compares skip runs
  with verbose off; no existing test exercises a verbose skip run.
- `route_pcb` / `_adapter_convert.py` / `_pipeline_route.py` /
  `_pipeline_grid.py` / `_pipeline_verify.py` / `_pipeline_types.py` /
  `adapter.py` — untouched (the E6 boundary already covers the pipeline-route
  surface; `route_pcb` is the run() call site, unchanged).

### Structural proof

**Claim (bit-identical parity).** For every config and input in the
differential suite's domains, the Rust driver issues the same leaf
call-backs in the same order with the same arguments, threads the same
objects, raises the same exceptions and assembles the same result as the
pinned pre-migration Python loop, with the documented boundary choices
below.

1. **The driver is a direct transcription of the run() body's control
   flow.** Every stage shim mirrors the oracle's block: the same
   conditionals, the same call order (parse → setup → legalize → validate →
   fence0.5 → ledger.checkin → dense/escape → fence1 → ledger.checkout →
   stage2 → resource_bound → stage3 → stage4 → manufacturing → fence4 →
   ERC → result), the same argument threading. The call-back boundaries are
   pinned by the differential's shared-fake logs; the object identity is
   pinned intra-arm (the pcb seen by stage4 IS the pcb the parse returned).
2. **The ERC evaluation order is observable and pinned.** `ErcGate()`
   constructs before the `BoardState(routed_pcb_path=...)` argument (the
   oracle's evaluation order), and the status branches use IDENTITY
   (`is`, not `==`) against `GateStatus.UNMEASURED`/`VIOLATIONS`.
3. **Exception identity by value.** A stage PyErr stores the ORIGINAL
   exception value in the context; the driver re-raises it via
   `PyErr::from_value` — type and message preserved, not re-wrapped. The
   driver-built raises (ValueError, ManufacturingDRCViolationError) are
   constructed through CPython (`str.format` for the message, the Python
   exception class), so the messages are byte-identical.
4. **CPython rendering.** Every interpolated print/format renders through
   CPython `print`/`str.format` (David-Gay `:.1f` and `{}` semantics, the
   tuple-f-string `{}/{}` ref join, the `%s`/`%d` logger formatting); the
   summary completion expression `100 * success / max(1, success+failure)`
   is computed in Rust as `100.0 * s / max(1, s+f)` — bit-identical for the
   small int counts the router produces (pinned by the pure-helper tests).
5. **The R7 branch boundary.** The skip decision + "SKIPPED" print stay in
   the shim (pinned by test_wave3_skip_sat.py's source inspection); the
   driver consumes the resolved empty Stage3Output. The empty-list identity
   semantics of the deterministic loop do not apply here — the router run
   always has its fixed stages.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above): the leaf call-backs (see above); the R7 skip
branch's print position; the `PipelineRunner` report is consumed internally
(only `halted_early` and the pending error surface); the router's own
nondeterminism (wall-clock, seeds, the route_board.py subprocess) is
preserved by design — the driver only sequences.

### Differential / PBT / runner suites (U-G)

| Suite | Location | Count |
|---|---|---|
| run-loop differential (oracle: `_pipeline_core_py_oracle.py`, sha256-pinned; call sequence, state threading, conditionals, fail-mode raise parity, fence gates, ERC status branches, verbose stdout, Stage-0 injection + net sort, real minimal-board end-to-end) | `packages/temper-placer/tests/router_v6/test_router_pipeline_rust_differential.py` | 21 |
| run-loop PBT (P1..P6, each mutation-guarded) | `packages/temper-placer/tests/router_v6/test_router_pipeline_pbt.py` | 12 |
| U-G runner (the canonical stage order, the R7 bypass, the exception propagation and the result assembly through the pyclass with sys.modules-registered fakes) | `packages/temper-orchestration/tests/ug_router_runner.rs` | 4 |
| existing router_v6 surface through the shim (wave3 source pins, the plane-condemnation parse seam, the fence integration incl. real SAT, the E6 route differentials/PBT/metamorphic, DFM, manufacturing DRC, adapter, structural) | `packages/temper-placer/tests/router_v6/` + `tests/test_router_v6_fence_integration.py` | 257 passed, 1 skipped (plus one pre-existing failure: `test_bundled_pipeline_reaches_rust_solve_boundary` — a networkx `edges_with_data` API drift in `bundle_analyzer.py`, reproduced unchanged on the base commit and the main venv) |

### R1 gate status (U-G)

- **R1a** — behavioural A/B vs the verbatim oracle: 21/21 green (call
  sequence byte-identical, state-threading object identity, every
  conditional, fail-mode raise parity, fence gate parity, ERC branch
  parity, verbose stdout modulo the wall-clock line, Stage-0 injection +
  power-first sort, real minimal-board end-to-end with the SAT path
  bypassed).
- **R1b** — performance: the loop is invoked once per pipeline run (the
  hot path); the added cost is one FFI crossing per stage (each stage's
  leaf compute already crosses FFI), and the sequencing itself is now
  Rust. No regression beyond noise is possible or claimed — the actual
  routing compute (subprocess + ortools + A*) is unchanged Python.
- **R1c** — 6 non-vacuous properties (P1..P6), each with a degenerate-mutant
  guard that must trip.
- **R1d** — metamorphic relations not claimed: the router run-loop is a
  fixed sequence (no fold structure to relate); the differential and the
  PBT cover the conditional surface. Recorded per the plan's per-module
  discretion.
- **R1e** — this section.
- **R1f** — TDD: the differential + oracle were committed first (RED —
  `temper_orchestration.RouterPipeline` did not exist, 1 failed), then the
  Rust pyclass + shim landed GREEN (35/35, then 39/39 with the runner).
- **R1g** — no `unwrap`/`expect` outside tests (crate denies both); every
  shim `run()` body runs under `catch_unwind` (panic → `StageError::Fatal`,
  the plan's error model); the pyclass methods by pyo3's own expansion;
  `cargo clippy --all-features --all-targets -- -D warnings` clean; the
  wasm tier (`--no-default-features`) compiles.
- **R1h** — not physics-gated (recorded explicitly: the driver sequences
  stages; no physics quantity is computed, asserted or gated by the
  migrated surface).

## Rust orchestration engine — U-F (the AutomatedZeroDRC feedback loop)

Orchestration-port unit U-F of the Rust Orchestration Engine plan
(2026-08-09-001): the iterate-until-clean LOOP of
`AutomatedZeroDRC.run()` (`deterministic/feedback/orchestrator.py`) moves to
`feedback_loop.rs` as the `run_automated_zero_drc` pyfunction, which drives
the per-iteration call-backs through `PipelineRunner<BoardState>` as
per-iteration shims (`FeedbackIterationStage`, one per iteration) — the U-E
pattern. The Python `orchestrator.py` keeps its public API and delegates.

### What migrated

| Python surface | Rust surface | Notes |
|---|---|---|
| `AutomatedZeroDRC.run()` (the `for i in range(max_iterations)` loop: `state = pipeline.run(state)` → `drc_runner()` → `parse_kicad_drc(report_path)` → per-violation `mapper.map_violation` → `adjuster.compute_adjustments` → `_update_config(adjustment)` → the EXP-5 `BoardState(board, netlist, locked_routes, config)` reset) | `run_automated_zero_drc` pyfunction → `FeedbackIterationStage` `Stage<BoardState>` impls through `PipelineRunner<BoardState>` | one shim per iteration; the Python `BoardState` threads through a shared side-channel (untouched fields keep OBJECT IDENTITY, the U-E contract); the runner's `is_active`/skip semantics ARE the loop's `break` semantics (a clean parse or an empty adjustments dict clears the continue flag and every later shim is Skipped); a raising call-back halts the runner and re-raises the ORIGINAL exception |
| the termination decisions | `if not raw_violations:` / `if not adjustment.adjustments:` (truthiness, not len) and the `if state:` reset gate, evaluated in Rust | the parsed report's `__bool__` and the adjustments dict's truthiness are the oracle's exact conditions |
| the log messages | emitted through the SAME logger name (`temper_placer.deterministic.feedback.orchestrator`) with the oracle's f-string formats | `--- Feedback Iteration {i+1}/{max} ---`, `Running DRC...`, `Found {n} raw DRC violations`, `Zero DRC violations achieved!`, `No further zone adjustments possible.`, `EXP-5: Preserving {n} locked routes for next iteration` — the observable log sequence is preserved |

### What stays Python (the U-F boundary, argued in the shim header and here)

- The `__init__` construction/marshalling: the config parsing (the
  `feedback` block, the `max_iterations or default` fallback), the
  `ViolationComponentMapper`/`ZoneAdjuster` wiring, `_get_zone_config` /
  `_inject_zone_config` (getattr chains assembling the zone dicts and
  mutating pipeline-stage config — the U-E boundary's "Python-object
  marshalling, not sequencing").
- `_update_config` (the zone-bounds delta math operating on the CALLER's
  config object: raw-dict `bounds_ratio` mutations and the
  PlacementConstraints `zone.bounds` writes + re-injection; the `next(...)` /
  `.index(zone)` name/equality chains are Python-object semantics not
  reimplemented). The loop receives it as a bound-method call-back, so the
  caller's config object mutates exactly as before.
- `parse_kicad_drc` (the JSON file read — library semantics not
  reimplemented; the traversal compute is the already-landed
  `deterministic_hubs.process_drc_violation` kernel) and the subprocess DRC
  invocation (`drc_runner` — kicad-cli via `_drc_api` stays behind the
  Python callable boundary).
- The leaf helpers `ViolationComponentMapper.map_violation` /
  `ZoneAdjuster.compute_adjustments` (their compute is the already-landed
  `map_violation_kernel` / `zone_adjustments_kernel`); the per-iteration
  `zone_config` refresh happens through the `get_zone_config` call-back
  exactly as the oracle re-assigns `mapper.zone_config` /
  `adjuster.zone_config` every iteration.

### Structural proof

**Claim (bit-identical parity).** For every pipeline/call-back configuration
and initial state, the Rust loop produces the same final Python `BoardState`
— same call order, same per-call arguments, same log messages, same
termination, same config mutations — as the pinned pre-migration Python loop,
with the documented boundary choices below.

1. **The loop is a pure left fold over the same call-backs.** Both arms call
   the identical call-back objects (the pipeline, the DRC runner, the parser,
   the mapper/adjuster instances, the config-marshalling bound methods) in
   the oracle's order per iteration; the Rust loop additionally marshals the
   Python state through `d1_bridge::from_python` per iteration (a read-only
   pass-through). The differential drives both arms with the same
   recording/scripted fakes and compares the recorded call sequences
   byte-identically.
2. **The termination is the runner's skip semantics.** A clean parse or an
   empty adjustments dict (both truthiness checks, matching the oracle's
   `if not …`) clears the shared continue flag; every later iteration shim
   reports `is_active() == false` and the runner records it Skipped — so the
   pipeline runs exactly the oracle's iteration count (pinned by the
   differential's cap / break scenarios and the PBT's counts).
3. **The EXP-5 reset is a direct transcription.** `if state:` (truthiness) →
   `BoardState(board=state.board, netlist=state.netlist,
   locked_routes=state.locked_routes, config=state.config)` through the
   Python dataclass constructor: the four preserved fields keep their exact
   objects (identity pinned by P6), derived fields reset to defaults.
4. **Exception identity by value.** A call-back raising mid-iteration halts
   the runner (`StageErrorKind::Fatal` from the shim's PyErr conversion) and
   the ORIGINAL exception is re-raised (its value object captured in the
   shared context; `PyErr::from_value` re-raises it) — pinned by the
   differential's boom scenario.
5. **`max_iterations` semantics.** `max_iterations == 0` (reachable only via
   the pyfunction; the constructor's `max_iterations or default` revives 5)
   runs zero shims and returns the initial state object unchanged (the
   oracle's `range(0)` identity).

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above):
- The config-object marshalling (`_get_zone_config` / `_inject_zone_config` /
  `_update_config`) stays Python; the loop calls it through bound-method
  call-backs, so the config mutations land on the caller's object exactly as
  the oracle's.
- The loop is invoked once per `AutomatedZeroDRC.run()`; the added cost is
  one `from_python` marshalling pass per iteration plus the shim call — the
  per-iteration compute is untouched, so no performance regression beyond
  noise is possible or claimed.
- The differential compares per-field state by `repr`, not `==` (the U4/U-E
  convention; the DRCOracle numpy members make `==` raise).

### Differential / PBT / runner suites (U-F)

| Suite | Location | Count |
|---|---|---|
| feedback-loop differential (oracle: `_orchestrator_py_oracle.py`, sha256-pinned; call sequence + zone_config refresh values, log-message parity through the same logger, real-leaves end-to-end config mutations, cap exhaustion + EXP-5 reset, no-adjustment break, exception parity, anti-vacuity) | `packages/temper-placer/tests/deterministic/test_orchestrator_rust_differential.py` | 10 |
| feedback-loop PBT (P1..P6: reference-model call order, determinism, iteration cap, clean break, no-adjustment break, EXP-5 reset preserve/clear split — each mutation-guarded) | `packages/temper-placer/tests/deterministic/test_orchestrator_pbt.py` | 12 |
| U-F runner (the loop through the pyfunction with fake call-backs + the `FeedbackIterationStage` impls through `PipelineRunner<BoardState>` directly: Completed/Completed/Skipped×3 report, zero-cap identity) | `packages/temper-orchestration/tests/uf_feedback_runner.rs` | 3 |
| U-F native proptests (P1 call-order + final-state provenance vs the reference model, P2 determinism, plus a golden-reachability and a reference-discrimination anti-vacuity check — the Python PBT's P1..P6 mirrored as `proptest` so the same decision surface runs under `PROPTEST_CASES`, not hypothesis's `max_examples=100`) | `packages/temper-orchestration/src/feedback_loop.rs` `proptests` module | 4 |
| existing shim surface (all `tests/deterministic/*` through the delegation shim) | `packages/temper-placer/tests/deterministic/` | 1551 passed, 1 skipped |

### R1 gate status (U-F)

- **R1a** — behavioural A/B vs the verbatim oracle: 10/10 (call sequence with
  per-call `zone_config` refresh values; log-message parity through the same
  logger; real-leaves end-to-end config mutations; cap exhaustion + EXP-5
  reset; zero-cap identity; no-adjustment break; exception parity).
- **R1b** — performance: one `from_python` marshalling pass per iteration
  plus the shim call; the per-iteration compute is untouched — no regression
  beyond noise is possible or claimed.
- **R1c** — 6 non-vacuous properties (P1..P6), each with a degenerate-mutant
  guard that must trip; mirrored as 2 native `proptest` properties in
  `feedback_loop.rs` (call-order + final-state provenance vs the reference
  model, determinism) verified at `PROPTEST_CASES=10000`.
- **R1d** — metamorphic relations not claimed: the reference-model call-order
  property (P1) plus the count-based termination properties already pin the
  loop's observable contract.
- **R1e** — this section.
- **R1f** — TDD: the differential + oracle were committed first (RED —
  `temper_orchestration.run_automated_zero_drc` did not exist, 13 failed),
  then the Rust loop + shim landed GREEN.
- **R1g** — no `unwrap`/`expect` outside tests (crate denies both); every
  shim `run()` body is `catch_unwind`-guarded (panic → `StageError::Fatal`),
  the pyfunction by pyo3's own expansion; `cargo clippy --lib -- -D warnings`
  and `cargo clippy --all-targets` clean; `cargo test` green for all
  pyo3-bound runner suites except the pre-existing d4 environment failure
  (`phased_validator_hv_kernel`: the 3.12 extension cannot load into the
  machine's 3.9 embedded interpreter — reproduced unchanged on the base
  commit); the wasm tier (`--no-default-features`) compiles.
- **R1h** — not physics-gated (recorded explicitly: the loop sequences
  call-backs; no physics quantity is computed, asserted or gated).

## Rust orchestration engine — U-I (the CP-SAT place->route loop port)

Orchestration-port unit U-I of the Rust Orchestration Engine plan
(2026-08-09-001), Wave-4 CP-SAT placement-loop slice: the RESIDUAL
non-ortools orchestration of the `placer/cp_sat` place->route loop
controller moves to `temper-orchestration` as three pyfunctions. Each
Python module keeps its public API and delegates.

### What migrated

| Python surface | Rust surface | Notes |
|---|---|---|
| `_loop_core.py` `run()` (legacy classifier loop) + `_run_with_gates()` (gate-driven loop) + `_solve_with_delta()` + `_solve_phase2()` | `cpsat_loop.rs`: `cpsat_run_legacy_loop` / `cpsat_run_gated_loop` / `cpsat_solve_with_delta` / `cpsat_solve_phase2` | the loop SEQUENCING (round budget, solve-timeout selection, UNSAT early exit, oscillation check, convergence decisions, delta backtracking), the gate checks (PLACEMENT/ROUTING-stage passes, `_check_unmeasured_exit`), the SC1a/SC1b stability counters, the thermal-field preparation and the unsat_core assembly — the CP-SAT solve (`_call_solver`), routing, the classifier, the gate implementations and the other-mixin leaf helpers stay Python call-backs in oracle order; wall-clock stays `_loop_core.time.monotonic` (the mockable clock) |
| `feedback.py` `FeedbackClassifier.classify()` | `feedback.rs`: `classify_feedback` | the routing-field extraction, the clean early-return, the four-class DISPATCH loops in oracle order, the unclassified-failure collection and the priority sort (`operator.attrgetter("priority")` stable sort); the four `_handle_*` constraint-building handlers and the leaf helpers stay Python call-backs |
| `validator_audit.py` `audit_domain_clearance_validator()` | `validator_audit.rs`: `audit_domain_clearance_validator` | the R24 post-solve audit SEQUENCING: the two `ValueError` guards (zero components / disjoint solved refs), the `build_validator_placement` call, the `verify_iec60335_compliance` re-run, the `stats` extraction, the geometry-trust computation (`components_without_pads` / `pairs_origin_modelled`) + the degraded-geometry `logger.error`, the `covered_pairs` frozenset build, the per-violation bucket dispatch (`classify_violation`: intra / hard / gap, reasons formatted through CPython) + `DomainClearanceValidatorViolation` construction, and the `DomainClearanceValidatorAuditResult` assembly |

### What stays Python (the U-I boundary, argued in the shim headers and here)

- **`_loop_core`**: `_call_solver` (the CP-SAT solve boundary — the lazy
  `encoder.solve_placement` import must keep resolving
  `mock.patch('...encoder.solve_placement')`); `_route_placement` /
  `_get_placement_pcb_path` / `_build_board_state` (the router_v6 / KiCad
  subprocess boundary); the classifier instance; the gate
  implementations (`gate.check` / `gate.to_delta`); the leaf helpers in
  the OTHER mixins (`_loop_stability` / `_loop_gates` / `_loop_routing`),
  invoked as call-backs in oracle order; the numpy thermal-field
  rasterization; the wall clock (`time.monotonic` on `_loop_core` — the
  field-feedback test mocks that exact target).
- **`feedback`**: the four `_handle_*` handlers — they CONSTRUCT the real
  PCL `SeparatedConstraint` / `KeepoutConstraint` / `AnchoredConstraint`
  objects and do the design-rules marshalling (U-E "Python-object
  marshalling"); the leaf helpers `_find_critical_components` /
  `_detect_persistent_ics` / `_compute_heuristic_position`; the
  `ConstraintDelta` / `UnclassifiedFailure` / `ClassificationResult`
  dataclasses (constructed by the Rust sequencing via keyword args).
- **`validator_audit`**: `build_validator_placement` (the deepcopy + dict
  mutation over the validator wire shape — Python-object marshalling) and
  the pad-schema serialization (`_pads_for_netlist_component` /
  `_netlist_component_by_ref`); `verify_iec60335_compliance` (the EXACT
  REQ-SAFE-01 validator — the R24 boundary; the CI gate's own function,
  fetched from the clearance module at call time); the
  `DomainClearanceValidatorViolation` / `DomainClearanceValidatorAuditResult`
  dataclasses and the `report()` / `clean` / `shortfall_mm` presentation.

### Structural proof

**Claim (bit-identical parity).** For every input, the Rust sequencing
produces the same observable result — same buckets, same per-record fields,
same reason strings, same stats, same geometry-trust verdict, same call
arguments — as the pinned pre-migration Python, with the documented
boundary choices below.

1. **Every migrated surface is a pure fold over the same Python call-backs
   in oracle order.** The loop drives `_call_solver` / `_route_placement` /
   `classifier.classify` / the gate impls / the leaf helpers; the classifier
   drives the four `_handle_*` handlers; the audit drives
   `build_validator_placement` / `verify_iec60335_compliance`. Both arms
   call the identical call-back objects with identical arguments; the
   differentials drive both arms with identical mocks/inputs and compare
   the canonicalized results byte-identically. The audit differential
   additionally pins call-ARGUMENT parity: the fake validator records the
   `validator_placement` each arm hands it and the two are compared
   canonicalized.
2. **The reason strings are formatted through CPython, not re-rendered.**
   The audit's hard-bucket reason runs `{measured_mm:.3f}` /
   `{required_mm}` through `str.format` via the Python `format` builtin, so
   the text is bit-identical by construction (pinned by the mocked edge
   case with a non-trivial 1.23456 measurement).
3. **Log parity through the same logger name.** The Rust emits the
   degraded-geometry `logger.error` and the post-audit summary `logger.info`
   through `logging.getLogger("temper_placer.placer.cp_sat.validator_audit")`
   — the oracle's own `__name__` — preserving the observable log sequence
   (captured by caplog in the differential). The loop/feedback log lines
   likewise go through the modules' own logger names with the oracle's
   f-string formats.
4. **The defensive fallbacks are transcribed exactly** (pinned by the ten
   mocked edge cases the real validator never emits): `pair_kind` falsy ->
   `v.pair_kind or ("intra" if v.ref_a == v.ref_b else "inter")` on the
   ORIGINAL attribute values with VALUE equality (`None == None` is intra;
   equal-valued distinct strings are intra — identity is not the test);
   `measured_mm`/`required_mm` None -> `float("nan")` in the record, and a
   covered pair with None measurements raises `TypeError` in BOTH arms
   (the reason formats the raw value before the audit's nan mapping);
   `stats.rows[].pairs_origin_modelled` falsy -> contributes 0 (`or 0`).
5. **Panic safety (R1g).** The pyfunction bodies run under pyo3's
   `#[pyfunction]` catch_unwind (the crate sets
   `profile.release.panic = "unwind"`); every Python call is a `PyResult`;
   no `unwrap`/`expect` anywhere (crate clippy lint). The `UnsatError`
   from `_solve_with_delta` is caught as a `PyErr` and re-raised by value.

**Documented boundary choices** (kept Python / deliberately different,
argued in-source and above):
- `_call_solver` stays Python: the ortools/pumpkin solve is the KEEP
  boundary (Phase-1 spike verdict), and the lazy
  `encoder.solve_placement` import must keep resolving the field-feedback
  test's `mock.patch`.
- Wall-clock timing goes through `_loop_core.time.monotonic` (NOT
  `std::time::Instant`) — the field-feedback test mocks that exact target,
  so the timing call-back must stay the Python `time.monotonic` reachable
  via `_loop_core.time` (a load-bearing import kept in the shim).
- The audit re-runs `verify_iec60335_compliance` exactly as the oracle
  does; it sequences the validator, it does not reimplement it (R24
  discipline unchanged: hard failures raise in `_encoder_solve`; the
  geometry-trust flag is computed identically).

### Differential / PBT / runner suites (U-I)

| Suite | Location | Count |
|---|---|---|
| loop-core differential (legacy + gated loop, solve_with_delta/phase2 kernels: solver/route call sequences, time-budget + delta-re-solve sequencing, UNSAT exits, oscillation + stability + convergence decisions, delta backtracking, log parity, deterministic wall-clock via mocked `time.monotonic`) | `packages/temper-placer/tests/placer/cp_sat/test_loop_core_rust_differential.py` | 10 |
| feedback differential (clean early-return, four-class dispatch, unclassified collection incl. the `loc +/- 5` region math, persistence threshold, priority sort) | `packages/temper-placer/tests/placer/cp_sat/test_feedback_rust_differential.py` | 11 |
| validator_audit differential + PBT + metamorphic (6 real-validator scenario differentials with per-scenario bucket non-vacuity, 2 ValueError-message parity, 10 mocked-validator fallback edge cases with call-argument parity, PBT P1-P5, metamorphic M1-M4) | `packages/temper-placer/tests/placer/cp_sat/test_validator_audit_rust_differential.py` | 27 |
| existing feedback PBT through the shim (all `tests/placer/cp_sat/test_feedback.py` now exercises the Rust sequencing) | `packages/temper-placer/tests/placer/cp_sat/test_feedback.py` | 13 |
| existing R24 audit suite through the shim (falsifier, clean, straddler, coverage-gap, reversed ordering, geometry-trust, solve-integration, production-board FREE={K3}) | `packages/temper-placer/tests/placer/cp_sat/test_validator_audit.py` | 23 passed + 1 env-skip (netlist not built) |

### R1 gate status (U-I)

- **R1a** — behavioural A/B vs the three verbatim oracles
  (`_loop_core_py_oracle.py` / `_feedback_py_oracle.py` /
  `_validator_audit_py_oracle.py`, all sha256-registered in
  `scripts/oracle_hashes.json`): 48 differential tests
  (10 + 11 + 27) byte-identical, including the audit reason strings, the
  `stats` capture, the geometry-trust verdict and the validator call
  arguments.
- **R1b** — performance: one pyfunction marshalling pass per call plus the
  shim-call overhead; the per-step compute is untouched (all call-backs),
  so no regression beyond noise is possible or claimed.
- **R1c** — 5 non-vacuous PBT properties (P1..P5: random-corpus
  differential with a corpus-histogram guard that FAILS if <5 hard or <5
  gap cases land; hard-implies-covered-pair soundness; intra-never-hard
  bucket discipline; geometry-trusted-iff-all-pads with a pad-less
  injection that must flip trust; covered_pair_count == distinct constraint
  pairs under duplicate + reversed injection) plus the 36 pre-existing
  PBT tests (13 feedback + 23 audit) that now exercise the Rust path.
- **R1d** — 4 metamorphic relations (M1 constraint-order irrelevance, M2
  unrelated-constraint additivity, M3 translation invariance, M4
  domain-role-swap invariance with the base case laid out so no
  same-domain pair violates — the validator measures LV-LV pairs but not
  HV-HV, which would otherwise break swap invariance).
- **R1e** — this section.
- **R1f** — TDD: the loop-core and feedback differentials + oracles were
  committed first (RED — the pyfunctions did not exist), then the ports
  landed GREEN (e2ac81533, 0094480c6). The validator_audit kernel was
  recovered from an interrupted session as an ORPHAN (d06cb5d44 — never
  wired, never compiled); it was wired + shimmed (7f04270ba, with three
  bit-parity fixes found by reading the port against the oracle: the
  pair_kind fallback compared defaulted refs by object identity where the
  oracle compares original values by `==`; a falsy pair_kind TypeError'd
  in classify where `==` returns False; a falsy `pairs_origin_modelled`
  TypeError'd where `or 0` contributes 0) and its differential/PBT landed
  last (73b767257). The wasm-tier compile regression the first U-I commit
  introduced (unconditional `pub use` of python-gated items) was fixed in
  c363fa5cf.
- **R1g** — no `unwrap`/`expect` outside tests (crate denies both);
  `cargo clippy --lib -- -D warnings` and `cargo clippy --all-targets`
  clean; `cargo test --no-fail-fast` 1129 passed across the lib suite and
  every runner suite except the pre-existing d4 environment failure
  (`phased_validator_hv_kernel`: the 3.12 extension cannot load into the
  machine's 3.9 embedded interpreter — reproduced unchanged on the base
  commit); the wasm tier (`--no-default-features`) compiles.
- **R1h** — not physics-gated (recorded explicitly: the migrated surfaces
  sequence call-backs and make convergence/feedback DECISIONS; no physics
  quantity is computed, asserted or gated by the Rust code itself — the
  REQ-SAFE-01 validator re-run stays a Python call-back, and the R24 audit
  discipline (hard failures raise in `_encoder_solve`, geometry trust
  gates the proof) is unchanged).

### Native proptests (fanout19 verification sweep, 2026-08-12)

The Python differential suites pin the full-loop sequencing through mocks,
but the three kernels carried no native (`#[cfg(test)]`) properties, and two
of their delegation targets ran uncovered by any differential: the
`cpsat_solve_with_delta` `UnsatError` message (every loop test mocks
`loop._solve_with_delta` above it) and the `classify_violation` bucket
decision under arbitrary violation shapes. The following native proptest
modules were added (each in the source file's own `#[cfg(test)]
#[cfg(feature = "python")]` sibling, so `gen_wasm_test_registry.py` censuses
them as `python-gated` and the wasm tier skips them — no registry drift):

- `cpsat_loop.rs::proptests` — P1 pins `cpsat_solve_with_delta`'s
  `f"UNSAT with delta(s): {[d.reason for d in new_deltas]}"` message
  byte-exactly (the suffix must be the CPython list repr of the delta
  reasons) and the raise/return dispatch (infeasible → `UnsatError`,
  feasible → placement returned untouched), over randomized reason counts;
  anti-vacuity pins the empty and multi-delta message shapes.
- `feedback.rs::proptests` — P1 pins the priority sort (scripted
  NON-monotonic priorities so a missing sort fails) and the unclassified
  count against a reference transcription of the oracle's accounting; P2
  pins the clean early-return (completion ≥ 1.0 and no DRC violations →
  empty result and zero handler calls). Anti-vacuity: the reference
  distinguishes scripted-vs-None classes and the production kernel
  demonstrably dispatches both handler classes.
- `validator_audit.rs::proptests` — P1 pins `classify_violation`'s bucket
  decision against a reference transcription of the oracle's
  `_classify_violation` (falsy `pair_kind` is "not intra" — never a
  TypeError; `ref_a == ref_b` is VALUE equality on the "?"-defaulted
  strings), so a regression of either of the two recovery-seam bit-parity
  fixes fails it; P2 pins the covered-pair reason's `:.3f` / default float
  CPython format path. Anti-vacuity: the reference and the production
  kernel each reach all three buckets.

All three modules' properties run under `PROPTEST_CASES` (verified at
10 000 cases, `--test-threads=1` for the shared interpreter): 11 new tests,
1084 lib tests + 17 runner suites green; `cargo clippy --all-features
--all-targets -- -D warnings` clean.

### Known unfixed divergence (reported, not fixed — log-only)

The degraded-geometry `logger.error` in `validator_audit.rs` joins the
`components_without_pads` ref list with an EMPTY separator where the oracle
writes `", ".join(sorted(...))`:

- delegated (Rust): `... 2 component(s) carry no pads (BX) ...`
- oracle (Python):   `... 2 component(s) carry no pads (B, X) ...`

Counterexample: two pad-less components `X` and `B` (degraded-geometry
scenario) — the audit result dataclasses are byte-identical on both arms
(the differential suite compares the result, not the log bytes, so it does
not see this), but the log message text diverges. It is the fourth
bit-parity defect at the recovered-validator_audit seam (the finish agent's
three — identity-vs-value pair_kind, falsy pair_kind TypeError, falsy
`pairs_origin_modelled` TypeError — are recorded in R1f above); this one is
log-rendering only and is reported here rather than fixed in the sweep, per
the report-don't-fix rule. The fix is a one-character separator change
(`""` → `", "` in the `str.join` call).

## U0 boundary marshaller + round-trip losslessness gate (O-C3/U0)

The boundary marshaller (`src/marshal.rs`) is the foundation for replacing
the 23 `Option<Py<PyAny>>` `BoardState` fields with owned Rust structs
(U1–U4). It proves, once at the boundary, that a Python object marshals
INTO an owned Rust value and back OUT bit-identically, before any stage is
rewritten. See `docs/evidence/2026-08-13-u0-boundary-marshaler-roundtrip-gate.md`.

### Design

- **`Marshal` trait** with `from_python`/`to_python`, wrapped by the free
  functions `to_owned::<T>(obj)` / `to_python::<T>(py, owned)`. Every impl
  reads scalars via `extract::<f64>()`/`extract::<i64>()`/
  `extract::<String>()` and iterates collections — **never**
  `extract::<Py<T>>()`, which is the cross-`.so` pyclass-identity blocker
  (`docs/evidence/2026-08-12-cross-extension-pyclass-identity.md`). Owned
  structs dodge that blocker by construction: a Rust field that *names* a
  foreign pyclass is the bug; an owned `struct`/`enum` of plain fields is
  not.
- **`Val` enum** (`Int(i64) | Float(f64)`) is the canonical type for any
  field that can hold `int` OR `float` (the concrete-Python-type hazard of
  `netlist_contracts.rs`: `Component("R1", "fp", (1, 2))` keeps `int`
  bounds). It records which one it was and round-trips it unchanged —
  `f64` alone would silently widen `1` to `1.0`.
- **`Plain` enum** is the lossless nested-value tree (`Null`/`Bool`/`Int`/
  `Float`/`Str`/`Bytes`/`Tuple`/`List`/`Set`/`FrozenSet`/`Dict`/`Opaque`),
  carrying the int-vs-float distinction at every leaf and the concrete
  collection kind at every node.

### Lossless-proven types (the round-trip gate)

`assert_roundtrip::<T>(py, "<python literal>")` (reusable — U1+ plug their
types in) marshals to `T` and back and asserts bit-identity: exact type
(`get_type().is(...)`), identical `repr`, and NaN-aware `==`. Proven:

| Rust type | Python | Notes |
|---|---|---|
| `i64` | `int` | rejects `bool` (an `int` subclass) |
| `f64` | `float` | rejects `int`/`bool` (no widening); NaN/±inf round-trip |
| `bool` | `bool` | |
| `String` | `str` | |
| `Val` | `int` or `float` | type-preserving, incl. NaN |
| `Option<T>` | `None` or `T` | |
| `Vec<T>` | `list` | homogeneous; a `tuple` needs `Plain` |
| `Plain` | any nested builtin tree | nested dict/list/tuple/set/frozenset/bytes |

End-to-end proof on real field shapes: `BoardState.placements`
(`frozenset` of `(ref, (x, y))` tuples) and `used_slots` (`frozenset` of
int-slot-id tuples) are read via `getattr` and round-tripped bit-identically
— the exact path a U1+ stage will take.

### Keeps (types that cannot round-trip through an owned struct)

`Plain::Opaque` passes the object through by reference (identity preserved,
nothing reconstructed). This is deliberate for numpy arrays (dtype and
element bit patterns are numpy's own — no Rust float conversion may widen
`float32`), shapely/GEOS geometries, and pyclasses owned by other `.so`
files. They stay `Py<PyAny>`-shaped until their owner crate migrates them.

### Gates

- `cargo test --lib`: 1122 passed (1112 pre-existing + 10 new `marshal::tests`).
- `cargo clippy --all-targets`: clean (no new warnings).
- `cargo check --no-default-features`: clean (wasm-tier build unaffected —
  `marshal` is `#[cfg(feature = "python")]`-gated).
- `scripts/gen_wasm_test_registry.py --crate temper-orchestration --check`:
  up to date (1019 tests; `marshal::tests` censused `python-gated`, 10 tests).
- `make regen-check`: unchanged — the two `need attention` items (drifted
  `_pipeline_core_py_oracle.py` pin from #1113, unmanifested
  `measure_uncapped_drc.py` from #1111) are pre-existing on origin/main.

## U1 used_slots port — the first owned BoardState field + the d1_bridge rewire pattern (O-C3/U1)

U1 ports the FIRST `Option<Py<PyAny>>` `BoardState` field to an owned Rust
type: `used_slots` (`frozenset` of `(x, y)` slot-id tuples) →
`Option<HashSet<SlotId>>`. It is the pattern unit U2+ fan out across the
remaining 22 fields, so the rewire is recorded here as the copy-paste
template.

### What migrated

- **`board_state.rs`** — `used_slots: Option<HashSet<SlotId>>`; the new
  `SlotId(f64, f64)` type (Hash/Eq normalize `-0.0` to `0.0` and all NaNs to
  one form, mirroring Python-set membership; the stored bit patterns stay
  ORIGINAL so a `-0.0` leaf round-trips as `-0.0`). Exported as
  `temper_orchestration::SlotId` (append-only re-export; the runner tests
  construct the owned value directly).
- **`marshal.rs`** — two new `Marshal` impls: `SlotId` ↔ a `(x, y)` 2-tuple
  (leaves validated through the `f64` impl's strictness — an int-shaped
  `(0, 1)` tuple is REJECTED, never widened; the real pipeline data is
  float-only, the D4/D5 oracles annotate `set[tuple[float, float]]`) and
  `HashSet<SlotId>` ↔ `frozenset`/`set` (read) → always `frozenset` (write).
- **`d1_bridge.rs`** — the read and the write-back for `used_slots`.
- **`phased_assignment_stage.rs`** — the WRITE: the oracle's
  `frozenset(used_slots)` construction is kept verbatim, then marshalled
  INTO the owned field (`to_owned::<HashSet<SlotId>>(&used_slots_fs)`).
- **`phased_component_assignment_validator_stage.rs`** — the READ: the
  recorded owned set is rebuilt into the real Python `set` the scans use via
  `to_python::<HashSet<SlotId>>` (a `frozenset`) driven through the same
  `set(...)` call the oracle makes.
- **Python side is UNCHANGED** — `deterministic/state.py` and the stage
  shims still hold/thread the Python `frozenset`; the marshalling happens
  entirely in the Rust bridge.

### The established rewire pattern (U2+ copy template)

READ (`d1_bridge::from_python`): replace `attr_opt(state, "used_slots")?`
with a boundary-marshalled read. `Option<T>`'s `Marshal` impl maps Python
`None` → Rust `None`, so one call covers both:

```rust
bs.used_slots =
    crate::marshal::to_owned::<Option<HashSet<SlotId>>>(&state.getattr("used_slots")?)?;
```

WRITE-BACK (`d1_bridge::to_python`): the `dataclasses.replace` semantics
(a changed field writes the new value; an unchanged field keeps the original
Python object — identity preserved) are preserved WITHOUT holding a `Py`
copy of the field:

1. The `changed` arm calls a typed helper that marshals the ORIGINAL Python
   attribute to the same owned type and compares with Rust equality:
   ```rust
   fn used_slots_changed(orig: &Bound<'_, PyAny>, out: &BoardState) -> PyResult<bool> {
       let orig_owned = crate::marshal::to_owned::<Option<HashSet<SlotId>>>(
           &orig.getattr("used_slots")?,
       )?;
       Ok(orig_owned != out.used_slots)
   }
   ```
2. The value arm writes through the marshaller (always a `frozenset` — the
   dataclass field contract):
   ```rust
   "used_slots" => crate::marshal::to_python::<Option<HashSet<SlotId>>>(py, &out.used_slots)?,
   ```
3. The field's `py_opt_changed` arm is DELETED (it returned `Option<&Py>`;
   typed fields must never appear there).

STAGE WRITE: keep the Python-side construction sequence the oracle uses
(`frozenset(...)` through CPython) and marshal its result into the owned
field — do NOT rebuild the value from scratch in Rust (bit-exactness by
construction).

STAGE READ: rebuild the Python object the stage's downstream Python calls
expect from the owned value via `to_python::<OwnedType>` and drive it
through the same Python call sequence the oracle makes.

### The owned type + why (the U1 decision record)

- **`HashSet<SlotId>`** (not `HashSet<(i64, i64)>` — the brief's suggestion):
  the real slot ids are FLOAT grid coordinates; `(i64, i64)` would reject
  every real board. `f64` has no `Hash`/`Eq` in std, so `SlotId` is the
  wrapper, with Python-set semantics (`(0.0, 5.0) == (-0.0, 5.0)`) baked
  into its `Hash`/`Eq`.
- **Leaf policy is strict** (`int` rejected): mirrors `Marshal for f64`'s
  "an int is not a float" — an int-shaped tuple must fail loudly, not widen
  silently (the U0 concrete-Python-type hazard). The dataclass default
  `frozenset()` (empty) has no leaves and marshals unconditionally.
- **`to_python` inserts in SORTED order** (by the same normalized bits the
  `Hash` impl uses), deliberately: `std::collections::HashSet` hashes with a
  process-random seed, so raw iteration order is nondeterministic across
  runs — unacceptable for a deterministic engine's write-back. The sorted
  order makes the rebuilt frozenset's table layout a deterministic function
  of the values.

### Recorded bound — set iteration order (R1-style, read before copying)

The U0 `Plain` type round-trips colliding sets bit-identically because its
`Vec` RECORDS the original iteration order. An owned `HashSet` cannot: for a
COLLISION-FREE slot set, CPython's set iteration order is a pure function of
the values (each element owns its bucket), so the rebuilt `frozenset`
round-trips bit-identically (type, repr, ==). With hash collisions — and the
U0 3-element example `{(0, 1), (2, 3), (1, 0)}` actually collides (buckets
2/2 mod 8) — the original frozenset's order is a table-layout artifact of
its original insertion sequence, not derivable from the values; the rebuilt
set iterates in a deterministic-but-different order. Type, membership
content and `==` are preserved in every case. The D4 over-claim scan's
`used_slots` set-iteration order is therefore bit-exact only for
collision-free over-claim sets; every exercised differential/PBT over-claim
set has a single phantom slot (order unobservable), and the D5 canon is
order-free (`set(...)` equality). A future test pinning multi-element
over-claim ORDER would need the `Plain`-style order-recording type instead —
recorded here as the known bound, not papered over. The round-trip gate
pins full bit-identity on the guaranteed shapes (empty/1-element/`None`) and
type+content+element-repr-multiset on multi-element sets, plus an explicit
determinism assertion (two `to_python` calls produce repr-identical
frozensets).

### Gates (U1)

- `cargo test -p temper-orchestration` (PYO3_PYTHON=<main venv python>):
  1125 lib passed (1122 base + 2 new `marshal::tests` + the multi-element
  content gate); d1/d2/d3/d5/d6/d7/e3/e4/e6/stages/ue/uf/ug runner binaries
  all green — including the d5 runner's `phased_hv_rings_reserved` /
  `phased_single_stage_end_to_end`, which exercise the owned WRITE and the
  rebuilt-set READ. Two runner failures are PRE-EXISTING on origin/main
  (verified identical on a pristine base worktree): d4
  `phased_validator_hv_kernel` (the validator's `py.import("temper_drc_rs")`
  has no fake registered — the fake list predates the 946cefa61 flatten
  delegate) and uh_marshal_runner (2 tests needing venv modules the
  embedded interpreter cannot see).
- `cargo clippy -p temper-orchestration --all-targets`: clean.
- `cargo check -p temper-orchestration --no-default-features`: clean.
- Python differentials (D4 25/25 incl. the 5 validator used_slots tests, D5
  24/24, D2 PBT 14/14, D4 PBT + D5 PBT 30/30) — all green against the
  pinned oracles through the rewire, run with the worktree-built
  `temper_orchestration` extension shadowing the venv's.
- `make regen-check`: all derived artifacts consistent (unchanged);
  temper-orchestration wasm census 1019 up to date (`marshal::tests` stays
  `python-gated`).
- Environment note: the main venv's `temper-design-bundle`/`temper-geometry`/
  `temper-io-types`/`temper-orchestration` extensions were STALE (2026-08-11
  builds vs 08-12/13 sources; `check_stale_extensions.py` flagged 4) —
  `make extensions` rebuilt all 10 fresh before the differentials. This was
  a pre-existing environment gap, not a U1 artifact.

## U2 leaf structs — the owned `Component`/`Pin`/`Net` data model (O-C3/U2)

U2 defines the OWNED leaf structs the later units compose: `Component`/`Pin`/
`Net` (the building blocks for U3's `Board`/`Netlist` aggregates), and
DECIDES the crate-home for the whole owned data model. No `BoardState` field
changes; the structs and their `Marshal` boundary are the deliverable.

### Crate-home decision: a new pure-Rust `packages/temper-data-model/` crate

The owned structs live in a NEW crate, `packages/temper-data-model/` — a
pyo3-free `rlib` (`temper-rust-router-core` template). The alternatives were
rejected for one shared reason:

- **(b) a `data_model.rs` module in `temper-design-bundle`** — design-bundle
  is a pyo3 extension (its `python` feature pulls pyo3). Putting the owned
  structs there would tie the Rust-internal data model to pyo3, and it would
  conflate the Python-facing surface (the pyclasses) with the Rust-internal
  surface (the owned structs). The wasm32 tier could not compile it.
- **(c) extending orchestration's `marshal.rs`** — `marshal.rs` is
  `#[cfg(feature = "python")]`-gated: the structs would vanish on the wasm32
  tier build (`--no-default-features`), which is exactly the forcing function
  the whole port exists for (`docs/evidence/2026-08-12-orchestration-loop-wasm-spike.md`).

The owned structs must be importable by BOTH the orchestration pyo3 surface
(the `Marshal` impls here, which `use temper_data_model::{...}`) AND
(eventually) the `wasm32-unknown-unknown` tier. A no-pyo3 rlib is the only
home that satisfies both; it is also the shape O-C4's physical
`temper-orchestration-core` split will `git mv` the leaves into. The crate
carries the full workspace metadata (`Cargo.toml` rlib, a setuptools-stub
`pyproject.toml` mirroring `temper-rust-router-core`, so `uv lock`/`uv sync`
stay consistent), and `make regen`'s README package count is regenerated
(17 → 18 packages). The `Val` enum MOVED from `marshal.rs` into this crate
(it is pure `Int(i64) | Float(f64)` — no pyo3) and is re-exported as
`crate::marshal::Val`; `Plain` STAYS in `marshal.rs` (its `Opaque(Py<PyAny>)`
variant is pyo3-shaped by construction and no leaf field needs it).

### The leaf structs (`packages/temper-data-model/src/lib.rs`)

Field types follow the U0 `Val`/`Plain` convention, applied per field:

| Field | Owned type | Why |
|---|---|---|
| `Component.bounds` | `Vec<Val>` | THE int-vs-float hazard: the pipeline demonstrably writes `(1, 2)` ints (`netlist_contracts.rs:11-28`, `dense_package_detection.py:67`) AND `(1.0, 2.0)` floats. `Val` records which, so `1` never widens to `1.0`. |
| `Pin.position`, `Component.initial_position` | `(f64, f64)` / `Option<(f64, f64)>` | `tuple[float, float]` — always-float in the real pipeline (KiCad parse + synthetic fixtures emit floats); an int coordinate is a LOUD rejection, never a widen. |
| `Pin.width/height/drill/roundrect_ratio/pad_rotation_deg`, `Net.weight/max_current` | `f64` | concrete `float` fields; same strict int-rejection. |
| `Component.initial_rotation/initial_side` | `Option<i64>` | the only genuinely `int | None` fields. |
| `Component.attributes` | `Vec<(String, String)>` | an insertion-ordered `dict[str, str]` (Python 3.7+ dicts are ordered); read/write in iteration order. |
| `Component.tags` | `Vec<String>` | a `frozenset` of strings read in iteration order (no duplicates by construction); `to_python` always writes back a `frozenset` (the dataclass contract). |
| `Component.pins`, `Net.pins` | `Vec<Pin>` / `Vec<(String, String)>` | the `list[Pin]` / `list[tuple[str, str]]` shapes, element-wise. |

### The `Marshal` impls (`src/netlist_owned.rs`)

- **Read** via `obj.getattr("...")` + the scalar/container `Marshal` impls —
  never `extract::<Py<T>>()` (the cross-`.so` blocker).
- **Write** reconstructs a faithful object of the design-bundle pyclass by
  RUNTIME IMPORT — `py.import("temper_design_bundle_python")?.getattr(
  "netlist_contracts")?.getattr("Component")` — then calling it with keyword
  args. This is approach #1 of the cross-extension evidence doc: the
  reconstructed type/repr/`==` are bit-identical to the original WITHOUT a
  `temper-design-bundle` dependency edge (which would re-introduce the
  duplicated-`LazyTypeObject` hazard). No Rust type names a foreign pyclass.
- **`bounds` is special**: it round-trips as a TUPLE (the contractual
  `tuple[float, float]`), not a `Vec`-marshalled list — the element-wise
  `Val` read/write is done inline rather than through `Vec<Val>`'s
  list-shaped impl. A list-shaped `bounds` is rejected.
- **Two new tuple impls** `(f64, f64)` and `(String, String)` serve
  `position`/`initial_position` and `Net.pins` elements.
- **Defaults are reconstructed explicitly** (empty `list`/`dict`/`frozenset`,
  `None` for the optionals), so `Component('R1','fp',(1,2))` comes back with
  the dataclass defaults intact — the repr/eq match the original exactly.

### Round-trip gate results

`assert_roundtrip_with` (a globals-accepting sibling of `assert_roundtrip`;
the leaf tests need `Component`/`Pin`/`Net` names in scope) pins bit-identity
— exact type, identical `repr`, NaN-aware `==` — against a faithful
`@dataclass` stand-in for the pyclasses (registered in `sys.modules` under
`temper_design_bundle_python.netlist_contracts`, the d3–d7 mock pattern, so
`cargo test` stays self-contained without building design-bundle's `.so`):

- **int-vs-float bounds**: `Component('R1','fp',(1,2))` and
  `Component('R1','fp',(1.0,2.0))` both round-trip bit-identically, and the
  owned `bounds` are asserted to be `[Val::Int(1), Val::Int(2)]` vs
  `[Val::Float(1.0), Val::Float(2.0)]` — the widening hazard is pinned, not
  merely tolerated.
- **full `Component`** with pins/non-default fields (zone, fixed,
  initial_position, attributes, tags, sheetpath) round-trips bit-identically.
- **full `Pin`** (12 fields) and **full `Net`** (6 fields, `(ref, pin)` tuple
  list) round-trip bit-identically.
- **NaN/±inf** in a leaf float field round-trip with type + repr preserved and
  the field still NaN (asserted on the owned field — a dataclass `__eq__`
  returns False for NaN fields, so the gate's bare-float NaN arm cannot see
  them).
- **Guards**: list-shaped bounds, int/str/bool bounds leaves, int `fixed`,
  int `zone`, and int pin `position` are all REJECTED loudly.

### Recorded bound — `tags` frozenset iteration order

`Component.tags` is owned as a `Vec<String>` (read order), so the rebuilt
`frozenset` iterates in insertion order. For a COLLISION-FREE tag set this
matches the original's order bit-for-bit; with hash collisions (a string
frozenset CAN collide), the original order is a CPython table-layout artifact
not derivable from the values, and the rebuilt set iterates in a
deterministic-but-different order. Type, membership and `==` are preserved in
every case. The gate pins full bit-identity on empty/single-element `tags`; a
future order-sensitive consumer would need `Plain`'s order-recording `Vec`
instead.

### Gates (U2)

- `cargo test -p temper-data-model`: 1 passed (the `Val` int/float
  distinction pin).
- `cargo test -p temper-orchestration --lib` (PYO3_PYTHON=/usr/bin/python3.12):
  1133 passed (1125 base + 8 new `netlist_owned::tests`).
- `cargo clippy --all-targets` on both crates: clean.
- `cargo check --target wasm32-unknown-unknown` on `temper-data-model`:
  clean (the crate is pyo3-free by construction); `cargo check
  --no-default-features` on `temper-orchestration`: clean.
- `scripts/gen_wasm_test_registry.py --crate temper-orchestration --check`:
  up to date (1019 tests — `netlist_owned::tests` is `python-gated`, censused
  not registered).
- `make regen-check`: all derived artifacts consistent — including the
  regenerated README package count (17 → 18, `temper-data-model` added) and
  `uv.lock` (the new workspace member).

## U3 aggregates — the owned `Board` + `Netlist` structs (O-C3/U3)

U3 defines the owned AGGREGATE structs the U2 leaves compose into:
`Board` + `Netlist` in `packages/temper-data-model/` (pyo3-free, wasm32-
compatible), with their `Marshal` boundary in `netlist_owned.rs` and the
aggregate round-trip gate. No `BoardState` field changes; the aggregates are
the building blocks U4+ ports `BoardState.board`/`BoardState.netlist` to.

### The structs (`packages/temper-data-model/src/aggregates.rs`)

`Board` holds the OWNED fields only (`width`/`height`/`origin`/`keepouts`);
`Netlist` holds `components`/`nets` (the U2 leaves). The full field table,
classified owned vs keep vs derived:

| Aggregate | Field | Classification | Owned type / handling | Why |
|---|---|---|---|---|
| `Netlist` | `components` | OWNED | `Vec<Component>` | the U2 leaf; `list[Component]` |
| `Netlist` | `nets` | OWNED | `Vec<Net>` | the U2 leaf; `list[Net]` |
| `Netlist` | `_component_index` | DERIVED | not stored | `__post_init__`/`build_indices` recompute it unconditionally from components (a pure function); `repr=False` so it never appears in `__repr__`; `compare=True` so `==` needs it — recomputed identically on write-back |
| `Netlist` | `_net_index` | DERIVED | not stored | same, from nets |
| `Netlist` | `_component_nets` | DERIVED | not stored | same, from components+nets |
| `Board` | `width` | OWNED | `Val` | the no-coercion hazard: `board_contracts.Board::new` raw-stores constructor args (`v.clone().unbind()`), and `Board.from_polygon` computes width as `x_max - x_min` (type-preserving) — `Board(100, 80)` and int-coordinate polygons produce INT width. `Val` records which; `1` never widens to `1.0` |
| `Board` | `height` | OWNED | `Val` | same |
| `Board` | `origin` | OWNED | `(Val, Val)` | `tuple[float, float]` raw-stored; int-shaped `(0, 0)` is a legal contract value |
| `Board` | `keepouts` | OWNED | `Vec<(Val, Val, Val, Val)>` | `list[tuple[float, float, float, float]]` raw-stored; consumers explicitly float-coerce (`validation/geometric.py:289` `tuple(float(v) for v in k)`) — ints occur |
| `Board` | `zones` | KEEP | `Plain::Opaque` passthrough | `list[Zone]` — a foreign pyclass not yet ported (a later unit's scope); identity-preserved, never reconstructed |
| `Board` | `mounting_holes` | KEEP | `Plain::Opaque` passthrough | `list[MountingHole]` — foreign pyclass |
| `Board` | `ground_domains` | KEEP | `Plain::Opaque` passthrough | `list[GroundDomain]` — foreign pyclass |
| `Board` | `layer_stackup` | KEEP | `Plain::Opaque` passthrough | `LayerStackup | None` — foreign pyclass |
| `Board` | `outline_polygon` | KEEP | `Plain::Opaque` passthrough | the outline GEOMETRY — consumed as shapely (`hv_lv_partition.py` wraps it in `Polygon(p)`, `guard_strip.py` demands "outline must be a shapely Polygon"); identity passthrough is lossless for BOTH the current `list[tuple[float, float]]` form and any shapely form, so no owned encoding can be lossier or wrong |
| `Board` | `_zone_map` | DERIVED | not stored | `dict[str, Zone]` recomputed by `__post_init__` from `zones`; `init=False` (never constructor-passed), `repr=True`+`compare=True` — recomputed identically on write-back because `zones` passes through by identity |

### Why the keeps live in the marshal layer, not the structs

`temper-data-model` is pyo3-free BY CONSTRUCTION (the wasm32 tier compiles
it), so its structs cannot hold `Py<PyAny>` — and an identity passthrough of
a Python object is exactly a `Py` reference. The keeps therefore live in the
pyo3-side aggregate [`OwnedBoard`] (`netlist_owned.rs`): a `Plain::Opaque`
per keep field, wrapped UNCONDITIONALLY on read (never tree-ified, never
inspected) and returned by reference on write (`to_python` errors loudly if a
keep field is ever non-Opaque — an internal invariant, since keeps are
identity-passthrough ONLY). U4+ ports `BoardState.board` to `OwnedBoard`;
the wasm tier keeps using `temper_data_model::Board` directly (no keeps —
there is no Python there).

### The `Marshal` impls (`src/netlist_owned.rs`)

- **`Marshal for Netlist`** — read `components`/`nets` via getattr + the U2
  leaf impls; write via runtime import
  (`temper_design_bundle_python.netlist_contracts.Netlist`) called with
  ONLY `components`/`nets` kwargs. The pyclass constructor (`__post_init__`
  → `build_indices`) recomputes the three index dicts identically — the
  round-trip is bit-identical (type, repr, and `==`, whose `compare=True`
  index fields are equal by recomputation).
- **`Marshal for OwnedBoard`** — read the owned fields into the data-model
  `Board` (`Val`-shaped: int stays int), wrap the five keeps as
  `Plain::Opaque`; write via runtime import
  (`temper_design_bundle_python.board_contracts.Board`) with the owned
  fields marshalled and the keeps passed by identity. `_zone_map` is never
  passed (init=False; the constructor rebuilds it from the same zone
  objects).
- **Two new tuple impls** `(Val, Val)` and `(Val, Val, Val, Val)` serve
  `origin` and `keepouts` quads — element-wise `Val` reads (a list-shaped
  quad or a wrong arity is rejected loudly), tuple write-backs.
- **Defaults are reconstructed explicitly** by the constructor (empty
  lists/dicts, `None`, the `__post_init__` 4-layer stackup fill) exactly as
  the oracle does, so `Board(100.0, 80.0)` round-trips bit-identically.

### Round-trip gate results

`assert_roundtrip_with` against faithful `@dataclass` stand-ins for BOTH
pyclass modules (the U2 d3–d7 mock pattern; the `Board` stand-in mirrors the
oracle's `__post_init__` — default stackup fill + `_zone_map` build — so
constructor-normalised fields round-trip identically):

- **`Netlist()`** (dataclass default), a **full `Netlist`** with
  U2-leaf components/nets, and the derived indices (equal by recomputation —
  asserted through the gate's `==` arm, which includes `compare=True`
  indices) round-trip bit-identically.
- **`Board(100.0, 80.0)`** (default stackup fill + empty `_zone_map` on both
  sides) and a **full `Board`** with zones/mounting_holes/keepouts/
  ground_domains/explicit stackup/outline round-trip bit-identically.
- **The keeps round-trip BY IDENTITY**: `back.zones is orig.zones`,
  `back.mounting_holes is orig.mounting_holes`,
  `back.ground_domains is orig.ground_domains`,
  `back.layer_stackup is orig.layer_stackup`,
  `back.outline_polygon is orig.outline_polygon` — the SAME Python objects,
  never reconstructed; `_zone_map` is recomputed value-equal.
- **int-vs-float at the aggregate level**: `Board(100, 80, origin=(0, 0),
  keepouts=[(0, 0, 50, 80)])` round-trips bit-identically and the owned
  fields are asserted `Val::Int(100)`/`(Val::Int(0), Val::Int(0))`/
  `(Val::Int(0), Val::Int(0), Val::Int(50), Val::Int(80))` — the widening
  hazard is pinned, not merely tolerated.
- **NaN/±inf in `Val`-shaped Board fields** round-trip with type + repr
  preserved and the owned field still NaN (manual type/repr arm — the
  dataclass `__eq__` is False for NaN fields, the recorded U2 bound).
- **Guards**: tuple-shaped `keepouts`, list-shaped quads, 3-tuple quads,
  bool quad leaves, 1-tuple/list `origin`, bool `width`, and tuple-shaped
  `Netlist.components` are all REJECTED loudly.

### Test-robustness fixes (R22-aligned drive-bys, in `netlist_owned.rs::tests`)

Two pre-existing flakes in this file's tests were diagnosed and fixed in this
unit (both reproduced on a pristine origin/main worktree with the mandated
venv python):

1. **U2 tags-frozenset hash-seed flake.** 
   `component_with_pins_and_all_fields_roundtrips_losslessly` used a
   multi-element string `frozenset({'power', 'top'})`; under a colliding
   `PYTHONHASHSEED` draw the rebuilt frozenset iterates in a
   deterministic-but-different order — the EXACT non-guaranteed case U2's
   own "Recorded bound — `tags` frozenset iteration order" section
   describes — so the gate failed ~13% of runs on origin/main with the
   seed unset. The test now uses a SINGLE-element `frozenset({'power'})`,
   the case the recorded bound explicitly guarantees bit-identity for.
2. **U2/U3 concurrent-registration type-mismatch flake.** Every test's
   `setup()` registered fresh stand-in classes into the PROCESS-GLOBAL
   `sys.modules`; concurrent test threads can interleave closures (the pyo3
   GIL pool's already-attached fast path runs a previously-attached thread's
   closure without re-acquiring the GIL), so a test whose eval saw one
   registration and whose `to_python` import saw another failed with a
   type mismatch whose reprs are identical. Fix: a module-level
   `NETLIST_TESTS_LOCK` taken BEFORE any Python (a lock taken inside a
   closure deadlocks — the closure's thread waits for the real GIL held by
   the thread blocked on the lock — an ABBA cycle), plus `setup()` REUSES
   an existing registration so every test's globals and the runtime-import
   path resolve the same class objects. The U2 leaf tests were affected
   too — the flake was latent in U2 and made ~3x more likely by U3's
   larger `setup()` and 7 new tests.

Both fixes are in the touch-listed file and were validated by 20/20
filtered + 3/3 full-lib green runs with RANDOM hash seeds (previously
~2/15 filtered failed).

### Gates (U3)

- `cargo test` on `temper-data-model`: 3 passed (1 U2 `Val` pin + 2 new
  aggregate pins: int-vs-float at the `Board` level, `Netlist` holding the
  U2 leaves).
- `cargo test --lib` on `temper-orchestration`
  (PYO3_PYTHON=/home/bennet/Desktop/temper/.venv/bin/python): **1140 passed**
  (1133 base + 7 new `netlist_owned::tests` U3 tests), verified green with
  RANDOM hash seeds (3/3 full-lib runs, 20/20 filtered) after the
  test-robustness drive-bys above.
- `cargo clippy --all-targets` on both crates: clean.
- `cargo check --target wasm32-unknown-unknown` on `temper-data-model`:
  clean (the aggregate structs are pyo3-free by construction, exactly like
  the U2 leaves); `cargo check --no-default-features` on
  `temper-orchestration`: clean (`netlist_owned` stays python-gated).
- `make regen-check`: unchanged (no derived artifact depends on this unit —
  no new crate, no new script, no README count change).
