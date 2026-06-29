---
title: "feat: JSONL Storage Hardening — Artifact-Primary with Git Commit as Queryable Copy"
type: feat
status: completed
date: 2026-06-28
---

# feat: JSONL Storage Hardening — Artifact-Primary

## Summary

Switch `metrics-record.yml` from per-push auto-commit to artifact-primary storage: upload `pipeline_metrics.jsonl` as a GitHub Actions artifact, then reconcile entries from multiple concurrent pushes via a scheduled or on-demand reconciliation job that merges and commits the deduplicated JSONL back to the main branch. The main-branch JSONL remains the queryable copy that `trend-check`, `pr-perf-check`, and the dashboard read — consumers see no change.

This is a follow-up to Plan 010 (`feat: CI Profiling Regression Platform`), which built the multi-module JSONL recording pipeline and flagged auto-commit merge conflicts as a deferred risk.

---

## Problem Frame

`metrics-record.yml` runs on every push to main (including concurrent merges from multiple PR authors landing at similar times). The workflow appends records to `power_pcb_dataset/metrics/pipeline_metrics.jsonl` and auto-commits via a `git pull --rebase` retry loop (3 attempts, 5s backoff). Three profiling modules (pipeline closure, loss-function, router-bench) write to the same JSONL file per push via `pipeline_metrics.py record --from-stdin`.

At current commit frequency (~1-2 pushes/hour), the retry loop handles conflicts. However, the retry loop has a fundamental flaw: if two concurrent pushes both succeed on attempt 3, each push only contains the records appended by _its own_ workflow run — the records from the other concurrent push are lost. The `git pull --rebase` brings in the other push's commit, but the workflow's JSONL was already written before the rebase; after rebase, the new commit is created from the pre-rebase state. Only the last committer's records survive.

Plan 010's risk table flagged this and deferred artifact-primary storage. With pipeline observability (Plan 011) adding per-stage data collection, the record volume per push grows, accelerating the conflict rate.

---

## Requirements

- **R1. Artifact upload.** `metrics-record.yml` uploads the JSONL file (or generated records) as a GitHub Actions artifact instead of auto-committing.
- **R2. Reconciliation.** A separate reconciliation step merges artifacts from all pushes within a configurable window, deduplicates by `(git_commit, module, stage)`, sorts by timestamp, and commits the reconciled JSONL.
- **R3. Consumer compatibility.** `metrics-trend-check.yml`, `pr-perf-check.yml`, and the dashboard continue to read `pipeline_metrics.jsonl` from the main branch with no change to their fetch logic.
- **R4. Deduplication.** Append-only merge: sort by timestamp, deduplicate by `(git_commit, module, stage)` key. Existing committed records take priority over artifact records (first loaded wins). If two artifact records collide on the same key, the first encountered artifact record wins.
- **R5. No record loss.** Every record produced by a metrics-record run must appear in the reconciled JSONL. The reconciliation job reads all uploaded artifacts, not just the latest.
- **R6. Graceful degradation.** If reconciliation fails (e.g., no artifacts found), the main-branch JSONL remains at its last known state. Consumers are unaffected.

---

## Scope Boundaries

- **In scope:** Remove auto-commit from `metrics-record.yml`, add artifact upload, create reconciliation workflow, add deduplication logic.
- **Out of scope:** Changing the JSONL schema or consumer workflows (they are consumers of the reconciled file, not participants in storage).
- **Deferred to Follow-Up Work:** Artifact retention policy monitoring (GitHub's 90-day default is sufficient; if a reconciliation window spans >90 days we'd need a backstop), multi-repo aggregation, artifact-based trend analysis (bypassing the committed copy).

---

## Context & Research

### Relevant Code and Patterns

- `.github/workflows/metrics-record.yml:68-80` — current auto-commit pattern with `git pull --rebase` retry loop and `secrets.GITHUB_TOKEN`.
- `.github/workflows/metrics-record.yml:63-67` — already uploads `pipeline_report.html` as an artifact (`actions/upload-artifact@v4`). Same pattern extended to JSONL.
- `scripts/pipeline_metrics.py` — `record` subcommand with `--from-stdin` flag reads NDJSON from stdin. Reconciliation will use the same NDJSON format as intermediate artifact payload.
- `power_pcb_dataset/metrics/pipeline_metrics.jsonl` — 126 lines, ~39KB. Three modules × ~600 bytes per push = ~1.8KB per commit.
- `.github/workflows/pr-perf-check.yml:42-46` — fetches main-branch JSONL via `git show origin/main:path` (sparse fetch, no clone). Consumer pattern unchanged.
- `.github/workflows/metrics-trend-check.yml` — weekly cron reads JSONL from main-branch checkout.
- `dashboard/` — GitHub Pages dashboard reads JSONL from `gh-pages` branch copy (deployed separately via `dashboard-deploy.yml`).

