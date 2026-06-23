---
title: "feat: Script Triage + Sunset — Reduce 118 Scripts"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-test-and-build-next-ideation.md
---

# feat: Script Triage + Sunset

## Summary

A two-phase debt-resolution initiative that reduces the 118-script `scripts/` directory (119 including `__pycache__`) and replaces the blanket import-linter exemption for `scripts/.*\.py`, `tools/.*\.py`, `experiments/.*\.py`, `simulation/.*\.py`, and `router-experiments/.*\.py` with per-file allowlist entries for surviving scripts only. A CI gate rejects new scripts that lack a manifest entry, and Phase 2 introduces a 30-day inactivity sunset: any script not invoked from CI, shell, or Makefile for 30 days is flagged for deletion.

This directly addresses the July 6 import-linter hard-block deadline (see plan 014, R14–R17) by shrinking the blanket exemption from 5 wildcard patterns to targeted per-file entries, eliminating noise from dead scripts on every CI gate scan.

---

## Problem Frame

### Current state

| Directory | Count | Import-linter treatment |
|-----------|-------|------------------------|
| `scripts/` | 118 | `scripts/.*\.py` blanket allowlist |
| `tools/` | 9 | `tools/.*\.py` blanket allowlist |
| `experiments/` | 14 | `experiments/.*\.py` blanket allowlist |
| `simulation/` | ~2 | `simulation/.*\.py` blanket allowlist |
| `router-experiments/` | ~3 | `router-experiments/.*\.py` blanket allowlist |
| **Total** | **~146** | 5 wildcard allowlist entries |

Of the 118 scripts in `scripts/`, only a handful are regularly invoked:
- **CI gate scripts** (5): `import_linter_gate.py`, `vulture_gate.py`, `check_coverage_gate.py`, `ci_check_drc.py`, `ci_closure_test.py`
- **Shell-invoked scripts** (~15): `internal_route.py`, `placement_quality_report.py`, `run_feedback_loop.py`, `debug_diff_pair_path.py`, `compare_drc_reports.py`, `validate_footprints.py`, `check_regression.py`, `check_perf_regression.py`, etc.
- **Utility scripts** (~10): `patch_pcb_footprint.py`, `force_drill_rule.py`, `finalize_pcb.py`, etc.
- **The remaining ~85 scripts** are experiment artifacts, duplicates (addressed by plan 005), one-off debugging tools, and dead exploration code. Many import monolith internals directly (`from temper_placer.router_v6.adapter import ...`) — each import is a time bomb on the strangler-fig endgame.

### Import-linter hard-block deadline

The existing blanket allowlist (plan 014, U7 — script audit) lists 5 wildcard patterns at `import-linter-allowlist.yaml:136-164`:

```yaml
- source: scripts/.*\.py
- source: tools/.*\.py
- source: experiments/.*\.py
- source: simulation/.*\.py
- source: router-experiments/.*\.py
```

After July 6, 2026 (R14 cutover), the import-linter gate becomes merge-blocking. Every wildcard entry is a gap in boundary enforcement. The blanket exemption means any script can import any monolith internal without detection, undermining the `core/ ⊥ router_v6/` independence contract and the public-interface-only contracts.

**Reducing scripts is a multiplier on every CI gate**: each script scanned by import-linter, ruff, vulture, and coverage measurement adds overhead and noise. Deleting 20-30% of scripts directly shrinks CI latency and reduces false-positive surface.

---

## Scope Boundaries

### In scope

- Create `scripts/manifest.yaml` declaring purpose, last-run date, owner, and import-linter disposition per script
- AST-based invocation tracing: scan CI workflows, shell scripts, Makefiles, and `uv run` patterns to build a call graph of `scripts/` invocations
- Phase 1 triage: classify every script as **keep**, **delete**, or **ticket** (needs migration before deletion)
- Delete unambiguous dead weight (≥20% reduction target for `scripts/`)
- Phase 2 sunset: scripts with no CI/CLI invocation expire after 30 days (CI flag, not auto-delete)
- Replace blanket import-linter exemption with per-file entries for surviving scripts
- CI gate: new scripts without manifest entry rejected

