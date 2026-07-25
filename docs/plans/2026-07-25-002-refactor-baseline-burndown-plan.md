---
title: "refactor: Baseline Burn-Down"
type: refactor
status: active
date: 2026-07-25
---

## Goal

The repo's dominant slop pattern is freezing current badness into a file instead of
fixing it — the same move as marking 86 plans "active." Of ~10 baseline-enforcing
mechanisms audited, half are decorative: `continue-on-error: true`, a disabled
feature flag, or a code path never invoked. Fix the wiring, then burn the debt down
under a mechanical ratchet instead of a comment promising future rigor.

## Inventory

Commands run: `git log --follow --numstat`, `grep -rn` over `.github/workflows/`,
direct reads of each gate script. "Gate actually runs?" = blocks a PR today, not
"exists and is invoked at all."

| Artifact | Entries now | Enforced by | Gate actually runs? | Growing? | Verdict |
|---|---|---|---|---|---|
| `deadcode-baseline.py` | 82 | `scripts/vulture_gate.py` (python-tests.yml, no continue-on-error) | **LIVE** — blocks new/stale finds | Churns, not shrinking: 508 lines added / 426 removed since seed (2026-06-22); one commit (`bd8bb68e`) added 85 with 0 removed | burn-down |
| `import-linter-baseline.yaml` | 0 | `import_linter_gate.py` | **LIVE** | Empty and stable 32 days (since `2334d647`, 2026-06-23) | obsolete — collapse the concept, gate on zero directly |
| `import-linter-allowlist.yaml` | 18 | `import_linter_gate.py` | **LIVE** (membership check only — no size comparison across commits) | Shrunk 164→18 since 2026-06-22; frozen-with-ticket policy stated in-file since 2026-07-06 but not mechanically checked | mixed: ~12 promote (ticketed, real router-v6 boundary exceptions), ~6 burn-down (Phase-3 per-file globs) |
| `power_pcb_dataset/drc_ceiling.json` | 1 board entry (158 err / 578 warn) | `ci_check_drc.py` via `make regression`/`make perf-regression` | **DEAD** — both steps `continue-on-error: true`; job only runs on push-to-main, never PRs | Was silently broken 2026-07-15→07-17 ("never-achievable ceiling", own commit message) before being retightened | fix wiring first, then burn down |
| `power_pcb_dataset/timing_baselines.yaml` | 145 stage entries | `temper timing tighten` in metrics-record.yml, post-merge only | **DEAD** — behind `FEATURE_AUTO_BASELINE_TIGHTEN` (defaults `false`) + continue-on-error; also listed as a python-tests.yml path filter that invokes nothing | Unmeasured net growth — mechanism has run 0 verified times | dead gate — decide: wire live or delete |
| `power_pcb_dataset/baselines/` (`temper_production_baseline.yaml`) | 1 snapshot file | 2 pytest files (`test_phase1_anti_false_zero.py`, `test_temper_production_board_routing.py`) inside a `continue-on-error: true` step | **SOFT** — runs, doesn't block | 18 commits in 3 days (2026-07-15→18), values move both directions | keep as fixture; un-soften the step or accept it's advisory |
| `power_pcb_dataset/corpus/*/baseline.json` (5 boards) | 39+ metrics/board | `placer-regression.yml` "Run corpus regression" + "Check for baseline changes without approval" | **DEAD** — both steps `continue-on-error: true` | At least one ceiling *loosened*: `final_loss` 4858→6000 (`1a3e6f80`, 2026-06-29) | policy is load-bearing (`BASELINE_POLICY.md` + `bless_baselines.py` are the right design) — un-soften enforcement, don't rewrite the policy |
| `.coverage-allowlist` | 1943 lines | `check_coverage_gate.py` | **DEAD** — explicit `\|\| echo "::warning ... gate is warn-only"` + continue-on-error | 193→1943 in one commit (`6b869752`, 2026-07-22): +1862/−112 | burn-down — largest single artifact by an order of magnitude |
| `.loc-allowlist.txt` | 19 entries | `tools/loc_cap_check.py` ("LOC Cap Gate" job) | **LIVE** | 14 sampled commits, all upward cap bumps (e.g. `1110→1187`), 0 downward events observed | gate blocks *silent* growth but the ceiling itself only ratchets up — needs a real shrink requirement |
| `.typecheck-allowlist` | 55 lines | `check_typecheck_gate.py` (default mode, "monotonic-shrink baseline" job) | **PARTIAL** — per-file cap is LIVE; `--check-shrink` cross-commit mode exists in the script and is **never invoked** in any workflow | Heavy churn, net shrink 2026-06-29→present but not mechanically required | unwired gate (class 3) — wire `--check-shrink`, then burn down |
| `.physics-provenance-allowlist` | 9 lines | `check_physics_provenance.py`, invoked in both default and `--check-shrink` mode | **LIVE**, best-wired of the set | Added once (2026-07-22), stable since | template for the others — no action needed |

