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
