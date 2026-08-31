---
title: Repo ratsnest cleanup — whole-repo audit and phased cleanup sequence
type: feat
date: 2026-08-19
topic: repo-ratsnest-cleanup
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-only
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Repo Ratsnest Cleanup — Whole-Repo Audit and Phased Cleanup Sequence

## Goal Capsule

**Objective:** Audit four accumulated tangles of defensive scaffolding,
dual-ownership shims, and sprawl. Rank each by cleanup ROI. Produce a
phased, gradual cleanup sequence where every phase is a low-risk,
independently mergeable PR, verified by an existing CI gate or oracle.

**Constraint:** This is a planning document only. No code is modified.
Each phase names the specific files/areas touched, the verification gate
that proves safety, and the dependencies on prior phases.

---

## Base-Commit Assertion

`scripts/assert-base.sh origin/main` was run at session start. It FAILED:
HEAD was 4 commits behind `origin/main` (on branch `spike/decomposition-map`).
A worktree was created from `origin/main` (`eb5022510`) for this plan.
All inventory below is measured against that commit.

---

## Tangle 1: Python/Rust Shim Debt

### Inventory

**Scale:**
- 462 Python source files in `packages/temper-placer/src/temper_placer/`
- 275 of those (60%) import at least one Rust pyo3 extension crate
- 172 `*_py_oracle.py` differential test files across `packages/temper-placer/tests/` and `packages/temper-workflow/tests/`
- 10 pyo3/maturin extension crates under `packages/` (temper-geometry, temper-orchestration, temper-thermal, temper-drc-rs, temper-io-types, temper-quality-oracle, temper-design-bundle, temper-constraint-compiler, temper-rust-router, temper-py-bridge)
- temper-orchestration alone exports 89 `add_function` registrations; temper-thermal exports 54

**Shim categories identified (by inspection of representative files):**

| Category | Description | Example files | Count (est.) | State |
|---|---|---|---:|---|
| **Pure delegation** | Entire body is a Stage subclass whose `run()` calls one Rust function across FFI. No logic. | `deterministic/stages/zone_assignment.py`, `deterministic/stages/apply_placements.py` | ~15 | Dead Python — Rust is sole source of truth |
| **Re-export hubs** | Module-level `x = _tg.x` assignments for 10-30 functions, plus a few functions with Python-side default-arg logic | `geometry/transform.py`, `geometry/sdf.py`, `geometry/__init__.py` | ~12 | Mostly dead — defaults could move to Rust or callers |
| **Marshaling shims** | Numpy array → list/tuple conversion around a Rust kernel call | `metrics/aesthetic.py`, `metrics/quality_score.py` | ~20 | Half-migrated — marshaling is real but thin |
| **Active orchestration** | Python that coordinates multiple Rust calls, handles control flow, error handling | `deterministic/feedback/orchestrator.py`, `router_v6/corridor.py` | ~50 | Real logic — not a shim |
| **No Rust dependency** | Pure Python modules (config types, CLI, etc.) | `_constraint_types/`, `__main__.py` | ~187 | Out of scope for this tangle |

**Existing infrastructure that makes deletion safe:**
- `scripts/check_orphaned_python_modules.py` — fails when a production Python module has zero importers
- `scripts/check_pyo3_duplicate_registration.py` — catches shadowed pyfunction registrations
- `scripts/check_unwired_kernels.py` — catches Rust kernels registered but never called from Python
- `_*_py_oracle.py` pattern — 172 verbatim differential oracles pin pre-migration behavior
- `docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md` — the established progressive-strangler methodology

**Existing plans this tangle overlaps with:**
- `docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md` — re-scores 42 NEVER-PORT rows; identifies 1,564 LOC as DELETE
- `docs/plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md` — adds "retire" stage to the migration pipeline
- `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` — the active migration program

### ROI Rating: **HIGH**

The largest tangle by dead-code volume. The existing oracle infrastructure
(172 differential tests) makes deletion provably safe — the standing rule
is "fix Rust → prove against Python with oracle → delete Python → keep
oracle." The effort is mechanical (identify pure shims, verify oracle
exists, delete, run CI) and the benefit is immediate: fewer dual-ownership
confusion points, smaller import graph, less stale-extension surface area.
Risk is low because each deletion is gated by an existing oracle test.

