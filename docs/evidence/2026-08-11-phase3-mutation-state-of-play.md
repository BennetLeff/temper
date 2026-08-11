<!-- provenance: commit=0c60dd8159c7f38a14ead94564be520bd00f0731 dirty=true -->

# Phase 3 (fault injection and mutation) — state of play, U3.1–U3.5

**Date:** 2026-08-11
**Commit:** `0c60dd8159c7f38a14ead94564be520bd00f0731` (this session's own fix commit, branched from `origin/main` at `d1b330b90`)
**Dirty:** `true` — the working tree also carries uncommitted changes under `packages/temper-geometry/` at measurement time that belong to a different, concurrently running agent (this session's scope explicitly excludes every crate under `packages/`; those files are untouched and unstaged by this work).
**Plan under assessment:** `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md` §5 (units U3.1–U3.5), which itself defers R42's own unit shape to `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`.

## Method: code and `gh api` are the ground truth, not plan prose

Per this task's own brief, every claim below was checked against the repository at HEAD and, where relevant, executed locally — not read off a plan document. Two things the phase2-4 plan states as fact were found to be **out of date in opposite directions**:

- The phase2-4 plan (written 2026-08-07) says *"R42's named files — `scripts/gate_mutate.py`, `scripts/check_gate_mutations.py` — do not exist... nothing has been built."* **This is false at HEAD.** Both files exist, are non-trivial (538 and ~460 lines respectively), are registered in `scripts/manifest.yaml` with `disposition: ci-gate`, and have their own unit-test suites (`scripts/tests/test_gate_mutate.py`, `scripts/tests/test_check_gate_mutations.py`, 28 tests total). A first sweep was already run and recorded the same day the phase2-4 plan itself claims nothing exists: `docs/evidence/2026-08-07-gate-mutation-sweep.md`, 19/19 mutations KILLED.
- That same 2026-08-07 sweep's clean 19/19 result had **silently regressed to 18/19 (one real SURVIVED mutant) by the time this session re-ran it**, four days later, with no code change to the mutation harness itself in between — a different, unrelated hardening of the real gate's evidence-validation logic broke one canary fixture's assumption. See "A regression, found and fixed" below. This is exactly the pattern this task's brief warned about: a plan claiming a gap that had already closed, sitting next to a real gap that had silently reopened.

## Per-unit verdict

| Unit | Plan's claim (2026-08-07) | State at HEAD, verified 2026-08-11 | Verdict |
|---|---|---|---|
| U3.1 — land R42 | Not built | **Built, and already had one real regression before this session started.** Fixed and CI-wired this session (see below). | **Closed** (was code-complete but silently regressed and CI-unwired; now genuinely green and wired) |
| U3.2 — port R38 onto `wasm32` dispatch | Not started | **Confirmed not started.** `grep -rn "defect\|mutat" packages/temper-drc-rs/src/**/*.rs` finds no defect-mutation test module; no `off-board`/`pad-short`/`creepage-crossing` WASM_TESTS entries. | **Not started.** Blocked this session by scope boundary (`packages/` is owned by other agents this session) |
| U3.3 — port R42 onto `wasm32` dispatch | Not started | **Confirmed not started.** All 7 gates `ci-corpus/mutations.yaml` targets are Python CI scripts (`check_creepage_clearance_drift.py`, `check_drc_ceiling_approval.py`, `check_hv_netclass_coverage.py`, `check_isolation_keepout.py`, `check_measurement_provenance.py`, `check_evidence_provenance.py`, `check_vacuous_gates.py`) — none names a `temper-drc-rs` rule kernel directly, so none is portable to the tier's dispatch surface by U3.3's mechanism as written. | **Not started.** Same scope block as U3.2 |
| U3.4 — volume run for ported tests | Blocked by U3.2/U3.3 | Still blocked — nothing to run at volume until U3.2/U3.3 produce wasm32-side tests. | **Blocked**, transitively |
| U3.5 — Phase 3 verdict | Blocked | Cannot be closed; see verdict statement below. | **Blocked**, transitively |

## U3.1 in detail: what existed, what was broken, what this session fixed

### What existed before this session (2026-08-07 payload)

- `scripts/gate_mutate.py` (538 lines): the mutation engine. Seven axes (`guard-strip`, `condition-invert`, `scope-remove`, `violation-discard`, `comparison-flip`, `threshold-set`, `return-stub`), each a real AST transform against a gate script's committed source, applied only to an in-memory copy or a scratch tempfile — never the checked-out file (verified by `committed_bytes_unchanged`, exercised in CI every run).
- `scripts/check_gate_mutations.py` (~460 lines): the canary-flip runner. For each `(gate, mutation, canary)` triple in `ci-corpus/mutations.yaml`, runs the canary's `pristine`/`seed` functions against the unmutated gate (must match `expected_pristine`/`expected_seed`), then against the mutated gate, and classifies KILLED / SURVIVED / UNVERIFIED / EQUIVALENT / NOT_APPLICABLE.
- `ci-corpus/mutations.yaml`: 19 triples across 7 gates, plus `ci-corpus/canaries/*.py`, one canary module per gate.
- Both scripts registered in `scripts/manifest.yaml` with `disposition: ci-gate`.
- `docs/evidence/2026-08-07-gate-mutation-sweep.md`: the first recorded sweep, 19/19 KILLED, mutation score 1.0000, three initially-surviving mutants triaged and fixed the same session by strengthening canary oracles (never by weakening assertions — KTD4).
- **Not done as of 2026-08-07:** CI wiring. That evidence doc's own closing section explicitly describes (not implements) the wiring, recommending the `consistency-gates` job, no `continue-on-error`.

### A regression, found and fixed

Re-running `uv run --no-sync python scripts/check_gate_mutations.py` at the start of this session (before any change) reproduced:

```
OVERALL: 17 killed, 1 survived, 0 unverified, 0 equivalent -- mutation score 0.9444

SURVIVED MUTANTS (gate blind spots -- triage required):
  scripts/check_drc_ceiling_approval.py :: drc-ratchet-invert-trailer-check
    [drc-ratchet-invert-trailer-check] scripts/check_drc_ceiling_approval.py:274 comparison #2 in run_gate:
    "'Ceiling-Approval:' in commit_messages" -> "'Ceiling-Approval:' not in commit_messages"
```

exit code 1. **Two independent things had drifted since 2026-08-07, neither caused by any change to the mutation harness itself:**

1. **`measurement-invert-freshness-guard` reported NOT_APPLICABLE.** `scripts/gate_mutate.py` locates AST nodes by `(function, node-kind, occurrence-index)`; `ast.walk`'s breadth-first order for `check_measurement_provenance.py`'s `evaluate()` shifted the target `if mismatches:` from index 6 to index 5 as unrelated nested `if` statements earlier in the function changed shape. The drift guard caught it correctly (reported `NOT_APPLICABLE`, did not silently mutate the wrong line) — **but nothing in `check_gate_mutations.py`'s own exit-code logic treated `NOT_APPLICABLE` as a failure**, despite the runner's own module docstring already describing it as effectively a failure mode, and despite an existing test named `test_drifted_locator_is_not_applicable_and_fails` that — before this session — never actually asserted on the exit code, only on the verdict string. Confirmed as a live bug by reproducing it: a hand-built manifest containing only a `NOT_APPLICABLE` triple (no `SURVIVED`, no `UNVERIFIED`) made `main()` return `EXIT_OK` before the fix. Fixed:
   - Re-located the mutation's `index` from 6 to 5 in `ci-corpus/mutations.yaml` (comment explains the drift).
   - Added `SweepReport.not_applicable` and included it in `main()`'s `ok` computation, so `NOT_APPLICABLE` fails the run exactly like `SURVIVED`/`UNVERIFIED` — matching the runner's own documented intent for the first time.
   - Added `scripts/tests/test_check_gate_mutations.py::TestNotApplicable::test_not_applicable_only_sweep_fails_main`, which fails against the pre-fix `main()` body (reproduced: `assert 0 == 1`) and passes post-fix.

2. **`drc-ratchet-invert-trailer-check` genuinely SURVIVED — the exact blind spot 2026-08-07's sweep closed had silently reopened.** Traced with a standalone probe (loaded the real gate, then the mutant, against the canary's `seed_unapproved_raise_with_valid_evidence` fixture directly): the mutant's exit message changed from `EXIT_OK` (2026-08-07's expected kill signal) to
   ```
   FAIL: ceiling raise carries a 'Ceiling-Approval:' trailer but fails the measurement-evidence
   contract (power_pcb_dataset/drc_ceiling.json): temper: provenance measured_at_commit=
   'aaaa...aaaa' does not resolve to a commit -- a measured-live raise must name the commit it
   was measured at
   ```
   `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`'s `validate_raise_evidence` gained a real `git cat-file --batch-check` commit-resolvability check between 2026-08-07 and today (a genuine, unrelated hardening — see that file's own comment at line ~905, which names the exact incident: a syntactically-valid-but-dangling SHA silently passing a shape-only check, "exactly how `drc_ceiling.json` carried an unresolvable `measured_at_commit` for weeks"). The canary fixture's `measured_at_commit` was `"a" * 40` — 40 well-formed hex characters, satisfying the *old* shape-only check, but not a real commit in *any* repository. Once resolvability started being enforced, the fixture's "valid evidence" seed started failing `validate_raise_evidence` for an unrelated reason (an unresolvable commit), regardless of the trailer mutation — silently recreating the exact "coarse oracle can't isolate the one variable that matters" failure mode 2026-08-07's fix (finding 3 in that sweep's evidence doc) explicitly set out to close. **Fixed in the canary fixture, not the gate:** added `_head_sha()` to `ci-corpus/canaries/check_drc_ceiling_approval.py`, which runs `git rev-parse HEAD` against the fixture's own throwaway repo, and used that real, resolvable SHA as `measured_at_commit` instead of the placeholder.

