---
date: 2026-07-23
topic: script-infrastructure-consolidation
---

# Script Infrastructure Consolidation: Shared Utilities for 53 Top-Level Scripts

## Summary

Extract 5 shared utility modules from the 53 top-level scripts in `scripts/` (plus 5 test files) to eliminate 10 independent implementations of `_find_repo_root()` / `REPO_ROOT` computation, 8 copies of `sys.path.insert` boilerplate, 2 structurally identical gate patterns (`--init`/`--check-shrink`), duplicated `TICKET_PATTERN` regexes, and 3 divergent GitHub step summary writers. The result is a `scripts/_lib/` package with ~200 lines of shared code replacing ~400+ lines of duplicated boilerplate across the codebase. Existing scripts become thin wrappers that import shared infrastructure.

**Note on counts:** Manifest-tracked scripts = 30; total top-level `.py` files = 53. The 23 untracked scripts are not in scope for this consolidation — only scripts with documented duplication patterns (10 for `find_repo_root`, 8 for `sys.path.insert`, 2 for gate patterns) are migrated. Untracked scripts remain as-is.

---

## Problem Frame

The `scripts/` directory contains 58 Python files (53 top-level `.py` + 5 tests) with no shared library, no `__init__.py`, and no package structure. Every script is an island. The consequences are measurable:

**Duplication inventory (verified by source scan):**

| Pattern | Independent Copies | Lines Duplicated (est.) |
|---------|-------------------|------------------------|
| `_find_repo_root()` / `REPO_ROOT` computation | 10 | ~55 |
| `sys.path.insert(0, ...)` for temper-placer/src | 8 | ~40 |
| `--init` / `--check-shrink` gate pattern | 2 | ~120 |
| GitHub step summary writer | 3 | ~6 |
| argparse `ArgumentParser` + `parse_args()` | 35+ | ~175 |
| **Total duplication (conservative estimate)** | | **~396 lines** |

**Note on gate pattern count:** `check_typecheck_gate.py` uses YAML-based allowlist format incompatible with the coverage/physics `# TODO: temper-xxx` pattern. R4 targets only the 2 structurally identical gates (`check_coverage_gate.py`, `check_physics_provenance.py`). Typecheck gate migration is deferred pending the Q1 resolution.

**Note on GitHub summary duplication:** The 3 implementations differ only in the `os.environ.get("GITHUB_STEP_SUMMARY")` + `open(path, "a")` pattern (~2 lines each). R7 extracts this as a helper function `get_github_summary_path() -> str | None`, not a full context manager.

**Note on `find_repo_root` count:** 8 scripts use the canonical git-walk function, 2 use the one-liner `Path(__file__).resolve().parent.parent` (including `human_reference_compare.py` which hardcodes 2-level depth). The canonical `find_repo_root()` is R2's primary target; one-liner scripts are migrated only if they work identically with the shared function.

Each duplication creates maintenance drag:
- A bug fix in `_find_repo_root()` must be applied to 9 files, and CI won't catch the ones missed
- Adding a new CI gate script requires copy-pasting the `--init`/`--check-shrink` pattern
- The `scripts/manifest.yaml` entries for these scripts show stale `last_run` dates and corrupted YAML (duplicate import keys), suggesting manual maintenance is error-prone
- Onboarding a new developer means searching through 58 files to find utility code rather than importing from a known location

The `scripts/tests/` already uses `sys.path.insert(0, ...)` to import sibling scripts -- proving that intra-script imports are technically feasible and already in use, just ad-hoc.

---

## Requirements

### Shared Library Creation

