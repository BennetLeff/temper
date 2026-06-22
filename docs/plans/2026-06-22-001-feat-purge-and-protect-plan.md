---
title: "feat: Purge-and-Protect Root Directory Hygiene Gate"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-21-purge-and-protect-requirements.md
---

# feat: Purge-and-Protect Root Directory Hygiene Gate

## Summary

A single-PR repo-hygiene sweep that (1) removes 162 git-tracked generated/artifact files from the repository root (1 via `git mv` in U1, 161 via `git rm --cached` in U2), (2) extends `.gitignore` with root-anchored patterns so the purged categories cannot re-enter tracked state, (3) adds a pytest gate in `packages/temper-drc/tests/` that fails CI when `git ls-files` returns any root-level `*.py`, `*.kicad_pcb`, `*.kicad_pro`, or `*-drc.json` outside an explicit (expected-empty) allowlist, and (4) introduces `.git-blame-ignore-revs` with the purge commit hash so `git blame` stays readable. One real root-module dependency (`add_power_planes.py`, imported by `tests/test_add_power_planes_thermal.py:8`) is relocated into `scripts/` as part of the same PR so the allowlist remains empty. No behavior change; the root becomes navigable.

---

## Problem Frame

The repository root holds 162 git-tracked generated/one-off files alongside the actual entry points (`pyproject.toml`, `Makefile`, `CLAUDE.md`, `AGENTS.md`, `opencode.json`). Verified counts via `git ls-files` on current `main`:

| Category | Count | Verified sample |
|---|---|---|
| `*.py` (debug/one-off scripts) | 49 | `add_power_planes.py`, `analyze_drc.py`, `hybrid_astar_snippet.py` (parse error confirmed), `run_benders_with_exact_router.py` |
| `*.kicad_pcb` (generated board snapshots) | 46 | `debug_placed.kicad_pcb`, `final_placement_v1.kicad_pcb`, `piantor_production.kicad_pcb` |
| `*.kicad_pro` (companion project files) | 24 | — |
| `*-drc.json` (DRC probe outputs) | 38 | `temper-drc.json`, `test1-drc.json`, `test_+all-drc.json` |
| `*.stats` (cProfile dumps) | 4 | `boost_router_profile.stats`, `optimized_profile.stats`, `profile_output.stats`, `router_profile.stats` |
| `10A` (orphan) | 1 | 0-byte file, no extension, no purpose |
| `*.md` (status/report dumps) | 33 | **Deferred** — out of scope per origin |

The canonical KiCad source board is `pcb/temper.kicad_pcb`; every root `*.kicad_pcb` is a generated output. `scripts/route_v3.sh` defaults `OUTPUT_PCB` to a root path (`routed_v3.kicad_pcb`), confirming root boards are outputs, not build inputs. `scripts/run_clean_flow.sh`, `scripts/measure_drc_improvement.sh`, and `scripts/run_temper_a98v_poc.sh` all read inputs from `pcb/` or `packages/temper-placer/tests/fixtures/`, never from root. The cost is navigation and trust, not disk.

CI enforces nothing about root layout today. `.github/workflows/python-tests.yml` runs `uv run pytest tests/core/` (temper-placer), `uv run pytest tests/` (temper-workflow, temper-tools, temper-drc), and `uv run ruff check packages/`. `ruff` is scoped to `packages/` only; no step inspects the root. Critically, the root `tests/` directory is **not** in `pyproject.toml` `[tool.pytest.ini_options] testpaths` (lines 29–37 list only `packages/*/tests`), so a gate test placed at root `tests/` would not be collected by any CI step.

---

## Scope Boundaries

### In scope

- R1–R5 from the origin requirements document: the purge (`git rm --cached`), `.gitignore` extension, pytest gate, and `.git-blame-ignore-revs`.
- Relocation of `add_power_planes.py` from root into `scripts/` and the one-line fix to its single importer `tests/test_add_power_planes_thermal.py:8` (required to keep the gate allowlist empty — see Key Technical Decisions).
- Extension of the `paths:` filter in `.github/workflows/python-tests.yml` so the workflow triggers on root-file PRs (otherwise the gate never runs).

### Deferred

