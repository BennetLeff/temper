# Open-PR backlog triage — `Required Python Tests = FAILURE`

**Date:** 2026-08-05
**Scope:** all 53 open PRs; 51 carry `Required Python Tests = FAILURE`
**Method:** `gh` API only — check-run rollups per head SHA, then the aggregator's
own job log for the `FAIL:` line and its `failed: <context>` line, then the named
failing job's log for the specific step. No branches were cloned.

---

## 0. How to read this document

`Required Python Tests` is an aggregator. It does not run tests; it watches the
candidate contexts that the changed paths select (`.github/required-checks.json`)
and reports one of three verdicts. Every classification below is anchored on that
verdict, quoted verbatim from the aggregator's job log.

Two failures are **excluded from every diagnosis** because they are red on `main`
and inherited by every PR, and neither is a required context:

| Context | Why it is red on `main` |
|---|---|
| `golden-check`, `regression` | #771 removed 48 zero-length track segments, un-masking 17 suppressed `via_dangling` warnings (`489 > 472`). Known, accepted, awaiting a `Ceiling-Approval:` trailer. |
| `Board, Provenance & Requirements Gates` | Red on **every** `main` run from 2026-08-04T06:48 through 2026-08-05T17:12 (40/40 completed runs sampled). Three independent causes — see §5. |

Neither appears as a cause for any PR below.

---

## 1. Bucket table

| Bucket | Count | Aggregator verdict | Action |
|---|---:|---|---|
| **A** — Inherited: trigger-list divergence | 5 | `FAIL: Python Tests trigger lists diverge from required-checks manifest` | Rebase (see §2 — **held**, with reason) |
| **B** — Capacity timeout | 23 | `FAIL: candidate checks did not reach a complete success before timeout` | Re-run when the queue drains |
| **C** — Real candidate failure | 22 | `FAIL: an applicable candidate check failed` | Per-PR, see §4 |
| **D** — Unknown / still running | 1 | — | Re-triage |
| **E** — No aggregator run | 2 | — | Out of scope |
| **Total open PRs** | **53** | | |

Bucket C decomposes further, and this is the load-bearing result of the triage —
**8 of the 22 "real" failures are not the PR's fault**:

| Sub-bucket | Count | PRs |
|---|---:|---|
| C1 — Inherited from `main`, PR is blameless | 8 | #562, #697, #719, #722, #724†, #730, #731†, #741 |
| C2 — PR-owned defect, needs the author | 11 | #563, #565, #583, #609, #611, #695, #702, #721, #724†, #749, #750 |
| C3 — Perf-baseline infrastructure gap | 4 | #721†, #731†, #737, #755 |
| C4 — Suspect false perf regression | 1 | #751 |
| C5 — Stale, recommend closure | 1 | #516 |

† PRs with two independent causes are counted in both sub-buckets.

---

## 2. Bucket A — inherited trigger-list divergence (5 PRs)

**PRs:** #639, #640, #641, #642, #643 — all Dependabot, all `uv.lock` only.

**Evidence.** Each PR's *only* failing check is the aggregator, and its log
contains exactly one line:

```
FAIL: Python Tests trigger lists diverge from required-checks manifest
```

The aggregator never reached the point of computing a candidate list (no
`changed files:` line in any of the five logs), so nothing else was even
evaluated. The gate is `validate_trigger_manifest()` in
`scripts/check_required_checks.py:255`.

**Parity is restored on `main`.** Verified directly against the tree at
`4db228e19`:

```
load_manifest(.github/required-checks.json)
validate_trigger_manifest(manifest, .github/workflows/python-tests.yml)
→ PARITY OK
```

**Rebase status: HELD, deliberately — 0 of 5 performed.**

The stale-base cause is fixed, but a *second* stale-base breakage is live on
`main` right now (§3): the `temper_design_bundle_python` stub is a syntax error,
which fails `Type Check`. `uv.lock` is in `catch_all_paths`, so a Dependabot
rebase makes **every** required context a candidate — including `Type Check`.
Rebasing these five today spends five full CI runs for a guaranteed red.

They are proven-ready. Rebase all five the moment the §3 fix lands.