### Phased Cleanup Sequence

#### Phase 1.1: Delete pure-delegation stage shims (lowest risk)

**Files:** `deterministic/stages/zone_assignment.py`,
`deterministic/stages/apply_placements.py`, and other stage files whose
entire body is a `Stage` subclass calling `_to.run_X(state)`.

**Method:**
1. For each candidate, grep for importers: `rg "from temper_placer.deterministic.stages.zone_assignment import" --include='*.py'`
2. Verify the corresponding oracle exists (e.g. `tests/deterministic/_zone_assignment_py_oracle.py`)
3. Rewire each importer to call `temper_orchestration.run_zone_assignment(state)` directly
4. Delete the Python stage file
5. Run `scripts/check_orphaned_python_modules.py` to confirm no remaining importers

**Verification gate:** `pytest tests/deterministic/ -k zone_assignment` + `scripts/check_orphaned_python_modules.py` + CI's `Required Python Tests`

**Risk:** Minimal. The Python file adds zero logic — it is a one-line FFI forward. The oracle already pins the behavior.

#### Phase 1.2: Collapse re-export hubs to direct Rust imports

**Files:** `geometry/transform.py`, `geometry/sdf.py`, `geometry/__init__.py`

**Method:** These files do `x = _tg.x` for most symbols. For each:
1. Identify which re-exports have external importers (grep for `from temper_placer.geometry.transform import x`)
2. Rewire importers to `from temper_geometry import x` (or `import temper_geometry as _tg; _tg.x`)
3. For the few functions with Python-side default-arg logic (e.g. `rotation_index_to_onehot` with `n_angles=4`), either: (a) move the default into the Rust pyfunction signature, or (b) keep only those specific functions and delete the re-exports
4. Delete the re-export lines / the file if fully collapsed

**Verification gate:** `pytest tests/geometry/` + `scripts/check_orphaned_python_modules.py` + import-linter boundary check

**Risk:** Low. Re-exports are identity assignments. The only subtlety is default-arg threading.

#### Phase 1.3: Retire marshaling shims where Rust can accept numpy arrays directly

**Files:** `metrics/aesthetic.py`, `metrics/quality_score.py`, and similar files whose body is numpy → list conversion + one Rust call.

**Method:** These shims exist because the Rust pyfunction expects Python lists, not numpy arrays. Two options:
- (a) Modify the Rust pyfunction to accept `numpy.ndarray` via pyo3's numpy bindings (if the crate already depends on `numpy` feature)
- (b) Keep the marshaling but move it into a shared utility, reducing per-file boilerplate

Prefer (a) where the crate already has numpy support; (b) where it does not. Each retirement is a separate PR.

**Verification gate:** `pytest tests/metrics/` + corresponding oracle test + `make extensions-check`

**Risk:** Medium. Modifying Rust pyfunction signatures touches the pyo3 boundary. Must run `make extensions` and `check_stale_extensions.py` after each change.

#### Phase 1.4: Audit `__init__.py` re-export surface

**Files:** All `__init__.py` files in `temper_placer/` that re-export Rust symbols.

**Method:** After phases 1.1-1.3 collapse the direct shim files, many `__init__.py` re-exports will have no remaining consumers. Run `scripts/check_orphaned_python_modules.py` to identify them and remove the dead re-exports.

**Verification gate:** `scripts/check_orphaned_python_modules.py` + `vulture_gate.py` + CI

**Risk:** Low. Removing unused re-exports is a pure deletion.

### Dependencies

- Phase 1.1 → independent, land first
- Phase 1.2 → independent of 1.1, can land in parallel
- Phase 1.3 → depends on 1.2 (importers must be rewired before Rust signature changes)
- Phase 1.4 → depends on 1.1, 1.2, 1.3 (cleans up after all shim deletions)

---

## Tangle 2: Script Sprawl

### Inventory

**Scale:**
- 119 scripts in `scripts/manifest.yaml` (2,993 lines of manifest)
- Categories: 115 `keep`, 0 `ticket`, 0 `delete` (40 already deleted per `_meta.ticket_scripts_deleted`)
- Dispositions: 112 `ci-gate`, 55 `utility`, 5 `shell-invoked`, 1 `spike`, 1 `measurement`, 1 `manual-tool`, 1 `library`
- `last_audit_date`: 2026-08-05