### Institutional Learnings

- **Metrics auto-commit fragility (Plan 010, Institutional Learnings):** `metrics-record.yml` uses `git pull --rebase` with retry. Works at current commit frequency but creates merge conflicts with concurrent pushes. _This plan directly addresses that learning._
- **Plan 022's earlier design note:** The JSONL auto-commit merge-conflict risk was flagged in Plan 022's risk table (2026-06-22-022, line 393-399), recommending artifact-based backup.
- **Plan 011's deferred item:** Plan 011's risk table lists "JSONL auto-commit merge conflicts" as a low-likelihood risk but acknowledges it and defers mitigation.

---

## Key Technical Decisions

- **K1: Artifact-primary, not artifact-only.** The committed JSONL file remains the authoritative queryable copy. The artifact is the append buffer — reconciliation flushes the buffer to the file. This preserves all consumer workflows exactly as-is.

- **K2: Reconciliation via scheduled cron, not per-push.** A scheduled workflow (e.g., every 30 minutes or every N pushes) downloads all unreconciled artifacts, merges, deduplicates, and commits. This eliminates the race condition entirely: the reconciliation job is the only writer to the JSONL file.

- **K3: Artifact naming convention.** Each `metrics-record.yml` run uploads an artifact named `pipeline-metrics-{run_id}-{run_attempt}.ndjson`. The reconciliation job downloads all artifacts matching `pipeline-metrics-*`, merges their contents, and commits. Record-level timestamp sort within the reconciliation script ensures deterministic ordering.

- **K4: Deduplication key = `(git_commit, module, stage)`.** Two pushes recording the same commit+module+stage are duplicates. First by `timestamp` wins. This handles the case where re-triggered workflows produce identical records (e.g., after a workflow dispatch re-run).

- **K5: Reconciliation job is idempotent.** If the reconciliation job runs twice with the same artifact set, the second run produces an identical JSONL (no duplicate lines). This is guaranteed by the deduplication logic operating over the full artifact set + existing committed file.

- **K6: Artifact retention: 90 days (GitHub default).** Sufficient for reconciliation windows. If reconciliation doesn't run for 90 days, artifacts expire — but the committed JSONL retains all previously reconciled data. Expired artifacts mean unreconciled pushes' records are lost — the cron schedule (30 min) makes this effectively impossible under normal operation.

---

## High-Level Technical Design

_This illustrates the intended approach and is directional guidance for review, not implementation specification._

### Data Flow

```mermaid
flowchart TD
    PUSH1[Push to main #1] --> RECORD1[metrics-record.yml]
    PUSH2[Push to main #2] --> RECORD2[metrics-record.yml]
    PUSH3[Push to main #N] --> RECORD3[metrics-record.yml]

    RECORD1 --> PROF1[Run profilers → NDJSON]
    RECORD2 --> PROF2[Run profilers → NDJSON]
    RECORD3 --> PROF3[Run profilers → NDJSON]

    PROF1 --> ART1[Upload artifact: pipeline-metrics-{run_id}.ndjson]
    PROF2 --> ART2[Upload artifact: pipeline-metrics-{run_id}.ndjson]
    PROF3 --> ART3[Upload artifact: pipeline-metrics-{run_id}.ndjson]

    CRON["Reconciliation job
    (scheduled or on-demand)"] --> DL[Download all pipeline-metrics-* artifacts]
    DL --> FETCH[Fetch current main-branch JSONL]
    FETCH --> MERGE[Merge: sort by timestamp, deduplicate by (commit, module, stage)]
    MERGE --> COMMIT[Commit reconciled JSONL to main]

    COMMIT --> JSONL[(pipeline_metrics.jsonl on main)]
    JSONL --> TREND[metrics-trend-check.yml]
    JSONL --> PRCHECK[pr-perf-check.yml]
    JSONL --> DASHBOARD[Dashboard deploy → gh-pages]
```

### Artifact Schema

The `metrics-record.yml` workflow produces a `.ndjson` file (newline-delimited JSON) containing the exact records it would have appended to the JSONL. The reconciliation job:

1. Downloads all `pipeline-metrics-*` artifacts.
2. Reads each `.ndjson` file line-by-line into in-memory records.
3. Reads the current committed `pipeline_metrics.jsonl` from main.
4. Merges: union of all records (committed + artifact), sort by `timestamp`, deduplicate by `(git_commit, module, stage)` keeping the first occurrence.
5. Writes the merged file and commits.

