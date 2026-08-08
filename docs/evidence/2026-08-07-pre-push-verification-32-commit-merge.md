---
title: "Pre-push verification: local main's 32-commit merge session vs origin/main"
date: 2026-08-07
author: Claude (verification agent)
---

# Pre-push verification: local `main` (32 commits ahead) vs `origin/main`

## Verdict: GO, conditional on one trivial fix and a recommended rebase

Local `main` (`ecaf45f2`, 32 commits ahead of the merge-base `90d5fd98`) is safe
to push **after**:

1. Adding one registry entry (`check_bom_source_reconciliation.py`) to
   `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py`'s
   `_CI_SCRIPT_SURVEY` — the only defect this verification attributes to the
   32-commit session itself.
2. Strongly recommended, not strictly required: rebase onto (or cherry-pick)
   `origin/main`'s current tip `7e1194b7` ("fix(ci): unbreak main — codegen
   drift + dead mutation scaffolding (2 of 8)", PR #911) before pushing.
   Without it, 7 pre-existing-but-already-fixed-upstream failures ship red
   again on the new `main` (see below) — none are regressions from this
   session, but pushing without the fix means re-breaking gates the
   maintainer already fixed once, on the same commit range.

## Scope note: `origin/main` moved during this verification

The task brief named `90d5fd98` as `origin/main`. A live `git fetch` at the
start of this verification showed `origin/main` had already advanced one
commit, to `7e1194b7`, sometime between the brief being written and this
session starting. `7e1194b7` is a squashed PR (#911, "2 of 8" of an
in-progress "unbreak main" series) built **directly on `90d5fd98`** — it is a
sibling of local `main`'s 32 commits, not a descendant of them
(`main..origin/main` = exactly this one commit; `origin/main..main` = the 32).
All comparisons below use both: `90d5fd98` (the task's named baseline, and
the true merge-base) for ancestry/attribution, and `7e1194b7` (current live
origin/main) as a second empirical baseline since it happens to fix most of
what's found red.

## Gate results (measured on a temporary worktree at local `main`, `ecaf45f2`)

