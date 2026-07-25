---
title: "refactor: Package Consolidation"
type: refactor
status: active
date: 2026-07-25
---

## Goal

19 package directories exist under `packages/` (the commonly-cited "20" counts
`packages/` itself); `temper-placer` alone is ~79% of package source by LOC
(measured: `find`+`wc -l` on `.py`/`.rs`, excluding tests/target/caches — my
125,668 vs. the prompt's cited 119,377; both agree on order of magnitude and
dominance, difference is measurement-method noise, not a correction). Of the
other 18, nine are under 500 LOC. Three of the four historical `-core` splits
turn out to be vestigial duplication rather than build necessity; this plan
merges those three, deletes two already-dead artifacts, and explicitly freezes
everything else — each extra package costs a workspace-exclude line, a CI
clippy-loop entry, and a manifest entry (§ AGENTS.md) for zero benefit once its
original reason has lapsed.

## Inventory

LOC = `find <pkg> -name '*.py' -o -name '*.rs'`, excluding
`tests/`,`target/`,`__pycache__/`,`.pytest_cache/`. "Dependents" = real
Cargo/pyproject/import edges from *other* packages, verified by `grep`.

| Package | LOC | Dependents | Reason it exists | Verdict |
|---|---|---|---|---|
| temper-placer | 125,668 | root CLI | main placement engine | keep — **out of scope** (see below) |
| temper-drc-rs | 7,267 | temper-placer (3 importers) | DRC rust engine | keep |
| temper-geometry | 7,385 | temper-placer (9 importers) | pyo3 geometry math | keep, absorb -core |
| temper-rust-router-core | 6,847 | temper-rust-router **and** temper-constraint-compiler (real 2nd Rust consumer) | GIL-crash fix + genuine multi-consumer split | **keep — load-bearing** |
| temper-constraint-compiler | 3,443 | temper-placer (4 importers) | constraint compilation | keep |
| temper-quality-oracle | 1,969 | temper-placer (2 importers) | quality-oracle checks | keep |
| temper-design-bundle | 1,758 | temper-placer (2 importers) | shared design-bundle types | keep |
| temper-io-types | 1,093 | temper-placer (6 importers) | shared IO pyo3 types | keep |
| temper-rust-router | 836 | temper-placer (maturin, explicit CI step) | pyo3 wrapper, **cdylib-only** | keep — see below |
| temper-geometry-core | 437 | temper-geometry **only**; 0 tests live here | orig: "breaks geometry→core import cycle" (`184357b5`) | **merge into temper-geometry** |
| temper-py-bridge | 291 | temper-geometry, temper-quality-oracle | shared pyo3 bridge helpers | keep |
| temper-pcl-ir | 209 | temper-design-bundle, temper-constraint-compiler | shared placement-constraint IR | keep — small but multi-consumer |
| temper-dsn-core | 222 | temper-dsn **only** | orig: rescue pyo3-unlinkable tests (`c2cde0c6`) | **merge into temper-dsn** |
| temper-py-bridge-derive | 244 | temper-py-bridge (1, but `proc-macro=true`) | Rust proc-macro crates must be separate | keep — hard language constraint |
| temper-ipc-core | 190 | temper-ipc **only** | orig: same as dsn-core, same commit | **merge into temper-ipc** |
| temper-workflow | 457 | none external; depends on temper-placer | GPBM orchestration CLI, own CI pytest job | keep |
| temper-ipc | 98 | temper-placer (2 importers) | pyo3 wrapper | keep, absorb -core |
| temper-dsn | 76 | temper-placer (3 importers) | pyo3 wrapper | keep, absorb -core |
| temper-validation | 0 | none | no source; untracked; matched by `pyproject.toml:26` glob | **delete** |
| `temper_placer/constraint_types/` (not a package, subpkg) | 1,007 | 0 importers (15 use `_constraint_types` instead) | committed duplicate, differs only in `__init__.py` docstring | **delete** |

**Key verified fact:** the dsn/ipc-core split's stated reason
("pyo3 exception DATA symbols abort at dyld load", `c2cde0c6`, 2026-07-20) no
longer holds. `temper-geometry` — same pyo3 0.29, same `crate-type =
["cdylib","rlib"]`, same `extension-module` feature — already carries its own
`.cargo/config.toml` with `-undefined dynamic_lookup` and passes `cargo test
--lib` today: **312/313 tests pass** (1 pre-existing, unrelated failure in
`congestion_tensor`, not touched here). `temper-dsn` already has the identical
`.cargo/config.toml` in place too. The linker flag, not the crate split, is
what fixed testability — the split is now redundant scaffolding.
`temper-rust-router` is the one genuine exception: its `crate-type = ["cdylib"]`
has **no rlib**, so `temper-constraint-compiler` (a real second Rust crate)
architecturally cannot depend on it and must depend on `-core` instead.

## Per-merge risk