### Workflow Schedule

- `metrics-record.yml`: Triggered on `push: main` and `workflow_dispatch`. Runs profilers, produces NDJSON, uploads artifact. **No longer auto-commits.**
- `metrics-reconcile.yml` (new): Triggered via `schedule` (cron: `*/30 * * * *` i.e., every 30 minutes) and `workflow_dispatch`. Downloads all unreconciled artifacts, merges, commits. Also triggered by `workflow_run` on `metrics-record.yml` completion for near-real-time reconciliation (with a concurrency gate to prevent overlapping reconciliation runs).

---

## Implementation Units

### U1. Modify `metrics-record.yml` — Remove Auto-Commit, Add Artifact Upload

**Goal:** Replace the git auto-commit step with an artifact upload step. The workflow produces an NDJSON file and uploads it.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `.github/workflows/metrics-record.yml`

**Approach:**
- Remove the "Commit and push metrics" step (lines 68-80).
- After all profiling steps, concatenate their NDJSON output into a single `pipeline-metrics.ndjson` file (each profiler pipes to a temp file; concatenation joins them).
- Upload the `.ndjson` file as an artifact named `pipeline-metrics-${{ github.run_id }}-${{ github.run_attempt }}.ndjson`.
- Retain the existing HTML report artifact upload.
- The `--from-stdin` path in `pipeline_metrics.py record` is no longer needed for CI — profilers write directly to the temp NDJSON file. (Keep `--from-stdin` for manual/local use.)

**Patterns to follow:**
- `metrics-record.yml:63-67` — existing `upload-artifact@v4` for pipeline report.
- Artifact naming: `pipeline-metrics-{run_id}-{run_attempt}.ndjson` ensures uniqueness even on re-runs.

**Verification:** After a push to main, the workflow run's "Artifacts" tab shows `pipeline-metrics-*.ndjson`. The main-branch JSONL is unchanged by this workflow.

---

### U2. Create `metrics-reconcile.yml` — Reconciliation Workflow

**Goal:** Create a new workflow that downloads all `pipeline-metrics-*` artifacts, merges them with the existing JSONL, deduplicates, and commits the reconciled file.

**Requirements:** R2, R3, R4, R5

**Dependencies:** U1

**Files:**
- Create: `.github/workflows/metrics-reconcile.yml`
- Create: `scripts/reconcile_metrics.py` (deduplication and merge logic)

**Approach:**
- Workflow triggers:
  - `schedule: cron: '*/30 * * * *'` (every 30 minutes).
  - `workflow_dispatch:` (manual trigger for backfill/debug).
  - `workflow_run: workflows: ["Metrics Record"], types: [completed]` (near-real-time, with `concurrency` group to serialize reconciliation).
- Steps:
  1. Checkout main branch (`fetch-depth: 0`, `token: ${{ secrets.GITHUB_TOKEN }}`).
  2. Download all artifacts matching `pipeline-metrics-*` via `gh api` (cross-run artifact access — `actions/download-artifact@v4` cannot access artifacts from other workflow runs). List artifacts by prefix, download each as zip, extract into an artifact directory.
  3. Run `scripts/reconcile_metrics.py`:
     - Read the current `pipeline_metrics.jsonl`.
     - Read all downloaded `.ndjson` files.
     - Merge: union of existing lines + artifact lines, deduplicate by `(git_commit, module, stage)`, sort by `timestamp`.
     - Write the reconciled `pipeline_metrics.jsonl`.
  4. If the file changed, commit and push.
  5. Delete consumed artifacts (optional; via `actions/delete-artifact` or a GH API call with `gh` CLI). Skipping this is acceptable — artifacts expire automatically.
- `concurrency: metrics-reconcile` ensures only one reconciliation runs at a time.
- Reconciliation is graceful: if no artifacts are found, the workflow exits cleanly (no-op).

**`scripts/reconcile_metrics.py` logic:**
```python
def reconcile(existing_path: Path, artifact_dir: Path, output_path: Path) -> int:
    """Merge existing JSONL with artifact .ndjson files, deduplicate, write output."""
    records: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    # Load existing committed records
    if existing_path.exists():
        for line in existing_path.read_text().strip().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    print(f"WARNING: Skipping invalid JSON line in {existing_path}", file=sys.stderr)
                    continue
                key = (r["git_commit"], r.get("module", "pipeline"), r["stage"])
                seen.add(key)
                records.append(r)

    # Load artifact records
    for ndjson_file in sorted(artifact_dir.glob("*.ndjson")):
        for line in ndjson_file.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                print(f"WARNING: Skipping invalid JSON line in {ndjson_file}", file=sys.stderr)
                continue
            key = (r["git_commit"], r.get("module", "pipeline"), r["stage"])
            if key in seen:
                continue  # deduplicate: keep first (existing > artifact)
            seen.add(key)
            records.append(r)

    # Sort by timestamp
    records.sort(key=lambda r: r.get("timestamp", ""))

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")

    return len(records)
```

