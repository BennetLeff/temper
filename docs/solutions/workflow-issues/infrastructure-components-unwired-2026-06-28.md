---
title: Infrastructure components tested in isolation but never wired into the pipeline execution path
date: "2026-06-28"
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

**StageLedger — before (no integration test):**
```python
def test_stage_ledger_records_entries():
    ledger = StageLedger()
    ledger.checkin(state)
    ledger.checkout("compile", state)
    assert report.is_balanced
    # Passes. But pipeline never creates a StageLedger because
    # fail_on_imbalance defaults to False and nobody calls it.
```

**StageLedger — after (connectivity proven):**
```python
# In pipeline.py constructor:
self.ledger = StageLedger(fail_on_imbalance=fence is not None)

# In pipeline.py run(), after each stage:
self.ledger.checkin(pcb)
# ... stage executes ...
self.ledger.checkout("escape_vias", pcb)
```

**Fence checks — lazy auto-registration:**
```python
def _ensure_checks_loaded(fence, invariants):
    needed = {inv.check_name for inv in invariants}
    existing = {c.name for c in fence._runner.checks}
    missing = needed - existing
    if "drc_via_spacing" in missing:
        fence._runner.checks.append(ViaSpacingCheck())
    if "drc_trace_clearance" in missing:
        fence._runner.checks.append(TraceClearanceCheck())
```

**Monitor hooks — variants inherit base invariants:**
```python
# In _astar_search_theta_star loop:
while frontier:
    _, current_key = heappop(frontier)
    _mon = get_monitor_state()
    if _mon is not None:
        _mon.record_pop((x, y), float(cost_so_far[current_key]))
    # ... search continues ...
```

## Related

- `packages/temper-placer/src/temper_placer/router_v6/stage_ledger.py` — StageLedger implementation
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:944` — `_ensure_checks_loaded` integration point
- `docs/plans/2026-06-28-003-feat-pipeline-contracts-integration-plan.md` — contracts plan that introduced these components
