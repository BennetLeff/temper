---
title: "Silent guard conditions prevent infrastructure from executing — a recurring failure pattern"
date: 2026-07-02
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Adding a feature toggle where ON/OFF should produce different output"
  - "Debugging why a config flag appears to have no effect despite being set"
  - "Reviewing guard conditions that gate significant computation"
  - "An A/B comparison across 2+ seeds produces byte-identical results for a state-modifying feature"
  - "A metric value is suspiciously constant (always 1.0, always 0.0, always alias)"
tags:
  - silent-failure
  - guard-condition
  - infrastructure
  - dark-metrics
  - dead-code-activation
  - indentation
  - temper-placer
  - integration-testing
  - a-b-testing
---

# Silent guard conditions prevent infrastructure from executing — a recurring failure pattern

## Context

Infrastructure is built, tested in isolation, wired into a call site behind a guard condition, and the guard condition is satisfied — but the code path is unreachable due to a structural issue. The failure mode is silent: no crash, no assertion failure, no logged warning. Output looks valid but is wrong. The temper-placer codebase has produced three instances of this pattern across different subsystems:

| # | Instance | Guard condition | Structural issue | Effect |
|---|----------|----------------|---------------------|--------|
| 1 | Dark physics metrics | `if hv_components and lv_components:` | Both sets were empty because net classification was never wired into `quality_config`. The score function fell through its "no components to check" path. | `hv_lv_clearance_score` returned `1.0` for all placements; `ClearanceLoss` weight of `100.0` produced zero gradient |
| 2 | Baseline extractor | Implicit: `try: import compute_hpwl except: pass` | Wrong function name (`compute_hpwl` vs `compute_total_hpwl`), bare `except` swallowed the `ImportError`. Three additional metrics were hardcoded `0.0`. | All five corpus baselines recorded `hpwl_final=0.0`; regression gate passed on every PR for months |
| 3 | C-CAP indentation | `if config.initialization.ccap_enabled and constraints is not None:` | The block was indented inside the `else:` branch of `if initial_state is not None:`. When `initial_state` was passed (always, in the oracle), the C-CAP code was unreachable. | 20-run A/B experiment concluded C-CAP had zero effect; the 968-line projector was never called |

The common thread: three different structural failure mechanisms (empty input set, swallowed exception, indentation nesting) each produced the same outcome — a guard condition whose boolean expression evaluates to `True`, but whose code path is never reached.

## Guidance

### Detection

Detection must assume the guard condition is satisfied — checking only the boolean flags will falsely confirm the infrastructure is active. Three strategies, from cheapest to most thorough:

**1. A/B comparison (smoking gun)**

Run the system with and without the infrastructure enabled. If the output is byte-identical or within floating-point epsilon, the treatment condition is a no-op. This is the most reliable single detector because it makes zero assumptions about the failure mechanism.

```python
# A/B diff for any toggleable feature
run_a = run_pipeline(corpus, feature_enabled=False)
run_b = run_pipeline(corpus, feature_enabled=True)

if jnp.allclose(run_a.positions, run_b.positions):
    raise SilentNoopError(
        f"Feature enabled/disabled produce identical output — "
        f"either the feature is a no-op or it never runs"
    )
```

Multi-seed coverage increases confidence: identical results across 10 seeds for ON vs OFF is impossible for any constraint that actually produces a nonzero gradient.

**2. Instrument guard conditions with explicit "executed / skipped" logging**

Every guard should log whether the block was entered, not just whether the condition was true. Logging the boolean is misleading when the guard evaluates to `True` but the block is unreachable due to nesting.

```python
# BEFORE — misleading: only logs the flag, not reachability
if config.initialization.ccap_enabled and constraints is not None:
    logger.info("C-CAP enabled")
    result = project_to_feasible(...)
    positions = result.positions

# AFTER — explicit: logs whether the block was entered
if config.initialization.ccap_enabled and constraints is not None:
    logger.info("C-CAP: executing projection (initial_state=%s, n_components=%d)",
                initial_state is not None, len(positions))
    result = project_to_feasible(...)
    positions = result.positions
    logger.info("C-CAP: projection complete (iterations=%d, max_delta=%.3f)",
                result.iterations, result.max_delta)
else:
    logger.debug("C-CAP: skipped (ccap_enabled=%s, has_constraints=%s)",
                 config.initialization.ccap_enabled, constraints is not None)
```

The critical distinction: the "executing" log line proves reachability. If the log never appears but the guard flags are `True`, the guard is the wrong test — it's either misplaced (indentation) or its preconditions are vacuously true (empty sets).

**3. Log the delta of any transformation that claims to modify state**

After a transformation, log the magnitude of change. A delta of `0.0` after a claimed projection, optimization step, or metric computation is a smoking gun.

