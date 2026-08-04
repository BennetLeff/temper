# Required-check aggregator design

## Problem

`Python Tests` is filtered at the workflow trigger level. A PR that changes a
path outside that filter produces no Python Tests job contexts, so requiring
those contexts in branch protection would leave the PR permanently waiting.
The current filter also omits safety-relevant `pcb/*.kicad_pro` changes and
the root `.loc-allowlist.txt`.

## Decision

Add a separate, unfiltered `pull_request_target` workflow with one stable
required check: `Required Python Tests`. It uses read-only permissions and
checks out the trusted base revision while evaluating the PR head commit, not
the merge commit, and will:

1. Read changed files from the pull-request API.
2. Match them against a committed JSON manifest describing the Python Tests
   trigger paths and the 16 currently-green candidate job contexts.
3. Treat a PR with no matching trigger path as an explicit, legitimate skip.
4. For a matching PR, poll check-runs until every candidate context is present
   and complete, then pass only when every candidate context concluded
   `success`.
5. Fail closed when a relevant context is absent, failed, cancelled, or still
   pending after the timeout, with the missing/failing contexts printed in the
   job summary.
6. Verify that the push and pull_request Python Tests path lists remain exactly
   synchronized with the manifest, so future additions cannot silently drift.

The polling budget is 2700 seconds (45 minutes): this leaves headroom for the
observed queue delay while still bounding a missing workflow. The workflow job
has a 240-minute timeout so runner setup and cleanup do not truncate that
budget. Measured in production (2026-08-03), the runner backlog exceeded the
45-minute budget with every required context still `queued`; the checker
failed closed on a PR that was simply waiting for a runner. A
`backlog_grace_seconds` manifest field (7200s) now covers that case: if no
required context has left the queue by the deadline (pure runner backlog, not
pipeline progress), the checker extends its polling window to
`timeout_seconds + backlog_grace_seconds` once. Any context that has started
(`in_progress` or later) disables the extension — a started-but-stuck pipeline
still fails at the original deadline. The budget is 165 minutes worst-case; the
job-level 240-minute timeout bounds it. The known-red
hardware and requirements jobs remain advisory in this phase;
they are not included in the candidate list. They will be added to the
manifest only after their underlying defects are resolved and main is green.

## Components

- `.github/workflows/required-checks.yml`: always-on PR workflow with read-only
  `contents`, `pull-requests`, and `checks` permissions.
- `.github/required-checks.json`: path/context manifest consumed by the
  checker; JSON keeps the runtime dependency-free.
- `scripts/check_required_checks.py`: pure path/context evaluation plus the
  GitHub API polling adapter.
- `scripts/tests/test_check_required_checks.py`: focused tests for path
  matching, explicit legitimate skips, missing contexts, failures, and
  completion polling.
- `.github/workflows/python-tests.yml`: add `pcb/*.kicad_pro` and
  `.loc-allowlist.txt` to both existing trigger lists.

## Error handling

The aggregator never converts an applicable failure into success. A skipped
Python Tests workflow is acceptable only when no manifest trigger path
matches. API errors, malformed event data, malformed manifest data, and
timeouts are hard failures. The 45-minute polling timeout accounts for the
observed roughly 20-minute slow CP-SAT shard while remaining bounded so a
missing workflow cannot consume a runner indefinitely; the backlog grace
(see "The polling budget" above) separately absorbs time the contexts spend
queued before a runner picks them up, without ever converting a failure into
a pass — the extension only keeps the check pending, and the job-level
240-minute timeout remains the hard bound.

## Verification

- Unit-test the checker with deterministic fixtures and no network access.
- Run the checker against a captured PR event/check-run fixture.
- Run `actionlint` with the repository's documented ShellCheck exception.
- Run the relevant manifest/import gates and inspect the workflow diff.
- Do not enable branch protection in this change; that remains a separate
  operation after the new required context has reported correctly on a PR
  that exercises both filtered and previously-unfiltered paths.
