---
title: "feat: Wholesale stale-directory purge"
type: feat
status: completed
date: 2026-06-23
origin: docs/brainstorms/2026-06-23-wholesale-stale-dir-purge-requirements.md
---

# feat: Wholesale Stale-Directory Purge

## Summary

Execute the wholesale deletion of `archive/`, the root `experiments/`, and `router-experiments/` from version control in a single draft-first PR with seven commits (three deletion commits — one per directory — plus the pre-flight import-linter update, the smoke-test commit, the script-deletion commit, and the blame-ignore follow-up). The PR updates `.git-blame-ignore-revs` and `.gitignore` for blame hygiene, updates the import-boundary CI gate in `scripts/import_linter_gate.py` to drop the deleted dirs from its Phase 3 scan and clean up the now-stale `import-linter-allowlist.yaml` entries, deletes three experiment-specific shell scripts that hardcode paths into the deleted `experiments/temper-a98v/`, and adds a smoke test that guards the production `from experiments.diff_pair.coupled_router` import against silent failure. The PR opens as draft first to surface any unforeseen breakage before review.

---

## Problem Frame

See the origin document for the full situational narrative (`docs/brainstorms/2026-06-23-wholesale-stale-dir-purge-requirements.md`). The plan's specific framing: the deletion is mechanically simple, but three tool-side dependencies must be updated in lockstep — the import-linter gate that scans the deleted dirs, three shell scripts that hardcode paths into the deleted `experiments/temper-a98v/`, and the `*.gitignore` block that targets the deleted dir. Each of these is a small change, but missing any one breaks CI or leaves a dangling reference. The plan's structure is "delete + update dependents + verify" in that order.

---

## Requirements

All eight R-IDs trace to the origin document. The plan advances each of them.

- R1. `archive/` is removed from version control in a single commit (271 tracked files, 45MB).
- R2. The root `experiments/` is removed from version control in a single commit (56 tracked files, 6.8MB).
- R3. `router-experiments/` is removed from version control in a single commit (111 tracked files, 952KB).
- R4. The package's `experiments/` namespace (`packages/temper-placer/experiments/` and `packages/temper-placer/src/temper_placer/experiments/`) is not touched in either of its two forms.
- R5. `.git-blame-ignore-revs` gains three new lines (one per deletion commit); each deletion commit message references the file.
- R6. `.gitignore` orphan entries targeting the deleted dirs are removed.
- R7. After merge, pytest passes, the production import in `sequential_routing.py:44` still resolves, the Vulture gate (when landed) does not gain new findings.
- R8. `git ls-files archive/ experiments/ router-experiments/` returns zero results.

---

## Scope Boundaries

Inherited from the origin document; the plan executes them, not re-litigates them.

- `packages/temper-placer/experiments/` and `packages/temper-placer/src/temper_placer/experiments/` — production-coupled, not in scope (R4).
- The 33 root `*.md` status reports — already deferred per the purge-and-protect plan.
- `deadcode-baseline.py` stale entries — the Vulture gate's responsibility, not this PR's.
- History rewriting via `git filter-repo` — out of scope.
- Pre-commit framework adoption — out of scope.

### Deferred to Follow-Up Work

- The docstring reference `experiments/diff_pair/` in `scripts/measure_usb_baseline.py:214` documents a closed bd epic (`temper-qlni`, consolidated into `temper-dxuj`). The reference is documentation-only — no code uses the path. Defer to a future docs-cleanup pass alongside other stale bd-epic doc references.

---

## Context & Research

### Relevant Code and Patterns

