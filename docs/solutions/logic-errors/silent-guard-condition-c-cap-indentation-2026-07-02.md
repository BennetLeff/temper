---
title: "Silent guard conditions prevent infrastructure from executing despite being wired and enabled"
date: 2026-07-02
category: logic-errors
module: temper-placer
problem_type: logic_error
component: infrastructure
symptoms:
  - "A/B comparison of C-CAP ON vs OFF produces byte-identical results across all 10 seeds"
  - "Explicit checks show ccap_enabled=True and constraints=not None — both guard conditions pass"
  - "Direct call to project_to_feasible produces 50mm position deltas — the operator itself works"
  - "But the experiment runner's C-CAP ON vs OFF runs are identical — the guard passes but the code path is never reached"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags:
  - ccap
  - indentation
  - guard-condition
  - silent-failure
  - infrastructure
  - temper-placer
related:
  - docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md
  - docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md
---

# Silent guard conditions prevent infrastructure from executing despite being wired and enabled

## Problem

The C-CAP feasibility projector (`project_to_feasible`, 968 lines of Dykstra alternating-projection code) was wired into `train.py:406` behind the guard condition `if config.initialization.ccap_enabled and constraints is not None:`. Both conditions were satisfied (`ccap_enabled=True`, `constraints=PlacementConstraints(...)`), yet C-CAP produced byte-identical results across all seeds with and without it enabled. A multi-seed experiment (10 seeds × 2 conditions, 20 runs) concluded "C-CAP has zero effect" — but the projector was never actually called.

The root cause was 4 spaces of indentation: the C-CAP block was nested inside the `else:` branch of `if initial_state is not None:`, so it only executed when `initial_state was None`. The physics oracle (and the experiment runner) always passed `initial_state` from the pipeline — the `if initial_state is not None:` branch was always taken, and the C-CAP block inside the `else:` was silently skipped.

## Symptoms

- **Byte-identical A/B results.** The smoking gun. When C-CAP ON and OFF produce identical scores for every seed, the treatment condition is a no-op. If C-CAP had actually run, the 50mm position change would produce at least slightly different gradient paths.
- **Guard conditions appear satisfied.** Both `ccap_enabled=True` and `constraints is not None` were True. Checking only the boolean flags would falsely confirm the infrastructure is active.
- **The infrastructure works when called directly.** `project_to_feasible()` called directly outside the training loop converges in 2 cycles, moves components by 50mm, and resolves all violations. The operator is fine — it was the call site that was unreachable.
- **No error, no log, no indicator of failure.** The code path simply wasn't taken. Unlike a crash or exception, a silently skipped block leaves no trace.

## Root Cause

```python
# train.py:315-406 (simplified)

if initial_state is not None:       # line 315
    positions = initial_state.positions
    rotation_logits = initial_state.rotation_logits
else:                                # line 320
    # ... method-based initialization ...
    rotation_logits = jnp.zeros(...)

    # C-CAP pre-projection           # line 405 — INDENT=8, INSIDE else:
    if config.initialization.ccap_enabled and constraints is not None:
        result = project_to_feasible(...)
        positions = result.positions
```

The C-CAP block (lines 405-428) was indented at 8 spaces — at the same level as the method initialization chains inside the `else:` branch. It was never reached when `initial_state` was provided.

## Occurrences in This Codebase

This is the third instance of the same pattern:

| # | Instance | Guard condition | What silently failed |
|---|----------|----------------|---------------------|
| 1 | Dark physics metrics | `if hv_components and lv_components:` — both sets empty because net classification wasn't wired | `hv_lv_clearance_score` returned 1.0 for all placements |
| 2 | Baseline extractor | `try: import compute_hpwl except: pass` — wrong function name, ImportError swallowed | All five corpus baselines recorded hpwl_final=0.0 |
| 3 | C-CAP indentation | `if ccap_enabled and constraints:` inside `else:` — condition true but code path unreachable | C-CAP never ran, 20-run experiment produced false null result |

The common thread: infrastructure is built, tested in isolation, wired into a call site behind a guard condition, and the guard condition is satisfied — but the code path is unreachable due to a structural issue (empty input set, swallowed exception, indentation). Each time, the failure is silent: no crash, no assertion failure, just output that looks valid but is wrong.

## Detection Pattern

- **A/B comparison is the most reliable detector.** Run the system with and without the infrastructure enabled. If the output is byte-identical, the infrastructure is either a no-op or not running. Either way, it's a finding.
- **Log guard conditions with explicit "executed / skipped" messages.** Each guard should log whether the block was entered, not just whether the condition was true. `logger.info("C-CAP: running (initial_state=%s)", initial_state is not None)` would have caught this.
- **Log the output delta of any transformation that claims to modify state.** After `project_to_feasible`, log `max(|positions - prev_positions|)`. A delta of 0.0 after a claimed projection is a smoking gun.

## Prevention

1. **Structure guards to run at the same nesting level as the data they depend on.** The C-CAP block should be at the top level of `initialize_training_state`, not nested inside the initialization method branching.
2. **Test infrastructure in integration, not just in isolation.** The C-CAP tests verify `project_to_feasible` directly (93 tests). None verify that `train_multiphase` actually calls it.
3. **Assert A/B divergence in integration tests.** A test that runs `train_multiphase` with C-CAP ON vs OFF and asserts `max(|pos_ON - pos_OFF|) > 0` would have caught this in CI.

## Resolution

Unindented the C-CAP block from 8 spaces to 4 spaces, moving it from inside the `else:` branch to the top level of `initialize_training_state`. Also duplicated the `rotation_logits = jnp.zeros(...)` initialization into a new `if initial_state is None:` guard to maintain the correct flow.