```python
prev = jnp.copy(positions)
result = project_to_feasible(positions, constraints, netlist)
delta = jnp.max(jnp.abs(result.positions - prev))
logger.info("C-CAP position delta: max=%.3f mm", delta)

# Assert in test; log in production
if delta == 0.0:
    logger.warning("C-CAP produced zero delta — possible no-op or empty input")
```

### Prevention

**1. Structure guards at the correct nesting level**

The C-CAP guard was at 8-space indent inside `else:`. The fix moved it to 4-space indent at the function's top level. The principle: a guard should sit at the same nesting depth as the data it operates on. If the guard is inside a branch, ask whether the branch condition is always `True` in practice — if so, the guard is de facto unreachable.

```python
# BEFORE: guard inside else: branch — unreachable when initial_state is provided
if initial_state is not None:               # line 315, indent=4
    positions = initial_state.positions
else:                                        # line 320, indent=4
    positions = jnp.zeros(...)
    rotation_logits = jnp.zeros(...)

    if config.initialization.ccap_enabled:   # line 405, indent=8 — INSIDE else:
        positions = project_to_feasible(...)  # never reached in normal operation

# AFTER: guard at top level, independent of initialization path
if initial_state is not None:
    positions = initial_state.positions
else:
    positions = jnp.zeros(...)
    rotation_logits = jnp.zeros(...)

# C-CAP runs regardless of how positions were initialized
if config.initialization.ccap_enabled and constraints is not None:  # indent=4
    positions = project_to_feasible(...)
```

**2. Test infrastructure in integration, not just in isolation**

All three instances had passing unit tests for the infrastructure itself. The C-CAP projector had 93 tests. Each physics metric had dedicated test coverage. The baseline extractor had its own test file. What was missing in every case was a test that verified the *caller* actually invokes the infrastructure.

```python
def test_ccap_runs_during_multiphase_training():
    """Integration: verify train_multiphase calls project_to_feasible."""
    config = default_config.with_overrides(initialization=dict(ccap_enabled=True))
    constraints = PlacementConstraints(...)
    initial_state = create_initial_state(...)  # NOT None

    with patch("temper_placer.ops.ccap.project_to_feasible") as mock_project:
        mock_project.return_value = initial_state
        train_multiphase(config, initial_state, constraints, ...)
        mock_project.assert_called_once()  # Would have failed before fix
```

**3. Assert A/B divergence in integration tests**

A single test that runs the pipeline with the feature ON vs OFF and asserts a measurable difference catches all three failure modes regardless of mechanism.

```python
def test_ccap_produces_different_output():
    """C-CAP ON vs OFF must produce different placements."""
    config_off = config.with_overrides(initialization=dict(ccap_enabled=False))
    config_on = config.with_overrides(initialization=dict(ccap_enabled=True))

    result_off = train_multiphase(config_off, initial_state, constraints, ...)
    result_on = train_multiphase(config_on, initial_state, constraints, ...)

    delta = jnp.max(jnp.abs(result_on.positions - result_off.positions))
    assert delta > 1e-3, (
        f"C-CAP ON/OFF produced identical positions (delta={delta:.6f}) — "
        f"either no-op or never called"
    )
```

**4. Assert metric dynamic range in CI gates**

For measurement infrastructure: every CI gate that compares a metric against a baseline should first assert the metric has meaningful range. A smoke test like `assert hpwl_final > 0` on every board with ≥2 components would have caught the baseline extractor bug immediately.

```python
def test_corpus_baselines_have_real_values(baseline_path):
    baseline = json.loads(baseline_path.read_text())
    n_components = baseline["n_components"]
    if n_components >= 2:
        assert baseline["hpwl_final"]["mean"] > 0, (
            f"hpwl_final is 0.0 on board with {n_components} components — "
            f"baseline extraction is broken"
        )
```

### Audit checklist

When an existing guard condition raises suspicion:

1. **grep the guard's log messages in CI output.** If the "executing" line never appears but the "enabled" flag is `True` in config, the guard is unreachable.
2. **print-debug immediately after the guard.** A `print("REACHED C-CAP")` inside the block is crude but definitive.
3. **Check the guard's nesting depth relative to the call site.** If the guard is inside a conditional whose branch is always taken in practice (e.g., `if initial_state is not None:` when the oracle always passes it), the block is dead.
4. **Bisect input cardinality.** For set-based guards (`if hv_components and lv_components:`), print `len(hv_components)` and `len(lv_components)`. Empty sets mean the wiring between data source and consumer is broken.

## Why This Matters