**Sunset clock status (as of 2026-08-19):**
- 0 scripts at 60+ days (ESCALATE) — the 60-day clock has not fired for any script
- 42 scripts at 30-59 days (WARNING) — predominantly CI gates and utilities whose `last_run` was last updated 2026-06-22 through 2026-07-23

**Observation:** The 42 WARNING scripts are mostly active CI gates (`ci_check_drc.py`, `check_manifest_gate.py`, `check_coverage_gate.py`, `import_linter_gate.py`, etc.) and utility scripts (`add_power_planes.py`, `generate_kicad_dru.py`, `trace_invocations.py`). Their `last_run` dates are stale not because the scripts are dead, but because the manifest's `last_run` field is updated manually and nobody updates it when CI runs the script automatically. The sunset clock is producing false-positive warnings on actively-used CI gates.

**Potential consolidation targets (by inspection):**
- `pipeline_metrics.py`, `pipeline_report.py`, `reconcile_metrics.py` — three metrics-related utilities that may overlap
- `pr_perf_compare.py`, `pr_scorecard.py` — two PR-scoring scripts
- `bench_coarse_to_fine.py`, `bench_rust_constraints.py`, `bench_rust_geometry.py` — benchmark scripts, possibly consolidatable
- `spc_rules.py`, `slo_evaluator.py` — SPC/SLO utilities that may be unused
- `gen_architecture_poster.py`, `gen_schematics.py` — generation utilities

### ROI Rating: **MEDIUM**

The manifest is already well-maintained (0 delete/ticket, 40 already
deleted). The primary issue is not dead scripts but a sunset clock that
produces false-positive WARNINGs on actively-used CI gates because
`last_run` is manually maintained. The benefit of cleanup is moderate
(reduces noise, potentially consolidates a few overlapping utilities),
the effort is low (refresh dates, audit a handful of consolidation
candidates), and the risk is low (CI gates are protected by the manifest
gate itself).

### Phased Cleanup Sequence

#### Phase 2.1: Refresh `last_run` dates for active CI gates

**Files:** `scripts/manifest.yaml`

**Method:** For each of the 42 WARNING scripts, determine whether it is actively used:
- CI gates: check `.github/workflows/` for references
- Utility scripts: check `scripts/trace_invocations.py` output and recent git history
- Update `last_run` to 2026-08-19 for confirmed-active scripts
- Flag genuinely stale scripts for triage in phase 2.2

**Verification gate:** `scripts/check_script_sunset.py` (should report 0 WARNINGs after refresh)

**Risk:** None. Pure metadata update.

#### Phase 2.2: Triage genuinely stale utility scripts

**Files:** Candidates: `spc_rules.py`, `slo_evaluator.py`, `gen_architecture_poster.py`, `debug_diff_pair_path.py`, `full_pipeline_profile.py`, `profile_router_v6_sampling.py`, `profile_rust_topology.py`

**Method:** For each:
1. `rg "<script_name>" --include='*.py' --include='*.yml' --include='*.yaml' --include='Makefile'` to find callers
2. If zero callers and not in any workflow: change `category` to `ticket`, create a triage issue
3. If confirmed dead after ticket triage: `category: delete` → `git rm`

**Verification gate:** `scripts/check_manifest_gate.py` + `scripts/check_script_sunset.py`

**Risk:** Low. Scripts are only deleted after explicit triage with a ticket.

#### Phase 2.3: Audit consolidation candidates

**Files:** `pipeline_metrics.py` / `pipeline_report.py` / `reconcile_metrics.py`, `pr_perf_compare.py` / `pr_scorecard.py`, bench scripts

**Method:** For each cluster:
1. Read all scripts in the cluster, compare their function and CLI surface
2. If they share >50% logic: propose a merge (one PR per cluster)
3. If they are genuinely independent: update their purposes in the manifest to disambiguate

**Verification gate:** Manual review + `scripts/check_manifest_gate.py`

**Risk:** Low-medium. Merging scripts changes their CLI surface; verify no workflow references break.