### Deferred

- Scripts under `tools/`, `experiments/`, `simulation/`, `router-experiments/` — Phase 1 focuses on `scripts/` as the largest and noisiest directory; the other directories follow the same pattern in a subsequent pass
- Deep refactoring of keep-category scripts to conform to public-interface boundaries
- The duplicate-script consolidation (plan 005, Track A/B/C) — that work runs independently and deletes confirmed duplicates; this plan's triage must not conflict (see Dependencies)
- Promotion of utility scripts into CLI subcommands — deferred to the source-of-truth-validation initiative

### Out of scope

- `packages/` scripts (e.g., `packages/temper-placer/scripts/`) — these live under package boundaries, not the blanket exemption
- `tools/gpbm/` and `tools/bd-*` scripts — these are the beads project-management tools, not placer tooling
- Firmware scripts under `firmware/`
- `scripts/tests/` directory — test infrastructure, not ad-hoc scripts
- `scripts/README.md` — documentation, not a script

---

## Requirements

### R1 — Manifest format (`scripts/manifest.yaml`)

Every script in `scripts/` must have a manifest entry declaring:
- `path`: filename relative to `scripts/`
- `purpose`: one-line description
- `owner`: who last modified or is responsible
- `last_run`: ISO date of last known invocation (CI, shell, or manual — initially `null` for unknown)
- `category`: `keep` | `delete` | `ticket`
- `disposition`: for `keep`: `ci-gate`, `shell-invoked`, `utility`, or `active-experiment`; for `delete`: one-line reason; for `ticket`: ticket reference
- `imports`: list of top-level import sources (populated by AST scan)

Example:
```yaml
scripts:
  - path: import_linter_gate.py
    purpose: "Import boundary enforcement CI gate wrapper"
    owner: pipeline
    last_run: "2026-06-22"
    category: keep
    disposition: ci-gate
    imports:
      - import_linter
      - yaml
```

### R2 — AST-based invocation tracing

A script (`scripts/trace_invocations.py`) scans the repo for all call sites of `scripts/` files:
1. Parse CI workflows (`.github/workflows/*.yml`) for `scripts/<name>` references
2. Parse shell scripts (`*.sh`, `Makefile`) for `scripts/<name>` references
3. Parse `uv run python scripts/<name>` and `python3 scripts/<name>` patterns in all tracked files
4. Parse `pyproject.toml` `[project.scripts]` and `[tool.*]` for script references
5. Cross-reference with `git log --diff-filter=A -- scripts/` to identify never-executed scripts (added but never invoked from tracked code)
6. Output a JSON call-graph: `{script: [caller_path, ...]}`

### R3 — Phase 1 triage: categorize into keep / delete / ticket

Every script in `scripts/` is classified into one of three buckets:

| Category | Criteria | Action |
|----------|----------|--------|
| **keep** | Invoked from CI, shell, Makefile, or actively maintained utility | Manifest entry; per-file import-linter allowlist entry |
| **delete** | No tracked invocation; no unique logic not available elsewhere; confirmed dead by `git log` review | `git rm`; manifest entry records deletion with reason |
| **ticket** | No tracked invocation but contains non-trivial unique logic worth preserving; or invoked but relies on deleted monolith internals; or a cluster of near-duplicates needing consolidation | Keep in tree, file a temper-xxx ticket, manifest entry points to ticket; 30-day sunset clock starts |

### R4 — Delete unambiguous dead weight (≥20% target)

