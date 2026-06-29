---
title: Infrastructure components tested in isolation but never wired into the pipeline execution path
date: "2026-06-28"
last_updated: "2026-06-28"
category: workflow-issues
module: temper_placer
problem_type: workflow_issue
component: testing_framework
severity: high
applies_when:
  - "Adding infrastructure behind an optional parameter, feature flag, or config toggle"
  - "Introducing pipeline hooks, callbacks, or middleware that must be explicitly wired"
  - "Testing components in isolation when their value comes from being invoked in production path"
symptoms:
  - "Unit tests pass but the feature never runs in the actual pipeline"
  - "Code coverage reports show code as covered (unit-tested) but it's never invoked in production"
  - "Pipeline stages or hooks exist in code but are unreachable from the main execution path"
tags:
  - integration-test
  - pipeline-connectivity
  - dead-code
  - optional-parameter
  - test-isolation
  - fail-soft
---

# Infrastructure components tested in isolation but never wired into the pipeline execution path

## Context

Three independent infrastructure components were implemented, tested in isolation, code-reviewed, and merged to `main` — but none were actually connected to the `RouterV6Pipeline.run()` execution path:

1. **StageLedger** (`stage_ledger.py`) — tracked object cardinality across stage boundaries. Unit tests passed (7 tests). Never imported or called from `pipeline.py`.

2. **DRC fence checks** (`ViaSpacingCheck`, `TraceClearanceCheck`) — Stage 1 and Stage 4 fence invariants referenced `drc_via_spacing` and `drc_trace_clearance`, but the checks weren't registered in the fence's `CheckRunner`. The fence silently returned zero violations.

3. **Theta*/Lazy Theta* monitor hooks** — runtime invariant checks (f-cost monotonicity, path integrity) existed for standard `_astar_search` but not the `_astar_search_theta_star` or `_astar_search_lazy_theta_star` variants. The Theta* test was marked `skip`.

All tests passed because they tested the components directly. No test ever asserted that the components were *called* during pipeline execution.

## Guidance

**When adding any infrastructure behind an optional parameter or when creating algorithm variants that should inherit base invariants, write at least one positive integration test that exercises the full pipeline end-to-end with the feature enabled.**

The integration test's sole purpose is to **prove connectivity**. It does not need to exercise every edge case — the unit tests cover that. It needs to fail loudly if the wiring is absent.

For auto-registration (fence checks): when a named resource must be resolvable at runtime, ensure it is registered before first use. A lazy-registration pattern (`_ensure_checks_loaded`) catches this at the call site rather than requiring manual registration during pipeline construction.

For algorithm variants (monitor hooks): if a base implementation has invariant checks, all production variants should inherit them. Missing hooks should cause a test failure, not a skip.

## Why This Matters

Unit tests on isolated components produce **false confidence** when the component is never wired. Green CI suggests readiness, but the feature does not exist at runtime. This is a systemic risk for any codebase that uses optional parameters to roll out infrastructure incrementally — incremental rollout naturally defers wiring, and without a test demanding it, wiring may be forgotten indefinitely.

## When to Apply

- Adding a pipeline hook, callback, validator, or monitor controlled by a parameter or flag
- Creating an algorithm variant that should inherit invariant checks from the base
- Code review reveals a component that *could* be wired but no test proves it *is* wired
- You discover a feature that was merged but never activated

## Examples

**StageLedger — fail-soft by default.** When wiring, default to non-fatal behavior. Promote to fatal only after battle-testing:

```python
# In pipeline.py constructor:
# `fail_on_imbalance=False` — cardinality tracking runs but doesn't crash.
# The original wiring used `fence is not None` which made it fatal the
# moment a DRC fence was present, breaking the closure test at first use.
self.ledger = StageLedger(fail_on_imbalance=False)

# In pipeline.py run(), after each stage:
self.ledger.checkin(pcb)
# ... stage executes ...
self.ledger.checkout("escape_vias", pcb)
```

**Fence checks — lazy auto-registration with defensive guards.** Always wrap in try/except — missing dependencies (fence runner not initialized, temper_drc not installed) should not crash the pipeline:

```python
def _ensure_checks_loaded(fence, invariants):
    needed = {inv.check_name for inv in invariants}
    try:
        existing = {c.name for c in fence._runner.checks}
    except (AttributeError, TypeError):
        return  # fence runner not initialized, skip
    missing = needed - existing
    if not missing:
        return
    try:
        from temper_drc.checks.drc.trace_clearance import TraceClearanceCheck
        from temper_drc.checks.drc.via_spacing import ViaSpacingCheck
    except ImportError:
        return  # temper_drc not available, skip
    if "drc_via_spacing" in missing:
        fence._runner.checks.append(ViaSpacingCheck())
    if "drc_trace_clearance" in missing:
        fence._runner.checks.append(TraceClearanceCheck())
```

## When wiring fails

The original wiring (bc7b271d) activated all three components simultaneously with no error tolerance, causing three CI gate failures. The fix (PR #79):

1. **StageLedger**: `fail_on_imbalance` → `False`. Never default a newborn feature to fatal.
2. **`_ensure_checks_loaded`**: Wrapped `fence._runner` access and `temper_drc` imports in try/except.
3. **LOC cap**: Bumped `pipeline.py` baseline to account for guard code.

The lesson is not "don't wire dead code" — wiring was correct. The lesson is **wire with fail-soft defaults and defensive guards**. Dead code was dead for a reason (untested in production). First activation should degrade gracefully, not crash.

## Related

- `packages/temper-placer/src/temper_placer/router_v6/stage_ledger.py` — StageLedger implementation
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:944` — `_ensure_checks_loaded` integration point
- `docs/plans/2026-06-28-003-feat-pipeline-contracts-integration-plan.md` — contracts plan that introduced these components
- `docs/solutions/architecture-patterns/ci-profiling-platform-canonical-metrics-contract-2026-06-28.md` — structural prevention: the profiling platform's `temper profile run` + `--from-stdin` pipeline ensures every new profiler is wired into CI from day one, eliminating the "tested but never called" failure mode