After both fixes:

```
OVERALL: 19 killed, 0 survived, 0 unverified, 0 equivalent, 0 not_applicable -- mutation score 1.0000
```

exit code 0. All 28 unit tests in `scripts/tests/test_gate_mutate.py` + `scripts/tests/test_check_gate_mutations.py` pass.

**Anti-vacuity demonstration (plant/revert/confirm):** the `NOT_APPLICABLE`-exit-code bug above was demonstrated concretely, not asserted: `git stash` the fix, re-run the new test — `assert exit_code == runner.EXIT_FAIL` fails with `assert 0 == 1`; restore the fix — the same test passes. (Note: this session hit a real environment hazard using `git stash` for that demonstration — see "An environment hazard encountered and worked around" below — the demonstration itself is genuine and is recorded in this session's commit history as a revert/restore, not fabricated.) The trailer-check regression above is itself a second, independently-occurring non-vacuity proof: the sweep was observed to *actually fail* for a real reason before either fix landed, not merely asserted capable of failing.

### CI wiring

Wired into `.github/workflows/python-tests.yml`'s `board-provenance-requirements-gates` job (name: `Board, Provenance & Requirements Gates`) as a new step, `Gate-mutation sweep (R42 canary-flip oracle)`, placed after the existing `Board-defect mutation corpus (R38)` step. **Deliberately not `continue-on-error`**, matching this file's own stated convention ("Never `continue-on-error`: a gate that cannot run must exit non-zero") and the gate's own exit-code contract.

**This deviates from `docs/plans/2026-08-02-035`'s U4, which recommended the `consistency-gates` job — for a specific, checked reason:** `board-provenance-requirements-gates` is the job that *already* builds `temper_placer`/`temper_drc_rs` (this gate's own runtime dependency, via `check_isolation_keepout.py`'s `temper_placer.core.isolation_constants` import) **and already runs six of the seven targeted gates individually** (`check_isolation_keepout.py`, `check_hv_netclass_coverage.py`, `check_drc_ceiling_approval.py`, `check_measurement_provenance.py`, `check_evidence_provenance.py`, `check_vacuous_gates.py` — the seventh, `check_creepage_clearance_drift.py`, is present but commented out pending a separate, unrelated human decision recorded in that job's own comment block). `consistency-gates` builds the same Rust extensions but does not run any of these seven gates, so co-locating the mutation sweep with the gates it targets is a strictly better fit than the plan's original (written before this session re-verified which job actually owns which gates).