**Test scenarios:**
- Happy path: Two artifacts with non-overlapping records → merged JSONL contains both sets plus existing records.
- Deduplication: Two artifacts containing records for the same `(commit, module, stage)` → only the first (by timestamp) is kept.
- Existing data preserved: Reconciliation with no new artifacts → JSONL unchanged, no commit made.
- Empty artifact dir: Reconciliation runs but `artifact_dir` has no `.ndjson` files → no changes.
- Sort stability: Records are ordered by timestamp ascending.
- Idempotency: Running reconciliation twice with the same artifacts produces the same JSONL.
- Concurrent artifact production: Two `metrics-record.yml` runs complete while reconciliation is running → next reconciliation run picks up both artifacts.

**Verification:** Manually trigger `metrics-reconcile.yml` via `workflow_dispatch`; verify the JSONL is correctly merged and committed. Run twice; verify idempotency.

---

### U3. Update Script Manifest

**Goal:** Add `scripts/reconcile_metrics.py` to `scripts/manifest.yaml` per repo conventions.

**Requirements:** None (tooling convention)

**Dependencies:** U2

**Files:**
- Modify: `scripts/manifest.yaml` (add entry for `reconcile_metrics.py`)
- Run: `uv run python scripts/trace_invocations.py`

**Approach:**
```yaml
- path: reconcile_metrics.py
  purpose: "Merge artifact-uploaded pipeline metrics NDJSON with committed JSONL, deduplicate, and sort"
  owner: bennet
  last_run: "2026-06-28"
  category: keep
  disposition: ci-gate
  imports: []
```

---

### U4. Verify Consumer Workflows (No Changes)

**Goal:** Confirm that `metrics-trend-check.yml`, `pr-perf-check.yml`, and `dashboard-deploy.yml` continue to function correctly with the reconciled JSONL.

**Requirements:** R3, R6

**Dependencies:** U2

**Files:**
- No changes expected. Verification only.

**Approach:**
- `metrics-trend-check.yml` checks out main and reads `pipeline_metrics.jsonl` from the checkout — unchanged.
- `pr-perf-check.yml` fetches main-branch JSONL via `git show origin/main:path` — unchanged.
- `dashboard-deploy.yml` reads from main-branch checkout — unchanged.
- The reconciliation job writes its commit with `[skip ci]` trailer (or a `[metrics-reconcile]` prefix) to prevent recursive workflow triggering (i.e., `metrics-record.yml` should not fire on reconciliation commits).

**Verification:** After reconciliation produces a new commit, `pr-perf-check.yml` on a test PR fetches the updated JSONL and produces a comparison. Weekly trend check runs and reads the latest data.

---

## System-Wide Impact