#### Phase 2.4: Fix the sunset clock's false-positive problem

**Files:** `scripts/check_script_sunset.py`, possibly `scripts/manifest.yaml` schema

**Method:** The sunset clock fires WARNING at 30 days for CI gates that run on every PR. Two options:
- (a) Add a `ci_scheduled: true` flag to manifest entries; the sunset clock skips CI-gate scripts that are referenced in `.github/workflows/`
- (b) Have `check_script_sunset.py` automatically check `.github/workflows/` for references and skip scripts found there

Prefer (b) — it requires no manifest schema change and is self-maintaining.

**Verification gate:** `scripts/check_script_sunset.py` (should report 0 false-positive WARNINGs)

**Risk:** Low. The sunset clock is a warning, not a hard gate.

### Dependencies

- Phase 2.1 → independent, land first
- Phase 2.2 → depends on 2.1 (triage the scripts 2.1 flags as genuinely stale)
- Phase 2.3 → independent of 2.1/2.2
- Phase 2.4 → independent, can land anytime

---

## Tangle 3: DRC Ceiling Machinery

### Inventory

**Scale:**
- `power_pcb_dataset/drc_ceiling.json`: 133 lines, 1 board (`temper`), 13 violation types, 39 `_march` log entries
- `scripts/ci_check_drc.py`: 201 lines — CI entry point, runs DRC, checks ceiling (exit 1), noise headroom (exit 3), cap saturation (exit 4)
- `scripts/check_drc_ceiling_approval.py`: 348 lines — enforces `Ceiling-Approval:` trailer + `_march` entry + provenance for raises (R27 monotone contract)
- `scripts/check_measurement_provenance.py`: 668 lines — verifies content hash, commit resolvability, dirty flag on every PR touching a measurement artifact
- `DrcRatchet` class in `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`: methods `check()`, `detect_ceiling_raise()`, `check_noise_headroom()`, `validate_raise_evidence()`, `find_ceiling_raises()`
- `scripts/calibrate_drc_ceiling.py`: utility for re-measurement
- `scripts/measure_uncapped_drc.py`: recovers true counts above kicad-cli's saturation cap
- `scripts/generate_kicad_dru.py`: regenerates the DRU file (required before any DRC run)

**Guard inventory — what each closes:**

| Guard | File | Gap closed | Redundant? |
|---|---|---|---|
| Ceiling comparison | `ci_check_drc.py` → `DrcRatchet.check()` | Board exceeds committed ceiling | No — the core check |
| Noise headroom | `ci_check_drc.py` → `DrcRatchet.check_noise_headroom()` | Single-sample DRC run can noise-fail a clean board | No — without it, a 1-spread category at max+0 ceiling would flake |
| Cap saturation | `ci_check_drc.py` exit 4 | kicad-cli truncates at 199/499; a capped count can hide a ceiling violation | No — without it, a saturated category is a vacuous pass |
| Raise approval | `check_drc_ceiling_approval.py` | A PR silently raises a ceiling without attribution | No — `ci_check_drc.py` only checks current board vs ceiling, never detects a raise |
| Provenance identity | `check_measurement_provenance.py` | A measurement's content hash doesn't match the board, or the commit is dangling, or the tree was dirty | No — closes the 2026-08-07 orphaned-commit incident |
| DRU regeneration | `ci_check_drc.py::_regenerate_kicad_dru` | Stale/absent DRU file makes creepage read 0 | No — without it, DRC is meaningless |

**Assessment:** The machinery is complex but **not redundant**. Each guard
closes a distinct, documented gap with a named incident behind it. The
`_march` log is verbose (39 entries) but is the single cause authority for
ceiling changes — removing it would destroy traceability. The
provenance check is large (668 lines) but covers three independent
invariants (content hash, commit resolvability, dirty flag) that each
closed a real incident.

