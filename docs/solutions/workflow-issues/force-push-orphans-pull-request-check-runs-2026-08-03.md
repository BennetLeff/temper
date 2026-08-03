---
title: "Force-push orphans pull_request-event check runs — the Required Checks aggregator sees 'missing' candidates"
date: "2026-08-03"
category: docs/solutions/workflow-issues/
module: CI, github-actions
problem_type: workflow_issue
component: development_workflow
severity: medium
symptoms:
  - "Required Checks aggregator fails with 'candidate checks did not reach a complete success before timeout' after a force-push, with every candidate listed as 'missing' in the polling log (not pending/failed)"
  - "`gh api .../actions/runs?head_sha=<new head>` shows only pull_request_target runs (Required Checks) — zero pull_request-event runs (Python Tests etc.) for the new head"
  - "Pushing an empty commit does NOT retrigger the candidate workflows (their push/pull_request triggers carry path filters; an empty diff matches nothing)"
  - "The PR checks UI can still show old green runs for the previous head, masking the gap"
root_cause: |
  GitHub computes the changed-files set for pull_request `synchronize` events against
  the PR's base; when a branch is force-pushed (history rewritten, e.g. rebase/squash),
  the synchronize event is sometimes not generated for the new head at all. The
  candidate workflows (which run on `pull_request` with path filters) therefore never
  run for the new SHA, while the `pull_request_target`-based Required Checks aggregator
  DOES run — and its evaluation queries check runs by head SHA, finds none, and burns
  its full polling budget reporting every candidate as `missing:` before failing.
  An empty commit does not help: the workflow's path filters see an empty changed-files
  set and skip the run by design (documented in check_required_checks.py's own module
  docstring — the filtered-out workflow produces no check-run context for branch
  protection to observe).
fix: |
  1. Confirm the gap: list runs for the head SHA
     (`gh api "repos/BennetLeff/temper/actions/runs?head_sha=<sha>"`); the presence of
     only `pull_request_target` runs with zero `pull_request` runs is the signature.
  2. Regenerate the event with a REAL push: sync the branch with origin/main (or any
     genuine content change) and push — a normal push to the PR head generates a fresh
     `synchronize` event and the candidates run against the new head.
  3. If the branch is already current with main and cannot change content, close and
     reopen the PR to force a fresh event (heavier hammer; last resort).
  Do NOT waste cycles rerunning the aggregator while the candidates are missing — the
  rerun repeats the same timeout.
prevention: |
  - Prefer merge-commit syncs over force-pushes on shared PR branches. When a
    force-push is unavoidable (rebuilt history), budget one follow-up sync push and
    verify runs exist for the new head before relying on RPT.
  - After any force-push, check `head_sha` on the runs list before reading the check
    states — the checks UI reports the latest run per context, which can be stale
    relative to the head (the second trap documented in the merge-ladder playbook).
evidence:
  - "PR #576 (2026-08-02): force-push of the rebuilt K3 branch produced zero
    pull_request-event runs for the new head; the Required Checks aggregator failed
    twice with all candidates 'missing' before the sync-push fix regenerated runs"