---

## 3. `main` is red on `Type Check` — stub syntax error (fixed in this PR)

`packages/temper-placer/stubs/temper_design_bundle_python/__init__.pyi` on
`origin/main` carries three stray `) -> LoopCollection: ...` lines — merge
residue from the Wave-4 stub merges, the same class of defect as `abb94784b`
("remove orphan diff3 conflict markers from stub").

```
$ ast.parse(git show origin/main:…/__init__.pyi)
SyntaxError line 581: unmatched ')'
```

It landed between `c74be4347` (17:12, 1 occurrence — clean) and `f26e92fd6`
(18:44, 4 occurrences — corrupt), and is still present at `4db228e19`.

**Blast radius.** mypy cannot parse the stub, so it analyses nothing else in the
placer package. `Type Check` then reports the collapse rather than the cause:

```
NEW: packages/temper-placer/stubs/temper_design_bundle_python/__init__.pyi has 1 errors (not in allowlist)
Total (excl. call-arg): 1 errors in 1 files (baseline: 209)
  27 stale allowlist entries — update with --init to lock in improvements
```

The `27 stale` line is the tell: 27 files that legitimately carry errors reported
zero, because they were never analysed. **Do not "fix" this by running `--init`**
— that would erase a real allowlist and mask the parse failure.

**Proof this is `main`'s fault and not the PRs'.** #722 and #730 both appear in
their GitHub diffs to *remove* the stray lines, yet both fail. Comparing the
actual blobs settles it:

| Ref | stray count | parses? |
|---|---:|---|
| #722 head `ee79a2162` | 1 | OK |
| #730 head `e1616e64e` | 1 | OK |
| #722 CI merge ref `f6df98961` | 4 | `SyntaxError line 581` |
| `origin/main` `4db228e19` | 4 | `SyntaxError line 581` |

Both PR heads are clean. The three-way merge with `main` re-introduces the
strays, because `main` added them independently after the branch point. The
apparent "fix" in their diffs is an artefact of diffing against the merge base.

**Repair applied in this PR:** delete the three stray lines. One-shape,
mechanical, verified with `ast.parse`. It unblocks `Type Check` for #719, #722,
#730, #731 and for every future PR that touches a `catch_all_path`.

---

## 4. Bucket C — per-PR diagnosis

### C1 — inherited from `main`; the PR is blameless

| PR | Failing candidate | Specific defect | Proof it is inherited |
|---|---|---|---|
| #719 | `Type Check` | stub parse failure (§3) | PR changes **2 files, both `docs/evidence/`** — it contains no typed Python at all. Its base `c5875adad` failed `Type Check` on `main` with the identical `NEW: …__init__.pyi has 1 errors`. |
| #722 | `Type Check` | stub parse failure (§3) | Head blob parses OK; CI merge ref does not (table in §3). |
| #730 | `Type Check` | stub parse failure (§3) | Head blob parses OK; CI merge ref does not. |
| #731 | `Type Check` | stub parse failure (§3) | Base `c5875adad` failed identically on `main`. (Also C3.) |
| #697 | `Invariant tests (router_v6 group 3)` | `test_astar_runtime_monitor.py::test_monitor_no_overhead_when_inactive` — `Monitor overhead 55.6% exceeds 50% threshold` | `main` at `c60825861` fails the **same test**: `overhead 58.2% exceeds 50%`. A wall-clock ratio on a 0.02 s baseline; the threshold is not calibrated for CI jitter. #697 migrates `metrics/` analysers and cannot touch the A* monitor. |
| #741 | `Core Tests` | `test_trace_analyzer_rust_differential.py::test_differential_random_stress` — `assert '0x1.3f006cfc844dbp+8' == '0x1.3f006cfc844dap+8'` | `main` at `90bc85a97` fails with the **byte-identical** hex pair. #741 changes 9 files, all `docs/evidence/`. |
| #724 | `Core Tests` | same 1-ULP mismatch as #741 | Same as above. (#724's *`Type Check`* failure is separate and PR-owned — see C2.) |
| #562 | `Type Check` | `REGRESSION: …/cp_sat/_encoder_solve.py: 2 errors > 1 allowed` | PR changes **4 files, all `docs/`**. It cannot move a mypy count in `_encoder_solve.py`. Stale Aug-2 base. |

