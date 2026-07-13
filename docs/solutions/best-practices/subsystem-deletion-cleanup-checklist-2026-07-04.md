---
title: "Systematic cleanup checklist for deleting a major Python subsystem"
date: 2026-07-04
category: best-practices
module: temper-placer
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "Deleting a major subsystem (10K+ lines) with deep import chains across 20+ consumer modules"
  - "Removing 50+ test files that imported from deleted modules"
  - "Updating 14 CI workflow files after a subsystem deletion"
tags:
  - subsystem-deletion
  - cleanup-checklist
  - ci-cd
  - import-wrapping
  - test-regression
---

# Systematic cleanup checklist for deleting a major Python subsystem

## Context

Deleting the JAX optimizer/losses/placement subsystem (~90K lines across source
and tests) left 37 import sites in 22 surviving consumer modules, 50+ test
files importing deleted modules, and 14 CI workflow files referencing deleted
code paths.  The cleanup followed a three-pass pattern that resolved everything
to 0 ruff errors, 0 test collection errors, and 1,156 tests passing.

## Guidance

### Pass 1: Wrap imports, don't delete consumer modules

Consumer modules that import deleted code but have independent value
(`pipeline/`, `regression/`, `validation/`, `metrics/`) should have their
module-level imports wrapped in `try/except ImportError` with `pass`, not
deleted.  The consumer module survives; the deleted code path silently degrades.

```python
# Before: direct import of deleted module
from temper_placer.losses.base import LossContext
from temper_placer.optimizer import OptimizerConfig, train

# After: graceful degradation
try:
    from temper_placer.losses.base import LossContext
    from temper_placer.optimizer import OptimizerConfig, train
except ImportError:
    pass  # JAX optimizer deleted (plan 2026-07-03-002 U5)
```

This is temporary — the report explicitly flags it as "graceful degradation, not
final state."  Per-file refactoring to CP-SAT equivalents follows in a separate
PR.

### Pass 2: Delete test files that import deleted modules

Test files that import from deleted modules must be deleted — they cannot be
salvaged by import wraps because the tests exercise deleted functionality.  Find
them with `grep -rl "from temper_placer.\(optimizer\|losses\)" tests/` and
remove in one pass.

Test directories for deleted modules (`tests/ablation/`, `tests/optimizer/`,
`tests/losses/`) are removed in their entirety.

### Pass 3: Sweep CI workflows

After deletions, sweep every CI workflow for references to:
- Deleted test paths (`tests/losses/`, `tests/optimizer/tests/ablation/`)
- Deleted module paths (`losses`, `optimizer`, `benders_loop`)
- Deleted test file names

Replace optimizer/losses test steps with surviving CP-SAT test steps.
Workflows that run deleted pipelines but already carry `continue-on-error: true`
can stay — they gracefully degrade alongside the import wraps.

### Verification order

After each pass, verify in this order before committing:

1. **Collection**: `pytest --co` — must return 0 errors
2. **Ruff**: `ruff check` on all modified source — must return 0 errors
3. **Surviving tests**: Run key surviving modules (`placer/cp_sat/`, `core/`,
   `pcl/`, `io/`, `deterministic/`) — must pass with 0 failures
4. **CI sweep**: `grep -rn <deleted_paths> .github/workflows/` — must return
   0 matches

## Why This Matters

- **Import wraps prevent cascade failures**: Deleting a module that 22 others
  import would cause all 22 to fail at import time, blocking every CI job that
  touches any of them.  Import wraps keep the surviving modules importable while
  the code paths are refactored.
- **Test file deletion is cleaner than test fixes**: A test that exercises
  deleted functionality has no salvageable value.  Fixing it means rewriting it
  for CP-SAT — which is new work, not cleanup.  Delete it and document what
  was lost.
- **CI workflow sweep catches the integration surface**: Source imports and
  test collection errors are the first two layers.  CI workflow references are
  the third — they fail at runtime, not at collection, and are harder to
  discover without explicit grep.

## When to Apply

Apply this pattern when:
- Deleting a subsystem that 10+ consumer modules import
- The consumer modules have independent value beyond the deleted dependency
- You need to keep the build green during a multi-PR decomposition

Do NOT apply when:
- The consumer modules exist solely to serve the deleted subsystem — delete them
  entirely instead of wrapping
- You have time to refactor each consumer module before the deletion commit —
  import wraps are a staging strategy, not a final state

## Examples

### Before/After: CI workflow

```yaml
# Before: tests/losses/ directory deleted in source but still referenced in CI
- name: Run invariant tests (router_v6, io, deterministic, losses)
  run: uv run pytest tests/router_v6/ tests/io/ tests/deterministic/ tests/losses/ ...

# After: losses/ removed, CP-SAT tests added
- name: Run invariant tests (router_v6, io, deterministic)
  run: uv run pytest tests/router_v6/ tests/io/ tests/deterministic/ ...

- name: Run CP-SAT placer tests
  run: uv run pytest tests/placer/cp_sat/ tests/metrics/test_external_oracle.py ...
```

### Verification result

```
5,048 tests collected, 0 errors
1,156 passed, 0 failures, 2 pre-existing FileNotFoundErrors
ruff: 0 errors
CI: 14 workflows, 0 references to deleted modules or paths
```

## Related

- `docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`
  — the feasibility-first paradigm that justified the deletion
- `docs/reports/2026-07-03-comprehensive-session-report.md` — full session report
  with import wrap count and test deletion tally
- `docs/plans/2026-07-03-002-feat-calendar-gate-jax-retirement-plan.md` — plan
  that defined the deletion scope
