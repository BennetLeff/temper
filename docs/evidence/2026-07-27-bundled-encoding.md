# Bundled/pruned SAT encoding: not wired, not runnable, not a flag-flip

**Date:** 2026-07-27
**Task:** Determine why `enable_bundling` defaults to `False` in Router V6's
`ModelBuilder`/`RouterV6Pipeline`, and whether it is safe to wire it into
`route_pcb()` to shrink the 3,876,012-variable Stage 3 model documented in
`docs/evidence/2026-07-27-stage3-model-and-rewrite.md`.

## Falsifier, stated before measuring

**"Bundling materially shrinks the model without changing routing
results."**

**Result: could not be tested — refuted at a more basic level.** The
bundled code path does not execute at all in the current build. Setting
`enable_bundling=True` does not produce a smaller model, an equal model, a
worse model, or a wrong route — it raises `ImportError` before any SAT
model is built, on every call, unconditionally. There is no "before/after"
to compare because "after" never runs. This is a more decisive answer than
the falsifier anticipated, so no size/timing/completion/quality table
follows — fabricating one would violate "report counts and timings, not
impressions."

## Why `enable_bundling` is `False`: reconstructed history

### It was built, wired, and tested once (2026-06-29)

The feature (`docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md`,
now `status: stale`, `swept_basis: "insufficient evidence - needs human
triage"`) was implemented across a real unit sequence on 2026-06-29:

- `810001294809` — feat(U6): wire bundle analyzer, bundled model builder,
  and CEGAR watchdog into pipeline
- `e8b5d5b471c9` — feat(U4): add CEGAR watchdog for lazy Performance
  grounding — commit message states explicitly: *"`solve_topology_rust_bundled`
  PyO3 entrypoint accepts BundleManifest dict alongside constraint model."*
  This touched `packages/temper-rust-router/src/lib.rs` (+128 lines) at the
  time.
- `d582532d5fe7` — feat(U7): add bundled constraint audit with
  homomorphism expansion
- `9b12f29198d9` — feat(U8): add correctness validation tests for bundled
  encoding

So on 2026-06-29 the bundled path was a real, PyO3-exposed, end-to-end
feature.

### The PyO3 entrypoint was lost in an unrelated refactor (~2026-07-08) and nobody noticed

`packages/temper-rust-router/src/lib.rs` — the file the 2026-06-29 commit
added `solve_topology_rust_bundled` to — was **replaced wholesale** during
`b27851fe` ("feat(router): extract temper-rust-router-core as pure-Rust
rlib") and `87bda65e` ("feat(router): slim wrapper to cdylib-only pyo3
crate depending on -core"), both 2026-07-08. That refactor split the crate
into a pure-Rust library (`temper-rust-router-core`) plus a slim PyO3
wrapper (`temper-rust-router`). Checked directly: `git log -p --follow`
over the *current* `packages/temper-rust-router/src/lib.rs`, across every
commit in its own history back to that split, **never contains the string
`solve_topology_rust_bundled`** — the wrapper function was not ported when
the crate was slimmed. The Watchdog/CEGAR core logic *was* carried into
`temper-rust-router-core` as public library code (`watchdog.rs`, 415
lines; `extraction.rs`'s `extract_bundled`/`expand_assignments`, homomorphism
expansion, 347 lines) and is even re-exported (`pub use extraction::{extract_bundled,
expand_assignments}` in `temper-rust-router-core/src/lib.rs:24`) — but
**nothing calls it**. Confirmed by direct grep: `Watchdog` appears only in
`watchdog.rs` itself; no caller anywhere in either crate.

The Python call site
(`packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:289`,
`from temper_rust_router import solve_topology_rust_bundled`) has been
importing a name that does not exist in the compiled extension since that
refactor — roughly three weeks as of today.

### Why it was never caught

- `route_pcb()` (`_adapter_convert.py:115`) does not expose
  `enable_bundling` as a parameter at all — production callers cannot
  reach this path regardless.
- The only tests that set `enable_bundling=True`
  (`packages/temper-placer/tests/router_v6/test_bundled_equivalence.py`,
  `test_bundled_model_builder.py`) instantiate `ModelBuilder` directly and
  assert on variable/constraint counts. Neither file references
  `RouterV6Pipeline` at all — grepped directly, zero hits. They never
  reach `_run_stage3`, so they never import `solve_topology_rust_bundled`
  and never exercise the missing binding.
- `packages/temper-rust-router-core`'s test suite (101 tests, verified
  below) has exactly two tests touching this code at all
  (`test_expand_assignments_singleton_bundle`,
  `test_expand_assignments_false_class_var` in `extraction.rs`), both
  tiny synthetic unit tests of `expand_assignments` alone.
  `Watchdog::solve` — the actual CEGAR loop — has **zero** test coverage
  anywhere in the repository, Rust or Python, synthetic or real-board.