The 1-ULP differential is a real standing defect worth its own ticket: a
Rust↔Python differential asserting **bit-exact** float equality will fail
intermittently forever. It is not a PR problem and must not be triaged as one.

### C2 — PR-owned defect

| PR | Failing candidate | Specific defect |
|---|---|---|
| #563 | `Generated Repo State` | `DRIFT: generated state differs from committed in: docs/plans/README.md`. Adds two plan docs without regenerating the index. Fix: `uv run python scripts/gen_repo_state.py`. |
| #565 | `Generated Repo State` | Same drift. Adds `2026-08-01-003-…-rescope-plan.md` (1 file) without regenerating. |
| #583 | `Generated Repo State` | Same drift. Adds `2026-08-02-001-…-change-driven-ci-plan.md` (1 file) without regenerating. |
| #609 | `Core Tests` | `test_gate_input_registry.py::test_every_invoked_ci_gate_script_is_registered` — 5 scripts invoked by `python-tests.yml` are absent from `gate_input_registry._CI_SCRIPT_SURVEY`: `check_netlist_board_reconciliation.py`, `check_board_defect_corpus.py`, `check_hv_netclass_coverage.py`, `generate_kicad_dru.py`, `check_netlist_mutation_corpus.py`. #609 *introduces* this invariant, so it owns closing it — each needs a covered or documented-non-covered entry. Judgement call per script; not mechanical. |
| #611 | `Type Check` | `NEW: …/regression/drc_ratchet.py has 1 errors (not in allowlist)`, `Total 215 (baseline: 214)`. The PR's own new file. |
| #695 | `PR Performance Comparison` | `NO_BASELINE` for `drc-inflate/synthetic/drc_proxy_score` and `…/smooth_relu_array` — a **new** module the PR adds. Correct gate behaviour: capture a baseline. Distinct from C3. |
| #702 | `Repo Hygiene & Import Gates` | `STALE BASELINE ENTRIES` — 13+ pins in `scripts/deadcode-baseline.py` for `cli/__init__.py:298…317` that the PR's edits shifted. Mechanical: delete the stale lines. |
| #721 | `Repo Hygiene & Import Gates` | `NEW DEAD CODE`: `tests/pcl/test_parse_utils_rust_differential.py:111` and `tests/pcl/test_pcl_rust_pbt.py:314` — `unsatisfiable 'ternary' condition` in the PR's own new tests. A real test bug (a branch that can never run), not a baseline miss. |
| #724 | `Type Check` | `REGRESSION: …/core/board.py: 6 errors > 1 allowed`, `Total 243 (baseline: 214)`. The PR's own pyclass migration. |
| #749 | `Repo Hygiene & Import Gates` | `NEW DEAD CODE`: 13 unused `restore_kernels` bindings in the PR's new `tests/router_v6/test_dfm_pbt.py`. |
| #750 | `Repo Hygiene & Import Gates` | `NEW DEAD CODE`: 13 unused `restore_kernels` bindings in the PR's new `tests/router_v6/test_quality_metrics_pbt.py`. Same shape as #749 — a shared fixture idiom that assigns a restore handle and never calls it. Worth fixing once and applying to both. |

### C3 — perf-baseline infrastructure gap, not a PR defect

| PR | Message |
|---|---|
| #721 | `loaders/synthetic/loaders: no baseline row, and this benchmark already exists on main` |
| #731 | 8+ modules, all `…no baseline row, and this benchmark already exists on main` |
| #737 | 6+ modules, same message |
| #755 | 4 `drc-geometry/synthetic/*` benchmarks, same message |

The clause **"and this benchmark already exists on main"** is the gate telling us
the *baseline capture* is short, not that the PR added an unbaselined module. In
#695's log the captured baseline was 12 rows for a matrix many times that size.
This is one bug in baseline capture on `main` (there is already a
`fix/perf-ab-baseline-capture-on-main` branch), not four PR problems. Do not ask
four authors to hand-capture baselines.

### C4 — suspect false perf regression