**Minor redundancy / simplification opportunities:**
- `check_measurement_provenance.py` (668 lines) and `check_drc_ceiling_approval.py` (348 lines) both load and parse `drc_ceiling.json` independently. A shared loader could reduce duplication.
- The `_march` log mixes string entries and structured entries; standardizing on structured entries would make programmatic querying easier.
- `ci_check_drc.py`'s docstring is ~80 lines of inline documentation that duplicates content in AGENTS.md and `drc_ceiling.json`'s own `_goal` header. The docstring could be shortened to cross-references.
- The noise-headroom guard invariant (`ceiling - max(observed) >= max(observed) - min(observed)`) is documented in 4 places (AGENTS.md, `ci_check_drc.py` docstring, `drc_ceiling.json` `_goal`, `drc_ratchet.py` docstring). Consolidating to one canonical source with cross-references would reduce drift risk.

### ROI Rating: **LOW**

The machinery is safety-critical and each guard closes a documented gap.
The cleanup opportunities are limited to documentation consolidation and
shared-loader refactoring — reducing duplication without removing any
guard. The benefit is modest (less documentation drift, slightly less
code duplication) and the risk is high (any change to safety-relevant
code requires re-verification against the incident it prevents). The
effort is medium (careful refactoring + documentation work).

### Phased Cleanup Sequence

#### Phase 3.1: Extract shared `drc_ceiling.json` loader

**Files:** `scripts/check_measurement_provenance.py`, `scripts/check_drc_ceiling_approval.py`, `scripts/ci_check_drc.py`

**Method:** All three scripts independently load and parse `drc_ceiling.json`. Extract a shared `scripts/_lib/drc_ceiling.py` with a single `load_ceiling(path) -> DrcCeilingData` function. Rewire all three scripts to use it.

**Verification gate:** All three scripts' existing tests pass. `pytest tests/ -k drc_ceiling -k provenance -k approval`

**Risk:** Low. Pure refactor of loading logic; no guard behavior changes.

**Safety argument:** The shared loader returns the same parsed data structure each script already constructs. No comparison logic changes. The existing tests for each guard prove the behavior is preserved.

#### Phase 3.2: Consolidate noise-headroom documentation

**Files:** AGENTS.md "Board Change -> DRC Ceiling Re-measurement" section, `ci_check_drc.py` docstring, `drc_ceiling.json` `_goal` header, `drc_ratchet.py` docstring

**Method:** The noise-headroom invariant is explained in 4 places. Designate `drc_ratchet.py`'s `NoiseHeadroomViolation` docstring as the canonical source (it is the implementation). Replace the other 3 copies with a one-line cross-reference: "See `temper_placer.regression.drc_ratchet.NoiseHeadroomViolation` for the invariant and its proof."

**Verification gate:** No code change. Manual review that the cross-references resolve.

**Risk:** None. Pure documentation change.

#### Phase 3.3: Standardize `_march` entry format

**Files:** `power_pcb_dataset/drc_ceiling.json`, `scripts/check_drc_ceiling_approval.py`

**Method:** The `_march` log currently mixes bare strings (early entries) with structured entries. This is a one-way migration: convert bare-string entries to structured `{"date": "...", "cause": "...", "per_type_delta": {...}}` format. No new entries are created — this is a format normalization of existing entries.

**Verification gate:** `check_drc_ceiling_approval.py` still passes on the reformatted file. `ci_check_drc.py` still loads and validates.

**Risk:** Low-medium. The `_march` log is the cause authority; reformatting must preserve all information. Do this only if phase 3.1's shared loader makes the format change a single-point edit.

**Safety argument:** No guard behavior changes. The `_march` entries' content is preserved; only their JSON shape changes. The approval gate's "NEW non-empty `_march` entry" check still works because it checks for new entries, not the format of existing ones.

### Dependencies

- Phase 3.1 → independent, land first
- Phase 3.2 → independent of 3.1, can land in parallel
- Phase 3.3 → depends on 3.1 (shared loader must handle both formats during migration)

### What this plan does NOT propose

- **Removing any guard.** Every guard closes a documented gap. The noise-headroom guard, cap-saturation guard, raise-approval gate, and provenance check are all load-bearing.
- **Simplifying the R27 monotone contract.** The "ceilings may only decrease; raises require attribution" contract is the core safety invariant.
- **Deleting the `_march` log.** It is the single cause authority for ceiling changes.
- **Reducing the 120-sample requirement.** The nondeterminism is documented and measured; the sample count is the minimum that bounds the observed spread.

---

## Tangle 4: Worktree/Venv Infra

### Inventory