- **False null results waste experiment cycles.** The C-CAP incident consumed a 20-run multi-seed experiment, analysis time, and a conclusion ("C-CAP has zero effect") that was exactly backward.
- **Silent failures corrode trust in infrastructure.** Once a team concludes a feature "doesn't work" because it was never actually called, the feature is abandoned — the infrastructure is dead code, even though the operator itself is correct.
- **Byte-identical A/B results are always a finding.** Any feature toggle that produces identical output in both positions is either a no-op or never reached. There is no third interpretation. Treating this as an investigation trigger rather than a result would have caught all three instances.
- **Isolation tests prove correctness; integration tests prove activation.** A module that passes 93 unit tests but never executes in the pipeline is dead. Both kinds of test are necessary — unit tests for the operator, integration tests for the caller.

## When to Apply

- Adding a feature toggle (config flag, CLI flag) where ON/OFF should produce different output
- Reviewing any guard condition whose block contains a significant computation (optimization step, projection, score computation)
- Debugging why a config flag "doesn't seem to do anything"
- Adding any `try: ... except Exception: pass` in a measurement or gate code path — ban it outright; every computation that feeds a CI comparison must fail loudly
- When A/B comparison across 2+ seeds produces byte-identical results for a feature that claims to modify state
- When a metric value is suspiciously constant (always `1.0`, always `0.0`, always identical to another field that shouldn't alias it)

## Examples

### C-CAP indentation: before/after (instance 3)

```python
# BEFORE: guard at indent=8, inside else: — unreachable
if initial_state is not None:                     # indent=4
    positions = initial_state.positions           # indent=8
    rotation_logits = initial_state.rotation_logits
else:                                              # indent=4
    positions = jnp.zeros((n, 2))                 # indent=8
    rotation_logits = jnp.zeros((n, 4))

    if config.initialization.ccap_enabled and constraints is not None:  # indent=8
        result = project_to_feasible(              # indent=12
            positions=positions,
            constraints=constraints,
            netlist=netlist,
            board=board,
        )
        positions = result.positions

# AFTER: guard at indent=4, top level — reached on all paths
if initial_state is not None:
    positions = initial_state.positions
    rotation_logits = initial_state.rotation_logits
else:
    positions = jnp.zeros((n, 2))
    rotation_logits = jnp.zeros((n, 4))

if config.initialization.ccap_enabled and constraints is not None:  # indent=4
    result = project_to_feasible(
        positions=positions,
        constraints=constraints,
        netlist=netlist,
        board=board,
    )
    positions = result.positions
```

### A/B integration test template

```python
@pytest.mark.parametrize("seed", range(5))
def test_feature_toggle_produces_divergence(feature_name, config, initial_state, seed):
    """Any feature toggle must produce measurably different output."""
    key = jax.random.PRNGKey(seed)
    config_off = dataclasses.replace(config, **{feature_name: False})
    config_on = dataclasses.replace(config, **{feature_name: True})

    result_off = train_multiphase(config_off, initial_state, key=key, ...)
    key = jax.random.PRNGKey(seed + 1)
    result_on = train_multiphase(config_on, initial_state, key=key, ...)

    delta = float(jnp.max(jnp.abs(result_on.final_state.positions -
                                  result_off.final_state.positions)))
    assert delta > 1e-4, (
        f"{feature_name} ON vs OFF produced identical positions across 2 seeds. "
        f"The feature is either a no-op or unreachable."
    )
```

### Instrumentation pattern for any guarded block

```python
def guarded_operation(config, state, context):
    logger.debug("guarded_operation: evaluating guard "
                 "(feature=%s, precondition=%s, n_inputs=%d)",
                 config.feature_enabled,
                 state.requires_precondition,
                 len(state.components))

    if config.feature_enabled and state.requires_precondition:
        prev = _snapshot(state)
        state = _apply_operation(state, context)
        delta = _delta_magnitude(prev, state)

        logger.info("guarded_operation: executed (delta=%.3f, units=%d)",
                    delta, len(state.components))

        if delta == 0.0:
            logger.warning("guarded_operation: executed but produced zero delta "
                           "(possible no-op or empty input)")
    else:
        logger.debug("guarded_operation: skipped "
                     "(feature=%s, precondition=%s)",
                     config.feature_enabled,
                     state.requires_precondition)
```

## Related

- `docs/solutions/logic-errors/silent-guard-condition-c-cap-indentation-2026-07-02.md` — instance 3: the C-CAP indentation bug producing a false null result across 20 runs
- `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md` — instance 1: the chain-of-proof pattern for wiring physics metrics (empty-set guards return `1.0`)
- `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — instance 2: five silent failures in baseline extraction including swallowed `ImportError`
- `docs/solutions/architecture-patterns/quality-metrics-built-but-never-connected-2026-07-01.md` — sibling pattern: infrastructure built and tested but never called (no guard condition, just absent call site)
- `docs/solutions/workflow-issues/infrastructure-components-unwired-2026-06-28.md` — audit methodology for finding unwired infrastructure
- `docs/solutions/workflow-issues/dead-code-from-features-with-no-activation-surface-2026-07-01.md` — superset pattern: config flags with `False` defaults and no reachable activation path