- **`scripts/import_linter_gate.py:163`** — defines `PHASE3_DIRS = ("tools", "experiments", "simulation", "router-experiments")`. The Phase 3 scan walks these directories looking for `temper_placer.*` imports. When `experiments` and `router-experiments` are deleted, the scan must be updated to drop them — otherwise it scans a non-existent path. Same pattern is used in the print message at line 355-356.
- **`scripts/run_temper_a98v_full.sh`**, **`scripts/run_temper_a98v_poc.sh`**, **`scripts/verify_temper_a98v_all_routing.sh`** — three experiment-runner scripts that hardcode `experiments/temper-a98v/` paths (`RESULTS_DIR="experiments/temper-a98v"`, config file paths, etc.). Not called by any CI workflow (`.github/workflows/*.yml` confirmed). Safe to delete.
- **`.gitignore:98-100`** — three lines that target the deleted dir: `experiments/temper-a98v/*.kicad_pcb`, `experiments/temper-a98v/*.json`, `experiments/temper-a98v/*.log`. Become orphan and must be removed (R6).
- **`.git-blame-ignore-revs`** — already exists at the repo root with one entry (`c2522d8e...`) from the purge-and-protect work. New entries append; the existing entry remains.
- **`packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py:43-49`** — wraps the production import in `try/except ImportError`. The smoke test (U5) guards this silent-failure path.
- **CI workflow** — `.github/workflows/python-tests.yml:53-54` calls `uv run python scripts/import_linter_gate.py` as the "Import boundary enforcement" step. This is the CI gate that U3 keeps passing.
- **Purge-and-protect plan** — `docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md` is the closest analog. It executes a similar `git rm --cached` + `.gitignore` + `.git-blame-ignore-revs` pattern for root-level files. The plan follows the same two-commit sequence for blame-ignore (a commit cannot contain its own hash).

### Institutional Learnings

- `docs/solutions/tooling-decisions/import-linter-boundary-enforcement-ratchet-2026-06-22.md` — the import-linter gate is ratcheting: existing entries are allowlisted, new entries fail CI. The plan's U3 update is a baseline adjustment, not a ratchet violation; the deleted dirs were allowlisted entries whose import surface is now gone.

### External References

None. The plan operates entirely on local git mechanics and the existing import-linter gate.

---

## Key Technical Decisions