- **CI pipeline:** One modified workflow (`metrics-record.yml` — removes auto-commit, adds artifact upload), one new workflow (`metrics-reconcile.yml` — scheduled + on-demand). Consumer workflows unchanged.
- **Repository layout:** New `scripts/reconcile_metrics.py`, new `scripts/manifest.yaml` entry. No changes to `power_pcb_dataset/metrics/` layout.
- **Artifact storage:** Each `metrics-record.yml` run uploads a ~2KB `.ndjson` artifact. GitHub Actions retains artifacts for 90 days. At current push frequency, ~10 artifacts/day × 2KB = ~20KB/day. Negligible.
- **Commit history:** Reconciliation commits are batched — instead of one commit per push, one commit per reconciliation window (30 min). Commits use `[skip ci]` or a distinct author to avoid triggering recursive workflows.
- **Developer workflow:** No change. PR authors still get perf delta comments. Developers still run `pipeline_metrics.py trend` locally against the committed JSONL.
- **Error propagation:** Reconciliation failures do not block CI. If reconciliation fails, the main-branch JSONL remains at the last successfully reconciled state. Artifacts accumulate and are picked up on the next successful reconciliation.
- **Unchanged invariants:** The committed `pipeline_metrics.jsonl` format is identical. All consumer workflows operate as before. The JSONL remains append-only in spirit (reconciliation is a batch append).

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Reconciliation job fails to run for >90 days, artifacts expire, records lost | Cron schedule ensures regular runs. `workflow_dispatch` allows manual reconciliation. Artifact retention is 90 days — far longer than the 30-min cron interval. Dashboard can alert on file staleness. |
| Reconciliation commits trigger `metrics-record.yml` (recursive workflow) | Commit message includes `[skip ci]` or `[metrics-reconcile]` prefix. `metrics-record.yml` already only triggers on `push: branches: [main]` — if needed, add a path filter excluding commits that only touch `pipeline_metrics.jsonl`. |
| Reconciliation job and a concurrent push race on `git push` | `concurrency: metrics-reconcile` serializes reconciliation runs. The standard `git pull --rebase && git push` retry loop handles the rare case where a human push conflicts with reconciliation. |
| High artifact count (thousands) makes download slow | `gh api` downloads artifacts individually; each is ~2KB zipped. At 1000 artifacts = 2MB total. Well within GitHub API rate limits for scheduled cron runs. |
| `workflow_run` trigger creates too-frequent reconciliation | Cron is the primary trigger. `workflow_run` is optional and can be omitted if it causes excessive runs. With `concurrency`, overlapping runs queue rather than fail. |
| `gh api` artifact listing picks up artifacts from other workflows | Artifact naming convention (`pipeline-metrics-*`) is distinct from existing artifacts (`pipeline-report`). Prefix filter via `--jq` ensures only target artifacts are downloaded. |
| Reconciliation downtime during GitHub Actions outages | Artifacts persist for 90 days. The backlog is reconciled when the outage ends. No data loss within the retention window. |

---

## Dependencies / Prerequisites

- **Upstream:** Plan 010 (`feat: CI Profiling Regression Platform`) — this plan hardens the storage layer built by Plan 010. Plan 010 must be complete (metrics-record.yml, multi-module profiling, JSONL schema v2).
- **New dependencies introduced:** None — all tooling uses existing GitHub Actions built-ins (`upload-artifact@v4`), `gh` CLI (pre-installed on `ubuntu-latest` runners), and standard Python stdlib (`json`, `pathlib`).
- **Downstream unblocks:** Plan 011 (`feat: Pipeline Observability`) adds per-stage recording — the hardened storage layer from this plan ensures those additional records don't exacerbate merge conflicts. Plan 011's risk table entry ("JSONL auto-commit merge conflicts") can be resolved as mitigated.

---

## Success Criteria

- **SC1.** `metrics-record.yml` no longer auto-commits to main. Workflow artifacts contain the expected NDJSON records.
- **SC2.** `metrics-reconcile.yml` runs on schedule (every 30 minutes) and produces a reconciled `pipeline_metrics.jsonl` with all records from concurrent pushes present and deduplicated.
- **SC3.** Running reconciliation twice with the same artifact set produces an identical JSONL file (idempotent).
- **SC4.** `pr-perf-check.yml` on a test PR fetches main-branch JSONL and produces a correct comparison against PR metrics — no change from current behavior.
- **SC5.** Weekly `metrics-trend-check.yml` runs successfully against the reconciled JSONL.
- **SC6.** After 3 concurrent pushes to main, the reconciled JSONL contains records from all 3 pushes (no record loss).

---

## Sources & References

- Plan 010: `docs/plans/2026-06-28-010-feat-ci-profiling-regression-platform-plan.md` — risk table entry "JSONL auto-commit merge conflicts" (line 525).
- Plan 011: `docs/plans/2026-06-28-011-feat-pipeline-observability-plan.md` — risk table entry "JSONL growth" (line 414).
- Plan 020 (original metrics time-series): `docs/plans/2026-06-22-020-feat-pipeline-metrics-timeseries-plan.md` — risk table entry "Concurrent main-branch pushes cause JSONL merge conflicts" (line 214).
- Plan 022 (per-stage timing gate): `docs/plans/2026-06-22-022-feat-per-stage-timing-regression-gate-plan.md` — risk table entry referencing auto-commit fragility.
- Existing workflows: `.github/workflows/metrics-record.yml`, `.github/workflows/pr-perf-check.yml`, `.github/workflows/metrics-trend-check.yml`, `.github/workflows/dashboard-deploy.yml`
- Metrics recorder: `scripts/pipeline_metrics.py`
- Metrics schema: `packages/temper-placer/src/temper_placer/regression/metrics_recorder.py`
- Data file: `power_pcb_dataset/metrics/pipeline_metrics.jsonl`
- GitHub Actions docs: `actions/upload-artifact@v4`, `actions/download-artifact@v4`
