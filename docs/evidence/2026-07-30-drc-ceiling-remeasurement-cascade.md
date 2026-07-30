# DRC ceiling re-measurement cascade: root cause and recommendation — 2026-07-30

<!-- provenance: commit=067527c96cefb2fb14e8d491f371b6ec9483cf7d dirty=true -->

**Base commit:** `067527c9` (`origin/main`), branch
`fix/drc-provenance-remeasure-20260729` in an isolated worktree. `dirty=true`
because this document is committed together with the `drc_ceiling.json`
re-measurement it explains.

**Task.** `power_pcb_dataset/drc_ceiling.json`'s measurement provenance went
stale for the third time in one day: `8bf18b41` (#459, footprint resync) and
`54372bbf` (#472, C25/C26 courtyard separation) both changed
`pcb/temper.kicad_pcb` after the record's last measurement, without either
PR re-measuring. Asked to re-measure honestly (done in this same PR — see
`drc_ceiling.json`'s `2026-07-30-board-resync-remeasure` `_march` entry) and
to investigate why this keeps recurring and propose the smallest durable
fix.

## 1. The gate that's supposed to catch this already does

`scripts/check_measurement_provenance.py` compares `drc_ceiling.json`'s
recorded `pcb/temper.kicad_pcb` content hash against the file's actual
content, on every push and every PR touching either file (both are in the
`python-tests.yml` path filters). This is exactly "a CI check that fails a
PR touching the board unless the ceiling was also updated" — the mechanism
the brief asked me to weigh building. It already exists, and it already
fired correctly on the PR that caused this cascade:

```
$ gh pr view 459 --json statusCheckRollup
...
"name":"Provenance & Anti-Vacuity Gates", "conclusion":"FAILURE"
...mergedAt: 2026-07-30T00:03:45Z (the FAILURE conclusion completed at 00:06:49,
   i.e. AFTER the PR had already merged, not before)
```

PR #459 changed `pcb/temper.kicad_pcb` without touching `drc_ceiling.json`.
Its own "Provenance & Anti-Vacuity Gates" run reported `FAILURE`. The PR
merged anyway. Building a second, differently-named check with the same
diff-based logic ("does this PR's diff touch the board without also
touching the ceiling") would be extensionally identical to the freshness
check that already ran and already failed here — it would not close the gap
that let this PR merge red.

## 2. The actual gap: no branch protection on `main`

```
$ gh api repos/BennetLeff/temper/branches/main/protection
{"message":"Branch not protected","documentation_url":"...","status":"404"}
```

`main` has zero required status checks. Every CI job, including
"Provenance & Anti-Vacuity Gates," is advisory only — a `FAILURE`
conclusion does not block the merge button, `gh pr merge`, or auto-merge.
This is not specific to the provenance gate: PR #459's own status rollup
also shows `FAILURE` on "Board & Netlist Gates," "Requirements Tests," and
"LOC Cap Gate" at merge time, alongside the provenance gate — main is
being merged into routinely while multiple required-candidate jobs are red.

This is the actual mechanism behind "someone changes the board, the gate
goes red, a separate PR re-measures later": the first PR's own red gate run
never had the authority to stop it. A second, cleverer CI check inherits
the identical problem — it would also just be advisory.

## 3. What would actually fix it, and why it's not done here

Enabling required status checks on `main` (at minimum "Provenance &
Anti-Vacuity Gates") would give the existing freshness gate real teeth: a
PR that changes the board without updating the ceiling would be
un-mergeable, not just visibly red. That is the durable fix for the
recurrence pattern.

It is deliberately **not applied in this PR**:

- It is a repository-settings change (branch protection), not a code change
  reviewable as part of a DRC re-measurement diff.
- Blast radius: turning it on right now, with "Board & Netlist Gates,"
  "Requirements Tests," and "LOC Cap Gate" all currently red on `main` for
  reasons unrelated to this task, would immediately block every PR
  repo-wide — including the concurrent constrained-placement re-solve
  mentioned in this task's own brief — not just board-provenance PRs. Which
  checks to make required, and how to sequence that against the
  currently-red ones, is a decision for whoever owns CI policy, not
  something to fold into this PR's diff.
- I hold `admin` on this repo (verified via `gh api repos/BennetLeff/temper`)
  and could flip it, but a repo-wide merge-blocking change with this much
  collateral impact on concurrent, unrelated work is exactly the kind of
  decision this task's own instructions say to describe precisely and defer
  on, rather than half-build or push through unilaterally.

**Recommendation:** enable required status checks on `main` for at least
"Provenance & Anti-Vacuity Gates," phased in after auditing which of the
other currently-red jobs are pre-existing, unrelated debt (and should be
fixed or explicitly descoped first) versus genuine regressions that should
also gate immediately. That audit and rollout is a separate piece of work.

## 4. What this PR does instead

`AGENTS.md` now documents the expected convention (mirroring the existing
Firmware Config Codegen / Transition Table Regeneration sections): any PR
touching `pcb/temper.kicad_pcb` re-measures and updates `drc_ceiling.json`
in the same PR, with the exact tool/flags/sample-count contract and the
Ceiling-Approval rule spelled out. This does not by itself stop a merge —
per §2, nothing does today — but it removes any ambiguity about what a
board-changing PR is expected to do, and gives the eventual required-check
rollout something already-documented to point at.

## 5. Timing: should this re-measurement land now, or wait?

A separate agent is running a full constrained placement re-solve that will
change `pcb/temper.kicad_pcb` again. Landing this re-measurement now will
almost certainly go stale again once that lands — repeating the exact
pattern this document describes.

Recommend landing anyway. `main` is red right now, on a real, verifiable
staleness (not a flake), and nothing about waiting shortens that window —
there is no scheduled landing time for the re-solve to wait for, and (per
§2) an in-progress red gate is not currently blocking anything else either
way. Holding this PR back gains nothing and leaves a currently-fixable red
gate red for no benefit. When the re-solve lands, it will go stale again and
need its own re-measurement PR — the same cost whether this one lands first
or not. This is precisely the case §3's recommended fix would prevent going
forward: co-locating the re-measurement inside the re-solve's own PR, once
that convention has real enforcement behind it.