**Meta-finding:** 32 `continue-on-error: true` steps across workflows share the
comment `hard-fail after 2026-09-01` (one shared ticket, `temper-N6-U8`). That
single deadline is currently the only thing standing between 5 of the above
artifacts and real enforcement. `scripts/check_traceability.py` (dead-wired per
`docs/plans/README.md`) is the same failure class, already documented — this
audit found it recurring at least 4 more times independently.

## Classification

| Class | Count | Artifacts |
|---|---|---|
| Burn-down (genuine deferral) | 82 + ~6 + 1943 + 55 = **2086 entries** | deadcode-baseline.py, import-linter-allowlist.yaml (Phase-3 globs), .coverage-allowlist, .typecheck-allowlist |
| Promote-to-rule (load-bearing intent) | 3 mechanisms | import-linter-allowlist.yaml (ticketed core-isolation entries), corpus `BASELINE_POLICY.md` + `bless_baselines.py`, `.physics-provenance-allowlist` design |
| Obsolete | 1 | import-linter-baseline.yaml (empty 32 days — the baseline concept itself, not the gate) |
| Dead gate wiring (fix before burning down) | 5 | drc_ceiling.json, timing_baselines.yaml, corpus baseline.json, .coverage-allowlist, .typecheck-allowlist `--check-shrink` |

## The 20 dead CLI params (`cli/__init__.py:298–325`)

Verified with `grep -rn` across `packages/`, `docs/`, and the full 365-line body of
`optimize()` (lines 293–657): every one of `weight_overlap`, `grad_norm`,
`multi_seed`, `ccap`, `spice_validate`, etc. appears **only** in the function
signature — zero references in the body, zero in config schemas, zero in string
dispatch. `skip_topological` is the one exception worth flagging: it is genuinely
wired elsewhere (`pipeline/state.py`, `dag_engine.py`, `configs/pipeline_default.yaml`
`skip_if`) — the *CLI option* is dead, not the concept.

This is not a new pattern: `docs/solutions/workflow-issues/dead-code-from-features-with-no-activation-surface-2026-07-01.md`
documents this exact failure (CLI flag exists, feature never wired) for `ccap` and
`precluster` specifically, five weeks before this audit. It recurred.

**Verdict: burn down.** Delete the ~20 params and their `@click.option` decorators
together (they were never load-bearing), or wire each to config in the same PR that
removes its baseline entry. Either way, `deadcode-baseline.py` should drop by ~20
lines as a direct, checkable side effect.

## Requirements

