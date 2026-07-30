# Required-check aggregator design

## Problem

`Python Tests` is filtered at the workflow trigger level. A PR that changes a
path outside that filter produces no Python Tests job contexts, so requiring
those contexts in branch protection would leave the PR permanently waiting.
The current filter also omits safety-relevant `pcb/*.kicad_pro` changes and
the root `.loc-allowlist.txt`.

## Decision

Add a separate, unfiltered pull-request workflow with one stable required
check: `Required Python Tests`. The workflow will evaluate the PR head commit,
not the merge commit, and will:

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

The known-red hardware and requirements jobs remain advisory in this phase;
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
timeouts are hard failures. The polling timeout is bounded so a missing
workflow cannot consume a runner indefinitely.

## Verification

- Unit-test the checker with deterministic fixtures and no network access.
- Run the checker against a captured PR event/check-run fixture.
- Run `actionlint` with the repository's documented ShellCheck exception.
- Run the relevant manifest/import gates and inspect the workflow diff.
- Do not enable branch protection in this change; that remains a separate
  operation after the new required context has reported correctly on a PR
  that exercises both filtered and previously-unfiltered paths.