- **R1.** Create `scripts/_lib/` as a Python package (`__init__.py`) containing shared modules, not a flat file. The `_lib` prefix signals "internal library, not a user-facing script."
- **R2.** Extract `_find_repo_root()` into `scripts/_lib/repo.py` with a single canonical implementation: walk up directory tree until `.git` is found. Return `Path`. The existing 9 implementations are replaced with `from _lib.repo import find_repo_root`.
- **R3.** Extract `sys.path.insert` boilerplate into `scripts/_lib/path_setup.py` as `setup_temper_placer_path(repo_root: Path) -> None`. The existing 7 copies are replaced with a single import.
- **R4.** Extract the `--init` / `--check-shrink` gate pattern into `scripts/_lib/gate_allowlist.py` with these shared functions:
  - `load_allowlist(path: Path) -> list[str]` -- parse a `# TODO: temper-xxx` allowlist file
  - `git_show_main_allowlist(filename: str, repo_root: Path) -> list[str]` -- fetch baseline from `origin/main`
  - `TICKET_PATTERN: re.Pattern` -- shared regex
  - `check_shrink_mode(old_entries, new_entries) -> tuple[list[str], list[str]]` -- monotonic-shrink validation
  - This eliminates the ~120 lines duplicated across `check_coverage_gate.py` and `check_physics_provenance.py`. `check_typecheck_gate.py` is excluded: it uses a YAML-based allowlist format incompatible with the `# TODO: temper-xxx` pattern. Migration of typecheck gate is deferred pending Q1 resolution.

### Import Bootstrap

- **R3a.** Every migrated script adds a single-line bootstrap preamble: `sys.path.insert(0, str(Path(__file__).resolve().parent))` before any `_lib` imports. This is unavoidable boilerplate (one line, not a function) because Python must resolve `_lib` as a package under `scripts/`. When scripts are invoked from the repo root (`python3 scripts/check_coverage_gate.py`), Python's default behavior adds `scripts/` to `sys.path[0]`, making `_lib` discoverable. The bootstrap line handles invocations from other directories. All CI and Makefile invocations use the repo-root pattern and are unaffected.

### Gate Script Migration

- **R5.** Migrate `check_coverage_gate.py` and `check_physics_provenance.py` to import from `_lib.gate_allowlist` and `_lib.repo`. Each script retains its domain-specific logic (coverage JSON parsing, AST float extraction) but delegates allowlist infrastructure to the shared library. `check_typecheck_gate.py` migration is deferred pending Q1.
- **R6.** Migrate `import_linter_gate.py` and `vulture_gate.py` to use `_lib.repo` for repo-root discovery and `_lib.github_summary` (see R7) for step summary output.

### Cross-Cutting Utilities

- **R7.** Create `scripts/_lib/github_summary.py` providing a helper function `get_github_summary_path() -> str | None` that returns `$GITHUB_STEP_SUMMARY` if the env var is set, or `None` in non-CI environments. Replace the 3 divergent `os.environ.get("GITHUB_STEP_SUMMARY")` + `open(path, "a")` patterns (~2 lines each, ~6 lines total) in `import_linter_gate.py`, `check_perf_regression.py`, and `vulture_gate.py`. Content written to the summary is script-specific; the helper only provides the path.
- **R8.** Create `scripts/_lib/argparse_helpers.py` providing `add_standard_args(parser: ArgumentParser, *, with_config: bool = False) -> None` that adds common flags (`--source-root`, `--allowlist`, `--output`). The helper function is available for adoption by scripts that use those flags; no existing scripts are migrated to use it in this phase. A script-by-script audit (deferred to planning) determines how many scripts benefit.

### Script Manifest Integrity

- **R9.** Fix structural YAML corruption in `scripts/manifest.yaml` -- the `imports` key is incorrectly indented as a child of `disposition` rather than as a sibling key. Serialize-deserialize-reserialize with PyYAML to normalize the hierarchy, then deduplicate import keys. After migration, update `trace_invocations.py` to correctly trace imports that now go through `_lib` rather than being inlined.
- **R9a.** Promote `trace_invocations.py` integration from Deferred to Planning to Resolve Before Planning: extend `trace_invocations.py` to recognize `from _lib.<module> import ...` and record edges from scripts to `_lib/<module>.py` in the invocation graph. Verify `check_manifest_gate` passes.
- **R9b.** Update `check_manifest_gate.py` to exclude `_lib/**` from its scan. `_lib` modules are infrastructure, not user-facing scripts, and are exempt from `scripts/manifest.yaml` entries per the Key Decision on the `_` prefix convention.

### Non-Goals

