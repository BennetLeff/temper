---
date: 2026-06-21
topic: purge-and-protect
---

# Purge-and-Protect: Root Directory Hygiene Gate

## Summary

A single-PR repo-hygiene sweep that removes git-tracked build/debug artifacts from the repository root, extends `.gitignore` so they stay gone, and adds a CI gate that blocks new top-level `.py` and `.kicad_pcb` files from re-entering the root. A `.git-blame-ignore-revs` entry masks the purge commit so `git blame` remains readable. No behavior change; the largest signal-to-noise win available to the repo today.

---

## Problem Frame

The repository root currently holds 170+ git-tracked generated or one-off files alongside the actual project entry points (`pyproject.toml`, `Makefile`, `CLAUDE.md`, `AGENTS.md`). Verified counts of **git-tracked** files at root:

| Category | Count | Notes |
|---|---|---|
| `*.py` (debug/one-off scripts) | 49 | Mostly runnable but not part of any package; one (`hybrid_astar_snippet.py`) has a parse error |
| `*.kicad_pcb` (placement/routing outputs) | 46 | Generated board snapshots, not source |
| `*.kicad_pro` (KiCad project files for the above) | 24 | Companions to the routed boards |
| `*-drc.json` (DRC probe outputs) | 38 | Benchmark fixtures from a Jan 14 sweep |
| `*.stats` (cProfile dumps) | 4 | `boost_router_profile.stats`, `optimized_profile.stats`, `profile_output.stats`, `router_profile.stats` |
| `10A` (orphan) | 1 | 2-byte file, no extension, no purpose |
| `*.md` (status/report dumps) | 33 | Sprint-status narratives; lower priority |

Already untracked (`.gitignore` covers them): `*.log`, `*.bak`, `*.kicad_prl`, `__pycache__/`, `*.txt`, `fp-info-cache`. The benders logs cited in the ideation brief (180KB / 1.2MB / 9.9MB) are **not** git-tracked — they are working-tree noise only and are already ignored. The `.bak` file visible in `ls` is likewise untracked.

The cost is not disk space — it is navigation and trust. A developer opening the repo cannot tell which `.kicad_pcb` is the canonical board (answer: none at root; the source of truth lives under `pcb/`), which `.py` is an entry point (answer: none at root; packages live under `packages/`), and which `-drc.json` is current. The root is a scratch directory that happens to be version-controlled. CI enforces nothing about this: `ruff check` runs only against `packages/`, and no test or workflow inspects the root layout.

---

## Actors

- A1. **Developer** — creates a one-off debug script or runs a routing sweep that drops a `*.kicad_pcb` at root. The source of the noise this initiative prevents.
- A2. **CI pipeline** (`.github/workflows/python-tests.yml`) — runs pytest and `ruff check packages/` on push/PR. The enforcement point for the new root-gate test.
- A3. **Reviewer** — currently the only defense against root-level file sprawl; unreliable and easily missed on large PRs.

---

## Key Flows

- F1. **One-off debug script lands at root**
  - **Trigger:** A1 prototypes a routing analysis and saves it as `analyze_thing.py` at the repo root.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 commits the file at root. (2) A2 runs the root-gate test, which asserts no tracked `.py` exists at the repository top level (excluding an explicit allowlist). (3) The test fails with a message naming the offending path and pointing to `scripts/` or `tools/debug/` as the intended location.
  - **Outcome:** The script is moved into a directory before merge, or the test fails. The root never accumulates the file.
  - **Covered by:** R3, R4

- F2. **Routing sweep writes a `.kicad_pcb` to root**
  - **Trigger:** A1 runs a placement/routing experiment whose output path defaults to the repo root.
  - **Actors:** A1, A2, A3
  - **Steps:** (1) A1 commits the generated board. (2) A2 root-gate test fails on the new top-level `.kicad_pcb`. (3) `.gitignore` already lists `/*.kicad_pcb`, so even an untracked file is invisible to `git add` without `-f`.
  - **Outcome:** Generated boards are written under `pcb/` or an experiments directory; root stays clean.
  - **Covered by:** R2, R3

