---
date: 2026-06-28
topic: repo-health-dashboard
---

# Repo Health Dashboard

## Summary

A personal project-health surface in two V1 pieces: a root README with GitHub-native workflow badges so the repo shows CI pass/fail at a glance, and a weekly health-digest GitHub Issue that CI synthesizes coverage, golden fixtures, drift, and gate status into one briefing. Future phases (dynamic badges, auto-README, strategy dashboard, metrics observatory) are directional markers gated on V1 proving measurable value (owner reads digest within 24h for 4 consecutive weeks).

---

## Problem Frame

Temper has 7 CI workflows producing rich health signals — coverage monotonic-shrink, golden fixture parity, import-boundary enforcement, metrics time-series with drift detection, timing regression gates — but the project owner has no way to see any of it at a glance. There is no root README, no badges, and no synthesized health summary. Checking project health today means digging through individual workflow run logs or reading raw JSONL files, which doesn't happen in practice. The gap is personal visibility: "is everything healthy right now?" has no answer shorter than several minutes of CI navigation.

---

## Actors

- A1. **Project owner**: The sole consumer of this surface. Wants to know at a glance whether CI is passing, coverage is trending right, and any gates have drifted.

---

## Key Flows

- F1. **Land on the repo and check health**
  - **Trigger:** Project owner opens the GitHub repo page
  - **Actors:** A1
  - **Steps:** Opens repo → sees README with badge tier groups → red badges draw attention → clicks badge to navigate to failing workflow → investigates
  - **Outcome:** Health status assessed in under 10 seconds
  - **Covered by:** R1, R2, R3, R4

- F2. **Weekly digest arrives**
  - **Trigger:** Monday 8am cron fires the digest workflow
  - **Actors:** CI (automated), A1 (consumer)
  - **Steps:** Workflow collects data from pipeline_metrics.jsonl, coverage gate status, golden fixture results, script sunset warnings → synthesizes into a single GitHub Issue with sections per signal → assigns label `health-digest` → A1 receives notification or checks Issues tab
  - **Outcome:** One issue tells the owner everything that changed in the last week — all-clear or specific regressions
  - **Covered by:** R5, R6, R7

---

## Requirements

**README and badges**

- R1. A root `README.md` exists to host the badge matrix (R2-R4). The README includes a brief project identifier and links to key subdirectories, but its primary function is the health badge surface — the README earns its keep by surfacing CI status, not by serving as a general project landing page.
- R2. The README displays GitHub-native workflow badges (the auto-generated `badge.svg` endpoint) for each of the 7 CI workflows currently in `.github/workflows/`.
- R3. Badges are grouped under semantic tier headers in the README: **Core Health** (python-tests, firmware-tests), **Regression Gates** (placer-regression, golden-check, regression), and **Observability** (metrics-record, metrics-trend-check).
- R4. Each badge hyperlinks to the latest run of its corresponding workflow.

**Weekly health digest**

- R5. A new CI workflow (`health-digest.yml`) runs weekly (Monday 8am, matching the existing trend-check schedule) and on `workflow_dispatch` for manual triggers. To avoid a race with `metrics-trend-check.yml` (same cron), the digest reads drift-issue state as it existed before the Monday run (snapshot at schedule time).
- R6. The digest issue body contains a markdown summary with sections for: CI pass/fail status across workflows, coverage gate status (entries remaining in `.coverage-allowlist`, shrinkage trend), golden fixture parity (pass/fail per boundary), open metrics-drift issues, script sunset warnings, and import-linter boundary compliance.
- R7. The digest issue is assigned the label `health-digest`. The workflow checks for an existing open `health-digest` issue and updates it rather than creating a duplicate, so the Issues tab shows exactly one current digest.

**Digest cadence and self-monitoring**

- R8. The digest fires every week regardless of whether regressions are detected. An "all clear this week" digest is the signal that the pipeline ran and found nothing — silence would be ambiguous (did the workflow fail to run?). To mitigate notification fatigue from ~40+ "all clear" weeks per year at solo-project scale, the digest cadence is a committed experiment: review after 8 weeks of operation and consider switching to monthly "heartbeat" digests with weekly digests only when something changed.
- R9. The health-digest workflow itself is monitored. The health-digest badge is included in the README badge matrix alongside the other CI workflows, so the owner can see at a glance whether the monitoring infrastructure is healthy. Additionally, the digest workflow's failure propagates to a visible signal: if the workflow fails, its badge turns red in the README with the rest of the Observability tier.

---

## Acceptance Examples

