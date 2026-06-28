---
date: 2026-06-28
type: feat
origin: docs/brainstorms/2026-06-28-repo-health-dashboard-requirements.md
status: completed
---

# feat: Add Repo Health Dashboard (Badge Matrix + Weekly Digest)

## Summary

Add a root `README.md` with GitHub-native workflow badges grouped into 3 semantic tiers (Core Health, Regression Gates, Observability) for all existing CI workflows plus a self-monitoring badge for the new health-digest workflow. Add a weekly `health-digest.yml` CI workflow that synthesizes coverage gate status, golden fixture parity, pipeline metrics drift, script sunset warnings, and import-linter compliance into a single update-in-place GitHub Issue.

---

## Problem Frame

Temper has 7 CI workflows producing rich health signals (coverage monotonic-shrink, golden fixture parity, import-boundary enforcement, metrics time-series, timing regression) but the project owner has no surface to see any of it at a glance. Checking health means digging through workflow run logs or reading raw JSONL files. The root repo surface has no README, no badges, and no synthesized health summary. (See origin: `docs/brainstorms/2026-06-28-repo-health-dashboard-requirements.md`)

---

## Actors

- A1. **Project owner** — sole consumer. Wants CI pass/fail at a glance and weekly changes in one issue.

---

## Key Flows

- F1. **Land on the repo and check health**: Owner opens GitHub repo → sees README with badge tier groups → red badges draw attention → clicks badge to navigate to failing workflow.
- F2. **Weekly digest arrives**: Monday 8am cron fires digest workflow → collects data from committed artifacts and GitHub API → updates the `health-digest` issue → owner receives notification or checks Issues tab.

---

## Key Technical Decisions

- **Digest reads committed artifacts, doesn't re-run gates**. Coverage count from `.coverage-allowlist` line count, import-linter from baseline/allowlist YAML line counts, metrics from `pipeline_metrics.jsonl`, script sunset from re-running `check_script_sunset.py` (~100ms). Golden fixtures are the exception — no artifact is uploaded, so the digest re-runs `temper dsn check` per boundary.
- **Update-in-place via `github.rest.issues.update()`**. The digest finds the existing open `health-digest` issue by label + title, then updates the body. Reuses the proven `actions/github-script@v7` + `issues: write` permission pattern from `metrics-trend-check.yml`.
- **Standalone `health-digest.yml` workflow** (not extending trend-check). Clean separation — trend-check detects anomalies, digest provides the weekly briefing. Follows the `golden-check.yml` workflow structure template.
- **Inline synthesis logic in the workflow YAML** rather than a separate Python script. The digest collects data from a mix of bash commands (file reads, line counts) and GitHub API calls (workflow status, issue queries). A separate script would add a `scripts/manifest.yaml` registration requirement and import chain. Inline bash + `actions/github-script` keeps V1 lightweight.
- **Digest badge in Observability tier**. The health-digest workflow itself appears in the README badge matrix so the owner can see at a glance if the monitoring infrastructure is healthy (R9).
- **Firmware-specific signals deferred**. The `firmware-tests.yml` workflow uploads no artifact with binary size or Unity test count, and re-running firmware tests in the digest is too expensive. Deferred to a future phase when firmware-tests produces a parseable artifact.

---

## Implementation Units

### U1. Root README.md with badge matrix

- **Goal**: Create the root `README.md` with GitHub-native workflow badges for all existing CI workflows, grouped under 3 semantic tier headers. Include a placeholder for the health-digest badge (resolved in U4).
- **Requirements**: R1, R2, R3, R4
- **Dependencies**: None (can land before U2)
- **Files**:
  - **Create** `README.md`
- **Approach**:
  - GitHub-native badge URL: `https://github.com/BennetLeff/temper/actions/workflows/{filename}/badge.svg`
  - Three tier headers: **Core Health** (python-tests, firmware-tests), **Regression Gates** (placer-regression, golden-check, regression), **Observability** (metrics-record, metrics-trend-check). Health-digest badge goes in Observability when U2 lands.
  - Include a brief project identifier line: "ESP32-S3 induction cooker — firmware, PCB, and JAX-based placer"
  - Link each badge to its workflow's latest run page
  - Health-digest badge placeholder: `<!-- health-digest badge: added by U4 -->`
- **Patterns to follow**: Standard shields.io / GitHub badge markdown pattern — `[![Label](badge-url)](workflow-url)`
- **Test scenarios**:
  - README renders on GitHub with all badges visible
  - Clicking a badge navigates to the correct workflow's latest run
  - Badge tiers are visually distinct (three bold headers with badges underneath)
  - Status reflects actual workflow state (badge SVG served by GitHub, not manually set)
- **Verification**: Open the repo page on GitHub — all 7 badges are visible, grouped, and clickable. A red badge indicates a failing workflow; clicking it shows the failing run.

---

### U2. Health-digest CI workflow (YAML + permissions + toolchain)

