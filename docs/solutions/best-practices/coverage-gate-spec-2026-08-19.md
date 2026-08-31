---
title: "Coverage gate specification — scope, allowlist format, --init workflow, shrink rule, and paydown cadence"
date: "2026-08-19"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "adding a new public function to temper_placer and wondering whether it needs a test"
  - "expanding the coverage gate to a new module or package (Phase 3+)"
  - "adding or removing an entry in .coverage-allowlist"
  - "deciding whether a stale allowlist entry (now covered) is a failure"
  - "an emergency need to skip the gate and no env-var override exists"
tags:
  - coverage-gate
  - allowlist
  - pytest
  - ci-gate
  - phase-2
---

# Coverage gate specification

## Scope (Phase 2)

The coverage gate currently applies to all public functions in
`temper_placer/` except `_constraint_types/` (pydantic `BaseModel` types —
hand-written, R7-resolved JUSTIFIED-KEEP 2026-08-11) and `profiling/`
(production diagnostics). These subpackages are permanently excluded via
`[tool.coverage.run] omit` in `pyproject.toml` and `--cov-config` in CI.
The gate catches public functions (module-level `def` not prefixed with
`_`, and methods of public classes not prefixed with `_`) whose body has
**zero executed lines** during the test suite.

## How it works (Phase 2 — inline coverage)

1. CI runs `uv run pytest tests/core/ -v --tb=short --maxfail=10
   --cov=temper_placer --cov-report=json --cov-report=term
   --cov-config=../../pyproject.toml` in `packages/temper-placer/`,
   producing `coverage.json` as a side effect during normal test execution.
   No separate pytest invocation.
2. `scripts/check_coverage_gate.py` reads `coverage.json`, AST-parses each
   source file to identify public functions, and checks coverage for each.
3. Any zero-coverage public function **not on the allowlist**
   (`.coverage-allowlist`) fails CI.
4. The CI gate step is currently **warn-only** (`continue-on-error: true`)
   until the Phase 1 paydown prerequisite is met. Once met, a follow-on PR
   removes `continue-on-error` and the gate becomes a hard CI block.

## Phase 1 paydown prerequisite

Phase 2's hard-fail gate is gated on the Phase 1 allowlist (entries for
`temper_placer/core/`) having shrunk by >=50% from the initial 193 entries.
Current count is tracked in the `.coverage-allowlist` header. The gate step
uses `continue-on-error: true` with a warning annotation providing context
until the prerequisite is verified and the guard is removed.

## `--init` workflow (for new phases)

When expanding scope to new modules:
1. Add the new module paths to `source` in `[tool.coverage.run]` in
   `pyproject.toml` and add `omit` patterns for excluded subpackages.
2. Run `uv run pytest tests/core/ --cov=<new.scope> --cov-report=json
   --cov-config=../../pyproject.toml` from `packages/temper-placer/` to
   generate `coverage.json`.
3. Run `python scripts/check_coverage_gate.py --init --coverage-json
   /path/to/coverage.json --allowlist .coverage-allowlist`. The `--init`
   mode preserves existing allowlist entries; new entries are appended with
   `# TODO: temper-xxx` placeholders.
4. Review the output: remove stale entries (now have coverage), replace
   `# TODO: temper-xxx` placeholders with real ticket IDs.
5. Commit the updated allowlist.

For Phase 2 specifically: `--init` appends new entries for modules outside
`temper_placer/core/`. Existing entries are preserved. Real ticket IDs
replace `# TODO: temper-xxx` placeholders before commit.
`_constraint_types/` and `profiling/` are permanently excluded via
`[tool.coverage.run] omit`.

## Excluded subpackages

- `temper_placer/_constraint_types/` — pydantic `BaseModel` constraint
  types (hand-written, not generated — R7 resolution 2026-08-11:
  JUSTIFIED-KEEP, see `docs/evidence/2026-08-11-r7-constraint-types-resolution.md`).
- `temper_placer/profiling/` — production diagnostics, wall-clock
  instrumentation.

These are excluded via `omit = ["*/_constraint_types/*", "*/profiling/*"]`
in `[tool.coverage.run]` (root `pyproject.toml`) and via
`--cov-config=../../pyproject.toml` in CI.

## Allowlist format (`.coverage-allowlist`)

```
temper_placer/core/<module>.py::function_or_Class.method  # TODO: temper-xxx
```

- One entry per line. `#` starts a comment.
- Every entry **must** have a `# TODO: temper-xxx` trailing comment (either
  a real ticket ID or the `temper-xxx` placeholder for initial baseline).
- The file lives at repo root, visible alongside `pyproject.toml`.

## Monotonic-shrink rule

- **Removals**: An allowlist entry may only be removed when the same PR
  either adds a test exercising the function OR deletes the function from
  source. `--check-shrink` enforces this.
- **Additions**: A new entry must include a `# TODO: temper-xxx` ticket
  reference. Placeholder `temper-xxx` is accepted for initial bulk
  population only; real tickets are required for subsequent additions.
- This ensures the allowlist shrinks over time — it is not a backdoor for
  ignoring uncovered code.

## Paydown cadence

- Phase advancement (e.g., expanding scope from `temper_placer/` to
  `temper-drc`, `temper-tools`, `temper-workflow` for Phase 3) is gated on
  50% allowlist entry paydown.
- Recommended cadence: quarterly hardening sprint focused on writing tests
  for allowlisted functions and removing entries.
- An allowlist entry that now has coverage triggers a `WARNING` in CI
  (stale entry) — not a failure.

## Escape hatch

There is no env-var override to skip the gate. The allowlist **is** the
recorded justification — a reviewer sees allowlist additions/removals in
`git diff`. To skip the gate temporarily in an emergency, the CI step
configuration (`python-tests.yml`) can be modified directly.
