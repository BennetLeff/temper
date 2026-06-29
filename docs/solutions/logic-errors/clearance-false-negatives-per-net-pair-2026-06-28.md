---
title: Clearance false negatives from per-net-pair reporting instead of per-layer
date: "2026-06-28"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "verify_clearance reported at most one clearance violation per net pair, even when multiple layers had violations"
  - "Violations on non-minimum layers were silently dropped — no error, warning, or trace"
  - "The completeness oracle (brute-force O(n^2) pair-check) detected violations the production engine missed"
root_cause: logic_error
resolution_type: code_fix
related_components:
  - testing_framework
tags:
  - clearance-check
  - false-negative
  - multilayer
  - pcb
  - router-v6
  - oracle-testing
  - completeness
---

# Clearance false negatives from per-net-pair reporting instead of per-layer

## Problem

`_calculate_minimum_clearance` aggregated clearance distances across all layers into a single global minimum per net pair and discarded the per-layer breakdown. If a net pair had violations on multiple layers (e.g., F.Cu at 0.04mm AND B.Cu at 0.06mm, both below the 0.127mm required clearance), only the closest layer's violation was reported. Every other layer's violation was a silent false-negative.

## Symptoms

- `verify_clearance` returned at most one `ClearanceViolation` per net pair regardless of how many layers actually had clearance breaches.
- Multi-layer boards with violations on multiple layers produced incomplete violation lists with no indication of data loss.
- The SC3b property test logged a `warnings.warn` but did not fail the build, allowing false-negatives to pass through CI undetected.

## What Didn't Work

The original design assumed "only the worst violation matters" — that reporting the single closest approach across all layers was sufficient. This holds for single-layer boards but fails catastrophically on multi-layer PCBs where the same net pair can violate clearance independently on each layer. The completeness oracle (`clearance_oracle.py` — an independent O(n²) brute-force pair-check with zero code-path overlap with `clearance_check.py`) was the first to surface the discrepancy. Without the oracle, the bug would have remained invisible.

## Solution

Replaced the single-return API with a per-layer dict:

```python
# Before — collapses all layers to global minimum
def _calculate_minimum_clearance(route1, route2) -> tuple[float, Point, str]:
    min_dist = float('inf')
    for s1 in segs1:
        for s2 in segs2:
            if s1[4] == s2[4]:  # same layer
                edge_dist = ...
                if edge_dist < min_dist:
                    min_dist = edge_dist
                    violation_layer = s1[4]
    return (min_dist, closest_point, violation_layer)

# After — preserves per-layer breakdown
def _calculate_minimum_clearance_by_layer(route1, route2) -> dict[str, tuple[float, Point]]:
    layer_info: dict[str, tuple[float, tuple[float, float]]] = {}
    def _update_layer(layer, edge_dist, point):
        if layer not in layer_info or edge_dist < layer_info[layer][0]:
            layer_info[layer] = (edge_dist, point)
    # ... populate layer_info for each same-layer segment pair ...
    return layer_info

# Backward-compatible wrapper preserved for existing callers
def _calculate_minimum_clearance(route1, route2):
    per_layer = _calculate_minimum_clearance_by_layer(route1, route2)
    if not per_layer:
        return (float('inf'), (0.0, 0.0), "unknown")
    best = min(per_layer, key=lambda k: per_layer[k][0])
    return (per_layer[best][0], per_layer[best][1], best)
```

The `verify_clearance` caller loop was updated to iterate per-layer results:

```python
per_layer = _calculate_minimum_clearance_by_layer(route1, route2)
for layer, (min_dist, location) in per_layer.items():
    required = _get_required_clearance(net1, net2, min_clearance, voltage_ratings, layer=layer)
    if min_dist < required:
        violations.append(ClearanceViolation(...))
```

The SC3b completeness test was upgraded from soft warning to hard assertion:

```python
# Before
warnings.warn(f"Oracle found {len(diff)} violations the engine missed")

# After
assert len(diff) == 0, f"false-negative: oracle found {len(diff)} violations production missed: {diff}"
```

## Why This Works

The root cause was an aggregation loss: the old function reduced a multidimensional result (layer × violation) into a single scalar (global minimum). By preserving the full per-layer dictionary, `verify_clearance` can iterate every layer and report every violating pair independently. The backward-compatible wrapper ensures callers that only need the global minimum (e.g., single-layer iterators) are unaffected. The upgraded test assertion ensures any future regression that reintroduces false-negatives immediately fails CI.

The defense-in-depth story: the existing property tests checked *correctness* (all reported violations are genuine — no false-positives). The completeness oracle checks *completeness* (all genuine violations are reported — no false-negatives). Both are needed.

## Prevention

1. **Oracle-driven completeness testing**: The brute-force O(n²) oracle must be an always-on CI gate for any change to the clearance engine. If the oracle disagrees with production output, the build fails.

2. **When a reduce/aggregate operation silently drops data, return the full structure and let callers reduce.** The fix embodies this: `_calculate_minimum_clearance_by_layer` returns the dict; `_calculate_minimum_clearance` is a thin convenience wrapper on top.

3. **Upgrade regression tests from `warnings.warn` to `assert` whenever a false-negative has been observed.** A warning that doesn't block CI is a recurrence waiting to happen.

4. **Extend the completeness oracle pattern to other validators.** The same "optimized engine vs. brute-force ground-truth" structure applies to creepage (`verify_creepage`), acid traps, and annular ring checks. The `drc_trace_clearance` and `drc_via_spacing` checks added in the pipeline contracts work already follow this pattern.

## Related

- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — same completeness-oracle methodology applied to SAT encoding validation. Both bugs share the meta-pattern: production code produces false negatives, an independent brute-force audit catches them, and the audit is promoted to an always-on CI gate.
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — per-stage DRC fence architecture; clearance validation context.
- `docs/plans/2026-06-28-002-feat-sat-drc-validator-validation-plan.md` — SAT+DRC validator validation plan that introduced the completeness oracle.
- `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py:124` — `_calculate_minimum_clearance_by_layer` implementation.
- `packages/temper-placer/src/temper_placer/router_v6/clearance_oracle.py` — brute-force O(n²) completeness oracle.
- `packages/temper-placer/tests/router_v6/test_clearance_properties.py:345` — SC3b completeness test (now with `assert`).