- The 33 root `*.md` status reports (`STATUS.md`, `BENDERS_STATUS.md`, `*_REPORT.md`, etc.) — out of scope per origin. A separate triage pass decides keep-vs-archive. The CI gate does not cover `*.md`.
- `scripts/` and `tools/` internal hygiene — not the root-sprawl problem this PR targets.
- Per-script repair of the 49 root `.py` files — they are removed as a category; the only exception is `add_power_planes.py` which is relocated, not deleted, because it has a live importer.
- History rewriting / `git filter-repo` — out of scope. The purge is a normal deletion commit; history bloat is mitigated only by R5.
- Pre-commit framework adoption — out of scope. No `.pre-commit-config.yaml` exists; the gate is a pytest that fits existing CI.

### Out of scope

- Benders logs and `.bak` files — already untracked (`.gitignore:46,54` cover `*.bak`, `*.log`).
- Broken-import remediation for root scripts beyond `add_power_planes.py`. `hybrid_astar_snippet.py` has a syntax error (confirmed) and is deleted with the category, not fixed.
- Root `*.kicad_prl` — already covered by global `*.kicad_prl` at `.gitignore:47`; a redundant root-anchored `/*.kicad_prl` is added for intent-explicitness per origin Open Question [Affects R2][Technical] (resolved: yes, add it — redundant but harmless, makes the root-purge intent self-documenting).

---

## Key Technical Decisions

**Gate mechanism: pytest test in `packages/temper-drc/tests/`, NOT root `tests/` and NOT pre-commit.** Research resolves origin Open Question [Affects R3][Technical]: the root `tests/` directory is **not** collected by CI. `pyproject.toml:29-37` (`testpaths`) lists only `packages/*/tests`, and the CI steps in `.github/workflows/python-tests.yml:36-50` run `uv run pytest` with `working-directory` set to each package — none of them invoke the root `tests/` directory. Placing the gate at root `tests/` would require both a new CI step *and* adding root `tests/` to `testpaths`; placing it in `packages/temper-drc/tests/test_root_hygiene.py` requires neither — it is collected by the existing "Run temper-drc tests" step (`.github/workflows/python-tests.yml:48-50`). The test resolves the repo root via `Path(__file__).resolve().parents[3]` (test file → `tests/` → `temper-drc/` → `packages/` → repo root) and shells out to `git ls-files` from that cwd. `temper-drc` is the natural home: it is the repo's design-rule-check package, and root-layout hygiene is a design rule. (resolves origin Open Question [Affects R3])

**Gate triggers only if the workflow runs on root-touching PRs — extend `paths:`.** The `paths:` filter at `.github/workflows/python-tests.yml:6-9` and `:12-15` includes only `packages/**`, `pyproject.toml`, and the workflow file itself. A PR that adds `analyze_new.py` at root touches none of these, so the workflow does not trigger and the gate never runs. GitHub Actions `paths:` patterns use `*` to match any character except `/`, so `*.py` matches **only** root-level `.py` files (not nested). The plan adds `'.gitignore'`, `'*.py'`, `'*.kicad_pcb'`, `'*.kicad_pro'`, `'*-drc.json'`, `'*.stats'`, and `'.git-blame-ignore-revs'` to both the `push` and `pull_request` `paths:` blocks. This ensures any root-file PR in a purged category triggers the workflow and thus the gate. No new CI job is created. (resolves the unstated CI-gating gap that the origin's Assumption A2 did not surface)

**`add_power_planes.py` is relocated, not deleted.** Origin Assumption A1 assumed "no package imports a root module." Research finds **one violation**: `tests/test_add_power_planes_thermal.py:8` does `from add_power_planes import add_unified_gnd_plane` after a `sys.path.append(str(Path(__file__).parent.parent))` hack (line 7). `add_power_planes.py` is git-tracked at root. If it is `git rm --cached`'d without relocation, this test breaks at import time. The plan relocates `add_power_planes.py` to `scripts/add_power_planes.py` (a script directory, consistent with the origin's stated intent for root scripts) and updates the test's import to `sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))` + `from add_power_planes import add_unified_gnd_plane`. The allowlist stays empty. Two other references to `add_power_planes_v2.py` at root (`scripts/finalize_pcb.py:88`, `scripts/run_clean_flow.sh:39`) are **dead** — `git ls-files` confirms no `add_power_planes_v2.py` exists at root (only `archive/add_power_planes_v{1,2,3,4}.py` under `archive/`). They are not modified by this PR; their brokenness predates the purge and is out of scope. (resolves origin Open Question [Affects R1][Evidence])