**Also deliberately does not touch `.github/required-checks.json`**, per this session's explicit scope boundary — and this is not merely a scope-following omission: `scripts/check_required_checks.py`'s `job_should_run` treats any path that matches none of a job's specific `trigger_paths`, none of `catch_all_paths`, and none of `mapped_to_nothing` as a **residual (unmapped) path that runs every path-conditional job** (fail-safe, not fail-silent). `ci-corpus/**` is exactly such a residual path today — it is not named in `board-provenance-requirements-gates`'s trigger set, but `scripts/**` already is (via `catch_all_paths`), and `ci-corpus/**` changes alone would still trigger every job via the residual-path rule. Confirmed by reading `scripts/check_required_checks.py:615-667` and `.github/required-checks.json`'s `catch_all_paths`/`mapped_to_nothing` arrays directly; not asserted from the plan text.

**`board-provenance-requirements-gates` ("Board, Provenance & Requirements Gates") is not in `required_contexts`** (`.github/required-checks.json`'s `required_contexts` array: `Rust Checks (cargo check + clippy)`, `Cross-Source Consistency Gates`, `Core Tests`, `Fast Gates`, `Cargo / Rustc Smoke Check`, `Invariant tests (router_v6 group 3)`, `Repo Hygiene & Import Gates`, `PR Performance Comparison` — eight names, this job is not among them). This was a **precondition**, checked before wiring, not an afterthought: the sweep was genuinely red (1 real SURVIVED mutant, exit 1) when first re-run this session, and wiring an already-red gate into a job inside `required_contexts` would have broken every concurrently open PR's required checks — including the other agents' PRs running in parallel this session — for a real but unrelated-to-them finding. Because the regression was fixed first (see above) and the sweep is now genuinely green, this precaution did not end up mattering for correctness, but it shaped the order of work: fix-before-wire, not wire-then-hope.

**Lint verification:** `actionlint -ignore 'constant expression "false" in condition'` (the exact invocation `.github/workflows/lint-workflows.yml` runs) exits 0 against the edited workflow file. YAML parses cleanly.

## U3.2 / U3.3: confirmed not started, and explicitly blocked this session by scope

The phase2-4 plan's own §0 already stated Phase 3's "already in flight" framing was misleading because R42 (unlike R38) had no landed code as of 2026-08-07 — that specific claim is now stale (R42 exists), but the *deeper* claim — that **porting either R38 or R42 onto `temper-drc-rs`'s `wasm32` dispatch surface is real, unstarted work** — is confirmed accurate at HEAD:

- `grep -rn "defect\|mutat" packages/temper-drc-rs/src/**/*.rs` (excluding comments referencing "mutators" on unrelated Python objects, or documentation prose) finds no defect-injection test module, no `off-board`/`pad-short`/`creepage-crossing` fixture, and no `WASM_TESTS` entry that registers a mutation-corpus test. `packages/temper-drc-rs/src/wasm_test_registry.rs` currently aggregates 34 `WASM_TESTS` const arrays; none is defect/mutation-shaped.
- `ci-corpus/mutations.yaml`'s 19 triples target seven Python CI scripts, none of which names a `temper-drc-rs` rule kernel directly — `check_isolation_keepout.py`, `check_hv_netclass_coverage.py`, etc. operate over `elec/*.ato` source, `pcb/temper.kicad_pcb`, and `temper_placer` config, not over `temper-drc-rs`'s in-process `BoardState`/rule-kernel API. None of U3.3's "(gate, mutation, canary) triple that names a `temper-drc-rs` rule as the gate" precondition exists in the current manifest.

**This session did not attempt U3.2 or U3.3.** The task's own scope boundary is explicit and was treated as binding: *"Do NOT touch: any crate under `packages/` (all nine are owned by other agents right now)."* Both U3.2 (constructing mutated `BoardState` fixtures directly in `temper-drc-rs` Rust code) and U3.3 (re-expressing R42's gate-mutation triples against `temper-drc-rs` rule kernels) require editing `packages/temper-drc-rs/src/`, which this scope boundary forecloses this session — not a technical blocker, a session-scoping one. The phase2-4 plan's own estimate (`docs/plans/2026-08-07-002-...md` §10, "not attempted here... not large per class, but not a thin wrapper either") stands unverified either way; nothing here confirms or refutes its sizing, since no attempt was made.

