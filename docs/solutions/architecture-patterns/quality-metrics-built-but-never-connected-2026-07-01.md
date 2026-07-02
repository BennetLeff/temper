---
title: "Production-ready quality metrics modules were built but never connected to any comparison system"
date: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "Quality metrics report all 1.0 normalized scores unexpectedly"
  - "Comparing placement results against reference designs"
  - "Need thermal-HV-LV component classification for quality scoring"
  - "A metrics module exists and passes tests but has no caller in the pipeline"
tags:
  - quality-metrics
  - dead-infrastructure
  - wire-up
  - quality-config
  - temper-placer
---

# Production-ready quality metrics modules were built but never connected to any comparison system

## Context

The temper-placer codebase contained four fully-implemented, unit-tested modules for placement quality scoring that had zero consumers:

| Module | What it computes | Status |
|--------|-----------------|--------|
| `validation/metrics.py::compute_metrics()` | 15+ placement quality metrics (overlap count, clearance violations, zone violations, keepout violations, wirelength stats, utilization, spread score) | Production-ready, exported from `__init__.py` |
| `metrics/quality.py::compute_quality_report()` | 8 normalized [0,1] scores (thermal, zone compliance, HV-LV clearance, loop area, congestion, compactness, connectivity clustering) + overall | Production-ready, exported from `__init__.py` |
| `metrics/aesthetic.py::compute_aesthetic_score()` | Grid snap, orientation consistency, prefix alignment, aesthetic index | Experimental, not in public `__init__.py` |
| `io/reference_loader.py::infer_quality_config()` | Thermal/HV/LV component inference from footprint names and net names | Production-ready, only caller was itself |

The `reference_loader.py` even contained a function that called `compute_quality_report()` on both a reference PCB and an optimizer placement, then... did nothing with the result. The comparison infrastructure was built, the metrics were computed, and the values were discarded.

This is the same class of problem documented in `docs/solutions/workflow-issues/infrastructure-components-unwired-2026-06-28.md` (StageLedger tested in isolation, never called from pipeline) and `docs/solutions/workflow-issues/dead-code-from-features-with-no-activation-surface-2026-07-01.md` (config flags with False defaults, no CLI flag, no pipeline wiring).

## Guidance

**Audit for built-but-unwired metrics before adding new ones.** Check three things:

1. **Is the module importable?** — present in the package, exportable from `__init__.py`
2. **Is it called from the pipeline?** — grep for the function name in CI workflows, scripts, CLI entry points
3. **If not called, it's an integration gap** — the module is correct in isolation but produces false confidence (tests pass, zero consumers)

**When wiring in dead infrastructure, prefer existing config inference over rewriting.** The `infer_quality_config()` function was already inferring thermal/HV/LV components from footprint names (`TO-247` → thermal), reference designators (`Q`/`D` → HV), and net names (`GATE`/`DRV` → critical loops). Calling it instead of writing a new config builder saved reimplementing the same inference logic.

**Each new metric module should added to the human-reference comparison on merge.** The human-reference oracle (`human_reference_compare.py`) now serves as the canonical consumer for placement quality metrics. Adding a new metric module without adding its outputs to the comparison comment is the same class of gap.

## Why This Matters

- **False confidence from green tests**: all four modules passed their unit tests. Nobody noticed they had no callers because the tests proved the logic was correct — they didn't prove the logic was used.
- **One-line wire-up produces disproportionate signal**: adding three function calls to `human_reference_extractor.py` added 29 new metrics (from 6 to 35) per board. The marginal cost of wiring is near-zero; the marginal benefit is every future PR getting that signal.
- **Normalized quality scores without config return 1.0**: `compute_quality_report()` with empty config (no thermal components, no zone assignments, no loops) returns perfect scores. This is correct behavior (no constraints to violate = no violations) but misleading if you don't know that config is required. Always pair quality score computation with `infer_quality_config()` or explicit constraint loading.
- **The "already exists" test**: before building a new metric, grep for it. In this case, all four modules already existed — the work was wiring, not building.

## When to Apply

- Before adding any new placement quality metric
- When all normalized quality scores are 1.0 and you suspect empty config
- When a metrics module has unit tests but no grep hits in CI/workflow/script files
- When comparing optimizer output against human reference designs
- When the PR comment shows fewer metrics than the codebase can produce

## Examples

**Before (human reference with 6 metrics)**:
```python
# extract_human_reference only computed placement losses
all_metrics = {
    **placement_metrics,   # hpwl, overlap_loss, boundary_loss
    **routing_metrics,     # rdl, via_count
    **drc_metrics,         # drc_violations
}
```

**After (35 metrics from 6 sources)**:
```python
all_metrics = {
    **placement_metrics,      # 3 metrics from loss functions
    **routing_metrics,        # 2 metrics from trace/via extraction
    **detailed_metrics,       # 17 metrics from validation.metrics.compute_metrics()
    **aesthetic_metrics,      # 4 metrics from metrics.aesthetic.compute_aesthetic_score()
    **quality_metrics,        # 9 metrics from metrics.quality.compute_quality_report()
    **drc_metrics,            # 1 metric from DRC runner
}
```

The detailed and quality metrics use `infer_quality_config()` to build real config from the netlist:

```python
from temper_placer.io.reference_loader import infer_quality_config
from temper_placer.metrics.quality import compute_quality_report

config = infer_quality_config(parse_result)  # infers thermal/HV/LV from footprints
report = compute_quality_report(state, netlist, board, context, config)
# report now has real variation: overall_score 0.40-0.76 across boards
```

## Related

- `docs/solutions/workflow-issues/infrastructure-components-unwired-2026-06-28.md` — same pattern (StageLedger tested but never called)
- `docs/solutions/workflow-issues/dead-code-from-features-with-no-activation-surface-2026-07-01.md` — superset pattern with reachability checklist
- `docs/solutions/workflow-issues/integration-hunting-audit-before-build-2026-06-28.md` — audit methodology for finding unwired code
- `docs/solutions/architecture-patterns/ci-profiling-platform-canonical-metrics-contract-2026-06-28.md` — structural prevention via `--from-stdin` pattern