- F3. **Reviewer opens the repo after the purge**
  - **Trigger:** Post-purge, A3 runs `git blame` on a file whose history crosses the purge commit.
  - **Actors:** A3
  - **Steps:** (1) `git blame` skips the purge commit because its hash is listed in `.git-blame-ignore-revs`. (2) A3 sees the last *real* change to each line, not the deletion sweep.
  - **Outcome:** Blame remains useful despite the large mechanical commit.
  - **Covered by:** R5

---

## Requirements

**Phase 1 — Purge (one PR, no gate yet)**

- R1. All git-tracked generated/artifact files at the repository root are removed from version control via `git rm --cached` (files remain on disk locally if desired). In-scope categories, verified by `git ls-files`:
  - 49 `*.py` one-off/debug scripts
  - 46 `*.kicad_pcb` generated board snapshots
  - 24 `*.kicad_pro` companion project files
  - 38 `*-drc.json` DRC probe outputs
  - 4 `*.stats` cProfile dumps
  - 1 `10A` orphan file
  - The 33 root `*.md` status reports are **deferred** (see Out of Scope) unless individually confirmed obsolete during execution.
- R2. `.gitignore` is extended with root-anchored patterns that block the purged categories from re-entering tracked state, while leaving nested directories unaffected: `/*.py`, `/*.kicad_pcb`, `/*.kicad_pro`, `/*.kicad_prl`, `/*-drc.json`, `/*.stats`, `/10A`. Existing broader patterns (`*.log`, `*.bak`, `__pycache__/`) remain.

**Phase 2 — Protect (CI gate, same PR)**

- R3. A pytest test (e.g. in `tests/`) asserts that `git ls-files` returns no paths matching `/*.py` or `/*.kicad_pcb` at the repository root, with an explicit allowlist for any genuinely-root-level scripts that must remain (expected: empty allowlist after purge). The test fails with a named message identifying each offending file and the intended target directory. It runs in the existing `python-tests.yml` workflow without a new job.
- R4. The gate test covers `.kicad_pro` and `*-drc.json` at root as well, so a regenerated KiCad project or DRC sweep committed at root fails CI, not just review.

**Phase 3 — Blame hygiene (same PR)**

- R5. A `.git-blame-ignore-revs` file is created at the repo root containing the hash of the purge commit. The commit message of the purge references this file so the link is discoverable. This is a one-time entry; future purge-style commits would append.

---

## Success Criteria

- After the PR lands, `git ls-files -- '*.py' '*.kicad_pcb' '*.kicad_pro' '*-drc.json' '*.stats'` with a root-only filter returns zero results (allowlist empty).
- A developer who adds a new `analyze_X.py` at root sees a CI failure on the root-gate test, not a review comment three days later.
- `git blame` on files touched by the purge commit skips the purge; the first real author of each deleted-then-recreated line is still reachable.
- The repository root contains only entry points and top-level config (`pyproject.toml`, `Makefile`, `CLAUDE.md`, `AGENTS.md`, `opencode.json`, `uv.lock`, `temper_config.yaml`, `config.toml`, `.ruff.toml`, `.gitignore`, `.gitattributes`, `.git-blame-ignore-revs`) plus intentional directories.

---

## Scope Boundaries

- **Root `*.md` status reports (33 files)** — out of scope for the initial purge. These are sprint narratives (`STATUS.md`, `BENDERS_STATUS.md`, `*_REPORT.md`, etc.) that may have reference value. A separate triage pass decides keep-vs-archive; lumping them into the artifact purge risks deleting context. The CI gate does not cover `*.md` at root.
- **`scripts/` and `tools/` cleanup** — out of scope. Those directories have their own hygiene issues but are not the root-sprawl problem this PR targets.
- **Broken-import root scripts** — the ideation claim that root scripts have "broken imports" is **not verified**. Sampling 9 root `.py` files: 8 parse and import cleanly (several even execute module-level code), only `hybrid_astar_snippet.py` has a syntax error (it is a snippet, by name). The purge justification is *location and purpose*, not brokenness. No per-script repair is in scope; they are removed as a category.
- **History rewriting / `git filter-repo`** — out of scope. The purge is a normal deletion commit; history bloat is accepted and mitigated only by R5.
- **Benders logs and `.bak` files** — already untracked; nothing to purge. The ideation brief over-counted these.
- **Pre-commit framework adoption** — out of scope. No `.pre-commit-config.yaml` exists today; introducing the framework is a separate decision. The gate is a pytest test that fits the existing CI.