## U3.4 / U3.5: blocked, transitively

U3.4 (volume run across ported R38/R42 tests) needs U3.2 and U3.3's output to exist; neither does. U3.5 (Phase 3 verdict) needs U3.1–U3.4 closed. Per the phase2-4 plan's own U3.5 template:

> **Phase 3 partially established.** R42's own machinery (the mutation engine, the canary-flip runner, the 19-triple manifest against 7 fail-closed CI gates) is now genuinely green (19/19 KILLED) and wired into CI as a real, non-`continue-on-error` gate — closing U3.1, including repairing a real regression this session found. **Neither R38 nor R42 runs on the tier's `wasm32` dispatch surface** — U3.2 and U3.3 remain fully unstarted, blocked this session by the `packages/` scope boundary rather than by any technical obstacle identified. U3.4 (volume) and U3.5 (this verdict, considered closed) cannot be completed until a future session with `packages/temper-drc-rs` write access attempts U3.2/U3.3. Findings from the U3.1 work (the regression, and the two related-but-out-of-scope corpora below) route into the burn-down per D8/R12 as findings, not as Phase 3 closure.

## Related findings, adjacent to Phase 3's named units but not directly in scope

Found while establishing ground truth; none of these is R38 or R42, so none was acted on this session beyond recording — but each is the same shape of gap (`disposition: ci-gate` in `scripts/manifest.yaml`, genuinely runnable, zero CI wiring) and is a reasonable next candidate for whoever picks up mutation/fault-injection work next:

- **`scripts/check_component_defect_corpus.py`** (`disposition: ci-gate`, `scripts/component_defect_mutator.py` alongside it): runs clean locally with no `kicad-cli` dependency — `uv run --no-sync python scripts/check_component_defect_corpus.py` reports `PASS -- 2/2 classes covered` (`fabricated-mpn`, `mpn-value-mismatch`). `grep -n "check_component_defect_corpus\|component_defect_mutator" .github/workflows/*.yml` returns nothing — not wired anywhere, and unlike R42 this gap was never previously closed and then reopened; it appears to simply never have been wired.
- **`scripts/check_ceiling_raise_evidence_corpus.py`** and **`scripts/check_corpus_specificity.py`**: named in `docs/evidence/2026-08-07-fault-injection-coverage-number.md` (the STRATEGY.md build-order steps 4–5 coverage measurement, 10/11 defect classes caught) as part of the same fault-injection landscape. Neither appears in any `.github/workflows/*.yml` either.
- **`tools/wasm/test_family_map.json`'s `canary_defects` block** (read-only per this session's scope — that file belongs to other agents' work) is a *different*, pre-existing (Phase 0/1) mechanism: one hand-picked mutation per wasm-tier rule family (8 entries: `drc`, `dfm`, `emc`, `placement`, `routing`, `safety`, `types`, `integration`), used as a minimal non-vacuity proof that the tier's dispatch harness can detect a broken kernel at all — not a mutation corpus at R38/R42's scale, and not itself evidence toward U3.2/U3.3 (it predates this Phase 3 unit breakdown and was not built by it). Distinguishing it from R38/R42 here because it is easy to mistake for prior Phase-3 progress on first grep.

None of the three items above was wired, fixed, or otherwise modified this session — flagged, not acted on, consistent with staying inside this session's stated scope (`scripts/*mutation*`, `scripts/*mutate*`, `scripts/*defect*`, `ci-corpus/**`, `docs/evidence/**`, and one CI step already spent on R42).

## An environment hazard encountered and worked around

