---
title: "Unit tests that never touch the pipeline can't see a deleted integration — 762 lines of unused pub code for three weeks"
date: "2026-07-27"
category: best-practices
module: router_v6
problem_type: best_practice
component: testing
severity: high
applies_when:
  - "a wholesale file replacement lands during a crate/module split or extraction refactor"
  - "a feature's only tests instantiate a lower-level object directly rather than going through the production entry point"
  - "a Rust/C library exposes `pub` items with zero callers and the compiler is silent about it"
  - "a feature flag has existed since before the last major structural refactor of its call path"
tags:
  - silent-feature-deletion
  - integration-coverage-gap
  - pyo3-binding
  - dead-pub-code
  - refactor-regression
  - unit-vs-integration
---

# Unit tests that never touch the pipeline can't see a deleted integration

## Context

Router V6's bundled/pruned SAT encoding (`enable_bundling`) was built,
wired, and tested end-to-end on **2026-06-29**: a bundle analyzer, a
bundled model builder, a CEGAR watchdog loop, and a dedicated PyO3
entrypoint, `solve_topology_rust_bundled`, added to
`packages/temper-rust-router/src/lib.rs` — the commit message states
explicitly that it "accepts BundleManifest dict alongside constraint
model." At that point the feature was real, callable from Python, and had
its own correctness-validation test unit.

**On 2026-07-08, `lib.rs` was replaced wholesale** during an unrelated
crate-architecture refactor that split the crate into a pure-Rust library
(`temper-rust-router-core`) plus a slim PyO3 wrapper
(`temper-rust-router`). `git log -p --follow` over the current `lib.rs`,
across every commit since that split, **never contains the string
`solve_topology_rust_bundled`** — the wrapper function was simply never
carried into the new file. The underlying logic was not deleted: the
CEGAR watchdog (`watchdog.rs`, 415 lines) and the homomorphism-expansion
extraction code (`extraction.rs`'s `extract_bundled`/`expand_assignments`,
347 lines) — **762 lines total** — were ported into the new
`temper-rust-router-core` as public library code, and are even
re-exported (`pub use extraction::{extract_bundled, expand_assignments}`).
**Nothing calls either of them.** The Python call site
(`_pipeline_route.py:289`, `from temper_rust_router import
solve_topology_rust_bundled`) has been importing a name that does not
exist in the compiled extension for roughly three weeks, undiscovered,
until a 2026-07-27 task tried to enable the flag and hit an immediate
`ImportError` before a single SAT variable was built.

**Why this went unnoticed for three weeks, confirmed by direct
inspection, not inferred:**

- `route_pcb()` — the production entry point — does not expose
  `enable_bundling` as a parameter at all, so no production caller could
  reach this path regardless of the flag's default.
- **The only tests that set `enable_bundling=True`
  (`test_bundled_equivalence.py`, `test_bundled_model_builder.py`)
  instantiate `ModelBuilder` directly and assert on variable/constraint
  counts. Neither file references `RouterV6Pipeline` at all** (confirmed
  by direct grep: zero hits). They never reach `_run_stage3`, so they
  never import `solve_topology_rust_bundled` and never exercise the
  missing binding — unit coverage over an integration that no longer
  existed.
- `temper-rust-router-core`'s own 101-test suite has exactly two tests
  touching this code at all, both tiny synthetic unit tests of
  `expand_assignments` alone. `Watchdog::solve` — the actual CEGAR loop —
  has **zero** test coverage anywhere in the repository, Rust or Python,
  synthetic or real-board.
- `cargo test` and `cargo clippy` both pass/are silent, because `Watchdog`
  and `extract_bundled` are `pub` items in a library crate — unused-but-
  public code is not a compile error or a dead-code lint warning in Rust,
  and there was no integration test present to fail.

Direct reproduction, 2026-07-27: `from temper_rust_router import
solve_topology_rust_bundled` raises `ImportError: cannot import name
'solve_topology_rust_bundled' from 'temper_rust_router'`. Setting
`enable_bundling=True` on any board, of any size, fails identically and
immediately — before Stage 3 builds a single SAT variable.

## Guidance

1. **A unit test that instantiates a lower-level object directly, and
   never goes through the production entry point, cannot detect the
   production entry point breaking.** `test_bundled_model_builder.py`
   correctly verifies `ModelBuilder`'s own variable/constraint counts
   forever — it was never going to notice that `RouterV6Pipeline`'s
   Python-to-Rust call for the same feature stopped resolving three weeks
   ago, because it never makes that call.
2. **Every feature flag needs at least one test that exercises it through
   its real production entry point**, not only through the lowest-level
   object the flag configures. If `route_pcb()` doesn't even expose the
   flag, that absence is itself worth flagging — a flag no production
   caller can reach is one refactor away from silently losing its wiring
   with nobody positioned to notice.
