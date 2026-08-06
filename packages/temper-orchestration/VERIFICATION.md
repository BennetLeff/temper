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

- **R1a** — bit-identical differentials vs verbatim oracles: green (51
  differential assertions across 3 modules; floats via `float.hex()`, type
  carried on every leaf, error parity via `canon_call`).
- **R1b** — performance/no-regression arm: the migrated compute is invoked
  per CLI command (once per stage-entry), not in any hot loop; per the
  guide, this is the no-regression-beyond-noise arm. The rust kernels are
  trivially faster or equal for the per-call work; no speedup claim is
  made. (The pr-perf-check baseline covers the CLI surfaces' wall time via
  the timing-gate itself.)
- **R1c** — >= 5 non-vacuous properties/module: timing 6, trace_commands 6,
  route_and_measure 5 (all G4-vacuity-guarded).
- **R1d** — >= 3 metamorphic relations/module: timing 4, trace_commands 3,
  route_and_measure 3.
- **R1e** — this document: structural proof + explicit non-applicability
  note for induction.
- **R1f** — TDD: the three differentials were written first and demonstrated
  RED (collection failure — `temper_orchestration` did not exist), then
  GREEN.
- **R1g** — borrow over clone; no `unwrap` outside tests; `catch_unwind`
  at every pyo3 boundary (pyo3's `#[pyfunction]` expansion); clippy
  `unwrap_used`/`expect_used` denied.
- **R1h** — not physics-gated (recorded above).
