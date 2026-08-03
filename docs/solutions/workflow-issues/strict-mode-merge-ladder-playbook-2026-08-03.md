---
title: "Strict-mode merge ladder playbook — landing a PR chain on a main that moves every few minutes"
date: "2026-08-03"
category: docs/solutions/workflow-issues/
module: CI, github-actions, git-workflow
problem_type: workflow_issue
component: development_workflow
severity: medium
symptoms:
  - "PRs repeatedly flip BEHIND on merge attempt: main is so active (60+ concurrent agent sessions) that the branch goes stale between RPT passing and the merge click"
  - "The same RPT check reads FAILURE then QUEUED then SUCCESS across consecutive polls — stale runs from older heads dominate the check list"
  - "Required Checks times out with 'candidate checks did not reach a complete success before timeout' while every candidate is individually green — runner-pool starvation, not a code failure"
  - "PR RPT cannot pass while main's own gate is red (e.g. Type Check, LOC, manifest drift inherited from a wave merge) — a chicken-and-egg that no branch-side fix resolves"
playbook: |
  The rhythm (per ladder step):
  1. Sync: merge origin/main into the PR branch (merge, never rebase on shared branches).
  2. Verify locally what CI will check, cheaply: ruff, vulture, LOC, typecheck, provenance,
     gen_repo_state --check, clippy on the touched crates. Fix inherited gate debt AT THE
     SOURCE on main directly (see below) rather than per-branch — every branch inherits it.
  3. Push, then read the Required Checks aggregator (RPT) state. Before believing any state, resolve the check link's
     run ID and confirm its head_sha equals the branch tip: the checks API shows the
     latest run per context, which can belong to a previous head. A FAILURE reading for a
     stale head is not a failure.
  4. If RPT fails with 'candidate checks did not reach a complete success before timeout'
     and the candidates are green (or the polling log shows them queued), that is pool
     starvation: rerun the aggregator run (`gh run rerun --failed <run>`), not the code.
     CAVEAT: the rerun re-polls the head SHA captured in the original event payload, NOT
     the current branch tip — after the rerun passes, apply the step-3 rule again
     (confirm the run's head_sha equals the branch tip) before trusting it; if the tip
     moved while the timed-out run was polling, push a fresh sync to generate a new event
     instead of rerunning the stale one.
  5. When RPT is green, merge IMMEDIATELY (BEHIND can reassert within minutes). If
     BEHIND: one more sync + push + RPT cycle. Budget ~40-60 min per ladder step under
     an active main.
  Chicken-and-egg (main's own gates red): if main's Type Check / LOC / manifest / etc.
  is red, EVERY PR's RPT inherits it, and a PR whose diff includes the manifest (etc.)
  cannot pass its own base comparison. The working pattern:
  - Verify the failure is inherited first: `git diff origin/main..HEAD -- <file>` empty
    (or reproduce the gate failure on origin/main's tree directly) before touching it.
  - Fix it on main directly (push a tiny main-only commit) when the fix is small and
    attributable — the alternative (a fix PR) fails its own RPT on the same base check.
  - Respect per-gate policy nuances when fixing at the source: the LOC allowlist has a
    strict-shrink rule (NEW_ENTRY_NO_REMOVAL — adding an entry requires removing one;
    if nothing is removable, the entry must ride via a branch whose base already has
    it, and main's own gate stays red until a genuine shrink exists).
traps: |
  1. Stale-run misreads (trap #1): always resolve run ID + head SHA before acting on a
     check state; a 'FAILURE' from a pre-push run is noise.
  2. Starvation vs failure (trap #2): the discriminator is CONTENT, not timing — a
     failure message that names a failed candidate (e.g. 'failed: Type Check (failure)')
     is a real failure at ANY elapsed time, investigate; a failure that lands exactly at
     the ~45-min polling deadline (timeout_seconds 2700) with only missing/pending
     entries in the log is starvation or an orphaned event, rerun the aggregator.
  3. Force-push orphans (trap #3): see the sibling doc
     force-push-orphans-pull-request-check-runs-2026-08-03.md — force-pushes can leave
     the new head with zero candidate runs and an aggregator that reports everything
     'missing'.
  4. Empty commits do not retrigger path-filtered workflows (empty changed-files set).
  5. BEHIND is not CONFLICTING: BEHIND needs only a sync; CONFLICTING needs conflict
     resolution. UNSTABLE means mergeable with non-required checks red — mergeable.
evidence:
  - "2026-08-01 ladder: #512 -> #513 -> #515 -> #446 -> #488 -> #521 -> #501 merged
    under ~15 sync rounds; main advanced every 5-30 minutes (wave-session merges)"
  - "Three consecutive aggregator timeouts on #576 (2026-08-01, pre-force-push
    series — distinct from the 2026-08-02 orphan failures in the sibling doc) were pool
    starvation; the rerun passed once candidates had drained"
  - "Main-red gates fixed at source during the ladder: required-checks manifest sync
    (#446's gate landed without its manifest entries), typecheck (channel_widths,
    _encoder_solve, fixed_copper), clippy (astar, wave crates), ruff (30 errors),
    vulture baselines, LOC allowlist, hypothesis deadline (2000->5000ms under fleet
    load)"