- **Three commits in one PR, draft-first.** Per origin: one commit per directory, blame-ignore-revs entries stay clean, `git bisect` can step over each deletion. The PR opens as draft (per the brainstorm's deferred question, resolved here) to surface any unforeseen breakage before review — the deletion is large (438 files) and a draft run catches import failures, hidden CI dependencies, or other surprises without a review round-trip.
- **`git rm -r --cached` per directory, not per file.** All 271 files in `archive/` are deleted in one `git rm -r --cached archive/` command, and likewise for the other two. The per-file pattern in the purge-and-protect plan is not needed here because the directories are uniformly deletable (no live importers).
- **Update import-linter gate inline, not as a separate baseline bump.** When `experiments` and `router-experiments` are removed from `PHASE3_DIRS`, the gate's per-file allowlist entries for those dirs (if any) become stale. The plan updates the tuple and the print message; stale-allowlist cleanup is left to the ratchet's normal flow.
- **Delete the experiment scripts outright, not preserve them in `archive/`.** The scripts are tightly coupled to the deleted `experiments/temper-a98v/` results dir; their entire purpose was running that one experiment. Without the results dir, they have no purpose. (If a contributor later wants the experiment re-runnable, the experiment design is in `temper-65nd/RUN_EXPERIMENT.md` and the configs are in the bd issue `temper-65nd` history — recoverable from git.)
- **Smoke test lives in `packages/temper-placer/tests/routing/`, not in `packages/temper-placer/src/`.** Tests live under `tests/`. The import is at `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`; the test asserts the import resolves, then asserts `COUPLED_ROUTER_AVAILABLE is True` after the import. It also asserts the `try/except` fallback path sets the flag to `False` when the module is mocked-as-missing — protecting against the silent-failure mode.
- **No `deadcode-baseline.py` cleanup in this PR.** The only baseline entry referencing a deleted-dir path is `required_length_mm # unused variable (packages/temper-placer/experiments/diff_pair/geometry.py:62)` — and that path is the **package's** experiments, not the root one (R4: out of scope). No baseline entries reference the root `experiments/`, `archive/`, or `router-experiments/`. The Vulture gate (when landed) will handle any future drift.

---

## Open Questions

### Resolved During Planning

- [Affects R1-R3][Process] Draft-first or direct? Resolved: draft first. The deletion is 438 files; a draft run surfaces hidden dependencies (e.g., the import-linter gate, the shell scripts) before review.
- [Affects R7][Verification] Smoke test or rely on CI? Resolved: smoke test. The production import is wrapped in `try/except ImportError`; CI's existing test suite does not exercise that code path because no test imports `SequentialRoutingStage` with a stubbed-out `experiments.diff_pair.coupled_router`. The test guards both the happy path and the fallback.
- [Affects R6][Technical] Are there orphan `.gitignore` entries? Resolved: yes, three lines targeting `experiments/temper-a98v/*` at `.gitignore:75-77`. Removed in U2.

### Deferred to Implementation

- [Affects U1][Process] Exact `git rm -r --cached` invocation. The plan prescribes the command shape; the implementer runs the three commands, confirms the per-directory file counts (271/56/111), and records each commit's hash for the blame-ignore update.
- [Affects U1][Process] Whether the deletion PR is opened against `main` or a feature branch. Standard repo convention is a feature branch named after the plan (e.g., `feat-wholesale-stale-dir-purge`); confirm at implementation time.
- [Affects U3][Verification] Whether the import-linter gate's allowlist has any entries that reference `experiments/` or `router-experiments/` paths. `import-linter-allowlist.yaml` should be searched; if entries exist, decide whether to remove them in this PR or let the ratchet catch them.

---

## Implementation Units

### U1. Wholesale directory deletion (3 commits, 1 draft PR)

**Goal:** Remove 438 tracked files across three directories from version control.

**Requirements:** R1, R2, R3, R4, R8

**Dependencies:** None (U3 and U5 are pre-flight changes that land in the same PR but before the deletion commits, so the PR contains a sensible commit sequence even if the implementer chooses a different order).

**Files:**
- Modify: 271 tracked files in `archive/`
- Modify: 56 tracked files in `experiments/`
- Modify: 111 tracked files in `router-experiments/`

**Approach:**

The PR contains five logical commits in this order (U3 and U5 are pre-flight; U1 is three deletion commits; U2 is the blame-ignore follow-up; U4 is the script deletions):

1. **U3 commit** — drop `experiments` and `router-experiments` from `PHASE3_DIRS` and the print message in `scripts/import_linter_gate.py`. This must land before the deletion commits so the import-linter gate is not run against non-existent paths mid-PR.
2. **U5 commit** — add the smoke test file. The test asserts that the import path resolves to the package's `experiments/`, not the deleted root one. Lands before the deletion so it provides a guard during subsequent steps.
3. **U1 commit 1** — `git rm -r --cached archive/`. One commit. Message references `.git-blame-ignore-revs`.
4. **U1 commit 2** — `git rm -r --cached experiments/`. One commit. Message references `.git-blame-ignore-revs`.
5. **U1 commit 3** — `git rm -r --cached router-experiments/`. One commit. Message references `.git-blame-ignore-revs`.
6. **U4 commit** — delete the three shell scripts. Can be combined with U2 if cleaner.
7. **U2 commit** — append three new lines to `.git-blame-ignore-revs`; remove the orphan `.gitignore` block. A commit cannot contain its own hash, so this lands after the deletion commits. (If the project uses squash-merge, the squashed commit hash differs from the three pre-squash hashes — in that case, replace the three new lines with the single squashed hash, or add a post-merge trivial commit updating them. Document the chosen approach in the PR description.)

The PR opens as draft. CI runs on the draft; if any step fails, the implementer fixes before converting to ready-for-review.

**Patterns to follow:** `docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md:U2` for the `git rm --cached` pattern, `:U4` for the two-commit blame-ignore sequence. The wholesale plan has no importer-relocation step (unlike purge-and-protect's U1); the sequencing discipline is the relevant analog.

**Test scenarios:**
- Happy path: After all deletion commits, `git ls-files archive/` returns zero lines, `git ls-files experiments/` returns zero lines, `git ls-files router-experiments/` returns zero lines. The origin brainstorm's per-directory counts (403/429/111) are filesystem counts from `find`; the plan's counts (271/56/111 = 438) are tracked counts from `git ls-files`. The 373-file difference in `experiments/` is untracked output artifacts (logs, generated JSONs, `.kicad_prl` files) that were never committed — confirming the directory is scratch space, not source. The plan uses tracked counts; the brainstorm's filesystem counts over-counted.
- Edge case: `ls archive/` from a working tree still shows the files (because `git rm --cached` does not delete from disk). `git status` on a fresh clone shows the directories are absent.
- Edge case: The package's `experiments/` namespace is untouched. `git ls-files packages/temper-placer/experiments/diff_pair/coupled_router.py` still returns the path; the file is in the index.
- Error path: If the implementer runs `git rm -r archive/` (without `--cached`), the files are deleted from disk. The plan uses `--cached` consistently; the implementer should verify `ls archive/` shows files after each commit.

**Verification:**
- `git ls-files archive/ experiments/ router-experiments/` returns zero lines on the final commit.
- `ls archive/ experiments/ router-experiments/` (filesystem) shows the files on the implementer's working tree.
- `git status` on a fresh clone from the merged commit shows the directories absent.

---

### U2. `.git-blame-ignore-revs` update + `.gitignore` orphan cleanup

**Goal:** Add three entries to `.git-blame-ignore-revs` (one per deletion commit) and remove the three `.gitignore` lines that target the deleted `experiments/temper-a98v/` block.

**Requirements:** R5, R6

**Dependencies:** U1 (the deletion commits must exist to be referenced)

**Files:**
- Modify: `.git-blame-ignore-revs` — append three lines (one per deletion commit's hash), with a comment naming the directories
- Modify: `.gitignore` — remove lines 98-100 (the `experiments/temper-a98v/*.kicad_pcb`, `*.json`, `*.log` block)

**Approach:**

Append to `.git-blame-ignore-revs`:
```
# Wholesale stale-directory purge — three mechanical deletions; skip in blame.
H_ARCHIVE
H_EXPERIMENTS
H_ROUTER_EXPERIMENTS
```

(Replace `H_*` with the actual commit hashes recorded from U1's three deletion commits.)

In `.gitignore`, delete the three-line block:
```
# Experiment artifacts (generated files)
experiments/temper-a98v/*.kicad_pcb
experiments/temper-a98v/*.json
experiments/temper-a98v/*.log
```

The surrounding context (the `.hypothesis/`, `.worktrees`, `firmware/test/build/` lines) stays. Confirm with `git check-ignore -v experiments/temper-a98v/foo.txt` post-cleanup — the response should be `experiments/temper-a98v/foo.txt` is *not* ignored, and the directory is *not* present.

**Patterns to follow:** `purge-and-protect-plan:U4` for the existing `.git-blame-ignore-revs` format (one full 40-char SHA per line, `#` comments allowed).

**Test scenarios:**
- Happy path: `.git-blame-ignore-revs` has 4 lines (1 existing + 3 new) plus 2 comment lines.
- Happy path: `.gitignore` no longer contains the strings `experiments/temper-a98v/*.kicad_pcb`, `experiments/temper-a98v/*.json`, or `experiments/temper-a98v/*.log`.
- Edge case: A file with history crossing one of the deletion commits (e.g., a re-created file in `packages/temper-placer/`) blames correctly when the new commit's hash is in the file. The plan's deletions are delete-only (no file moves), so this is forward-looking for future purges.
- Integration: `git blame --ignore-revs-file .git-blame-ignore-revs <any-file-not-deleted>` returns the last real author, not the deletion commits.

**Verification:**
- `cat .git-blame-ignore-revs` shows the expected content.
- `grep -E 'experiments/temper-a98v' .gitignore` returns nothing.
- `git log --oneline -1 <H_ARCHIVE>` confirms the hash resolves to the archive deletion commit.

---

### U3. Update import-linter gate to drop deleted dirs from Phase 3 scan

**Goal:** Remove `experiments` and `router-experiments` from `PHASE3_DIRS` in `scripts/import_linter_gate.py` so the import-boundary gate does not scan non-existent paths.

**Requirements:** R7 (the gate must keep passing)

**Dependencies:** None (lands in the same PR as U1, but before the deletion commits so the gate's CI run during the PR's draft phase still passes)

**Files:**
- Modify: `scripts/import_linter_gate.py` — line 163 (`PHASE3_DIRS`) and lines 355-356 (the print message)
- Modify: `import-linter-allowlist.yaml` — remove the 168 entries for `experiments/` (21) and `router-experiments/` (147)

**Approach:**

Change line 163 from:
```python
PHASE3_DIRS = ("tools", "experiments", "simulation", "router-experiments")
```
to:
```python
PHASE3_DIRS = ("tools", "simulation")
```

Update the docstring at line 179 from `"""Scan tools/, experiments/, etc. for temper_placer imports."""` to `"""Scan tools/, simulation/, etc. for temper_placer imports."""`.

Update the comment at line 345 from `# Phase 3: scan tools/, experiments/, simulation/, router-experiments/` to `# Phase 3: scan tools/, simulation/`.

Update the f-string at lines 355-356 from:
```python
f"\n=== PHASE 3 SCAN: tools/, experiments/, simulation/, "
f"router-experiments/ ==="
```
to:
```python
f"\n=== PHASE 3 SCAN: tools/, simulation/ ==="
```

Also search `import-linter-allowlist.yaml` for any `experiments/` or `router-experiments/` entries. Per the file's current state, 168 entries will be found (21 for `experiments/`, 147 for `router-experiments/`); remove them in the same commit. The 168-entry deletion is a one-pass removal (no survivors expected); verify by `grep -c 'experiments/\|router-experiments/' import-linter-allowlist.yaml` returning 0 after the change.

**Patterns to follow:** The existing tuple structure; no structural change to the gate, only a member removal.

**Test scenarios:**
- Happy path: `PHASE3_DIRS == ("tools", "simulation")` after the change.
- Happy path: `uv run python scripts/import_linter_gate.py` runs to completion without scanning non-existent paths.
- Error path: A future PR that adds a `temper_placer.*` import to a new top-level `experiments/` directory is caught by the gate (the import would not be allowlisted).
- Integration: The CI step `name: Import boundary enforcement` in `.github/workflows/python-tests.yml:53-54` passes.

**Verification:**
- `grep -E "experiments|router-experiments" scripts/import_linter_gate.py` returns nothing (after the U1 commits land and the dirs are gone).
- CI's import-boundary enforcement step passes on the merged PR.

---

### U4. Delete three experiment-runner shell scripts

**Goal:** Remove the three shell scripts that hardcode paths into the deleted `experiments/temper-a98v/` directory.

**Requirements:** R7 (no broken references)

**Dependencies:** U1 (the deleted dir must be gone for the scripts to be unrunnable)

**Files:**
- Delete: `scripts/run_temper_a98v_full.sh`
- Delete: `scripts/run_temper_a98v_poc.sh`
- Delete: `scripts/verify_temper_a98v_all_routing.sh`

**Approach:**

`git rm scripts/run_temper_a98v_full.sh scripts/run_temper_a98v_poc.sh scripts/verify_temper_a98v_all_routing.sh` in a single commit. Each script's purpose is documented in its first 10 lines (verified: all three hardcode `experiments/temper-a98v/` as the `RESULTS_DIR` or config path; all three are manual-run, not CI-driven).

**Patterns to follow:** The plan's U1 pattern of wholesale directory deletion; scripts are leaf-level and have no dependents.

**Test scenarios:**
- Happy path: `ls scripts/run_temper_a98v*.sh scripts/verify_temper_a98v*.sh` returns nothing.
- Edge case: `git log --diff-filter=D -- scripts/run_temper_a98v_full.sh` shows the deletion commit.
- Integration: No CI workflow references the scripts (confirmed: `grep -E "run_temper_a98v|verify_temper_a98v" .github/workflows/*.yml` returns nothing).

**Verification:**
- `ls scripts/run_temper_a98v_full.sh 2>&1` returns a "No such file" error.
- `git log --all --oneline -- scripts/run_temper_a98v_full.sh` shows the deletion commit (and the original creation commits before it).

---

### U5. Add smoke test for the production `experiments.diff_pair.coupled_router` import

**Goal:** Guard the production import in `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py:44` against silent failure. The import is wrapped in `try/except ImportError`, so a missing module would not crash — it would set `COUPLED_ROUTER_AVAILABLE = False` and USB diff pairs would silently route as separate single-ended pairs.

**Requirements:** R7

**Dependencies:** None (lands in the same PR as U1, before the deletion commits, so the test provides a guard during the PR's draft phase)

**Files:**
- Create: `packages/temper-placer/tests/routing/test_sequential_routing_coupled_import.py`

**Approach:**

The test module has two test functions:

1. **`test_coupled_router_imports_successfully`** — imports `packages.temper_placer.deterministic.stages.sequential_routing`, then asserts that `sequential_routing.COUPLED_ROUTER_AVAILABLE is True`. This is the happy-path guard: the import resolves, the production module is present.

2. **`test_coupled_router_import_fallback`** — uses `unittest.mock.patch.dict(sys.modules, {"experiments.diff_pair.coupled_router": None})` to make the import raise `ImportError`, then calls `importlib.reload(sequential_routing)` to force re-execution of the import block (a plain re-import would return the cached module and the except branch would never run), and asserts `COUPLED_ROUTER_AVAILABLE is False`. This is the error-path guard: the `try/except` wrapper sets the flag correctly when the import fails.

The tests live in `packages/temper-placer/tests/routing/` because the import being tested is in the routing subsystem. The package's test layout already has `tests/routing/` (confirmed: `ls packages/temper-placer/tests/routing/` shows existing routing tests like `test_path_simplifier_dynamic.py`).

**Patterns to follow:** `packages/temper-placer/tests/routing/test_path_simplifier_dynamic.py` for test style; `unittest.mock` from stdlib for the import-failure simulation.

**Test scenarios:**
- Happy path: `COUPLED_ROUTER_AVAILABLE is True` after a normal import of `sequential_routing`. Asserted in the test body.
- Edge case: The import target is the package's `experiments/diff_pair/coupled_router.py` (resolved via `sys.path.insert` at sequential_routing.py:38-42), not the root `experiments/`. The test passes regardless of which `experiments/` directory the import resolves through — the test only asserts the flag's boolean value.
- Error path: When `experiments.diff_pair.coupled_router` is mocked as missing, `COUPLED_ROUTER_AVAILABLE is False` after re-import. This proves the `try/except` wrapper works.
- Integration: `uv run pytest packages/temper-placer/tests/routing/test_sequential_routing_coupled_import.py` from `packages/temper-placer/` passes locally and in CI.

**Verification:**
- The test file exists at the specified path.
- `uv run pytest packages/temper-placer/tests/routing/test_sequential_routing_coupled_import.py -v` shows both test functions passing.
- A regression scenario (manually breaking the import by deleting `packages/temper-placer/experiments/diff_pair/coupled_router.py`) would fail the happy-path test, catching the silent-failure mode.

---

## System-Wide Impact

- **CI pipeline:** The "Import boundary enforcement" step (`.github/workflows/python-tests.yml:53-54`) calls the updated `scripts/import_linter_gate.py`. U3 keeps this step passing by removing the deleted dirs from the scan. No new CI jobs. No `paths:` filter changes (the import-linter gate already runs on every PR).
- **`scripts/import_linter_gate.py`:** Tuple change at line 163 plus three print/comment updates. The Phase 3 scan continues to run on `tools/` and `simulation/`. The deleted dirs had 168 `temper_placer.*` import entries in `import-linter-allowlist.yaml` (21 for `experiments/`, 147 for `router-experiments/`); these become orphan after deletion and are cleaned up in U3's same commit. The scan's allowlist is per-file per-import; orphan entries are housekeeping, not correctness.
- **`scripts/measure_usb_baseline.py`:** Unchanged. The docstring reference at line 214 (`experiments/diff_pair/`) documents a closed bd epic; deferred to a future docs-cleanup pass.
- **`.gitignore`:** Three lines removed (the `experiments/temper-a98v/*` block at lines 98-100). The 80+ other patterns (Python, C++, KiCad, IDE, Temper-specific, Beads, root hygiene) are unchanged.
- **`.git-blame-ignore-revs`:** One file with 4 lines + 2 comments (was 1 line + 1 comment). Future purge-style commits append.
- **Root working tree:** The 438 files leave git tracking but remain on disk for existing clones via `git rm --cached` semantics. A fresh clone is clean.
- **`packages/temper-placer/experiments/` and `packages/temper-placer/src/temper_placer/experiments/`:** Unchanged. These are out of scope (R4) and remain the production-coupled namespaces.
- **`packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`:** Unchanged. The `try/except ImportError` wrapper at lines 43-49 is the surface U5 guards.
- **Test suite:** One new test file with two test functions. Additive; no existing test is modified. The new test is collected by the existing pytest run for `packages/temper-placer/tests/routing/`.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| A file in one of the deleted dirs is referenced by a CI step, Makefile, or shell script not found by the research | `grep -rE "archive/\|experiments/\|router-experiments/" .github/ Makefile bd-setup.sh scripts/ tools/` was run during planning; only the five known dependents (import_linter_gate.py, the three shell scripts, measure_usb_baseline.py docstring) are affected. Re-run at implementation time to catch any new references. |
| Squash-merge changes the deletion commit hashes, invalidating `.git-blame-ignore-revs` entries | Document in the PR description: if squash-merge is used, replace the three pre-squash hashes with the single squashed hash in a follow-up commit. The blame-ignore file is a per-commit reference; the squashed commit is also fine to reference. |
| The import-linter gate's allowlist has stale entries referencing the deleted dirs | Search `import-linter-allowlist.yaml` at implementation time. If entries exist, remove them in U3's commit; if not, the ratchet's normal flow catches them. |
| The smoke test's `mock.patch.dict(sys.modules, ...)` approach doesn't actually trigger the `ImportError` because the module is already imported | The test re-imports `sequential_routing` after patching; if the import is cached, the test must use `importlib.reload` to force re-execution of the import block. Implementer should verify both test functions pass independently. |
| Draft-first PR sits in draft too long, blocking other work | Standard cadence: open draft, wait for CI green (typically <10 min for this repo), convert to ready-for-review. No long-running blocking expected. |
| A file the implementer thought was a local-only debug script is actually imported somewhere outside the scan paths | Re-run `grep -rE "^(from\|import) (archive\|experiments\|router_experiments)" packages/ tests/ scripts/ tools/` at implementation time. The research found zero matches; if a match surfaces, the deletion either skips that file or relocates it first (precedent: purge-and-protect's U1 relocate of `add_power_planes.py`). |
| A developer pushes a new file to `archive/` or `router-experiments/` after the deletion, recreating the noise | No CI gate against this (the dirs don't exist). The `.gitignore` no longer has patterns targeting the dirs. The plan does not add a gate; the worktree is clean and the dirs are not regenerated by any tooling. If a new file lands at the repo root with a deleted-dir name, the root-hygiene gate from purge-and-protect (if landed) catches the `.py` case. |

---

## Documentation / Operational Notes

- **PR description** must include: (a) the per-directory file counts (271/56/111), (b) the bash-shape commands the implementer ran for each deletion, (c) the squash-merge handling for `.git-blame-ignore-revs`, (d) a one-line note that the production `experiments/` namespace is untouched.
- **No `CLAUDE.md` or `AGENT_INSTRUCTIONS.md` change** is required. The deletion is mechanical; the smoke test's failure message (when triggered) is self-documenting.
- **bd issues:** No bd issue needs to be created for this work — the origin brainstorm is the source of truth, and the plan executes it. If the team prefers bd-tracked work, the implementer can create one issue with the plan path as the body.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-23-wholesale-stale-dir-purge-requirements.md](docs/brainstorms/2026-06-23-wholesale-stale-dir-purge-requirements.md)
- **Analogous plan (root-file purge):** [docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md](docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md)
- **Import-linter gate ratchet:** [docs/solutions/tooling-decisions/import-linter-boundary-enforcement-ratchet-2026-06-22.md](docs/solutions/tooling-decisions/import-linter-boundary-enforcement-ratchet-2026-06-22.md)
- **CI workflow (import boundary enforcement step):** `.github/workflows/python-tests.yml:53-54`
- **Production import guarded by U5:** `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py:43-49`
- **Out-of-scope `experiments/` namespace (R4):** `packages/temper-placer/experiments/diff_pair/coupled_router.py` and `packages/temper-placer/src/temper_placer/experiments/`
- **Closed bd epic referenced in `measure_usb_baseline.py`:** `temper-qlni` (consolidated into open epic `temper-dxuj`)