**No root `*.kicad_pcb` is a build input.** Origin Open Question [Affects R1][Specificity] resolved: grep across `scripts/`, `tools/`, `firmware/`, `packages/` finds no root `.kicad_pcb` referenced as an input board. `scripts/placement_routing_loop.py` *writes* `debug_placed.kicad_pcb` (output via `with_name`), and `scripts/profile_router.py` reads `pcb/debug_placed.kicad_pcb` (under `pcb/`, not root). All shell scripts that set `INPUT_PCB` point at `pcb/temper.kicad_pcb` or `packages/temper-placer/tests/fixtures/medium_board.kicad_pcb`. Root boards are safe to purge as a category.

**Purge is a single commit via `git rm --cached`, not split by category.** Per origin Key Decisions: one commit, one `.git-blame-ignore-revs` entry. Files remain on disk for anyone with a working copy; the `.gitignore` patterns prevent re-adding. Splitting by category would require multiple blame-ignore entries and multiple CI-green intermediate states for no benefit.

**`.git-blame-ignore-revs` requires a two-commit sequence.** A commit cannot contain its own hash. The plan lands in two commits: (1) the purge commit — `git rm --cached` the 162 files, extend `.gitignore`, add the gate test, relocate `add_power_planes.py`, fix the test import; the commit message references the intent to add the hash to `.git-blame-ignore-revs`; (2) a follow-up commit that creates `.git-blame-ignore-revs` at root containing the purge commit's hash. If the project's branch protection requires green CI on every commit, both commits are green independently (commit 2 only adds a text file). (resolves the mechanical reality behind R5)

**Allowlist expected empty; gate covers `.py`, `.kicad_pcb`, `.kicad_pro`, `*-drc.json`.** Per R3 and R4. `*.stats` and `10A` are covered by `.gitignore` only (R2) — the gate does not enumerate every purged category, it covers the four that a developer is most likely to re-add by accident (`*.py` and `*.kicad_pcb` per R3; `.kicad_pro` and `*-drc.json` per R4). `*.stats` and `10A` are one-off categories unlikely to recur; if they do, the `.gitignore` blocks them silently. The allowlist is a Python set literal in the test file, documented as expected-empty, with a comment naming `scripts/` and `tools/debug/` as intended destinations.

---

## Implementation Units

### Phase 1 — Relocate the one live root module

### U1. Move `add_power_planes.py` to `scripts/` and fix its importer

**Goal:** Eliminate the single root-module import dependency so the purge can remove all 49 root `.py` files without breaking any test.

**Requirements:** R1 (enabling — makes the allowlist empty)

**Dependencies:** None

**Files:**
- `add_power_planes.py` → `scripts/add_power_planes.py` (`git mv`, then `git rm --cached` is implicit in the move; the file leaves root)
- `tests/test_add_power_planes_thermal.py:7-8` (update sys.path target and confirm import still resolves)

**Approach:**

1. `git mv add_power_planes.py scripts/add_power_planes.py`. This moves the file out of root in one step; no separate `git rm --cached` is needed for this file.
2. In `tests/test_add_power_planes_thermal.py`, replace line 7 `sys.path.append(str(Path(__file__).parent.parent))` with `sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))`. The import on line 8 (`from add_power_planes import add_unified_gnd_plane`) stays unchanged — the module name is the same, only the search path changes.
3. Run `uv run pytest tests/test_add_power_planes_thermal.py` from repo root to confirm the test still passes. Note: this test is not in any CI `testpaths` (root `tests/` is excluded from `pyproject.toml:29-37`), so it must be verified locally; it is not a CI-gated test today and the purge does not change that.

**Patterns to follow:** `scripts/` already holds runnable scripts with no `__init__.py` (confirmed: `ls scripts/__init__.py` returns nothing). The relocated file is invoked the same way other `scripts/*.py` files are.

**Acceptance:**
- `git ls-files | rg '^add_power_planes\.py$'` returns empty (file no longer at root).
- `git ls-files | rg '^scripts/add_power_planes\.py$'` returns the new path.
- `uv run pytest tests/test_add_power_planes_thermal.py` passes locally.
- No other root `.py` file is imported by any package or test (verified by grep: `rg "^(from|import) [a-z_]+ import|^import [a-z_]+$" tests/*.py packages/ scripts/` finds no other root-module imports).