**#751** — `parse-engine/synthetic/parse_kicad_pcb: rust_over_oracle_ratio
regressed +48.5% (baseline 0.052907 → PR 0.078565)`.

Treat as unproven and **re-run before diagnosing**:

- #751 is a **test-only** PR (pinned oracles, RED differentials, PBTs). It has no
  plausible path to the KiCad parse engine's runtime.
- The metric is `rust_over_oracle_ratio` — a quotient of two noisy wall-clock
  measurements, so it carries both timings' noise.
- The harness is independently known to swing `+27.7%` → `-10.8%` on the same
  commit — a 43% spread against a 20% margin. `+48.5%` is outside that, but not
  by enough to convict a test-only diff.

Do not widen the margin. Re-run; if it reproduces on a third run, escalate.

### C5 — stale

**#516** (2026-07-31, `docs(handoff): CI enforcement state and outstanding board
defects`) — `Rust Checks (cargo check + clippy)` failed with 4 clippy denials in
`packages/temper-rust-router-core/src/astar.rs` (approx `SQRT_2` literal, two
manual assign-ops, redundant `i32` cast). **None of those lines exist on `main`
today** — `astar.rs:114` now only mentions `1.4142135` in a comment. The PR
carries a 40-file snapshot of a Rust tree that has moved on. See §6.

---

## 5. Why `Board, Provenance & Requirements Gates` is red on `main`

Not a required context and not any PR's cause, but it has been red for two solid
days and every PR inherits it. Three independent causes in one job
(`main` @ `c74be4347`, job `92394893963`):

1. **28 evidence-provenance violations** — e.g. `2026-08-02-board-defect-corpus.md`
   cites `commit=d3e99b153…`, which does not resolve to any object in the repo
   (`209 with real commit provenance, 33 allowlisted UNKNOWN, 28 violations`).
2. **`packages/temper-placer/tests/core/_contract_canon.py:144`** — unguarded
   aggregation: `if all(hasattr(value, f) for f in FIELDS):` is vacuously true on
   an empty collection.
3. **Missing `MAINS_SELV_ISOLATION_BARRIER` keepout zone** on the board — the
   long-running #518 defect. This is the gate the whole isolation-barrier PR
   chain in §6 is trying to close.

Each is separately actionable; none is mechanical enough to fix here.

---

## 6. Closure recommendations (recommendations only — nothing was closed)

| PR | Recommendation | Reason |
|---|---|---|
| #562 | **Close — superseded by #563** | #562's file set is a **strict subset** of #563's (all 4 files: both plan docs plus `2026-08-01-isolation-barrier-feasibility.{md,py}`). #563 is the later PR and carries the decision record as well. Verified by file-set comparison, not by title. |
| #551 | **Close or fold into #563** | Shares 3 of its 4 files with both #562 and #563 (`plan-001` + the feasibility evidence pair). Its one unique file is `docs/evidence/2026-08-01-staircase-corridor-feasibility.py`; salvage that into #563 first, then close. |
| #516 | **Close — superseded by the merged Rust work** | Jul-31 handoff snapshot. Its clippy failures reference `astar.rs` code that no longer exists on `main`, and its 40-file diff spans `temper-geometry` / `temper-rust-router-core` / `temper-thermal`, all heavily rewritten since. The *handoff document* may still be worth salvaging as a standalone doc-only PR; the code half is dead. |
| #514 | **Close — targets a dead base** | Base is `codex/drc-burndown-to-zero`, not `main`. It has no aggregator run at all and cannot merge into `main` as-is. Re-cut against `main` if the closeout doc is still wanted. |

**Explicitly not recommended for closure**, despite being old or red:

- #565 depends on #563 landing (it is the post-NO-GO rescope); sequence, don't close.
- #690 → #711 is live, current work — #711 moves R24 to make the barrier
  admissible and directly targets §5 cause 3.
- The `(DO NOT MERGE …)` PRs (#731, #741, #743, #746, #747, #748, #749, #750,
  #751) are held open **by design** as spike verdicts and RED-differential
  evidence awaiting review. Their CI being red is expected and is not a backlog
  problem. They should be reviewed and closed by their authors, not swept.

---

## 7. Needing real engineering

| # | Defect | Owner surface |
|---|---|---|
| 1 | **Bit-exact float differential.** `test_trace_analyzer_rust_differential::test_differential_random_stress` asserts hex-exact equality between Rust and Python and fails on a 1-ULP difference (`…844dbp+8` vs `…844dap+8`). Fails on `main` intermittently; blocks #724 and #741. Needs a ULP tolerance or a documented exact-arithmetic contract. | `tests/validation/` |
| 2 | **Wall-clock ratio in an invariant test.** `test_monitor_no_overhead_when_inactive` compares a 0.018 s baseline to a 0.029 s monitored run against a fixed 50% threshold. Fails on `main`. Blocks #697. Needs a floor on the measured interval or a different observable. | `tests/router_v6/` |
| 3 | **Perf-AB baseline capture on `main` is short.** Benchmarks that demonstrably exist on `main` have no baseline row, failing four unrelated PRs (C3). Root-cause the capture job. | `scripts/pr_perf_compare.py`, the capture workflow |
| 4 | **Evidence-provenance rot.** 28 docs cite commit SHAs that no longer resolve (§5.1). Likely force-pushed or GC'd branches. Needs a policy answer: re-point to merge commits, or move to `UNKNOWN` with ticketed allowlist entries. | `docs/evidence/`, `.evidence-provenance-allowlist` |
| 5 | **`_contract_canon.py:144` vacuous `all()`** (§5.2). One-line guard, but it is a test-contract file — needs someone who knows the intended semantics. | `packages/temper-placer/tests/core/` |
| 6 | **Aggregator timeout under queue pressure.** 23 of 51 PRs (45%) failed for no reason other than never getting a runner inside the 45-minute budget. This is the single largest bucket and no per-PR work will fix it. | `.github/required-checks.json` (`timeout_seconds`, `backlog_grace_seconds`), job-count reduction |

---

## 8. Bucket B — capacity timeouts (23 PRs)

#529, #551, #557, #580, #616, #690, #692, #693, #694, #700, #705, #707, #709,
#710, #711, #714, #725, #740, #743, #744, #746, #747, #748.

All carry `FAIL: candidate checks did not reach a complete success before
timeout`. The aggregator's final poll line names what it was still waiting on —
e.g. #714 timed out with **ten** contexts still `missing:` (never scheduled), and
#690, #707, #725 timed out waiting on `PR Performance Comparison` alone.

**These need a re-run, not a diagnosis.** Re-run them in small batches as the
queue drains, not in bulk.

**Caveat — latent failures behind the timeout.** For five of them, a candidate
that was still `queued` when the aggregator gave up later concluded `failure`.
Their true bucket is unknown until re-run:

| PR | Later concluded failure |
|---|---|
| #551 | `Generated Repo State` (same `docs/plans/README.md` drift shape as #563/#565/#583) |
| #694 | `PR Performance Comparison` |

The other 21 have no failing non-excluded context on their head SHA, so a re-run
is likely to turn them green.

---

## 9. Bucket D / E

- **#767** (`feat(wave4): Phase 5 — deterministic hubs`) — **UNKNOWN.** Its
  aggregator run `31029987905` was still `IN_PROGRESS` throughout this triage and
  its job log 404s. Re-triage once it concludes. Not filed anywhere else.
- **#96** (`chore(main): release 1.0.0`, release-please) and **#514** — no
  aggregator run on the head SHA. #514 is covered in §6.

---

## 10. What this triage changed

- **Fixed:** the stray `) -> LoopCollection: ...` lines in
  `packages/temper-placer/stubs/temper_design_bundle_python/__init__.pyi` (§3).
  This is the only code change; it repairs `main`.
- **Rebased:** none. Five are proven-ready and held for one reason, stated in §2.
- **Closed:** nothing. Four closure recommendations in §6.
- **Not touched:** `power_pcb_dataset/drc_ceiling.json`, any measurement
  baseline, `docs/wave4-verdicts.yaml`, and every gate threshold. No gate was
  weakened; where a gate failed correctly, that is recorded as a finding about
  the PR.