---

## Key Decisions

- **Gate mechanism: pytest test, not pre-commit or a ruff custom rule.** The repo already runs pytest in CI on every PR and has no pre-commit framework installed. A test that shells out to `git ls-files` and asserts on root-level paths is ~15 lines, runs in milliseconds, and reuses the existing workflow. A ruff custom rule cannot express "file location at repo root"; pre-commit would require a new toolchain adoption for one rule.
- **Purge is a single commit, not split by category.** Splitting (artifacts vs scripts) would require multiple `.git-blame-ignore-revs` entries and multiple CI-green intermediate states for no benefit — the change is mechanical and atomic. One commit, one blame-ignore entry.
- **`.git-blame-ignore-revs` is worth it for one commit.** The purge touches 160+ files in deletion; without the ignore entry, `git blame` on any file with history crossing the purge would surface the deletion as the last change. The setup cost is one file with one line.
- **Allowlist expected empty.** No root `.py` or `.kicad_pcb` is a legitimate entry point — `pyproject.toml` and `Makefile` are the entry points, and source lives under `packages/` and `pcb/`. If execution surfaces a genuine exception, it is added to the allowlist at that time.
- **`git rm --cached`, not `git rm`.** Files remain on disk for anyone with a working copy, avoiding surprise data loss. The `.gitignore` patterns prevent re-adding.

---

## Assumptions

- **A1 — Root `.py` scripts are not imported by package code.** Assumed true; packages live under `packages/*/src` with their own `__init__` graphs, and root scripts use `sys.path.insert` hacks to reach packages, never the reverse. If a package imports a root script, the purge would break it — verify with a grep for root-module imports during planning.
- **A2 — No CI step outside `python-tests.yml` depends on root-level `.py` files.** The workflow runs `uv run pytest` against `packages/*/tests` and `ruff check packages/`. No step executes a root script. Assumed safe; confirm by grepping the workflow file (already read: no root-script references).
- **A3 — The pytest gate test can shell out to `git ls-files` in the CI runner.** The Actions checkout provides a git repo; `git ls-files` is available on `ubuntu-latest`. Assumed reliable.
- **A4 — The 33 root `*.md` files have no active CI dependency.** Deferred per Out of Scope; if a CI step reads one (e.g. a docs check), it would need to be handled. No such step was found in `python-tests.yml`.
- **A5 — No external tooling (release scripts, bd tooling) reads root `.kicad_pcb` by name.** The `bd-setup.sh` and `bd-*` scripts operate on git/worktree state, not board files. Assumed safe; spot-check during planning.

---

## Open Questions

### Resolve Before Planning

- **[Affects R1][Evidence]** Does any package or test under `packages/` import a module that lives at the repo root (e.g. `import analyze_drc`)? A grep for `from analyze_` / `import analyze_` / `import run_` across `packages/` and `tests/` settles A1. If yes, those scripts must be relocated, not just removed.
- **[Affects R1][Specificity]** Are any of the 46 root `*.kicad_pcb` files referenced by path in `scripts/`, `tools/`, or firmware build steps as a *source* board (vs. an output)? The canonical board is assumed to live under `pcb/`; confirm no root board is a build input.

### Deferred to Planning

- **[Affects R3][Technical]** Should the gate test live in `tests/` at root or in a new `tests/hygiene/`? `tests/` already exists at root with 30 entries; a dedicated subdirectory keeps the gate discoverable but is a layout call for planning.
- **[Affects R2][Technical]** Should `/*.kicad_prl` be added to `.gitignore` given it is already covered by the global `*.kicad_prl`? Redundant but harmless; the root-anchored pattern makes intent explicit. Decide during planning.