---

### Phase 2 — Purge

### U2. `git rm --cached` the 162 root artifacts and extend `.gitignore`

**Goal:** Remove all git-tracked generated/artifact files from the repository root and prevent the purged categories from re-entering tracked state.

**Requirements:** R1, R2

**Dependencies:** U1 (must run first so `add_power_planes.py` is already moved and not caught by the `/*.py` purge)

**Files:**
- 48 root `*.py` files (after U1; the 49th, `add_power_planes.py`, was moved in U1) — `git rm --cached`
- 46 root `*.kicad_pcb` files — `git rm --cached`
- 24 root `*.kicad_pro` files — `git rm --cached`
- 38 root `*-drc.json` files — `git rm --cached`
- 4 root `*.stats` files (`boost_router_profile.stats`, `optimized_profile.stats`, `profile_output.stats`, `router_profile.stats`) — `git rm --cached`
- `10A` — `git rm --cached`
- `.gitignore` (add root-anchored patterns)

**Approach:**

1. Enumerate the exact file sets via `git ls-files` and `git rm --cached` them. The command shape:
   ```
   git rm --cached $(git ls-files '*.py' | rg '^[^/]+$' | rg -v '^add_power_planes\.py$')
   git rm --cached $(git ls-files '*.kicad_pcb' | rg '^[^/]+$')
   git rm --cached $(git ls-files '*.kicad_pro' | rg '^[^/]+$')
   git rm --cached $(git ls-files '*-drc.json' | rg '^[^/]+$')
   git rm --cached $(git ls-files '*.stats' | rg '^[^/]+$')
   git rm --cached 10A
   ```
   (`add_power_planes.py` is excluded from the `*.py` purge because U1 already moved it.) Files remain on disk; only the tracked state is removed.
2. Append root-anchored patterns to `.gitignore` under a new `# Root hygiene — no generated/artifact files at repo root` section:
   ```
   /*.py
   /*.kicad_pcb
   /*.kicad_pro
   /*.kicad_prl
   /*-drc.json
   /*.stats
   /10A
   ```
   The leading `/` anchors the pattern to the repository root, leaving nested directories (e.g. `packages/*/src/*.py`, `pcb/*.kicad_pcb`) unaffected. The existing global patterns (`*.log` at `.gitignore:54`, `*.bak` at `.gitignore:46`, `*.kicad_prl` at `.gitignore:47`, `__pycache__/` at `.gitignore:2`) remain. The `/*.kicad_prl` entry is redundant with the global but added for intent-explicitness per origin Open Question [Affects R2][Technical] (resolved: add it).
3. Verify the purge is complete: `git ls-files -- '*.py' '*.kicad_pcb' '*.kicad_pro' '*-drc.json' '*.stats' | rg '^[^/]+$'` returns zero lines (the `rg '^[^/]+$'` filter ensures root-only). `git ls-files | rg '^10A$'` returns empty.

**Patterns to follow:** Existing `.gitignore` section headers (e.g. `# KiCad` at `.gitignore:44`, `# Temper Specific` at `.gitignore:65`). Root-anchored `/pattern` syntax is standard gitignore.

**Acceptance:**
- `git ls-files | rg '^[^/]+\.py$'` returns zero results.
- `git ls-files | rg '^[^/]+\.kicad_pcb$'` returns zero results.
- `git ls-files | rg '^[^/]+\.kicad_pro$'` returns zero results.
- `git ls-files | rg '^[^/]+-drc\.json$'` returns zero results.
- `git ls-files | rg '^[^/]+\.stats$'` returns zero results.
- `git ls-files | rg '^10A$'` returns empty.
- The 33 root `*.md` files remain tracked (out of scope).
- The purged files still exist on disk in the working tree (verified by `ls`).
- `git check-ignore analyze_drc.py` returns the path (now ignored); `git check-ignore packages/temper-placer/src/temper_placer/__init__.py` returns nothing (nested `.py` not affected).

---

### Phase 3 — Protect (CI gate)

### U3. Root-hygiene pytest gate in `packages/temper-drc/tests/`