- **R10.** `_lib` modules must have zero Python package dependencies beyond the standard library. They may use system tools (`git`, accessible via `subprocess`) present in all CI and developer environments. `git_show_main_allowlist()` raises a specific exception with a human-readable message if git is unavailable or the working directory is not inside a repo.

### Library Testing

- **R11.** `scripts/tests/` must include `test_lib_repo.py`, `test_lib_gate_allowlist.py`, and `test_lib_github_summary.py` covering all public functions in `_lib/`. Consolidating 10+ callers onto a single implementation without tests centralizes risk: a bug in `find_repo_root()` currently breaks one script; after consolidation it breaks all consumers.

---

## Acceptance Examples

- **AE1. Covers R2.** Given `_lib/repo.py` exists and all scripts have been migrated, when `rg 'def _find_repo_root' scripts/ --include '*.py' --glob '!_lib/**'` runs, it returns zero hits (the old function definitions are gone outside `_lib/`) and `rg 'from _lib.repo import' scripts/ --include '*.py'` returns 10+ hits (all scripts use the shared import). The one-liner `REPO_ROOT = Path(__file__).resolve().parent.parent` patterns are replaced where semantically equivalent to the canonical `find_repo_root()`. Scripts that differ (e.g., `human_reference_compare.py` which hardcodes 2-level depth) are documented as special cases.
- **AE2. Covers R4, R5.** Given `check_coverage_gate.py` imports from `_lib.gate_allowlist`, when the allowlist logic needs a bug fix, a single edit to `_lib/gate_allowlist.py` fixes all gate scripts. CI test `scripts/tests/test_coverage_gate.py` still passes.
- **AE3. Covers R10, R3b.** Given only `python3` is installed (no `uv`, no virtualenv), when `python3 scripts/check_coverage_gate.py --help` runs from the repo root, it succeeds because Python's default behavior adds `scripts/` to `sys.path[0]`, making `_lib` discoverable. Invocation from other directories requires the R3b bootstrap line.

---

## Success Criteria

- `scripts/_lib/` exists with 5 modules (`repo.py`, `path_setup.py`, `gate_allowlist.py`, `github_summary.py`, `argparse_helpers.py`)
- All 10 `_find_repo_root()` / `REPO_ROOT` implementations are replaced by a single import
- All 8 `sys.path.insert` boilerplate blocks are replaced by a single import
- `check_coverage_gate.py` and `check_physics_provenance.py` pass CI after migration
- `scripts/tests/test_lib_repo.py`, `test_lib_gate_allowlist.py`, and `test_lib_github_summary.py` exist with >=80% coverage on `_lib/` public functions
- `scripts/manifest.yaml` is valid YAML (no duplicate keys, correct indentation hierarchy) and `check_manifest_gate` excludes `_lib/**`
- `trace_invocations.py` runs successfully, produces a correct `invocation_graph.json`, and includes `_lib` edges

---

## Scope Boundaries

- **In scope:** Extracting shared infrastructure (repo root, path setup, gate patterns, GitHub summary, argparse helpers) into `scripts/_lib/`. Migrating the following scripts: `check_coverage_gate.py`, `check_physics_provenance.py` (R5), `import_linter_gate.py`, `vulture_gate.py` (R6), and all scripts with the git-walk `_find_repo_root()` function (R2). Migration of `check_typecheck_gate.py` and mass argparse adoption are deferred to follow-on phases.
- **Out of scope:** Rewriting script logic or behavior. The migration is mechanical (replace inline code with import). No script changes what it does.
- **Out of scope:** Creating a full CLI framework or replacing argparse with click/typer. `argparse_helpers.py` only adds shared argument definitions.
- **Out of scope:** Migrating shell scripts (`.sh`) -- Python-only.
- **Out of scope:** Changing `scripts/manifest.yaml` conventions or the sunset clock mechanism.
- **Out of scope:** Requiring all scripts to be migrated in a single commit. Incremental migration is acceptable -- not all scripts must be migrated in a single commit. Each migrated script must pass its own CI independently. Inline implementations remain until their last caller is migrated.

---

## Key Decisions

