---
title: Netclass calibration only takes effect where the routing engine actually consumes it — verify the full clearance path before predicting impact
date: "2026-07-12"
category: conventions
module: temper_placer
problem_type: convention
component: development_workflow
severity: medium
applies_when:
  - >-
    changing a netclass clearance rule (e.g., FinePitch 0.1mm) and predicting
    its DRC impact
  - >-
    a netclass SSOT exists (netclass_rules.yaml) but the router uses a single
    default_clearance_mm value
  - >-
    predicting that a config change will clear a large DRC violation bucket
tags:
  - netclass
  - routing
  - clearance
  - drc
  - prediction-calibration
  - architecture-limits
---

# Netclass calibration only takes effect where the routing engine actually consumes it

## Context

R4 (FinePitch netclass calibration) was predicted to clear the largest DRC
bucket on the temper board — the 73% "marginal" clearance band at 0.1–0.2mm,
median 0.107mm. Assigning SPI/USB/PWM/sensor nets to FinePitch (0.1mm
clearance) was expected to resolve most of these as a zero-cost config change.

The measurement: **403 → 381 (−22).** Not the largest bucket — a 5% reduction.
The 0.107mm median gap sits below the 0.15mm Signal-class clearance that was
actually achievable, so only the [0.15, 0.2) band cleared.

## Why the prediction was wrong

The A* routing kernel uses a **single `default_clearance_mm` value** for all
nets (`astar_pathfinding.py:451`). It does NOT call the per-net
`design_rules.get_rules_for_net(net_name)` that exists in `stage0_data.py:103`.
So no matter what netclass assignments exist in the config or design_rules,
every net routes at the same clearance.

The `default_clearance_mm` was correctly set to 0.15mm — the Signal netclass
SSOT value from `netclass_rules.yaml`, which is the correct inter-net Signal
clearance. Setting it to 0.1mm would incorrectly lower clearance for non-FinePitch
nets (Power 0.25mm, GateDrive 0.25mm, GND 0.3mm, ACMains 6.0mm safety-critical).

The FinePitch 0.1mm intra-class clearance **cannot be applied** without per-net
routing clearance — which requires threading `get_rules_for_net()` through
the A* mark/unmark blocking path. That is an architecture change, not a config
change.

## Guidance

**Before predicting a netclass clearance change's impact, trace the full
consumption path from config to routing engine:**

1. The `netclass_rules.yaml` SSOT defines per-class clearances.
2. `net_assignments` in the cooker config maps nets to classes.
3. `load_constraints` must parse these into `constraints.net_classes`.
4. The pipeline must inject them into `pcb.design_rules.net_class_assignments`.
5. **The routing engine must call `get_rules_for_net(net_name).clearance_mm`
   instead of using a single `default_clearance_mm`.**

If step 5 is missing (as it was on temper), only a single global clearance
value can be changed. That value must be the most-restrictive-permissive
clearance across all nets using it — in this case, the Signal-class SSOT of
0.15mm, which is the min of {Signal=0.15, Power=0.25, GateDrive=0.25, GND=0.3}.

## Why This Matters

A netclass SSOT that isn't consumed by the routing engine creates a false
sense of constraint fidelity. The config says "FinePitch nets get 0.1mm" but
the router ignores it, so the prediction inflates the expected DRC improvement.
The measurement corrects it — but the correction comes after the prediction,
not before. Awareness of the architecture gap allows accurate impact forecasting
before committing to the change.

## When to Apply

- Before claiming a netclass clearance change will clear a DRC violation
  bucket by a predicted amount
- When the netclass SSOT exists but DRC results don't match the expected
  clearance values
- When the router's clearance model (single default vs. per-net) hasn't been
  verified against the netclass architecture

## Examples

The per-net routing clearance gap in A*:

```python
# CURRENT: single default for all nets (astar_pathfinding.py:451)
clearance=design_rules.default_clearance_mm,

# NEEDED: per-net clearance from the SSOT
rules = design_rules.get_rules_for_net(net_name)
clearance = rules.clearance_mm  # FinePitch=0.1, Power=0.25, etc.
```

The netclass plumbing already exists in `stage0_data.py:103`:

```python
def get_rules_for_net(self, net_name: str) -> NetClassRules:
    class_name = self.net_class_assignments.get(net_name, None)
    if class_name and class_name in self.net_classes:
        return self.net_classes[class_name]
    return NetClassRules(
        clearance_mm=self.default_clearance_mm,
        ...
    )
```

The gap is in the A* kernel — `get_rules_for_net` is never called during
pathfinding, only the `default_clearance_mm` is used. This is the
architecture change needed to make R4 achieve its full predicted impact.

## Related

- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md` —
  the generalizable discipline this instance exemplifies
- `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md` —
  the seam bugs that made every placement metric a lie
- `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py:103` —
  `get_rules_for_net` (exists, not consumed during routing)
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py:451` —
  `default_clearance_mm` usage site (the single-default bottleneck)