| Merge | Breaks | Mitigation |
|---|---|---|
| delete `temper-validation/` | Nothing found — no CI ref, no Cargo/pyproject ref, untracked in git | `rm -rf packages/temper-validation`; re-run `uv sync --all-packages` to confirm the `packages/*` glob no longer needs it |
| delete `constraint_types/` dup | Nothing found — 0 importers, not in `.coverage.run.omit` (only `_constraint_types` is) | `git rm -r packages/temper-placer/src/temper_placer/constraint_types` |
| dsn + dsn-core | No `.importlinter`/allowlist reference (contracts are scoped to `temper_placer` root package only); `python-tests.yml:199-200` clippy loop lists `temper-dsn-core` by name | Fold `-core`'s `src/lib.rs` into `temper-dsn/src/`, keep `crate-type=["cdylib","rlib"]`, drop the `temper-dsn-core` workspace-exclude line (`pyproject.toml:27`) and clippy-loop entry; verify with `cargo test --lib` |
| ipc + ipc-core | Same as dsn (identical shape, same commit) | Same steps, substitute `temper-ipc` |
| geometry + geometry-core | Widest blast radius: 9 Python importers, `temper-geometry` also depends on `temper-py-bridge` (extra edge to preserve) | Same steps; do this **last**, after the dsn/ipc pattern is proven once in CI — **riskiest of the three** by consumer count, not by technical difficulty |

No merge here touches `import-linter-allowlist.yaml`'s router-v6 exceptions or
any `Origin: U5 of docs/plans/...` provenance comment — those all live inside
`temper-drc-rs` and `temper-rust-router-core`, neither of which changes.

## Requirements

- **R1.** Delete `packages/temper-validation/` (untracked, 0 LOC, matched only
  by the `packages/*` glob). Free — no code depends on it.
- **R2.** `git rm -r packages/temper-placer/src/temper_placer/constraint_types/`
  (9 files, 1,007 LOC, 0 importers, byte-identical to `_constraint_types` bar
  one docstring). Free — already dead per pre-verified audit.
- **R3.** Merge `temper-dsn-core` into `temper-dsn`. Update
  `pyproject.toml:27` (drop from `exclude`) and
  `python-tests.yml:199-200` (drop from clippy loop). Acceptance: `cargo test
  --lib -p temper-dsn` passes all 8 currently-in-`-core` tests; `import
  temper_dsn` still works.
- **R4.** Merge `temper-ipc-core` into `temper-ipc`, same steps. Acceptance:
  `cargo test --lib -p temper-ipc` passes all 5 currently-in-`-core` tests.
- **R5.** Merge `temper-geometry-core` into `temper-geometry`, same steps.
  Acceptance: `cargo test --lib -p temper-geometry` still passes 312/313 (the
  1 failure is pre-existing and out of scope for this plan).

Ordering is cheapest-and-most-provable first: R1/R2 are pure deletions with
zero dependents (verify, don't re-derive). R3/R4 are identical, low-consumer-
count merges that establish the pattern. R5 repeats the same pattern on the
highest-consumer-count target once R3/R4 are proven in CI.

## Out of scope

- **`router_v6` (28,144 LOC, inside `temper-placer`).** Not touched, not
  split, not refactored. It just received its first trustworthy completion
  baseline (0% → 79%, `STRATEGY.md` "Honest state"); any internal
  restructuring risks invalidating that measurement before it's been used for
  anything. Frozen until that changes.
- **`temper-placer` internal restructuring generally.** 125k LOC / ~79% of
  package source is a real concentration, but subdividing it trades intra-
  stage complexity for interface count (`METHODOLOGY.md` §3.3) — exactly the
  failure class this repo is trying to avoid. Not proposed here.
- **`temper-rust-router` / `temper-rust-router-core`.** Genuinely load-bearing:
  cdylib-only wrapper, a real second Rust consumer
  (`temper-constraint-compiler`), and a documented GIL-crash fix
  (`docs/plans/2026-07-23-003-perf-rust-migration-roadmap-plan.md`). Keep as-is.
- **`temper-py-bridge` / `temper-py-bridge-derive`.** Rust requires proc-macro
  crates (`proc-macro = true`) to live in their own crate. Not a "split
  fatigue" instance — hard language constraint.
- **Baselines, allowlists, `import-linter-allowlist.yaml` re-classification,
  dead CI gates.** Ceded entirely to
  `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md`; not
  re-audited here.
- **`packages/temper-autoprof/`** — referenced by path in
  `pyproject.toml` (`testpaths`, `pythonpath`) but the directory does not
  exist on disk. UNMEASURED whether this is stale config or a not-yet-created
  package; flagged, not resolved, here.

## Review record (2026-07-25)

Independently re-verified before acceptance. All technical claims held, and
the plan corrected the reviewer: there are **19** package directories, not 20.

| Claim | Verified |
|---|---|
| `temper-rust-router` is `crate-type = ["cdylib"]`, no rlib | confirmed |
| `temper-constraint-compiler` depends on `-core` out of necessity | confirmed — `Cargo.toml:13`, and `temper_rust_router_core::types::InternalConstraint` used in `src/pyo3_bridge.rs:307` (source, not only tests) |
| `temper-geometry-core` has zero external dependents | confirmed — only `temper-geometry` references it |
| `temper-geometry` carries `.cargo/config.toml`; so does `temper-dsn` | confirmed |
| `constraint_types/` duplicate, zero importers | confirmed independently |

Additional verification supporting the geometry merge (the plan's own
riskiest item): **no other Rust crate depends on `temper-geometry`**, the
wrapper enables `pyo3 extension-module`, and `temper-geometry-core` has no
pyo3 at all. Merging a pure-Rust core into an extension-module wrapper with
no external Rust consumers is therefore lower risk than the plan credits —
though its ordering (prove on dsn/ipc first) is still the right sequence.

Accepted as written. The `temper-rust-router-core` keep-decision is correct
and is the one this reviewer expected to be gotten wrong.