| Gate | Result | Notes |
|---|---|---|
| `import_linter_gate.py` | **PASS** | 0 violations |
| `check_typecheck_gate.py` (plain `uv sync`, matching CI's `fast-gates` job exactly) | **PASS** | 217 errors / 217 baseline, 0 call-arg violations |
| `check_verdict_coverage.py` | **PASS** | R7 axis 100% covered (gate's actual pass/fail criterion); R1 axis is informational only |
| `check_measurement_provenance.py` (+ `--check-shrink`) | **RED, pre-existing** | `drc_ceiling.json`'s `measured_at_commit` is a dangling SHA (the exact incident `AGENTS.md` documents). Reproduces on `origin/main` too (as a different symptom — STALE there vs. dangling-commit here, because local main's own 32 commits include the *checker* enhancement that closes the dangling-SHA detection gap; the underlying bad data record is unchanged on both branches). Not required by branch protection (`Board, Provenance & Requirements Gates` isn't in `required_contexts`). |
| `check_bom_source_reconciliation.py` | **RED, expected** | 49 findings, exactly matching the briefed count; allowlist fix in flight elsewhere |
| `make regen-check` | **PASS** | repo-state, wasm registry, oracle hashes, hash-order, manifest, unwired kernels, wire formats all consistent |
| Firmware codegen (`gen_config.py`, `gen_transition_table.py` x2, `gen_fault_list.py`) | **PASS**, byte-identical | all four regenerate with zero diff |
| `check_stale_extensions.py` | **PASS** | 13/13 pyo3 extensions fresh |
| `actionlint` | **PASS** | 0 findings across `.github/workflows/` |
| Firmware test suite (`firmware/test/build`, all 22 binaries) | **PASS** | 380 tests, 0 failures (the SIL fault-injection binary needs to run from `firmware/test/`, not repo root, for its relative `traces/manifest.json` lookup — a harness detail, not a defect) |
| `cargo clippy -D warnings` (16 CI-mandated crate manifests) | **3 RED, all pre-existing** | see below |
| `cargo test` (CI's 3 mandated crates: orchestration, geometry, design-bundle) | **1 pre-existing env/config issue** (temper-geometry), 2 PASS | see below |
| `cargo test` (14 more crates, opportunistic, beyond CI's actual scope) | **3 RED, all pre-existing**, 11 PASS | temper-quality-oracle, temper-thermal, temper-constraints — all reproduce identically on `origin/main`; not CI-gated at all |
| WASM32 build + clippy (`temper-drc-rs`, `temper-geometry`, `--no-default-features`) | **PASS** | |
| `packages/temper-placer/tests/core/` + validation subset (CI's actual "Core Tests" gate) | **3 FAILED / 1022 passed / 9 skipped** | 2 pre-existing (`H_CONV_BACKGROUND` dead-parameter), 1 **new** (gate script registry gap — see fix above) |
| `packages/temper-placer/tests/` (full suite, 17974 collected) | **partial: 2309/17974 (12.8%) run, 3 FAILED** (all `tests/closure/`, all attributable to absent `kicad-cli` and empty placement result — file byte-identical to `origin/main`, so not a regression) | Suite not run to completion — see "What did not complete" |
| `packages/temper-workflow/tests/` | **PASS** | 32/32 |

## Pre-existing failures traced to a specific cause

Every non-BOM, non-provenance red result above was independently attributed
to a **specific commit that predates `90d5fd98`** (confirmed via
`git cat-file -e 90d5fd98:<path>` and `git log origin/main..main -- <path>`
returning empty for each file) and a **specific fix already written**, either
squashed into `origin/main`'s `7e1194b7` or sitting on the unmerged
`origin/fix/main-triage` branch (commits `b1a13651`, `a70bc618`):

1. `gen_domain_models.py --check` fails — `NetClassRules` template
   (`scripts/templates/netclass_rules.rs.j2`) never got the
   `Serialize, Deserialize` derives that `board.rs` was hand-patched with in
   `d559b446a`. Fixed in `7e1194b7`.
2. `cargo clippy temper-design-bundle`: `neg_cmp_op_on_partial_ord` at
   `kicad_exporter_geometry.rs:202`. Introduced in `62a27ff5` (an ancestor of
   `90d5fd98`). Fixed in `7e1194b7` / `b1a13651`.
3. `cargo clippy temper-drc-rs`: `unnecessary_sort_by` at
   `deterministic_leaf_drc.rs:51` (clippy 1.97-only lint; this sandbox's and
   CI's clippy are both 1.97+, so it fires here). Fixed in `7e1194b7` /
   `a70bc618`.
4. `cargo clippy temper-io-types`: `expect_used` in a `dag_expr.rs` test
   module. Fixed in `7e1194b7` / `b1a13651`.
5. `cargo test temper-geometry --features python` fails to link
   (`rust-lld: undefined symbol: PyImport_ImportModule` etc. — pyo3's
   `extension-module` feature deliberately omits linking libpython, which
   breaks a real test binary). This is what local `main`'s own
   `.github/workflows/python-tests.yml` still says to run. Confirmed the
   *fixed* invocation, `--no-default-features`, passes 514/514 on **both**
   branches' source. `7e1194b7` changed the workflow to
   `--no-default-features`; local `main` has neither the flag change nor a
   broken test — it has an unfixed **workflow config** bug that predates
   `90d5fd98`.
6. `tests/validation/test_dead_parameter_probe.py::test_physics_parameter_live[H_CONV_BACKGROUND]`
   (and its aggregate) fails — `heat_removal.rs`'s Rust port stopped
   threading `H_CONV_BACKGROUND` through to the computation. Bug and fix
   both predate `90d5fd98`'s local-main-side history; fixed in `7e1194b7`.
7. `tests/requirements/safety/test_rotation_convention_remaining_sites_oracle.py::...dogbone...`
   fails with `TypeError: 'float' object cannot be interpreted as an
   integer` — `escape_via.rs`'s rotation field was `Option<i64>` where the
   Python behavior it mirrors accepts any numeric. Fixed in `7e1194b7`.
8. `vulture_gate.py` reports 3 "NEW dead code" (unsatisfiable ternary)
   findings in `test_parse_utils_rust_differential.py`,
   `test_pcl_rust_pbt.py`, `test_escape_via_pbt.py` — leftover mutation
   scaffolding (`X if False else Y`) never reverted after landing. Fixed in
   `7e1194b7`.

None of files 2–8 above were touched by any of local `main`'s 32 commits
(`git log --oneline origin/main..main -- <path>` returns empty for every
one); all existed, unfixed, at `90d5fd98` itself. `7e1194b7` was built
directly on `90d5fd98` (not on top of the 32 commits), as a sibling "unbreak
main" pass — it happens to fix nearly everything this verification found
red, because it targeted the same broken merge-base.

## The one genuine new gap (attributable to the 32 commits)

`tests/validation/test_gate_input_registry.py::test_every_invoked_ci_gate_script_is_registered`
fails: `check_bom_source_reconciliation.py` was added to
`.github/workflows/python-tests.yml` (commit `cfc81fab`, part of the 32) but
never added to `gate_input_registry._CI_SCRIPT_SURVEY`
(`packages/temper-placer/src/temper_placer/validation/gate_input_registry.py:555`).
One-line fix: add an entry analogous to the existing ones, e.g.

```python
("check_bom_source_reconciliation.py", "docs/hardware/BOM.md", "BOM<->source reconciliation gate (R14); probe harness deferred"),
```

## Diff audit (`git diff origin/main..main`, 197 files, +10033/-702)

- No secrets/tokens/keys found (`api[_-]?key|secret|password|token|BEGIN
  (RSA|OPENSSH|PRIVATE)|AKIA...` grep over the full diff — the only `token`
  hits are prose about `wrangler` API tokens and a PCB-parsing tokenizer).
- No absolute agent-sandbox paths (`/tmp/claude-*`, worktree paths) in any
  added line.
- No `.orig`/`.rej`/`.bak`/`.swp` files.
- No committed build artifacts or files over 200KB.
- `git status --porcelain -uall` clean on the merge-base-derived worktree
  both before and after regenerating all codegen artifacts in place.
- The ~90 `docs/plans/*.md` files each showing a small `+6/-6` diff are a
  single plan-triage sweep (`f1c24282`) updating `status`/`swept`/
  `swept_basis` frontmatter — legitimate, matches `docs/plans/README.md`'s
  regenerated summary and the new `docs/plans/PLAN_TRIAGE_2026-08-07.md`.
- `bom-reconciliation-allowlist.yaml` and `docs/wave4-verdicts.yaml` (new,
  598 and 961 lines) are hand-curated data files with clear provenance
  headers, not generated noise.

## What did not complete

The full `packages/temper-placer/tests/` suite (17974 collected tests) was
run but not to completion — 2309 tests (12.8%) had executed when this
verification was wrapped up, all passing except the 3 pre-existing
`tests/closure/` failures already accounted for above. The machine this
verification ran on is shared by dozens of other concurrent agent sessions
(`ps aux` showed several other unrelated `pytest`/`cargo` processes at
90%+ CPU throughout), which made the full suite far slower than the ~4-8
minutes CI budgets for the equivalent split-out jobs. CI's own actually-gating
subset — `tests/core/` + the two named `tests/validation/` files — **did**
run to completion (1022 passed, 9 skipped, 3 failed as detailed above) and is
the result this verdict rests on for Python test coverage; the broader
partial run found no failure category beyond what the core subset and the
file-identity argument above already explain.

## Method

Two detached, temporary worktrees were created outside the tracked
`.claude/worktrees/` tree (`git worktree add --detach <path> <sha>`) — one at
local `main` (`ecaf45f2`), one at live `origin/main` (`7e1194b7`) — verified,
then removed (`git worktree remove --force`) before this report was written.
Neither `main` nor `origin/main` was checked out, modified, merged, or
pushed by this verification.