- `cargo test --release` and `cargo clippy --release` both pass/are silent
  on this because `Watchdog` and `extract_bundled` are `pub` items in a
  library crate — unused-but-public code is not a compile error or a
  clippy dead-code warning, and there is no integration test to fail.

### Direct reproduction, today

```
$ cd packages/temper-rust-router && uv run maturin develop --release
   Finished `release` profile [optimized] target(s) in 3.59s
   Installed temper-rust-router-0.1.0

$ uv run python -c "import temper_rust_router as t; print([n for n in dir(t) if not n.startswith('_')])"
['CapacityConstraint', 'Constraint', 'DiffPairConstraint', 'LayerConstraint',
 'NetChannelVar', 'NetLayerVar', 'OrderVar', 'Variable', 'ViaVar',
 'audit_result', 'auto_extract_loops_rust', 'solve_topology_rust',
 'temper_rust_router']

$ uv run python -c "from temper_rust_router import solve_topology_rust_bundled"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ImportError: cannot import name 'solve_topology_rust_bundled' from
'temper_rust_router' (.../temper_rust_router/__init__.py).
Did you mean: 'solve_topology_rust'?
```

This is the exact import `_pipeline_route.py:289` performs when
`self.enable_bundling and bundle_manifest is not None`. Any attempt to run
`RouterV6Pipeline(enable_bundling=True).run(...)` on any board, of any
size, fails identically and immediately — before Stage 3 builds a single
SAT variable.

## Classification against the task's decision tree

This does not cleanly match any of the three named cases:

- **Not** "never finished or wired up" in the simple sense — it *was*
  finished and wired once (2026-06-29), with its own U1–U8 implementation
  units and a dedicated correctness-validation unit (U8).
- **Not** "disabled because it produced wrong or worse routes" — no
  evidence exists of it ever running against real routing data after the
  2026-07-08 refactor to produce a route of any quality, right or wrong.
  Before that, no full-board (or even multi-net-through-pipeline)
  measurement of it is on record either — only the ModelBuilder-level unit
  tests and Rust-level synthetic tests.
- **Not** "off for a reason that no longer applies" — no deliberate
  decision to turn it off exists in the history; the entrypoint was
  dropped as a side effect of an unrelated crate-architecture refactor.

The practical consequence is the same as the second case, though: **it is
not safe to enable**, for a stronger reason than "might route worse" — it
cannot route at all. Per the task's instruction to stop and report rather
than push a fix through when something surprising turns up: restoring this
is not "wiring an existing encoding into `route_pcb()`" as the task
framed it. It is closer to *finishing an abandoned feature*:

1. Write a new `#[pyfunction] solve_topology_rust_bundled` in
   `packages/temper-rust-router/src/lib.rs` that constructs a `Watchdog`
   from `temper-rust-router-core` and calls `.solve()`, then
   `extract_bundled`/`expand_assignments` to turn the result back into
   per-net channel assignments Stage 4 can consume.
2. Add `enable_bundling`/`bundle_manifest` parameters to `route_pcb()`
   itself (currently absent).
3. Get first-ever integration test coverage on `Watchdog::solve` — a
   415-line CEGAR loop that has run exactly zero times against non-trivial
   data since it was written, per every test file in the repository.
4. Only then run this task's measurement plan (model size, Stage 3 timing
   broken into encode/rewrite/solve, completion rate vs. the 48/96 = 50.0%
   baseline, route quality) to decide a default.

Each of those is itself a multi-step, unverified change to code that has
never been exercised end-to-end. Doing that inside this task would be
exactly the kind of "guess and push through" the task's hard constraints
warn against ("UNVERIFIED rather than guessing"). **No wiring change was
made.**

## What this task did verify