Target: delete at least 24 scripts from `scripts/` (~20% of 118). Candidates are scripts that:
- Have no CI/CLI invocation
- Were last modified >6 months ago (or `git log` shows only bulk-churn commits, no substantive edits)
- Contain only imports, no `main()` or `if __name__` guard
- Are dead-end experiment artifacts (`test_exp*`, `verify_*`, `debug_*` without callers)
- Are `_fixed.py` / `_v2.py` supersession patterns where the canonical already absorbed the delta (plan 005 handles the confirmed duplicates; this plan catches the ones plan 005 didn't)

A terminal `git rm` batch in one PR; manifest records each deletion.

### R5 — Phase 2 sunset: 30-day inactivity expiry

Scripts in the **ticket** category (and **keep** scripts that lose their invocation path) are subject to a 30-day sunset:

1. The manifest records `last_run` for each script
2. A CI step (`scripts/check_script_sunset.py`) reads the manifest and the invocation trace
3. Any `keep` or `ticket` script whose last tracked invocation is >30 days ago triggers a **WARNING** (not a block)
4. After 2 consecutive warnings (60 days), a script in the **ticket** category auto-promotes to **delete** priority
5. **keep** scripts with stale `last_run` are flagged for human review — a CI comment on the PR, not a block
6. The sunset mechanism never auto-deletes — it flags and informs; deletion is always a human `git rm`

Sunset clock starts at plan landing date for existing scripts with unknown `last_run` (set to `2026-06-22`).

### R6 — Replace blanket import-linter exemption with per-file entries

The five wildcard entries in `import-linter-allowlist.yaml` (lines 136-164) are replaced with per-file entries for **keep**-category scripts only:

```yaml
# Before (blanket):
- source: scripts/.*\.py
  target: temper_placer\..*
  contract: .*
  reason: "Ad-hoc tooling scripts — re-evaluate in temper-xxx"

# After (per-file):
- source: scripts/import_linter_gate\.py
  target: temper_placer\..*
  contract: .*
  reason: "CI gate script — imports temper_placer internals for boundary enforcement"
  ticket: temper-xxx
```

Scripts in the **ticket** category get per-file entries with the sunset ticket reference. **delete**-category scripts are removed from the allowlist (since they're deleted from the tree).

This shrinks the blanket exemption from 5 wildcard entries to N per-file entries where N = number of surviving scripts, and the per-file granularity means each entry can be individually justified and eventually removed when the script is refactored to use public interfaces.

### R7 — CI gate: new scripts without manifest entry rejected

A CI step enforces that every `scripts/*.py` file has an entry in `scripts/manifest.yaml`:

1. The gate script (`scripts/check_manifest_gate.py`) reads the manifest and `ls scripts/*.py`
2. Any `.py` file in `scripts/` not in the manifest → **FAIL**, message: `Script '<name>' has no manifest entry. Add an entry to scripts/manifest.yaml before committing.`
3. Any manifest entry with `category: delete` but the file still exists → **FAIL**, message: `Script '<name>' is marked for deletion in manifest but still tracked. Run 'git rm scripts/<name>' before committing.`
4. The gate runs as part of the existing `python-tests.yml` workflow (alongside the import-linter and vulture gates)
5. The existing `paths:` trigger for `scripts/**` in `python-tests.yml` already covers this gate

---

## Key Technical Decisions

### 1. Manifest as YAML, not Python dataclass

YAML is human-editable without Python knowledge, integrates with the existing `.importlinter` YAML ecosystem, and avoids adding a runtime dependency. The manifest is validated by CI, not imported at runtime. Consistent with `import-linter-baseline.yaml` and `import-linter-allowlist.yaml` conventions.

### 2. AST-based tracing, not runtime profiling

Runtime tracing would require executing every script across every possible board — infeasible for 118 scripts. AST-based tracing is a one-time static scan of the repo's CI workflows, shell scripts, and Makefiles. It captures the call graph, not runtime coverage. The invocation trace is the authoritative source for `last_run` dates.

### 3. Triage is a one-time audit, sunset is ongoing

Phase 1 is a batch classification of all 118 scripts done once. Phase 2 is a persistent CI mechanism that runs on every PR to detect scripts drifting toward dead weight. The two phases compose: Phase 1 sets the baseline, Phase 2 prevents recurrence.

### 4. Delete is terminal and irreversible — and that's the point

Scripts that pass the deletion criteria are `git rm`'d. Git history retains them. No archive directory, no `legacy/` folder. The consolidation log (`docs/consolidation-log.md` from plan 005) records each deletion with a one-line rationale and a git SHA so the deleted content is recoverable. This prevents the "deleted but not really" anti-pattern where scripts accumulate in an archive that nobody reads.

### 5. 30-day sunset clock, not 30-day auto-delete

Auto-deleting scripts from CI is too aggressive — it could break a manual workflow that happens on a 6-week cycle. The sunset mechanism flags and informs via CI warning; the actual `git rm` is always a human decision. After 60 days of warnings, scripts auto-promote to **delete** priority in the manifest, making them visible in `bd ready` as debt-resolution tasks.

### 6. Import-linter per-file entries use regex patterns

For scripts that import from multiple packages, the allowlist entry uses a broad `contract: .*` pattern (matching all contracts) but narrows the `source` to the specific script file. This is the minimum-change path to replace the blanket exemption: the `source` pattern shrinks from `scripts/.*\.py` to `scripts/<specific_file>\.py`, but the `contract` stays broad until each script is individually refactored. Future work can tighten `contract` per-script as boundaries are respected.

### 7. Phase 1 targets `scripts/` only

`tools/`, `experiments/`, `simulation/`, and `router-experiments/` are smaller (9, 14, ~2, ~3 files) and have different ownership patterns. Phase 1 delivers the biggest impact per effort-hour by targeting the 118-script directory. The other directories follow the same manifest + sunset pattern in Phase 3 (deferred).

---

## Implementation Units

### Phase 0 — Scaffolding (lands first as a standalone PR)

**U0. Create `scripts/manifest.yaml`**

- **Files:** `scripts/manifest.yaml` (new)
- **Steps:**
  1. Create the YAML file with a header explaining the format and conventions
  2. Include a commented template block that contributors copy-paste for new scripts
  3. Populate with entries for the 5 known CI gate scripts (`import_linter_gate.py`, `vulture_gate.py`, `check_coverage_gate.py`, `ci_check_drc.py`, `ci_closure_test.py`) — these are confirmed **keep**, so they serve as the example entries
  4. Include a `_meta` section with `last_audit_date: 2026-06-22` and `total_scripts: 118`

- **Acceptance:** `scripts/manifest.yaml` exists, parses as valid YAML, contains the template and the 5 CI gate entries. The 5 entries are accurate (correct purpose, correct imports).

---

### Phase 1 — Triage (PRs 1-3)

**U1. Build invocation tracer (`scripts/trace_invocations.py`)**

- **Files:** `scripts/trace_invocations.py` (new)
- **Steps:**
  1. Parse `.github/workflows/*.yml` with PyYAML; extract all `run:` and `working-directory:` steps; match `scripts/<filename>` patterns
  2. Parse all `*.sh` files and `Makefile` in repo root; match `scripts/<filename>` with word-boundary awareness
  3. Parse all tracked Python files for `"scripts/<name>"` string arguments (the `python scripts/` and `uv run python scripts/` patterns)
  4. Parse `pyproject.toml` for `[project.scripts]` entries pointing into `scripts/`
  5. Build a JSON call graph mapping each `scripts/<name>.py` to its caller paths
  6. Cross-reference with `git log --diff-filter=A -- 'scripts/*.py'` to flag scripts that were added but never invoked from any tracked file
  7. Output the call graph to `scripts/invocation_graph.json` (committed, so CI can diff it)

- **Acceptance:** Run `uv run python scripts/trace_invocations.py`; output `scripts/invocation_graph.json` maps each script to its callers. Scripts like `import_linter_gate.py` show callers in `.github/workflows/python-tests.yml`. Dead scripts show empty caller lists.

**U2. Triage: classify all 118 scripts**

- **Files:** `scripts/manifest.yaml` (populate all 118 entries)
- **Steps:**
  1. Run U1's tracer to get the invocation graph
  2. For each of the 118 scripts, classify based on:
     - **Has CI/CLI caller** → `keep` + appropriate disposition (`ci-gate`, `shell-invoked`, `utility`)
     - **No caller, has `main()` / `if __name__`, last modified <6 months** → `ticket` (may be a manual tool worth preserving)
     - **No caller, last modified >6 months, experiment artifact** → `delete` (dead weight)
     - **Duplicate / supersession pattern** → if not handled by plan 005, flag as `ticket` with a pointer to the canonical
  3. For each `ticket` script, create a `bd create` issue with a brief description of what the script does and why it needs a disposition decision
  4. For each `delete` script, record the deletion rationale in the manifest (one line)

- **Acceptance:** `scripts/manifest.yaml` has 118 script entries, each with `category`, `disposition`, and `purpose`. At least 24 scripts (20%) are categorized as `delete`. Every `ticket` script has a `ticket` field with a valid `temper-xxx` reference.

**U3. Delete Phase 1 dead weight**

- **Files:** `git rm` 24+ scripts marked `delete` in the manifest
- **Steps:**
  1. `git rm` each script in the `delete` category
  2. Update `scripts/manifest.yaml` to remove entries for deleted scripts (or mark them as `deleted` with `deletion_date` and `deletion_sha`)
  3. Append an entry to `docs/consolidation-log.md` summarizing the deletion batch: date, count, representative examples, rationale class
  4. Verify `ls scripts/*.py | wc -l` shows the reduced count
  5. Verify no remaining tracked file references deleted scripts (U1's tracer confirms zero callers)

- **Acceptance:** `scripts/` contains ≤94 `.py` files (≥20% reduction). `git ls-files scripts/` shows only surviving scripts. No CI workflow, shell script, or Makefile references a deleted script (verified by U1 re-run).

**U4. Create ticket-anchored sunset entries for ticket-category scripts**

- **Files:** Ticket references in `scripts/manifest.yaml`
- **Steps:**
  1. Run `bd create` for each unique disposition decision needed (not one ticket per script — batch by disposition class)
  2. Example batch tickets:
     - `temper-xxx`: "Disposition: 12 experiment validation scripts in scripts/ — archive or delete?"
     - `temper-xxx`: "Refactor 8 utility scripts to use public interfaces (import-linter cleanup)"
     - `temper-xxx`: "Consolidate 5 debug/diagnose scripts into unified CLI tool"
  3. Update each `ticket` manifest entry with the ticket reference
  4. Set `last_run: "2026-06-22"` for ticket-category scripts (sunset clock starts)

- **Acceptance:** Every `ticket`-category script has a non-null `ticket` field. Batch tickets exist in the issue tracker.

---

### Phase 2 — Sunset CI Enforcement (PR 4)

**U5. Create sunset check script (`scripts/check_script_sunset.py`)**

- **Files:** `scripts/check_script_sunset.py` (new)
- **Steps:**
  1. Read `scripts/manifest.yaml`
  2. Read `scripts/invocation_graph.json` (committed, regenerated by U1)
  3. For each **keep** script: if its `last_run` is >30 days ago AND the invocation graph shows zero callers → **WARNING**: `Script '<name>' is marked 'keep' but has no tracked invocation in 30 days. Verify it is still needed or reclassify as 'ticket'.`
  4. For each **ticket** script: if its `last_run` is >30 days ago → **WARNING**: `Script '<name>' has been in 'ticket' category for >30 days with no invocation. Resolve ticket <ref> or reclassify as 'delete'.`
  5. For each **ticket** script with `last_run` >60 days ago → escalated warning: `Script '<name>' has been in 'ticket' category for >60 days. Auto-promoting to 'delete' priority. Create a PR to delete it.`
  6. Exit 0 in all cases (warnings only — sunset never blocks PR merge)
  7. On main branch pushes, the script writes updated `last_run` dates back to the manifest based on the invocation graph (auto-update in CI, committed by CI bot or human on next PR that touches the manifest)

- **Acceptance:** `uv run python scripts/check_script_sunset.py` produces warnings for stale scripts, exits 0. Modifying a `last_run` date to >30 days ago triggers the warning.

**U6. Replace blanket import-linter exemption with per-file entries**

- **Files:** `import-linter-allowlist.yaml` (modify lines 136-164)
- **Steps:**
  1. Remove the 5 wildcard entries (`scripts/.*\.py`, `tools/.*\.py`, `experiments/.*\.py`, `simulation/.*\.py`, `router-experiments/.*\.py`)
  2. Add per-file entries for every **keep**-category script in `scripts/`:
     ```yaml
     - source: scripts/<name>\.py
       target: temper_placer\..*
       contract: .*
       reason: "<purpose from manifest>"
       ticket: temper-xxx
     ```
  3. Add per-file entries for every **ticket**-category script, with the ticket reference from the manifest
  4. Verify `uv run python scripts/import_linter_gate.py` exits 0 (no new violations from existing scripts)
  5. Verify that adding a new `scripts/new_script.py` that imports from `temper_placer.core` WITHOUT a corresponding allowlist entry causes the import-linter gate to FAIL

- **Acceptance:** `import-linter-allowlist.yaml` contains no wildcard entries for `scripts/`, `tools/`, `experiments/`, `simulation/`, or `router-experiments/`. Instead, it contains N per-file entries for surviving scripts. `uv run python scripts/import_linter_gate.py` exits 0.

**U7. Create manifest gate script (`scripts/check_manifest_gate.py`)**

- **Files:** `scripts/check_manifest_gate.py` (new)
- **Steps:**
  1. List all `scripts/*.py` files (excluding `__pycache__`, `tests/`)
  2. Read `scripts/manifest.yaml` entries
  3. For each `.py` file NOT in the manifest → **FAIL**: `Script '<name>' has no manifest entry. Add an entry to scripts/manifest.yaml.`
  4. For each manifest entry with `category: delete` where the file still exists → **FAIL**: `Script '<name>' is marked for deletion but still tracked.`
  5. For each manifest entry where `imports` is empty → **WARNING**: `Script '<name>' has no imports listed. Run trace_invocations.py to populate.`
  6. Exit 0 if no violations (manifest validation only — import-linter enforcement is U6's concern)

- **Acceptance:** Creating a new `scripts/foo.py` without a manifest entry causes `check_manifest_gate.py` to exit non-zero. Deleting the file or adding a manifest entry resolves the failure.

**U8. Wire gates into CI**

- **Files:** `.github/workflows/python-tests.yml` (add steps)
- **Steps:**
  1. Add a step after "Import boundary enforcement" for the manifest gate:
     ```yaml
     - name: Script manifest gate
       run: uv run python scripts/check_manifest_gate.py
     ```
  2. Add a step after the manifest gate for the sunset check:
     ```yaml
     - name: Script sunset check (warnings only)
       run: uv run python scripts/check_script_sunset.py
       continue-on-error: true  # warnings, not blocks
     ```
  3. Add path trigger entries to the `paths:` lists:
     ```yaml
     - 'scripts/manifest.yaml'
     - 'scripts/invocation_graph.json'
     - 'scripts/check_manifest_gate.py'
     - 'scripts/check_script_sunset.py'
     - 'scripts/trace_invocations.py'
     ```
  4. Verify all three gates (import-linter, manifest, sunset) run in CI and report results

- **Acceptance:** Push to a PR branch; `python-tests.yml` runs the manifest gate and sunset check. Deliberately missing manifest entry → CI fails. Stale last_run → CI warning.

---

### Phase 3 — Documentation and Follow-up (PR 5)

**U9. Update developer documentation**

- **Files:** `AGENTS.md`, `AGENT_INSTRUCTIONS.md` (as applicable)
- **Steps:**
  1. Add a section to the "Quick Reference" explaining the script manifest convention:
     ```markdown
     ### Adding a New Script
     
     1. Add an entry to `scripts/manifest.yaml` with purpose, owner, and imports
     2. If the script imports from `temper_placer` internals, add a per-file entry to `import-linter-allowlist.yaml`
     3. The CI manifest gate rejects scripts without manifest entries
     ```
  2. Document the sunset mechanism: scripts unused for 30 days are flagged; 60 days escalates
  3. Document the invocation tracer: run `uv run python scripts/trace_invocations.py` to update the call graph after adding new CI/shell callers

- **Acceptance:** Documentation is clear; a new contributor can follow it to add a script without hitting CI failures.

**U10. Record the triage in `docs/consolidation-log.md`**

- **Files:** `docs/consolidation-log.md` (append)
- **Steps:**
  1. Append a Phase 1 triage summary: date, initial count, deleted count, ticket count, keep count
  2. List representative deletion rationales by class (experiment artifact, superseded, dead import-only, etc.)
  3. Cross-reference the duplicate-script consolidation (plan 005) — note any boundary cases where both plans touched the same script
  4. Record the plan reference for future auditors

- **Acceptance:** `docs/consolidation-log.md` has a triage summary entry. Future contributors can understand what was deleted and why.

---

## Files Changed Summary

| File | Action | Unit |
|------|--------|------|
| `scripts/manifest.yaml` | **Create** | U0, U2 |
| `scripts/trace_invocations.py` | **Create** | U1 |
| `scripts/invocation_graph.json` | **Create** (committed) | U1 |
| `scripts/check_script_sunset.py` | **Create** | U5 |
| `scripts/check_manifest_gate.py` | **Create** | U7 |
| `import-linter-allowlist.yaml` | Modify — replace 5 wildcard entries with per-file entries | U6 |
| `.github/workflows/python-tests.yml` | Modify — add manifest + sunset steps | U8 |
| `docs/consolidation-log.md` | Modify — append triage summary | U3, U10 |
| `AGENTS.md` | Modify — document manifest convention | U9 |
| ~24 `scripts/*.py` | **Delete** (`git rm`) | U3 |

---

## System-Wide Impact

- **`scripts/`** — reduced from 118 to ≤94 `.py` files (≥20% reduction). Gains 4 new infrastructure scripts (`manifest.yaml`, `trace_invocations.py`, `invocation_graph.json`, `check_script_sunset.py`, `check_manifest_gate.py`). Net reduction: ≥20 files.
- **`import-linter-allowlist.yaml`** — 5 wildcard entries replaced with N per-file entries (N ≈ keep + ticket count). No functional regression; import-linter gate continues to pass.
- **`.github/workflows/python-tests.yml`** — 2 new CI steps (manifest gate, sunset check). Both run in <5 seconds (YAML parse + set comparison). Total CI latency increase: negligible.
- **`docs/`** — `consolidation-log.md` gains a triage summary entry. No new docs files.
- **No firmware, no PCB schematics, no placer algorithm changes.** This is a repo-hygiene + CI-gate-hardening initiative.

---

## Dependencies

- **Plan 005 (Duplicate-Script Consolidation):** Must land first or coordinate boundaries. Plan 005 deletes confirmed duplicates (`scripts/strip_routing*.py`, root `run_router_v6_*.py`, root `batch_validate_power_pcb_fixed.py`). This plan's Phase 1 triage must not re-classify those files (they'll already be deleted). The triage script should skip files already absent from `git ls-files`.
- **Plan 014 (Import-Linter Boundary Enforcement):** The July 6 hard-block deadline is the motivating constraint. This plan's U6 (per-file entries) must land before July 6 to replace the blanket exemption before the soft-launch cutover.
- **Plan 010 (Placer Regression Infrastructure):** Not a dependency, but the regression gate may add new `scripts/` entries. Those entries must follow the manifest convention (U7 gate catches missing entries).
- **`import-linter` itself:** Must remain installed as a dev dependency (already handled by plan 014, U1).

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Triage misclassifies an actively-used script as `delete` | Low | High — breaks a manual workflow | U1 invocation tracer is the ground truth. Every `delete`-category script must have zero callers in the tracer output. Manual review of the `delete` list before `git rm` in PR. Git history preserves the file. |
| Per-file allowlist entries cause import-linter CI noise | Medium | Low — CI failures on unrelated PRs | U6 verification step: run `import_linter_gate.py` after swapping blanket for per-file entries; must exit 0 before merge. |
| Manifest drifts out of sync with actual `scripts/` | Medium | Medium — CI gate becomes untrustworthy | U7 manifest gate enforces manifest ↔ filesystem consistency on every PR. Drift is detected at the next PR that touches `scripts/` or the manifest. |
| Sunset warnings are ignored (alert fatigue) | High | Low — dead scripts persist | Warnings are informational only; they don't block PRs. The auto-promotion at 60 days makes stale scripts visible in `bd ready` as debt-resolution tasks. If still ignored, the scripts are benign dead weight, not active risk. |
| Invocation tracer misses dynamic callers (e.g., `eval`, `subprocess` with constructed paths) | Medium | Medium — false "dead" classification | The tracer scans for string literal patterns only. Dynamic callers are rare in this codebase (verified: no `eval`-based script dispatch found). If a dynamic caller exists, it's caught at PR review when the author objects to the deletion. |
| Blanket exemption removal causes CI failures for `tools/`, `experiments/`, etc. | Low | Medium — unexpected failures in other directories | U6 only removes the `scripts/` blanket entry. `tools/`, `experiments/`, etc. blanket entries remain until Phase 3 (deferred). The removal is scoped to `scripts/.*\.py` only. |
| Phase 1 triage takes longer than estimated (118 scripts to classify) | Medium | Low — deadline pressure for July 6 | Triaged in waves: first pass classifies obvious keep/delete by automated criteria (CI invocation + git log age). Second pass classifies the remainder with human judgment. The 20% deletion target is achievable from automated criteria alone. |

---

## Success Criteria

1. `scripts/` reduced from 118 to ≤94 `.py` files (≥20% reduction) — verified by `ls scripts/*.py | wc -l`
2. `import-linter-allowlist.yaml` contains zero wildcard entries for `scripts/` — replaced by per-file entries for surviving scripts
3. `uv run python scripts/import_linter_gate.py` exits 0 with per-file entries (no regression)
4. Creating a new `scripts/foo.py` without a manifest entry causes CI to fail with a named message
5. `scripts/manifest.yaml` has entries for all 118 original scripts (deleted scripts recorded with deletion date + SHA, surviving scripts with purpose + category + imports)
6. A script with `last_run` >30 days ago triggers a CI warning (not a block)
7. CI runtime for the two new gate steps (manifest + sunset) is <5 seconds combined

---

## Sequencing

```
PR 1 (Phase 0):  manifest.yaml scaffolding + 5 CI gate entries
PR 2 (Phase 1a): trace_invocations.py + invocation_graph.json + full triage
PR 3 (Phase 1b): git rm dead scripts + per-file import-linter entries (U3 + U6 combined)
PR 4 (Phase 2):  sunset check + manifest gate + CI wiring
PR 5 (Phase 3):  documentation updates + consolidation log entry
```

PRs 1-2 can be developed in parallel with plan 005 (different files). PR 3 (deletions) must await plan 005's deletions to avoid merge conflicts. PR 4-5 are independent.
