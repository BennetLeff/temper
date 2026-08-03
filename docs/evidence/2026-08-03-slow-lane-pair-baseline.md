# Slow-lane pair baseline — pre-change measurement (plan 2026-08-03-001, U6)

<!-- provenance: commit=08bb58db1efcbd08c8c4044d8b7cec873760be52 dirty=false -->

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

Median span: **206s (3m26s)**. Range: 204-211s. All three steps
concluded `success`; all three runs are on `main`, 2026-08-02/08-03,
after the 08-01 hybrid-to-nightly move and the 07-30 trio split.

The step-level span is the pytest execution ("Run cp-sat suite (slow
pair, parallelized)"), excluding the ~2m19-2m45s job setup — per K5 the
job-level figure includes setup no test change affects.

## Context

- **Board:** `pcb/temper.kicad_pcb` sha256
  `e2fb92370da13554710e00857ad03a460340a2ee4f1782220f02c8c552c80277`
  — unchanged since the 07-29 baseline seed (drc_ceiling.json records
  the same hash).
- **Toolchain:** CI temper-ci container, kicad-cli 10.0.4 (recorded in
  `power_pcb_dataset/drc_ceiling.json` provenance).
- **Verdict implication (R6):** the measured median of 206s is far under
  the 6 min threshold. Under the confirmed scope (K4/K5), the migration
  trigger is structurally parked on speed grounds — the restructure
  buys margin and robustness, not the verdict. This was disclosed at
  plan time and is recorded here so the post-change verdict has a
  measured, dated baseline to compare against.
- **Queue contention (R8 signal, does not fire the trigger):** queue
  times of 12 min to 2h15m across three runs corroborate the
  2026-07-29-ci-health-after-split finding (20-27 concurrent runs).
  Recorded here to ride into the migration follow-up plan.

## Local-environment discrepancy note

On this developer machine (Homebrew kicad-cli 10.0.4, worktree-built
Rust extensions) the routing-DRC assertion gate reads unconnected
median 408 vs baseline 407. CI passes the same gate on the same board
(runs above conclude success). The routed board is byte-identical
(deterministic routing; the restructure does not touch routing), so the
delta is environmental — PPA-vs-Homebrew kicad-cli build differences
and/or the router build the local venv linked. The assertion gates are
CI-authoritative per the measurement-provenance discipline; the
07-30 "flaky" routing-DRC failure was the same class.

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
via `gh run list --workflow python-tests.yml --branch main`. No
collector script — the manual method is the repo's established evidence
convention (2026-07-29-extended-suites-timeout-split.md).