**Scale:**
- `scripts/check_stale_extensions.py`: 907 lines — per-crate freshness gate (content-hash + mtime fallback)
- `scripts/check_venv_integrity.py`: 497 lines — venv identity gate (editable-install pointers resolve to expected repo root)
- `scripts/check_stash_stack_gate.py`: 106 lines — stash reflog snapshot/diff detector (manual, not CI)
- `scripts/check_no_worktree_target_dirs.py`: 180 lines — detects private cargo target dirs in worktrees
- `scripts/install_cargo_target_dir_guard.py`: 233 lines — installs PATH wrapper for shared CARGO_TARGET_DIR
- `scripts/install_git_stash_guard.py`: 104 lines — installs ref-transaction hook blocking `git stash push/save/clear`
- `scripts/git-hooks/reference-transaction`: the hook itself

**The 5 documented poisoning modes and their guard coverage:**

| Mode | Description | Guard that closes it | Still needed? |
|---|---|---|---|
| 1. `maturin` refuses (CONDA_PREFIX + VIRTUAL_ENV) | Loud failure | None needed — fails loudly | Documentation only |
| 2. `uv run maturin develop` targets per-worktree venv | Silent no-op against shared venv | `make venv-isolate` or `check_stale_extensions.py` (mtime/content-hash) | Guard exists |
| 3. `maturin develop --active` rewrites shared venv pointers | Silent hijack | `check_venv_integrity.py` | Guard exists |
| 4. `maturin develop` reports "Installed" without replacing .so | Silent stale | `check_stale_extensions.py` (content-hash, not mtime) | Guard exists |
| 5. Shared venv reads `main`, not your worktree | Silent wrong-code | `make venv-isolate` or manual `import` path check | Partial — no automated gate |

**Assessment:** The guards are layered defense-in-depth, each closing a
specific documented failure mode. The primary issue is not redundant
guards but **redundant documentation**: the AGENTS.md sections on
worktree/venv infrastructure are extremely verbose (the "Worktree .venv"
section alone is ~400 lines, the "Git Stash Guard" section is ~120 lines,
the "Shared cargo build cache" section is ~80 lines). Much of this is
incident narrative that could be moved to `docs/evidence/` with a
cross-reference, leaving AGENTS.md with the operational rules only.

**Simplification opportunities:**
- Mode 1 (CONDA_PREFIX + VIRTUAL_ENV) is a loud failure — the AGENTS.md documentation of it is informational only and could be a one-line note.
- Mode 2 is closed by `check_stale_extensions.py`'s content-hash gate — the "per-worktree venv no-op" scenario is caught because the shared venv's .so is never updated, so the freshness gate reports STALE.
- Mode 3 is closed by `check_venv_integrity.py` — this guard runs in CI before the staleness gate.
- Mode 4 is closed by `check_stale_extensions.py`'s content-hash comparison (not mtime).
- Mode 5 (shared venv reads main) is only partially closed — there is no automated gate that checks "the venv I'm importing from is built from MY worktree's sources." `make venv-isolate` is the defense, but it is opt-in.

**Consolidation opportunities:**
- `check_stale_extensions.py` (907 lines) is the largest script. Its size is justified by its module docstring (which documents the "Installed but not replaced" incident in detail). The docstring could be moved to `docs/evidence/` to shrink the script.
- `check_venv_integrity.py` (497 lines) similarly has a large docstring documenting the 2026-08-11 incident. Same treatment.
- The two installers (`install_cargo_target_dir_guard.py`, `install_git_stash_guard.py`) are small and focused — no consolidation needed.

### ROI Rating: **MEDIUM**

The guards themselves are necessary and non-redundant (each closes a
distinct poisoning mode). The cleanup opportunity is primarily
**documentation consolidation**: moving incident narratives out of
AGENTS.md and script docstrings into `docs/evidence/`, leaving operational
rules and cross-references. The benefit is reduced AGENTS.md size (which
agents must read at session start) and reduced documentation drift. The
effort is medium (careful extraction + cross-referencing). The risk is
low — no guard behavior changes.

### Phased Cleanup Sequence

#### Phase 4.1: Extract incident narratives from AGENTS.md to docs/evidence/