- **Goal**: Create the `health-digest.yml` workflow file with schedule, dispatch, permissions, checkout, and uv toolchain setup. This unit covers the CI skeleton; data collection and issue content are in U3.
- **Requirements**: R5, R7, R9
- **Dependencies**: None (can land before U3; U3 builds on this skeleton)
- **Files**:
  - **Create** `.github/workflows/health-digest.yml`
- **Approach**:
  - Trigger: `schedule: cron: "0 8 * * 1"` (Monday 8am) + `workflow_dispatch`
  - Job: `runs-on: ubuntu-latest`, `timeout-minutes: 10`
  - Permissions: `issues: write` (for issue creation/update), `contents: read` (default, for checkout)
  - Provisioning steps (reuse existing CI pattern):
    1. `actions/checkout@v4`
    2. `astral-sh/setup-uv@v4` with `version: "latest"`
    3. `uv python install 3.12`
    4. `uv sync --all-packages` (needed for `pipeline_metrics.py` and `temper dsn check`)
  - Issue management step: `uses: actions/github-script@v7` with script that:
    1. Finds existing open `health-digest` issue by label + title → `issue_number`
    2. If found: `github.rest.issues.update({owner, repo, issue_number, body: digestBody})`
    3. If not found: `github.rest.issues.create({owner, repo, title, body: digestBody, labels: ["health-digest"]})`
  - Body content (`digestBody`) is assembled by inline bash steps + github-script from U3's collection logic
- **Patterns to follow**:
  - `.github/workflows/metrics-trend-check.yml:66-84` — issue creation with label-based dedup
  - `.github/workflows/golden-check.yml` — standalone workflow structure, `workflow_dispatch`
  - `.github/workflows/metrics-record.yml` — `astral-sh/setup-uv@v4` + `uv python install 3.12` + `uv sync --all-packages`
- **Test scenarios**:
  - `workflow_dispatch` trigger succeeds — creates a new `health-digest` issue
  - Running a second time updates the same issue (no duplicate)
  - If the issue is closed, a new run creates a new issue
  - Workflow fails with clear error if `uv sync --all-packages` cannot install deps
- **Verification**: Trigger `workflow_dispatch` from the Actions tab, verify a `health-digest`-labeled issue appears in the Issues tab with a synthesized body.

---

### U3. Digest content generation (data collection + synthesis into issue body)

- **Goal**: Implement the data-collection steps that gather signals from committed artifacts and GitHub API, then assemble the markdown issue body. This unit covers the inline bash and github-script logic that populates the digest.
- **Requirements**: R6, R8, R9
- **Dependencies**: U2 (the workflow skeleton must exist for the collection steps to run)
- **Files**:
  - **Modify** `.github/workflows/health-digest.yml` (add data-collection steps between toolchain setup and issue management, plus enhance the github-script body assembly)
- **Approach**:
  - **CI pass/fail**: Use `github.rest.actions.listWorkflowRunsForRepo()` in the github-script step to query latest `main`-branch runs for all 7 workflows. Filter to the most recent per workflow, extract `conclusion` (success/failure/cancelled).
  - **Coverage gate**: Count non-comment, non-empty lines in `.coverage-allowlist`. For trend: compare against last week's digest snapshot (stored as a comment or artifact, or just report current count). Report: "Coverage allowlist: N entries (Δ from last digest)"
  - **Golden fixture parity**: Run `uv run temper dsn check --boundary B --input pcb/temper.kicad_pcb --config pcb/temper_config.yaml --golden-dir power_pcb_dataset/goldens/temper` for each boundary (semantic, topological, placement, routing, validation). Capture exit codes.
  - **Pipeline metrics drift**: Run `uv run python scripts/pipeline_metrics.py trend --board temper --stage all --window 7d --json` and parse output for any stage with sigma drift > threshold.
  - **Open drift issues**: Use `github.rest.issues.listForRepo({state: "open", labels: ["metrics-drift"]})` to count open auto-filed drift issues.
  - **Script sunset**: Run `uv run python scripts/check_script_sunset.py`, parse stdout for WARNING and ESCALATE counts.
  - **Import-linter**: Count entries in the YAML files: `import-linter-baseline.yaml` (violations array) and `import-linter-allowlist.yaml` (allowlist array). Report: "Boundaries: clean (0 baseline violations, N allowlist exemptions)"
  - **Digest cadence observation**: If this is an "all clear" week (no regressions, no drift, no fixture failures), the body begins with "All clear — no drift, no fixture failures, no new sunset warnings" per AE4. Otherwise, regressions are listed first.
  - **Delta snapshot**: Store the current allowlist count, import-linter counts, and timestamp as a JSON artifact (`digest-snapshot.json`) uploaded to the workflow run, for next week's delta calculation.
- **Patterns to follow**:
  - `scripts/check_script_sunset.py` — already parses `manifest.yaml` with a custom parser; invoke directly
  - `scripts/pipeline_metrics.py trend --json` — produces structured drift output
  - `.github/workflows/metrics-trend-check.yml:40-60` — `while IFS=, read -r board stage; do ...` pattern for iterating board/stage combinations
