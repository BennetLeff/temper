---
date: 2026-07-01
topic: linear-ci-issues
---

# CI Failure to Linear Issues

## Summary

A shared Rust binary that CI enforcement gates call to create or update Linear
issues on failure. Deduped by gate name and branch. Auto-closes when the same
gate passes again on the same branch. Fail-soft on Linear unavailability.

---

## Problem Frame

CI enforcement gates — import linter, transition table drift, config drift,
manifest gate, sunset check, traceability, coverage, type-check, golden
checks — block PRs when they fail. But the failure signal is a red X in a
workflow log. There's no tracking home, no way to see recurring failures across
PRs, and no structured path from detection to fix.

The project already creates GitHub issues from scheduled workflows
(health-digest, metrics-trend-check), but those are periodic health snapshots.
Enforcement gate failures — the kind that actually block work — have no issue
lifecycle. Enforcement gates go to Linear because they represent actionable
blockers for the development workflow; health-digest and metrics-trend-check
are informational summaries visible to a broader audience on GitHub and are
out of scope for this integration. On a single branch, repeated failures compound invisibly. Across
branches, cross-PR failure correlation is not addressed by v1 (dedup is per
gate + branch); Linear's search and label views provide partial discovery.

---

## Actors

- A1. **CI runner**: The GitHub Actions workflow executing enforcement gates
- A2. **Linear workspace**: The target Linear team where issues land
---

## Key Flows

- F1. **Gate failure creates issue**
  - **Trigger:** CI enforcement gate exits non-zero
  - **Actors:** A1, A2
  - **Steps:** Binary checks for existing open issue matching gate name + branch
    → creates new issue with gate metadata and `ci:<gate>` label, or updates
    existing
  - **Outcome:** A Linear issue exists with commit SHA, error excerpt, and CI
    run URL
  - **Covered by:** R1, R2, R4

- F2. **Gate re-pass closes issue**
  - **Trigger:** Same enforcement gate passes on the same branch
  - **Actors:** A1, A2
  - **Steps:** Binary finds the open issue → transitions it to "Done" → posts
    comment with link to green CI run
  - **Outcome:** Issue is closed with resolution trace
  - **Covered by:** R3, R4

- F3. **Linear unreachable — fail-soft**
  - **Trigger:** Binary cannot reach Linear API (network, bad token, rate limit)
  - **Actors:** A1
  - **Steps:** Binary logs a structured warning → exits zero so the CI gate's
    own failure/success signal is preserved
  - **Outcome:** CI continues normally; Linear issue is not created or updated
  - **Covered by:** R9

---

## Requirements

**Linear issue lifecycle**

- R1. When a CI enforcement gate fails, the binary creates or updates a Linear issue
  containing: gate name, commit SHA, error excerpt (first N lines), and CI run
  URL
- R2. Each issue carries a label `ci:<gate-name>` (e.g., `ci:import-linter`,
  `ci:transition-table-drift`)
- R3. When the same gate passes on the same branch on a subsequent commit, the
  binary transitions the existing open issue to the completion state configured
  via `LINEAR_DONE_STATE` environment variable (defaults to `"Done"`) and posts
  a comment linking the green CI run
- R4. Dedup: the binary queries for an existing open issue matching the same
  gate name + branch. If found, the issue is updated with the new failure
  context rather than creating a duplicate

**Binary interface**

- R5. The binary accepts arguments: `--gate <name>`, `--status <failure|pass>`,
  `--error <output>`, `--sha <commit>`, `--run-url <url>`, `--branch <name>`
- R6. The binary reads the Linear API token from `LINEAR_API_KEY` environment
  variable
- R7. When the binary fails for a non-Linear reason (missing arguments,
  malformed input), it exits non-zero with structured error output

**CI integration**

- R8. Each enforcement gate workflow calls the binary on both the failure path
  (`--status failure`) and success path (`--status pass`). Enforcement gates
  must run as independent CI steps so each gate can report its own status.
  Restructuring CI jobs to split gates into separate steps with `if: always()`
  or independent jobs is a prerequisite for wiring R8