- AE1. **Covers R2, R3, R4.** Given a visitor opens the repo page, the README renders with badges grouped under three tier headers. Clicking the "Python Tests" badge navigates to `.../actions/workflows/python-tests.yml`.
- AE2. **Covers R5, R7.** Given a Monday 8am cron trigger, the digest workflow runs, creates a new issue labeled `health-digest`, and populates it with the synthesized summary. The following Monday, the workflow finds the existing open issue and updates it in place.
- AE3. **Covers R6.** Given the digest workflow runs and coverage has shrunk (allowlist entries decreased), the digest body includes a line like "Coverage allowlist: 187 → 185 (↓2, improving)".
- AE4. **Covers R8.** Given a week with zero regressions across all signals, the digest issue body begins with "All clear — no drift, no fixture failures, no new sunset warnings" followed by the current-status summary.
- AE5. **Covers R9.** Given the health-digest workflow fails on a Monday cron run, its README badge in the Observability tier turns red, drawing attention to the monitoring infrastructure failure.

---

## Success Criteria

- The project owner can assess CI health in under 10 seconds by opening the repo page (R2).
- The weekly digest issue is the single place to check for changes — no need to visit individual workflow runs, the `.coverage-allowlist` file, or the metrics JSONL to answer "what changed this week?" (R5, R6).
- If a CI workflow breaks, a red badge in the README draws attention within one push cycle (R2).
- The system requires zero ongoing manual maintenance — badges update automatically, digest runs on cron (R8).
- V1 is considered proven when the owner reads the digest within 24 hours of publication for 4 consecutive weeks, confirming the digest habit has formed. This gates future-phase investment.

---

## Scope Boundaries

### Deferred for later

- **V2 — Custom dynamic badges**: Per-gate shields.io badges showing coverage percentage, golden fixture pass/fail grid, allowlist shrinkage rate. Requires CI steps to produce badge-status artifacts. Gates on V1 shipping and proving the digest + badge pattern.
- **V3 — CI-generated README sections**: CI updates README content (gate status table, metric trend summary) on main push so no human edits the README. Gates on V2 establishing the badge-status artifact pipeline.
- **V4 — Strategy dashboard + auto-changelog**: Auto-generated `GATE_STATUS.md` from `@req` traceability annotations. Adopt conventional commits and auto-generate `CHANGELOG.md` and GitHub Releases. Gates on V3.
- **V5 — Deployed metrics observatory**: GitHub Pages site rendering `pipeline_metrics.jsonl` as interactive charts (reusing or extending the existing `session-dashboard/` codebase). Gates on the overhead feeling worth it relative to the digest.
- GitHub Discussions, CODEOWNERS, issue/PR templates, contributor recognition, LICENSE — all community-oriented, not needed for a solo-developer project.

### Outside this product's identity

- A public-facing project website or marketing page — this is a personal visibility tool, not an external product surface.
- Real-time alerting (Slack, email, webhooks) — the digest issue and README badges are the notification surface.

---

## Key Decisions

- **GitHub-native binary badges over custom dynamic ones for V1**: Zero maintenance, works today, defers per-gate detail to V2. Binary pass/fail answers the core question ("is anything broken?") fast enough for V1.
- **Standalone digest workflow over extending trend-check**: The existing `metrics-trend-check.yml` already auto-creates drift-only issues on a different schedule. A dedicated `health-digest.yml` keeps the drift alert and the synthesis cleanly separated — one detects anomalies, the other provides the weekly briefing.
- **Weekly "all clear" digest over drift-only**: Silence is ambiguous in automated systems. A digest that says "all clear" confirms the pipeline ran; a missing digest means something failed.
- **Update-in-place over per-week duplicate issues**: A single `health-digest` issue that updates each week keeps the Issues tab clean and provides a running log in the issue's comment/edit history.

---

## Dependencies / Assumptions

- GitHub-native workflow badges are available for all 7 workflows — assumes each workflow has `push: [main]` or equivalent triggers that produce badge-able runs. (Verified: all 7 workflows have `push` or `schedule` triggers.)
- The `pipeline_metrics.jsonl` file is committed to the repo and accessible to CI (already true — `metrics-record.yml` commits it on main push).
- The digest workflow can read `.coverage-allowlist`, `import-linter-baseline.yaml`, and `docs/traceability-registry.yaml` from the checked-out repo.
- The project owner has GitHub notifications enabled for Issues in this repo (to notice the digest).

---

## Outstanding Questions

### Deferred to Planning

- [Affects R6][Technical] Exact data sources and query commands for each digest section (e.g., how to extract coverage allowlist count trend, how to query latest golden fixture results).
- [Affects R7][Technical] GitHub API approach for update-in-place — whether to use issue comments or edit the issue body directly.
- [Affects R6][Technical] Whether to include firmware-specific signals (binary size, Unity test count) in the digest, and if so, how to extract them from the firmware-tests workflow.
