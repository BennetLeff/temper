# Slow-lane pair baseline — pre-change measurement (plan 2026-08-03-001, U6)

<!-- provenance: commit=3040db99ecdaff4b0ea09285989fb64396e6384c dirty=false -->

## What this records

The step-level span of the `extended-cpsat-slow` job ("Extended Test
Suites (cp-sat, slow x2)") measured on three real `main` runs **before**
the trio parallelization restructure lands. This is the R6 baseline: the
pair — zone-pour XFAIL + routing-DRC regression — runs concurrently on
the lane's two xdist workers, and its pytest step span is what the <6 min
verdict threshold is measured against.

## Measurements

| run_id | job_id | step | span | queue (run created -> job start) |
|---|---|---|---|---|
| 30760788830 | 91530764425 | 18:33:49 -> 18:37:15 | 206s (3m26s) | ~12 min |
| 30784225011 | 91594619340 | 06:39:47 -> 06:43:11 | 204s (3m24s) | ~2h15m |
| 30790268516 | 91615484507 | 06:52:26 -> 06:55:57 | 211s (3m31s) | ~21 min |

Median span: **206s (3m26s)**. Range: 204-211s. All three runs are on
`main`, 2026-08-02/08-03, after the 08-01 hybrid-to-nightly move and the
07-30 trio split.

The step-level span is the pytest execution ("Run cp-sat suite (slow
pair, parallelized)"), excluding the ~2m19-2m45s job setup — per K5 the
job-level figure includes setup no test change affects.

## The runs were RED — read this before using the spans

The step *spans* are valid measurements, but the gates inside them
**failed on all three runs**, masked by `continue-on-error: true` (the
steps' `success` conclusions are the mask's rewrite, not green runs):

- `test_regression_drc.py::test_production_board_routing_drc_regression`
  FAILED on all three runs — the routing-DRC gate has been red on `main`
  since at least 08-02 (e.g. run 30790268516: router-output total median
  1524 vs threshold 1436, unconnected 463, shorting 146; zero scatter
  within runs).
- `pytest_guard` printed `FAIL: only 1 tests executed (1 skipped),
  expected at least 2` on all three runs — the exit-3 masked guard
  failure this plan's U5 fixes (floor 2 -> 1 for the XFAIL zone test).

This is a sustained, pre-existing main-trunk state, not a consequence of
this restructure: the routed board is byte-identical (deterministic
routing; the restructure does not touch routing), and DRC is a pure
function of board + kicad-cli version. The routing gate's red predates
this plan and is separately attributable to main's board/router churn
(K2 relay swap re-baselines on 07-31, edge-ref nudges on 08-02) and the
in-flight wave4 migration (pyo3 DesignRules API change, #599/#619) —
which currently breaks the routing-test parse path on `main@HEAD`
entirely (see the plan PR's Known Residuals).

**Decision (2026-08-03, user):** the trio PR ships as-is on rebased
main; the routing-gate red and the wave4-migration breakage stay visible
(instead of masked, per R3) and the router-output baseline re-seed is
deferred until the wave4 migration settles. The post-change verdict
protocol below runs when the lane is executable again.

## Context

- **Board:** `pcb/temper.kicad_pcb` sha256
  `e2fb92370da13554710e00857ad03a460340a2ee4f1782220f02c8c552c80277`
  at the time of these runs (drc_ceiling.json records the same hash;
  the board has since moved per the 07-31/08-02 re-baselines).
- **Toolchain:** CI temper-ci container, kicad-cli 10.0.4 (recorded in
  `power_pcb_dataset/drc_ceiling.json` provenance).
- **Verdict implication (R6):** the measured median of 206s is far under
  the 6 min threshold. Under the confirmed scope (K4/K5), the migration
  trigger is structurally parked on speed grounds — the restructure
  buys margin and robustness, not the verdict. This was disclosed at
  plan time and is recorded here so a post-change verdict has a
  measured, dated baseline to compare against.
- **Queue contention (R8 signal, does not fire the trigger):** queue
  times of 12 min to 2h15m across three runs corroborate the
  2026-07-29-ci-health-after-split finding (20-27 concurrent runs).
  Recorded here to ride into the migration follow-up plan.
- **Reconciliation with the plan's baseline figure:** the plan text's
  "5.2-5.8 min" figure was the serial sum of the pair's per-test
  estimates (211s + 102s); the lane actually runs the pair concurrently
  via `-n auto --dist loadgroup`, which is what these 204-211s measured
  spans show.

## Local-environment discrepancy note

On this developer machine (Homebrew kicad-cli 10.0.4, worktree-built
Rust extensions, docs/wave4-plan-based base) the routing-DRC assertion
gate read unconnected median 408 vs baseline 407 pre-rebase, and total
~1453 vs threshold 1436 post-rebase — both red, consistent with the
CI-side red (1524/463), i.e. the gate is red in both environments and
the local numbers are not a local-only artifact. The assertion gates
remain CI-authoritative; the re-seed is deferred per the decision above.

## Post-change verdict protocol (R5-R8, G5)

- Measure the same step-level span on **N=5** PR runs of the restructured
  lane, same runner class (ubuntu-latest 2-CPU), recording run/job IDs.
- Verdict statistic: **median** of the 5 spans, with the range reported
  (U6 step 5; R6). Threshold: < 6 min -> "fix sufficient"; >= 6 min ->
  "migration primary".
- Record queue time separately from execution time per run (R8).
- **Invalidation rules:** a board content-hash change mid-protocol
  restarts the count from the run after the change (the measurement is
  board-bound, per the measurement-provenance contract); a runner
  profile change restarts the count; a flaky-failure run is excluded and
  replaced only when the failure is attributable (known-failure pin or
  unrelated-path evidence), otherwise it counts as the run's span.
- **Time-box:** the verdict is computed at 5 valid runs OR 3 weeks,
  whichever comes first, with the achieved count stated plainly in the
  verdict doc (docs/evidence/2026-08-XX-slow-lane-verdict.md).
- Provenance for the verdict doc: PR `baseRefOid` or merge commit SHA —
  never a branch SHA that squash-merge orphans (handoffs
  2026-07-31-ci-enforcement-and-board-defects.md) — plus the board hash
  per run.

## Method

Step timestamps via `gh api repos/BennetLeff/temper/actions/jobs/<id>`
(`steps[].started_at/completed_at` for the pytest step); run inventory
via `gh run list --workflow python-tests.yml --branch main`; gate
outcomes via `gh api .../jobs/<id>/logs`. No collector script — the
manual method is the repo's established evidence convention
(2026-07-29-extended-suites-timeout-split.md).