3. **A wholesale file replacement during a refactor is exactly the moment
   an existing integration point is most likely to be silently dropped.**
   `b27851fe`/`87bda65e` (the crate split) replaced `lib.rs` in full rather
   than editing it incrementally — there is no line-level "removal diff"
   to point to, because the new file was simply never given the function.
   Before replacing a file wholesale, diff the *symbol list* it exports
   against the old file's, not just its structure or its tests.
4. **`pub` in a Rust library crate is not a substitute for a caller.**
   The compiler and clippy have no complaint about unused-but-public
   code — 762 lines compiled cleanly, with zero callers, through every
   `cargo build`/`cargo clippy` run since the refactor. If a feature's
   correctness depends on code actually being called end-to-end, an
   integration test — not the compiler — is the only thing that can prove
   that call still resolves.
5. **When restoring a dropped integration, treat it as finishing an
   abandoned feature, not flipping a flag.** The correct fix here is not
   "re-add one function" — it requires rebuilding the PyO3 binding,
   wiring `enable_bundling`/`bundle_manifest` into `route_pcb()` (which
   never had them), and getting first-ever integration coverage on a
   415-line CEGAR loop that has run zero times against non-trivial data.
   Scoping this correctly, rather than patching the missing import in
   isolation, is itself part of the fix.

## Why This Matters

Nothing about this defect produced an error for three weeks. `cargo build`
succeeded. `cargo clippy` was silent. `cargo test` passed 101/101. The
unit tests written specifically to validate this feature passed every
single run, because they were never structured to notice the production
call path had gone missing. The gap was purely architectural: unit-level
coverage of `ModelBuilder` and integration-level coverage of
`RouterV6Pipeline` were never the same test, and the feature's only tests
lived entirely in the former. This is a durable risk for any project where
a feature is validated at the object-construction level but consumed
through a separate orchestration layer — a refactor of the orchestration
layer can sever the connection with zero observable symptom until someone
tries to use the feature for the first time since the break.

## When to Apply

- After any wholesale file replacement in a refactor (a crate split, a
  module extraction, a "rewrite this file cleanly" pass) — diff the
  exported symbol list against the pre-refactor file, not just structure
  or behavior of what remains.
- When writing tests for a feature flag or configuration option — include
  at least one test that goes through the actual production entry point,
  not only the lowest-level object the flag configures.
- When auditing why a feature flag defaults to off — check whether its
  code path is even reachable today before assuming the default reflects
  a deliberate quality/performance tradeoff.
- When a library crate has `pub` items with no callers anywhere in the
  codebase — treat this as a standing question ("is this integration
  still wired?"), not just an unused-code cleanup candidate.

## Examples

```python
# test_bundled_model_builder.py -- exercises ModelBuilder directly.
# Passes today. Cannot detect that RouterV6Pipeline's Python->Rust call
# for this same feature has been broken for three weeks, because it
# never makes that call.
def test_bundled_model_has_fewer_variables():
    builder = ModelBuilder(enable_bundling=True, ...)
    model = builder.build()
    assert model.variable_count < unbundled_variable_count

# grep confirms: zero references to RouterV6Pipeline in this file,
# or in test_bundled_equivalence.py.
```

```
# The missing symbol, confirmed live:
$ python -c "from temper_rust_router import solve_topology_rust_bundled"
ImportError: cannot import name 'solve_topology_rust_bundled' from
'temper_rust_router'. Did you mean: 'solve_topology_rust'?

# What WOULD have caught it three weeks earlier: one integration test
# that runs RouterV6Pipeline(enable_bundling=True).run(...) on any board,
# even a trivial synthetic one -- it would have failed on 2026-07-08.
```

## Related

- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
  — mechanism 3 ("an uninvoked code path") is the closest sibling: a check
  or feature that runs correctly in isolation but whose real call path is
  never exercised. This incident is that same shape applied to a feature's
  own tests rather than to a CI gate.
- `docs/solutions/best-practices/subsystem-deletion-cleanup-checklist-2026-07-04.md`
  — a different mechanism for a related symptom: that doc covers
  deliberate, planned subsystem deletion with a checklist to avoid orphaned
  references; this incident is the opposite — an accidental, undetected
  deletion during a refactor that was not about this feature at all.
- `scripts/check_rust_drc_presence.py` — an existing gate in the same
  problem space (verifies a compiled PyO3 extension's exported symbols
  match what the current Rust source registers) but checks build
  *freshness* against `lib.rs`'s own current registration, not caller
  satisfiability — it would not have caught this defect, because `lib.rs`
  itself no longer expects the dropped symbol. A gate that instead checked
  every `from temper_rust_router import X` call site in Python against the
  compiled module's actual exports would have.
- `docs/evidence/2026-07-27-bundled-encoding.md` — full reconstruction:
  the 2026-06-29 build, the 2026-07-08 refactor that dropped the binding,
  the direct `ImportError` reproduction, and the scoped restoration plan.
- `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` — identifies
  bundling's `O(n_nets × E) → O(b × E + n)` model-size reduction as the
  highest-leverage remaining lever on Stage 3's model size, blocked on
  this restoration.
