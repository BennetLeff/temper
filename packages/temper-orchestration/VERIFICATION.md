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