- R9. When Linear is unreachable (network error, bad token, rate limit), the
  binary exits zero with a structured warning on stderr — the CI gate's own
  exit code is not affected

---

## Acceptance Examples

- AE1. **Covers R1, R2.** Given the import-linter gate fails on branch
  `feat/foo` at commit `abc123`, when the binary runs with `--gate
  import-linter --status failure`, a Linear issue is created with label
  `ci:import-linter` and body containing `abc123` and the error output

- AE2. **Covers R4.** Given an open `ci:import-linter` issue already exists for
  branch `feat/foo`, when the gate fails again, the existing issue is updated
  with the new failure context — no duplicate is created

- AE3. **Covers R3, R4.** Given an open `ci:import-linter` issue exists for
  branch `feat/foo`, when the gate passes on the same branch at a later commit,
  the issue transitions to "Done" with a comment linking the green run

- AE4. **Covers R4 (dedup scope).** Given an open `ci:import-linter` issue
  exists for branch `feat/foo`, when the same gate fails on branch
  `feat/bar`, a separate issue is created — dedup is per gate + branch, not
  per gate alone

- AE5. **Covers R9.** Given the Linear API is unreachable, when the binary runs
  with `--status failure`, it exits zero, prints a warning to stderr, and the
  CI gate's own failure signal is preserved

---

## Success Criteria

- Every enforcement gate failure produces exactly one Linear issue per branch,
  with full context to reproduce (commit, error, run URL)
- Gate re-pass reliably closes the issue within one CI run of the passing
  commit
- CI workflows continue unaffected when Linear is unreachable (no spurious CI
  failures from the integration itself)
- A developer seeing a `ci:<gate>` issue can reproduce the failure from the
  issue body alone

---

## Scope Boundaries

- Only enforcement gates (import linter, transition table drift, config drift,
  manifest gate, sunset check, traceability, coverage, type-check, golden
  checks) — other workflows (health-digest, metrics-trend-check,
  pr-perf-check) continue to use GitHub issues or are out of scope
- No bidirectional sync — Linear → GitHub direction is out of scope
- No agent auto-dispatch from CI issues — this is issue creation only; MCP or
  dispatch tooling is a follow-up
- No webhook infrastructure — purely CI-push via GraphQL API
- No dashboard or UI for viewing CI issue status — Linear's own views are the
  interface

---

## Key Decisions

- **Shared Rust binary over inline per-workflow scripts**: Centralizes Linear
  API logic, eliminates duplication across 8+ workflows, and is testable
  locally. The trade-off is a build step in CI that doesn't currently exist for
  Rust crates
- **Dedup key is gate name + branch**: A flaky gate on a long-lived branch
  updates one issue rather than creating a new one per push. Different branches
  get separate issues (a gate failing on `main` and `feat/foo` are different
  incidents)
- **Auto-close on re-pass from day one**: The issue lifecycle is self-healing —
  when the gate passes, the issue closes without manual intervention. Flaky
  gates will create noisy open/close cycles; this is acknowledged and
  acceptable for v1
- **Fail-soft on Linear unavailability**: The CI gate's signal (pass/fail) must
  not be contaminated by the integration's health. If Linear is down, CI
  continues normally

---

## Dependencies / Assumptions

- A Linear API token is stored as a GitHub organization or repository secret
  accessible to CI workflows
- A Linear workspace and team exist with labels matching each enforcement gate
  name (labels are created manually before workflows are wired)
- The sunset check is promoted from informational (`continue-on-error: true`)
  to a blocking enforcement gate; coverage and traceability gates are enabled
  and wired into CI workflow steps before the binary is called for them.
  Enforcement gates currently non-blocking or unwired cannot create issues
  without this prerequisite
- The team is monitoring the target Linear workspace for CI issues. This
  integration assumes Linear is being used as the primary issue tracker for
  development work; if Linear adoption trails the integration, CI issues may
  not be discovered