- **`_lib` over `utils` or `shared`.** The underscore prefix is the Python convention for "internal, not a public API." This signals to developers that `_lib` modules are infrastructure, not application scripts with their own manifest entries.
- **Standard library only for `_lib`.** Prevents creating a dependency chain where scripts need `uv sync` to run. Scripts that already depend on `temper_placer` (via `sys.path.insert`) keep that dependency; `_lib` itself stays pure stdlib.
- **Minimal extraction, not maximal.** Only patterns with 3+ copies are extracted. Two-copy patterns (like `TICKET_PATTERN`) are included only when they're part of a larger extraction (the gate pattern). One-off patterns stay in place.
- **`scripts/tests/` imports `_lib` via `sys.path.insert`** -- same mechanism already used for sibling script imports. No need for editable installs or `pyproject.toml` changes.
- **Import bootstrap.** When scripts are invoked from the repo root (`python3 scripts/foo.py`), Python's default behavior adds `scripts/` to `sys.path[0]`, making `_lib` discoverable as a subpackage. For invocations from other directories, each migrated script adds a single-line preamble: `sys.path.insert(0, str(Path(__file__).resolve().parent))`. This one line is acceptable unavoidable boilerplate -- it replaces the 9-line `_find_repo_root()` function, not adds to it.

---

## Dependencies / Assumptions

- **Methodology.** All implementation follows TDD (Red-Green-Refactor per AGENTS.md), with property-based tests (Hypothesis) for invariants where applicable. For shared library functions (e.g., `find_repo_root`, `git_show_main_allowlist`), base cases are proven correct via unit tests and the implementation generalizes by construction (inductive reasoning over directory depth / git ref structure). No shared utility ships without at least one PBT invariant.

- **Assumption:** The 10 `_find_repo_root()` / `REPO_ROOT` implementations are semantically identical and a single canonical version works for all callers. Verified by source scan -- all walk up finding `.git`, except the two special cases documented in Outstanding Questions.
- **Assumption:** The 7 `sys.path.insert` blocks use the same path (`packages/temper-placer/src`) and are interchangeable. Verified by source scan.
- **Assumption:** The 3 gate scripts' `--init`/`--check-shrink` patterns are similar enough for a shared library without breaking any script's unique behavior. The differences (allowlist format, shrink validation details) are parametrizable.
- **Dependency:** `scripts/manifest.yaml` repairs must happen atomically with `_lib` migration -- a half-migrated state (scripts reference `_lib` but manifest still has old imports) breaks `check_manifest_gate`.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R5][User decision]** Should `check_typecheck_gate.py` also migrate to `_lib.gate_allowlist`? It currently implements its own allowlist parsing (YAML-based, not the `# TODO: temper-xxx` format) and may diverge enough from the coverage/physics pattern that a shared base isn't worth the abstraction cost.
- **[Affects R4][Technical]** What is the public API surface of `gate_allowlist.py`? The shared pattern must cover `--init` mode (populate baseline), `--check-shrink` mode (validate vs `origin/main`), and default mode (validate vs allowlist). Does type-check's YAML allowlist fit this API?
- **[Affects R9][Technical]** How does `trace_invocations.py` discover `_lib` imports? It currently parses `import` statements from script source. If `_lib` modules are used, the invocation graph should show edges from scripts to `_lib` modules. This is a CI gate prerequisite (`check_manifest_gate`) and must be resolved before planning.
- **[Affects R2][Verified fact]** Two of the 10 find_repo_root implementations use hardcoded `Path(__file__).resolve().parent.parent` and may not work with the canonical git-walk function: `human_reference_compare.py` (assumes exactly 2-level depth from repo root) and `verify_proofs.py` (accepts optional `start` parameter, returns `start` on failure instead of raising). These are documented as special cases and require individual verification before migration.

### Deferred to Planning

- **[Affects R8][Technical]** How many scripts actually benefit from `add_standard_args()` vs. have unique argument requirements? A script-by-script audit is needed.
- **[Affects R6][Technical]** Does `import_linter_gate.py`'s GitHub summary pattern (append mode with markdown) differ enough from `check_perf_regression.py`'s (write mode) to warrant separate paths, or can `github_summary.py` handle both?
