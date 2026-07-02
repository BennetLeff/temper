---
title: Feature merged with config flags but no activation surface
date: 2026-07-01
category: workflow-issues
module: feature-activation
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - A feature is gated behind a config flag with a False default
  - No CLI flag, YAML config, or pipeline integration sets the flag to True
  - The feature is tested in isolation but never through an application entry point
symptoms:
  - Feature code exists on main and passes tests but is never exercised in practice
  - Config flag defaults to False with no mechanism to change it
  - Tests only exercise the feature through direct Python imports, not through CLI or pipeline
  - CI passes because import-chain tests succeed, but the feature has no integration test through the activation surface
root_cause: missing_workflow_step
resolution_type: workflow_improvement
tags:
  - dead-code
  - config-flags
  - feature-activation
  - cli
  - pipeline-integration
related_components:
  - cli
  - pipeline
  - ci
  - testing
---

# Feature Merged With Config Flags But No Activation Surface

## Context

After merging 6 placement initialization features (#108-#113), an audit of the default execution path revealed that 5 of 6 features were dead code — they existed on main, passed tests, but were never activated by any default configuration:

| Feature | Config flag | Default | CLI flag? | Pipeline? | Auto-activate? |
|---------|-------------|---------|-----------|-----------|----------------|
| Constraint-Weighted Laplacian | `method="constraint_weighted_spectral"` | `"random"` | No | No | No |
| C-CAP | `ccap_enabled=True` | `False` | No | No | No |
| Group Pre-Clustering | `group_preclustering=True` | `False` | No | Dead orchestrator only | No |
| Thermal Anchoring | `thermal_anchoring_enabled=True` | `False` | No | Stage existed but DAG entry lost in merge | No |
| DPP Multi-Seed | `multi_seed.enabled` | `False` | `--multi-seed` | No | Manual only |

Only DPP Multi-Seed had a CLI activation path. The other 4 features were config flags that nothing ever set to True.

This pattern is a superset of the previously documented "infrastructure components unwired" problem (`docs/solutions/workflow-issues/infrastructure-components-unwired-2026-06-28.md`) — those components were wired in code but never connected to the pipeline. These features weren't even wired to any config surface.

## Guidance

### For every config-gated feature, the same PR MUST include at least one activation surface:

1. **CLI flag** — `--feature-name` or `--init-method <choice>`. This is the user-facing surface.
2. **Sensible default** — if the feature provides value with no downside, default to True. Auto-degrade when prerequisites aren't met (e.g., no constraints loaded → fallback to plain spectral).
3. **Pipeline/DAG integration** — if the feature is a pipeline stage, register it in the DAG manifest with appropriate `requires`/`provides`.
4. **Auto-activation on data presence** — when the feature depends on constraint data being present (groups, thermal properties, zones), auto-enable when that data is available.

### Reachability check before merging

```bash
# Verify the feature's activation path is reachable from at least one entry point
rg "feature_flag|feature_name" packages/temper-placer/src/temper_placer/cli/ \
  packages/temper-placer/configs/ \
  packages/temper-placer/src/temper_placer/pipeline/
```

If no match is found, the feature is unreachable from any entry point and is dead code.

### Integration test through the activation surface

A feature is not "working" unless tested through its activation surface — not just through direct import:

```python
# Wrong: tests the module, not whether it's reachable
from temper_placer.new_feature import do_thing
def test_feature(): assert do_thing()

# Right: tests through the CLI or pipeline entry point
def test_feature_via_cli():
    result = subprocess.run(["temper-placer", "optimize", "--new-feature", ...])
    assert result.returncode == 0
```

## Why This Matters

Code that exists on main but is never exercised is dead code — it carries maintenance burden without delivering value. Worse, it creates false confidence that a feature is available. When someone eventually tries to use it and it fails (because it was never tested end-to-end), the failure happens in production rather than in CI.

The specific risk for config-gated features:
1. **Refactors break unreachable code silently** — someone changes a shared interface, CI passes because the feature isn't tested through an activation path, and the feature silently breaks.
2. **Merge conflicts drop feature code** without detection — if no integration test imports the feature through its activation path, CI won't notice.
3. **Onboarding confusion** — new team members see the config flag, assume the feature works, and waste time debugging when it doesn't.

## When to Apply

- **Before merging any PR** that introduces a new config flag with a False default.
- **During code review** — verify the PR includes an activation surface and an integration test through it.
- **During post-merge audit** — run the reachability check against all config flags in `config.py` to find dead features.

## Examples

### Before (dead code — PR #109 merged without activation)

```python
@dataclass
class InitializationConfig:
    method: str = "random"  # "constraint_weighted_spectral" exists but unreachable
    ccap_enabled: bool = False  # No CLI flag, no pipeline wiring
    group_preclustering: bool = False  # Dead orchestrator only
```

### After (live code — post-audit fix)

```python
@dataclass
class InitializationConfig:
    method: str = "constraint_weighted_spectral"  # Sensible default
    ccap_enabled: bool = True  # Auto-degrades when no constraints
    group_preclustering: bool = True  # Auto-degrades when no groups
```

```python
# CLI flags added for user control
@click.option("--init-method", type=click.Choice([...]), default=None)
@click.option("--ccap/--no-ccap", default=None)
@click.option("--precluster/--no-precluster", default=None)
```

```python
# Auto-degrade pattern prevents errors when data isn't present
if config.initialization.method == "constraint_weighted_spectral":
    if constraints is None:
        logger.info("No constraints loaded, falling back to spectral")
        # fall back gracefully
```

## Related

- `docs/solutions/workflow-issues/infrastructure-components-unwired-2026-06-28.md` — same pattern: code tested in isolation but never connected to execution path
- `docs/solutions/workflow-issues/integration-hunting-audit-before-build-2026-06-28.md` — audit pattern for finding built-but-never-called code
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md` — companion doc: merge loss discovered during the same audit
- `docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md` — safe removal of dead code once identified