- `enable_bundling` remains `False` everywhere (`RouterV6Pipeline.__init__`
  default, `route_pcb()` doesn't expose it at all). **No source files
  changed.**
- `solve_topology_rust_bundled` does not exist in the compiled
  `temper_rust_router` extension (direct `ImportError`, reproduced above,
  after a clean `uv run maturin develop --release` build in this
  worktree).
- `Watchdog` (the CEGAR loop) and `extract_bundled`/`expand_assignments`
  (the homomorphism expansion) exist as compiled, `pub`, but uncalled
  library code in `temper-rust-router-core`.
- No test in the repository — Python or Rust — runs the bundled path
  through `RouterV6Pipeline` or exercises `Watchdog::solve` against
  anything beyond two tiny synthetic `expand_assignments` cases.

## Verification (gates required to stay green — none touched by this task)

- `cargo test --release` (`temper-rust-router-core`): **101 passed, 0
  failed** across 6 binaries (90 unit + 1 + 1 + 8 + 1 integration + 0
  doc-tests) — identical to the stated baseline. No source changed.
- `cargo clippy --release` (`temper-rust-router-core`): **0 warnings.**
- `make netlist`: **76 assertions passed, 0 failed.**
- `scripts/check_domain_partition.py`: exit 0.
- `scripts/capacity_budget_gate.py`: exit 0.
- `scripts/mpn_fabrication_gate.py`: exit 0.
- `scripts/check_derived_doc_drift.py`: exit 0.
- `scripts/check_vacuous_gates.py`: exit 0 (0 violations).
- No changes made to `pcb/`, `elec/`, or gate scripts. No changes made to
  any source file in this task — the only local build artifacts produced
  were `uv run maturin develop --release` rebuilds needed to reproduce the
  `ImportError`, matching the reproduction steps in
  `docs/evidence/2026-07-27-stage3-model-and-rewrite.md`.

## Recommended default

**Keep `enable_bundling=False`.** Not because bundling was measured and
found to trade completion rate for model size — no such measurement is
possible today — but because the code path required to run it does not
exist in the compiled extension. Flipping the flag today converts every
route attempt into a guaranteed `ImportError`, which is strictly worse
than the current 52.67s / 50.0%-completion baseline this session's other
work established.

If bundling's `O(n_nets × E) → O(b × E + n)` reduction is worth pursuing
later (Part 2 of `docs/evidence/2026-07-27-stage3-model-and-rewrite.md`
still identifies it as the highest-leverage remaining lever on model
size), it needs to be scoped as its own feature-restoration task —
rebuild the missing PyO3 binding, add real integration test coverage for
`Watchdog::solve`, and only then repeat this task's measurement plan
against the 48/96 = 50.0% baseline. That is materially larger than "wire
an existing encoding into `route_pcb()`" and is reported here rather than
attempted.

## UNVERIFIED

- Whether `Watchdog::solve`, `extract_bundled`, and `expand_assignments`
  are even correct against real (non-synthetic) constraint data — no test
  anywhere exercises them beyond two tiny hand-built cases for
  `expand_assignments` alone; `Watchdog::solve` itself has never been
  called from any test.
- The exact commit where the `solve_topology_rust_bundled` PyO3 wrapper
  was dropped. Traced to the `packages/temper-rust-router` crate-split
  window (`b27851fe`, `87bda65e`, both 2026-07-08), which replaced
  `packages/temper-rust-router/src/lib.rs` wholesale rather than editing
  it incrementally — a line-level "removal diff" doesn't exist to point
  to; the new file was simply never given the function.
- Whether restoring the binding would compile cleanly today without
  further changes — `InternalConstraint`/`InternalBundleManifest`/`types.rs`
  in `temper-rust-router-core` may have drifted in the ~4 weeks since
  `Watchdog` was last touched by anything other than lint/dead-code
  passes (`857dae1b`, `cbbe6de8`, `953b56d0` — all mechanical, none
  functional).
- Model-size, timing, completion-rate, and route-quality numbers for the
  bundled encoding at any scale — not measurable, since the path does not
  execute. Any such table would be fabricated; none is provided.
- Whether `BundleAnalyzer` (`bundle_analyzer.py`, 422 lines, Python side)
  itself still produces correct `BundleManifest`s against a real board's
  `pcb.nets`/`stage2.skeletons` — it is exercised only by the same
  ModelBuilder-level unit tests noted above, never through the full
  pipeline.