- **Test scenarios**:
  - Digest body contains all 6 sections from R6, even when some are "all clear"
  - Coverage trend differs from last week → delta shown in body with direction arrow
  - Golden fixture boundary fails → section shows which boundary and exit code
  - No open drift issues → section shows "No open drift issues"
  - Script sunset has 2 WARNING, 1 ESCALATE → body includes counts
  - Import-linter baseline is clean → body shows "0 violations, N allowlist exemptions"
  - All signals all-clear → body begins with "All clear" preamble
  - `digest-snapshot.json` is uploaded as a workflow artifact for next week's delta
- **Verification**: Trigger `workflow_dispatch`, inspect the GitHub Issue body — all sections are present, counts are accurate, pass/fail indicators match current CI state.

---

### U4. Health-digest self-monitoring badge + final integration

- **Goal**: Add the health-digest workflow's own badge to the README Observability tier, completing the self-monitoring requirement (R9). Verify end-to-end by triggering a digest run and checking the badge reflects its status.
- **Requirements**: R9
- **Dependencies**: U1 (README exists), U2 (workflow file exists)
- **Files**:
  - **Modify** `README.md` (replace health-digest badge placeholder with actual badge)
- **Approach**:
  - Badge URL: `https://github.com/BennetLeff/temper/actions/workflows/health-digest.yml/badge.svg`
  - Place in the Observability tier alongside metrics-record and metrics-trend-check
  - The badge shows the latest digest workflow run conclusion — if the digest fails, the badge turns red
- **Patterns to follow**: Same badge markdown pattern as the other 7 badges in the README
- **Test scenarios**:
  - After a successful `workflow_dispatch` run, the health-digest badge shows green/passing
  - Badge is grouped under the Observability tier header
  - Clicking the badge navigates to the health-digest workflow's latest run
- **Verification**: Trigger `workflow_dispatch` on health-digest, wait for it to complete, open the repo page — health-digest badge is green and clickable.

---

## Scope Boundaries

### In Scope

- Root README with 7 existing workflow badges + health-digest self-monitoring badge (8 total)
- `health-digest.yml` weekly cron workflow with `workflow_dispatch`
- Digest covers: CI pass/fail, coverage gate, golden fixture parity, pipeline metrics drift, script sunset, import-linter — all sourced from committed artifacts and GitHub API
- Update-in-place single `health-digest` issue
- Weekly "all clear" digests with 8-week cadence review (per R8)

### Deferred to Follow-Up Work

- Firmware-specific signals (binary size, Unity test count) — requires `firmware-tests.yml` to upload a parseable artifact
- Monthly "heartbeat" digest with weekly drift-only digests — to be evaluated after 8 weeks of V1 operation
- Custom dynamic badges (coverage %, per-gate pass/fail) — V2 in origin doc
- CI-generated README sections (auto-updating gate status table) — V3 in origin doc
- Deployed metrics dashboard (GitHub Pages from `pipeline_metrics.jsonl`) — V5 in origin doc

---

## System-Wide Impact

- **New root `README.md`** — first impression surface for the repo. Must not break any existing CI or tooling (none reference a root README).
- **New CI workflow** — `health-digest.yml` adds one weekly cron job. Uses minimal resources (reads files, queries GitHub API, ~2-5 minute runtime). No impact on existing workflows.
- **No changes to existing workflows** — the digest is purely additive. No existing CI file is modified.
- **No new Python dependencies** — all data collection uses existing tools (`pipeline_metrics.py`, `check_script_sunset.py`, `temper dsn check`, bash, `github-script`).

---

## Dependencies / Assumptions

- All 7 existing workflows have badge-producing triggers (verified: all have `push` or `schedule` triggers with `main` branch scope)
- `pipeline_metrics.jsonl` is committed to the repo and accessible during checkout (verified: `metrics-record.yml` commits it on main push)
- GitHub Actions runner has `uv`, `python`, and `jq` available (verified: `ubuntu-latest` includes these; `astral-sh/setup-uv@v4` provides uv)
- `temper dsn check` is available after `uv sync --all-packages` (verified: the `temper-drc` package is in the workspace)
- The repo owner has GitHub Issues notifications enabled for this repo (to notice the digest)
- The repo's default branch is `main` (verified: workflow triggers target `main`)

---

## Outstanding Questions

### Deferred to Implementation

- Whether to store delta snapshots as workflow artifacts or as a committed file — artifacts are simpler (no push contention) but expire after 90 days
- Exact formatting of the `digest-snapshot.json` for week-over-week deltas
- Whether inline bash or a standalone `scripts/health_digest.py` ends up being cleaner for the data-collection logic (inline is simpler for V1, but if the script grows beyond ~60 lines of bash, a standalone script with `scripts/manifest.yaml` entry becomes warranted)