- The Rust toolchain is available on CI runners, or a pre-built binary approach
  is used (decision deferred to planning)
- The binary produces structured stdout on success and structured stderr on
  warning, so CI logs remain parseable

---

## Deferred / Open Questions

### From 2026-07-01 review

- **CI error output sent to Linear without sanitization** -- R1, F1 (P1, security-lens, confidence 75)

  R1 mandates CI gate error output be included in the Linear issue body,
  crossing a trust boundary from internal CI to an external SaaS platform.
  CI error output can inadvertently carry secrets, file paths, environment
  values, or internal configuration. Without a sanitization or filtering
  requirement, sensitive data could be persisted in Linear where access
  controls differ from the CI environment.

  <!-- dedup-key: section="r1 f1" title="ci error output sent to linear without sanitization" evidence="r1 mandates that ci gate error output be included in the linear issue body crossing a trust boundary from internal ci to an external saas platform ci error output can inadvertently contain secrets" -->

- **Linear API token security properties not specified** -- R6, Dependencies (P1, security-lens, confidence 75)

  R6 specifies the token reading mechanism (env var) but no requirement
  forbids the token from appearing in CI logs, error output, or the Linear
  issue body. Since R1 sends error output to Linear, a token inadvertently
  captured in CI output could be transmitted to Linear and persisted in an
  issue visible to the entire workspace.

  <!-- dedup-key: section="r6 dependencies" title="linear api token security properties not specified" evidence="r6 specifies the token reading mechanism env var but the requirements document does not assert any security properties that the token must never appear in ci logs" -->

- **TOCTOU race condition in issue dedup under concurrent CI runs** -- R4, AE (P1, adversarial, confidence 75)

  The dedup mechanism queries then creates. Between query and create, a
  concurrent CI job can also query, find nothing, and create a second
  issue. The repo already uses parallel matrix builds (e.g.,
  golden-check.yml with 10 jobs for the same commit). AE2 only tests
  sequential dedup.

  <!-- dedup-key: section="r4 acceptance examples" title="toctou race condition in issue dedup creates duplicates under concurrent ci runs" evidence="the dedup mechanism queries for an existing issue then conditionally creates one r4 between the query and the create a concurrent ci job on the same branch can also query find nothing" -->

- **No reconciliation path when fail-soft permanently drops CI failures** -- R9, F3 (P1, adversarial, confidence 75)

  R9 and F3 specify exit-zero when Linear unreachable with no retry queue
  or catch-up mechanism. A 30-minute Linear outage permanently loses all
  CI failure signals during that window.

  <!-- dedup-key: section="r9 key flows f3" title="no reconciliation path when failsoft permanently drops ci failure signals during linear outages" evidence="r9 and f3 specify that when linear is unreachable the binary exits zero and no issue is created there is no retry queue no reconciliation" -->

- **No lifecycle handling for CI issues when branches are deleted** -- F2, Scope Boundaries (P2, adversarial, confidence 75)

  Merged+deleted branches leave orphaned CI issues that can never
  auto-close (R3 requires a CI run on that branch). Without a
  branch-deletion webhook or cleanup job, these accumulate permanently.

  <!-- dedup-key: section="key flows f2 scope boundaries" title="no lifecycle handling for ci issues when branches are deleted" evidence="when a feature branch is merged and deleted standard pr workflow any open ci issue tied to that branch will never autoclose r3 requires" -->

- **Rate limiting (HTTP 429) treated identically to permanent failures** -- R9 (P2, adversarial, confidence 75)

  R9 bundles rate limits with network errors and bad tokens as
  unreachable. Linear's API returns HTTP 429 with Retry-After — rate
  limits are transient and recoverable. A simple retry with backoff would
  recover most rate-limited requests.

  <!-- dedup-key: section="requirements r9" title="rate limiting http 429 treated identically to permanent failures discarding recoverable signals" evidence="r9 bundles rate limit with network error and bad token as unreachable conditions that trigger failsoft but linears api returns http" -->