**Files:** AGENTS.md sections: "Worktree .venv: shared vs. isolated", "Four ways a worktree silently poisons the venv", "The fifth mode", "Git Stash Guard", "Shared cargo build cache"

**Method:** Each of these sections contains a mix of:
- **Operational rules** (what to do / not do) — keep in AGENTS.md
- **Incident narratives** (what happened, when, why) — move to `docs/evidence/`
- **Design rationale** (why the guard exists, what it catches) — move to the guard script's module docstring or a `docs/solutions/` entry

For each section:
1. Extract the incident narrative to `docs/evidence/<date>-<topic>.md`
2. Extract the design rationale to `docs/solutions/best-practices/<topic>.md`
3. Replace the AGENTS.md section with a condensed operational rule + cross-reference

**Target:** Reduce the AGENTS.md worktree/venv/stash sections from ~600 lines to ~150 lines of operational rules.

**Verification gate:** Manual review that cross-references resolve. No code change.

**Risk:** None. Pure documentation reorganization.

#### Phase 4.2: Shrink guard script docstrings by cross-referencing evidence docs

**Files:** `scripts/check_stale_extensions.py`, `scripts/check_venv_integrity.py`

**Method:** Both scripts have 100+ line module docstrings documenting incidents in detail. After phase 4.1 creates the evidence docs, replace the detailed incident narrative in the docstring with a 5-line summary + cross-reference to the evidence doc.