**Goal:** A pytest that runs `git ls-files` from the repo root, filters to root-level paths, and fails CI if any match `*.py`, `*.kicad_pcb`, `*.kicad_pro`, or `*-drc.json` outside an explicit allowlist.

**Requirements:** R3, R4

**Dependencies:** U2 (purge must be complete so the gate passes on the PR that introduces it)

**Files:**
- `packages/temper-drc/tests/test_root_hygiene.py` (new — the gate test)
- `.github/workflows/python-tests.yml:6-15` (extend `paths:` filter so root-file PRs trigger the workflow)

**Approach:**

The gate is a single pytest module. It runs at collection time:

1. Resolve repo root: `REPO_ROOT = Path(__file__).resolve().parents[3]` (test file at `packages/temper-drc/tests/test_root_hygiene.py` → `parents[0]=tests`, `parents[1]=temper-drc`, `parents[2]=packages`, `parents[3]=repo root`).
2. Run `subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)`. The `actions/checkout@v4` step at `.github/workflows/python-tests.yml:23` produces a git repo (shallow clone, `fetch-depth: 1` default — `git ls-files` works on shallow clones).
3. Parse stdout into a list of paths. Filter to root-only: `root_files = [p for p in paths if "/" not in p]`.
4. Define the allowlist: `ALLOWLIST: frozenset[str] = frozenset()` — expected empty after purge. Document with a comment: `# No root .py/.kicad_pcb/.kicad_pro/*-drc.json is a legitimate entry point. Add here only with a recorded reason; intended destinations: scripts/, tools/debug/, pcb/.`
5. Define the forbidden categories: `FORBIDDEN_SUFFIXES = (".py", ".kicad_pcb", ".kicad_pro", "-drc.json")`. Note: `*-drc.json` is a suffix match (`endswith("-drc.json")`), not a glob, so `temper-drc.json` and `test1-drc.json` both match but `packages/temper-drc/src/...` does not (it's filtered out by the root-only step).
6. Collect violations: `violations = [f for f in root_files if f.endswith(FORBIDDEN_SUFFIXES) and f not in ALLOWLIST]`.
7. Assert `violations == []`. On failure, build a message naming each offending file and the intended target directory: `f"{f}: root-level {suffix} not allowed — move to scripts/ (for .py), pcb/ (for .kicad_*), or an experiments directory (for *-drc.json)"`.

Wire into CI: the test lives in `packages/temper-drc/tests/`, so the existing "Run temper-drc tests" step (`.github/workflows/python-tests.yml:48-50`, `uv run pytest tests/ -v --tb=short` with `working-directory: packages/temper-drc`) collects and runs it. No new CI job.

Extend the `paths:` filter at `.github/workflows/python-tests.yml:6-9` (push) and `:12-15` (pull_request) to add:
```yaml
paths:
  - 'packages/**'
  - 'pyproject.toml'
  - '.github/workflows/python-tests.yml'
  - '.gitignore'
  - '*.py'
  - '*.kicad_pcb'
  - '*.kicad_pro'
  - '*-drc.json'
  - '*.stats'
  - '.git-blame-ignore-revs'
```
GitHub Actions `paths:` glob `*` matches any char except `/`, so `*.py` matches **only** root-level `.py` files. This ensures a PR that adds `analyze_new.py` at root (touching nothing under `packages/**`) still triggers the workflow and thus the gate.

**Patterns to follow:** `packages/temper-drc/tests/test_cli.py` (existing pytest style in this package). `subprocess.run(["git", ...])` stdlib usage. The `assert set(...) == set(...)` style used in `packages/temper-placer/tests/core/`.

**Test scenarios:**
- On the purge PR (after U1+U2), `uv run pytest packages/temper-drc/tests/test_root_hygiene.py` passes — `violations == []`, allowlist empty.
- A PR that adds `analyze_thing.py` at root: the workflow triggers (via the new `*.py` path filter), the "Run temper-drc tests" step runs, the gate fails naming `analyze_thing.py` and pointing to `scripts/`.
- A PR that adds `routed_v4.kicad_pcb` at root: the gate fails naming the file and pointing to `pcb/`.
- A PR that adds `packages/temper-placer/src/temper_placer/new_module.py`: the gate does NOT flag it (the `/` in the path excludes it from `root_files`).
- A PR that adds `pcb/temper_v2.kicad_pcb`: the gate does NOT flag it (nested, not root).
- A PR that adds `temper_v2-drc.json` at root: the gate fails (R4 coverage).
- A PR that adds `snapshot.kicad_pro` at root: the gate fails (R4 coverage).
- A PR that adds `boost_profile.stats` at root: the gate does NOT flag it (`*.stats` is not in `FORBIDDEN_SUFFIXES` — covered by `.gitignore` only). This is intentional per Key Technical Decisions.
- A PR that adds `10A` at root: the gate does NOT flag it (not in forbidden suffixes; covered by `/10A` in `.gitignore`).
- With `ALLOWLIST = frozenset({"legacy_entry.py"})`, a root `legacy_entry.py` is permitted and all other root `.py` files still fail.

**Acceptance:**
- `uv run pytest packages/temper-drc/tests/test_root_hygiene.py` passes on the purge PR.
- Temporarily creating a tracked `fake_debug.py` at root (e.g. `touch fake_debug.py && git add fake_debug.py`) and re-running the test fails with a named violation. Remove the file to restore green.
- The CI workflow triggers on a simulated root-file PR (verified by the `paths:` filter change).
- The existing `packages/temper-drc/tests/` suite continues to pass — the new test file is additive.

---

### Phase 4 — Blame hygiene

### U4. `.git-blame-ignore-revs` with the purge commit hash

**Goal:** Mask the purge commit in `git blame` so the deletion sweep does not become the last-change for every deleted-then-recreated line.

**Requirements:** R5

**Dependencies:** U2 (the purge commit must exist to be referenced)

**Files:**
- `.git-blame-ignore-revs` (new — created at repo root in a follow-up commit)

**Approach:**

A commit cannot contain its own hash, so this is a two-commit sequence:

1. **Commit A (the purge):** U1 + U2 + U3 land as a single commit. The commit message references the blame-ignore intent, e.g.:
   ```
   chore: purge root-generated artifacts and add hygiene gate

   Removes 162 git-tracked generated/artifact files from the repo root
   via git rm --cached, extends .gitignore with root-anchored patterns,
   and adds a pytest gate in packages/temper-drc/tests/test_root_hygiene.py.

   Relocates add_power_planes.py to scripts/ (single live importer updated).

   The hash of this commit will be appended to .git-blame-ignore-revs in
   a follow-up commit so git blame skips the deletion sweep.
   ```
   Record the commit hash as `H_PURGE`.
2. **Commit B (blame-ignore):** Create `.git-blame-ignore-revs` at repo root containing exactly:
   ```
   # Purge root-generated artifacts — large mechanical deletion; skip in blame.
   <H_PURGE>
   ```
   Commit it: `git add .git-blame-ignore-revs && git commit -m "chore: add purge commit to .git-blame-ignore-revs"`.

Both commits are independently green: Commit A passes the gate (allowlist empty, purge complete); Commit B only adds a text file and does not affect any test. If the project's branch protection requires green CI on every commit, this sequence is safe. If squash-merge is used, the squashed hash differs from `H_PURGE` — in that case, after merge, update `.git-blame-ignore-revs` with the squashed hash in a third trivial commit. Document this in the PR description so the reviewer knows the hash may need a post-merge correction.

**Patterns to follow:** Standard `.git-blame-ignore-revs` format (one full 40-char SHA per line, `#` comments allowed). No existing file at root (confirmed: `ls .git-blame-ignore-revs` returns nothing).

**Acceptance:**
- `.git-blame-ignore-revs` exists at repo root and contains the purge commit's hash.
- `git blame --ignore-revs-file .git-blame-ignore-revs <any file touched by the purge>` skips the purge commit. (Verification is best-effort: the purge commit deletes files, so `git blame` on a *deleted* file shows nothing; the value is for files that were *modified* by the purge commit, if any — the purge is deletions-only, so this is primarily forward-looking for future purge-style commits.)
- The purge commit message is discoverable from `.git-blame-ignore-revs` via the comment line.

---

## System-Wide Impact

- **CI pipeline (`.github/workflows/python-tests.yml`):** One new test file in `packages/temper-drc/tests/` — collected by the existing "Run temper-drc tests" step (lines 48-50), no new job. The `paths:` filter (lines 6-9, 12-15) is extended with root-file patterns so root-touching PRs trigger the workflow. The gate runs in milliseconds (one `git ls-files` call).
- **`.gitignore`:** Seven new root-anchored patterns under a new section header. No existing patterns are modified; the global `*.kicad_prl`, `*.bak`, `*.log` remain. Nested directories are unaffected (root anchor `/`).
- **`pyproject.toml`:** NOT modified. The gate test lives in `packages/temper-drc/tests/` which is already in `testpaths` (line 33). Root `tests/` remains excluded from `testpaths` — this is intentional and unchanged.
- **Root working tree:** 162 files leave git tracking but remain on disk. Developers with existing working copies see no data loss. A fresh clone has a clean root.
- **`tests/test_add_power_planes_thermal.py`:** One-line edit to the `sys.path` target (line 7). The import on line 8 is unchanged. This test is not in CI `testpaths` today and remains a local-only test; the purge does not change its CI status.
- **`add_power_planes.py`:** Moves from root to `scripts/`. The `archive/add_power_planes_v{1,2,3,4}.py` files under `archive/` are NOT touched (already in a non-root directory, not in purge scope).
- **Developer workflow:** A developer who creates `analyze_thing.py` at root and commits it sees a CI failure on the "Run temper-drc tests" step, naming the file and pointing to `scripts/`. A developer who runs a routing sweep that writes `routed_v4.kicad_pcb` to root finds it silently ignored by `git add` (no `-f`); if they force-add it, the gate fails CI.
- **`CLAUDE.md` / `AGENT_INSTRUCTIONS.md`:** No documentation change required by this plan. The gate's failure message is self-documenting (names the file and the intended directory). If the project convention requires recording the gate mechanism, add a one-line entry to `CLAUDE.md` — deferred to implementation per the companion plan's convention.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| A root `.py` file is imported by a package or test not caught by grep, and the purge breaks it | High | Low | Researched: `rg "^(from\|import) [a-z_]+" tests/*.py packages/ scripts/` finds exactly one root-module import (`tests/test_add_power_planes_thermal.py:8` → `add_power_planes`), handled by U1. `scripts/finalize_pcb.py:88` and `scripts/run_clean_flow.sh:39` reference `add_power_planes_v2.py` which does not exist at root (dead references, pre-existing breakage, out of scope). `packages/temper-placer/temper_placer/io/zone_manager.py:149` is a function *definition* named `add_power_planes`, not an import. Re-run the grep at implementation time before committing the purge. |
| The CI `paths:` filter extension is too broad and triggers the workflow on unrelated changes, increasing CI minutes | Low | Medium | The added patterns (`*.py`, `*.kicad_pcb`, etc.) match root-only files (GitHub `*` does not cross `/`). Unrelated changes under `packages/` already trigger the workflow. The marginal CI-minute cost is limited to PRs that touch root files — exactly the PRs the gate exists to catch. |
| The gate test does not run in CI because `packages/temper-drc/tests/` is not collected | High | Low | Researched: `pyproject.toml:33` lists `packages/temper-drc/tests` in `testpaths`, and `.github/workflows/python-tests.yml:48-50` runs `uv run pytest tests/` with `working-directory: packages/temper-drc`. The test is collected. Verified that `packages/temper-drc/tests/` already contains `test_cli.py`, `conftest.py`, and subdirs `checks/`, `core/`, `integration/` — the directory is live. |
| A shallow CI checkout (`fetch-depth: 1`) breaks `git ls-files` | Low | Low | `git ls-files` works on shallow clones; it lists the index, not history. `actions/checkout@v4` default is `fetch-depth: 1` (confirmed at `.github/workflows/python-tests.yml:23` — no `with: fetch-depth:` override). The index is populated on checkout. |
| A legitimately-needed root `.py` file is purged and breaks a workflow not covered by grep | Medium | Low | The allowlist in `test_root_hygiene.py` is the escape hatch. If execution surfaces a genuine exception, the file is added to `ALLOWLIST` with a comment, and the `.gitignore` `/*.py` pattern is overridden for that file via a `!<filename>` negation line. No such file is known today. |
| `add_power_planes.py` has hidden importers via `__import__` or `importlib` | Low | Low | `rg "add_power_planes" packages/ scripts/ tests/` finds only the four references analyzed (one real import, two dead refs to a non-existent `_v2`, one function-definition false positive). Dynamic import is unlikely for a zone-adding utility. Re-run the grep at implementation time. |
| Squash-merge changes the purge commit hash, invalidating `.git-blame-ignore-revs` | Low | Medium | Documented in U4: if squash-merge is used, a third trivial commit updates `.git-blame-ignore-revs` with the squashed hash. The PR description flags this for the reviewer. |
| The 33 root `*.md` files are accidentally purged | Medium | Low | The purge commands enumerate exact categories (`*.py`, `*.kicad_pcb`, `*.kicad_pro`, `*-drc.json`, `*.stats`, `10A`) — `*.md` is never referenced. The acceptance criterion explicitly checks that root `*.md` files remain tracked. |
| `git rm --cached` on 162 files produces a noisy diff that obscures review | Low | High | Inherent to a purge. The `.git-blame-ignore-revs` entry (U4) and the single-commit design (per origin Key Decisions) are the mitigation. The PR description lists the categories and counts. Reviewers can filter the diff by path. |

---

## Test Strategy

- **U1 (relocate):** `uv run pytest tests/test_add_power_planes_thermal.py` passes locally (the test is not in CI `testpaths`, so local verification is the gate). `git ls-files | rg '^add_power_planes\.py$'` is empty.
- **U2 (purge):** `git ls-files -- '*.py' '*.kicad_pcb' '*.kicad_pro' '*-drc.json' '*.stats' | rg '^[^/]+$'` returns zero lines. `git ls-files | rg '^10A$'` is empty. The 33 root `*.md` files remain. `git check-ignore` confirms the purged categories are now ignored at root while nested files are not.
- **U3 (gate):** The gate IS a test (`packages/temper-drc/tests/test_root_hygiene.py`). It passes on the purge PR. Temporarily `touch fake_debug.py && git add fake_debug.py` and re-run → test fails naming the file. `rm fake_debug.py` → green. The CI `paths:` filter change is verified by observing that a root-file-only PR triggers the workflow (confirmed at merge time).
- **U4 (blame-ignore):** `.git-blame-ignore-revs` exists and contains the purge commit hash. `git log --oneline -1 <hash>` confirms the hash resolves to the purge commit.
- **Regression:** The existing `packages/temper-drc/tests/` suite, `packages/temper-placer/tests/core/` suite, and `ruff check packages/` continue to pass. No existing test is modified except `tests/test_add_power_planes_thermal.py` (U1, one-line sys.path edit).

---

## Deferred to Implementation

- **Exact purge command invocation:** The plan prescribes `git rm --cached $(git ls-files ...)` shapes. At implementation time, run each category's command separately and confirm the file count matches the verified totals (48 py after U1, 46 kicad_pcb, 24 kicad_pro, 38 drc.json, 4 stats, 1 `10A` = 161 files; 162 if U1 is not counted as a move). Commit all `git rm --cached` results plus the `.gitignore` edit in a single commit.
- **`CLAUDE.md` vs `AGENT_INSTRUCTIONS.md` documentation:** The plan requires no doc change. If the project convention (per `AGENTS.md` "Documentation & Context Maintenance") requires recording the gate mechanism, add a one-line entry to `CLAUDE.md` (prefer it if present, else `AGENT_INSTRUCTIONS.md`). Confirm at implementation time.
- **Squash-merge handling for `.git-blame-ignore-revs`:** If the repo's merge policy squashes PR commits, the hash in `.git-blame-ignore-revs` (set to the pre-squash `H_PURGE`) will not match the squashed commit on `main`. A third trivial commit post-merge updates the hash. Confirm the merge policy at implementation time; if squash is used, flag it in the PR description.
- **Allowlist format:** The plan prescribes a `frozenset[str]` literal in the test file. If the allowlist grows beyond a few entries, migrate it to a committed `root_hygiene_allowlist.yaml` alongside the test (mirrors the companion plan's `safety_constant_overrides.yaml` pattern). Empty today; no file needed.
- **`tests/test_add_power_planes_thermal.py` CI status:** The test is not in `testpaths` and thus not in CI. This predates the purge. If the project wants this test in CI, add `tests/` (or `tests/test_add_power_planes_thermal.py` specifically) to `testpaths` in a separate changeset — out of scope for N1.