Mid-session, `git stash push` / `git stash pop` was used to A/B-test whether a test failure was pre-existing (per this task's own instruction to verify a red/main state before attributing it). The `pop` returned a **different agent's stash entry** (`On worktree-agent-a5c0b5cffc7f8b7c0: pc2-wip`, not this session's own `wip-phase3` push), and this session's own uncommitted edits to all five touched files were lost from the working tree in the process. Root cause, confirmed via `git fsck --unreachable` and `git reflog` (which showed two unattributed `reset: moving to HEAD` entries): **`refs/stash` is a single, non-worktree-scoped ref shared across every concurrently running agent's `git worktree` checkout of this repository**, unlike `HEAD`/the branch pointer, which are correctly worktree-private. All five edits were reconstructed from this session's own record of the exact changes made (not re-derived or guessed) and re-verified (tests green, sweep 19/19, actionlint clean) before committing. **Practical consequence for future sessions in this environment: avoid `git stash` entirely when multiple agents may be running concurrently against worktrees of the same repository — commit early and often instead**, since branch refs (unlike `refs/stash`) are correctly isolated per worktree.

## Reproducing this session's work

```
uv sync --all-packages --inexact --no-install-package temper-rust-router \
  --no-install-package temper-drc-rs --no-install-package temper-constraints
uv run maturin develop --release --manifest-path packages/temper-drc-rs/Cargo.toml
uv run --no-sync python -m pytest scripts/tests/test_gate_mutate.py scripts/tests/test_check_gate_mutations.py -v
uv run --no-sync python scripts/check_gate_mutations.py
```

Expect: 28/28 tests pass; the sweep reports `19 killed, 0 survived, 0 unverified, 0 equivalent, 0 not_applicable -- mutation score 1.0000`, exit code 0.

## Files touched this session

- `ci-corpus/mutations.yaml` — re-located `measurement-invert-freshness-guard`'s drifted AST index (6 → 5).
- `ci-corpus/canaries/check_drc_ceiling_approval.py` — `seed_unapproved_raise_with_valid_evidence` now uses a real, resolvable `git rev-parse HEAD` commit SHA instead of a `"a" * 40` placeholder.
- `scripts/check_gate_mutations.py` — `SweepReport.not_applicable`, `main()`'s exit-code condition now includes it, `print_report` surfaces `not_applicable` counts and lists NOT_APPLICABLE triples explicitly (previously only referenced in the UNVERIFIED block's label text without ever appearing there), module docstring corrected to match.
- `scripts/tests/test_check_gate_mutations.py` — new regression test for the exit-code fix, reproduced failing pre-fix.
- `.github/workflows/python-tests.yml` — one new step, `Gate-mutation sweep (R42 canary-flip oracle)`, in the `board-provenance-requirements-gates` job.
- This document.

## Sources / Research

- `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md` §5 (U3.1–U3.5), §0 (Phase 3 state as understood 2026-08-07).
- `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md` (R42's own implementation plan, U1/U2/U4).
- `docs/evidence/2026-08-07-gate-mutation-sweep.md` (the first sweep, 19/19 KILLED, and the three findings whose fixes this session partially re-verified — one of which, finding 3, had silently regressed).
- `docs/evidence/2026-08-02-board-defect-corpus.md`, `docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md` (R38, off-tier, already wired into `board-provenance-requirements-gates` as `Board-defect mutation corpus (R38)` — confirmed via direct read of `.github/workflows/python-tests.yml`, not re-derived).
- `docs/evidence/2026-08-07-fault-injection-coverage-number.md` (the broader fault-injection landscape context for the "related findings" section — `check_component_defect_corpus.py`, `check_ceiling_raise_evidence_corpus.py`, `check_corpus_specificity.py`).
- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py` (the real, unrelated hardening — commit-resolvability enforcement — that caused this session's canary regression).
- `scripts/check_required_checks.py:615-667` (`job_should_run`'s residual-path fail-safe, the basis for not editing `.github/required-checks.json`).
- `.github/required-checks.json` (`required_contexts`, `catch_all_paths`, `mapped_to_nothing`, `job_triggers` — read directly to confirm `board-provenance-requirements-gates` is not a required context and that `ci-corpus/**` reaches it via the residual-path rule without any manifest edit).