**Verification gate:** `pytest tests/ -k stale_extensions -k venv_integrity` (docstring changes don't affect behavior, but run tests to confirm no accidental edits)

**Risk:** None. Docstring-only change.

#### Phase 4.3: Add automated check for mode 5 (shared venv reads wrong checkout)

**Files:** New check script or extension to `check_venv_integrity.py`

**Method:** Mode 5 (shared venv serves `main`'s code to a worktree agent) is the only poisoning mode without an automated gate. Add a check that:
1. If `VIRTUAL_ENV` points to the shared `.venv` (not a worktree-isolated one)
2. And the current working directory is a worktree (not the main checkout)
3. Warn that imports will resolve to `main`'s code, not the worktree's

This is a WARNING, not a hard failure — `make venv-isolate` is the documented fix.

**Verification gate:** Manual test from a worktree with shared venv.

**Risk:** Low. Warning-only; no build-breaking behavior.

### Dependencies

- Phase 4.1 → independent, land first
- Phase 4.2 → depends on 4.1 (evidence docs must exist before cross-referencing)
- Phase 4.3 → independent of 4.1/4.2

---

## Overall Ranking and Recommended Sequencing

| Rank | Tangle | ROI | Effort | Risk | First phase |
|---:|---|---|---|---|---|
| 1 | Python/Rust shim debt | HIGH | Medium | Low | Phase 1.1 (pure delegation shims) |
| 2 | Worktree/venv infra docs | MEDIUM | Medium | None | Phase 4.1 (AGENTS.md extraction) |
| 3 | Script sprawl | MEDIUM | Low | Low | Phase 2.1 (refresh last_run dates) |
| 4 | DRC ceiling machinery | LOW | Medium | High | Phase 3.1 (shared loader) |

### Recommended cross-tangle sequence

**Sprint 1 (low-risk, high-benefit):**
1. **Phase 1.1** — Delete pure-delegation stage shims. Highest ROI, lowest risk. Existing oracles prove safety.
2. **Phase 2.1** — Refresh `last_run` dates. Zero risk, clears 42 false-positive warnings.
3. **Phase 4.1** — Extract incident narratives from AGENTS.md. Zero risk, reduces agent context burden.

**Sprint 2 (medium-risk, medium-benefit):**
4. **Phase 1.2** — Collapse re-export hubs. Low risk, medium benefit.
5. **Phase 2.4** — Fix sunset clock false-positive problem. Low risk, reduces ongoing noise.
6. **Phase 3.1** — Extract shared DRC ceiling loader. Low risk, reduces duplication.
7. **Phase 4.2** — Shrink guard script docstrings. Zero risk, depends on 4.1.

**Sprint 3 (higher-effort, diminishing returns):**
8. **Phase 1.3** — Retire marshaling shims (Rust numpy acceptance). Medium risk, medium benefit.
9. **Phase 1.4** — Audit `__init__.py` re-exports. Low risk, cleanup after 1.1-1.3.
10. **Phase 2.2** — Triage genuinely stale utility scripts. Low risk, requires investigation.
11. **Phase 2.3** — Consolidate overlapping utility scripts. Low-medium risk.
12. **Phase 3.2** — Consolidate noise-headroom documentation. Zero risk.
13. **Phase 4.3** — Add mode-5 automated check. Low risk, fills the last documented gap.

**Sprint 4 (optional, lowest ROI):**
14. **Phase 3.3** — Standardize `_march` entry format. Low-medium risk, requires shared loader from 3.1.

### Key principles guiding the sequence

1. **Delete before refactor.** Phases that remove dead code (1.1, 1.2, 1.4, 2.2) land before phases that restructure live code (1.3, 3.1).
2. **Oracle-proof before rewrite.** Every Python deletion phase cites the oracle that pins the behavior being deleted.
3. **Documentation before code.** Phase 4.1 (doc extraction) lands before 4.2 (docstring shrinking) and before 4.3 (new check), because the evidence docs are prerequisites for the cross-references.
4. **Safety-relevant code last.** DRC ceiling machinery (tangle 3) is deferred to sprint 2-3 because the risk/effort ratio is highest, and the cleanup is purely structural (no guard removal).
5. **Each phase is one PR.** No phase spans more than a day of work. Each is independently mergeable and independently revertable.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Deleting a Python shim that still has an unknown importer | `scripts/check_orphaned_python_modules.py` runs in CI and will fail closed if an importer remains |
| Oracle test is stale (pinned against a Python version that has since drifted) | Re-pin the oracle before deletion: run the oracle test, confirm it passes, then delete. A re-pinned oracle is a deliberately-committed act requiring evidence. |
| Rust pyfunction signature change breaks callers | `make extensions-check` + `check_stale_extensions.py` + `check_pyo3_duplicate_registration.py` all run in CI |
| DRC ceiling loader refactor changes parsing behavior | Phase 3.1 is a pure extraction; the shared loader returns the same data structure. Existing tests for all three scripts prove preservation. |
| AGENTS.md doc extraction loses operational rules | Phase 4.1 explicitly separates rules (stay) from narratives (move). Manual review required. |
| Sunset clock fix (phase 2.4) misses a workflow reference | `check_script_sunset.py` is a warning, not a hard gate. A miss produces a WARNING, not a build break. |
| Marshaling shim retirement (phase 1.3) introduces numpy ABI mismatch | Each retirement is a separate PR with `make extensions` + `check_stale_extensions.py` verification. |

---

## CI Gates to Satisfy

Every phase must pass these CI gates before merge:

- **Required Python Tests** — `pytest` suite including all oracle differential tests
- **Import boundary check** — `scripts/import_linter_gate.py`
- **Script manifest gate** — `scripts/check_manifest_gate.py` (if any script is added/removed)
- **Coverage gate** — `scripts/check_coverage_gate.py` (warn-only currently, but deletion must not remove the last test for a covered function)
- **Stale extensions gate** — `scripts/check_stale_extensions.py` (if any Rust pyfunction signature changes)
- **Venv integrity gate** — `scripts/check_venv_integrity.py` (if any extension is rebuilt)
- **DRC ceiling gates** — `ci_check_drc.py`, `check_drc_ceiling_approval.py`, `check_measurement_provenance.py` (if `drc_ceiling.json` or DRC scripts change)
- **Oracle hash gate** — `scripts/check_oracle_hashes.py` (if any oracle file is re-pinned)
- **Derived artifact gates** — `make regen-check` (if any generated file is touched)

---

## What This Plan Does NOT Propose

- Removing any DRC ceiling guard (safety-critical, each closes a documented gap)
- Removing any worktree/venv guard (each closes a documented poisoning mode)
- Removing the `git stash` prohibition or its enforcement hook
- Removing the script manifest or sunset clock
- Removing the coverage gate or import boundary check
- Any change to the R27 monotone contract
- Any change to the 120-sample DRC re-measurement requirement
- Any rewrite of Python code that still carries real orchestration logic (the ~50 active-orchestration files in tangle 1 are out of scope)