- **R1 (ratchet rule).** Every baseline/allowlist file gets a CI check comparing
  entry/line count against the same file on `origin/main`. Growth fails unless the
  commit message carries an explicit override token (extend `BASELINE_POLICY.md`'s
  `Ceiling-Approval:` convention repo-wide, applied mechanically — not by comment
  convention alone, per `.loc-allowlist.txt`'s current gap).
- **R2 (fix dead wiring).** Remove `continue-on-error: true` from: the coverage
  gate step, both DRC-ceiling regression steps, both corpus-baseline steps
  (placer-regression.yml), and the timing auto-tighten step — or replace each with
  an explicit, dated, tracked decision instead of the shared `temper-N6-U8`
  stub. Wire `check_typecheck_gate.py --check-shrink` into the `type-check` job.
- **R3.** Move `power_pcb_dataset/drc_ceiling.json` enforcement onto the PR path
  (currently push-to-main only) so it can't silently break for two days again.
- **R4.** Collapse `import-linter-baseline.yaml`: after 32 days at zero, gate on
  "any violation fails" directly; delete the baseline-diff indirection.
- **R5.** Burn down the 20 dead CLI params in one PR: delete unused params/options,
  or wire them and add a CLI-path integration test per
  `dead-code-from-features-with-no-activation-surface-2026-07-01.md`'s guidance.
  Either path shrinks `deadcode-baseline.py` by the same PR.
- **R6.** Burn down `.coverage-allowlist` (1943 lines) against real coverage
  numbers — do not let "Phase 1 paydown prerequisite" remain the permanent state.
  UNMEASURED: current `temper_placer` coverage % (not run in this audit).
- **R7.** Re-classify `import-linter-allowlist.yaml`'s 18 entries individually:
  ticketed core-isolation entries (promote), Phase-3 per-file globs (burn down —
  `tools/benchmark_router.py`, `tools/demo_explainability.py`).

## Ordering (cheapest / most provable first)

1. R4 — delete the empty-baseline indirection (no behavior change, single file).
2. R2's typecheck `--check-shrink` wiring (script already exists, one workflow line).
3. R5 — dead CLI params (isolated file, mechanical, shrinks the biggest live gate).
4. R3 — move drc_ceiling.json onto the PR path.
5. R2's remaining `continue-on-error` removals, one gate at a time, verifying each
   passes clean before flipping it live (avoid re-breaking CI wholesale).
6. R1 — generic ratchet check, once individual gates are live and stable.
7. R6 — coverage burn-down (largest, slowest, needs real test-writing, not scripting).
8. R7 — human judgment call on the remaining 12 import-linter entries.

## Out of scope

- Rewriting `BASELINE_POLICY.md` or `bless_baselines.py` — design is sound, only
  enforcement is soft.
- `power_pcb_dataset/quarantine/baseline.json`, `docs/benchmarks/v5_baseline_*.json`,
  `.enola/baseline` — historical snapshots, not enforced gates; not audited here.
- Per-entry adjudication of the 82 vulture findings and 55 typecheck errors —
  R5/R6 start the mechanism; clearing the backlog is separate follow-up work.
- Router/placer hygiene track — halted per `STRATEGY.md`; this plan does not
  reopen it.

## Review record (2026-07-25)

Independently re-verified before acceptance. Every load-bearing claim held:

| Claim | Verified |
|---|---|
| `.coverage-allowlist` = 1943 lines | exact |
| `import-linter-baseline.yaml` empty | `violations: []` |
| `check_typecheck_gate.py --check-shrink` never invoked in any workflow | confirmed |
| 32 `continue-on-error` steps share the `2026-09-01` comment | confirmed |
| ~20 CLI params signature-only | confirmed (`ccap`, `grad_norm`, `multi_seed`, `spice_validate` absent from the 293–657 body) |
| `skip_topological` wired elsewhere, CLI option dead | confirmed — `dag_engine.py:141`, `state.py:61`, `dag_schema.py:33`, `pipeline_default.yaml:23` |

Two corrections, both **under**-reports in the plan's favour:

1. **36** `continue-on-error: true` steps exist, not 32. Thirty-two carry the
   `hard-fail after 2026-09-01` / `temper-N6-U8` comment; **four carry no
   comment or ticket at all** and are unaccounted. R2 should cover all 36.
2. `check_coverage_gate.py` also defines a `--check-shrink` mode that no
   workflow invokes — the same class-3 defect as `check_typecheck_gate.py`.
   R2 should wire both.

Add to R2's scope: `scripts/check_traceability.py`, which exits 1 today and is
invoked by no workflow step (`docs/plans/README.md`). That makes **seven**
independent instances of dead gate wiring found in a single day — enough that
R1 should also require a CI check asserting every gate script in
`scripts/manifest.yaml` with `disposition: ci-gate` is actually invoked by some
workflow.
