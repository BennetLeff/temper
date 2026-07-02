---
module: temper-placer
date: 2026-07-02
problem_type: best_practices
component: tooling
severity: medium
tags:
  - physics-oracle
  - tuning
  - target-calibration
  - human-reference
  - thermal-metric
---

# Calibrate Physics Targets Against Human Reference Before Optimizing

## Context

During tuning of the three physics loss weights (clearance, thermal, loop area), the thermal target was set to `thermal_score ≥ 0.7` — meaning Q1 and Q2 must be within 9mm of the BOTTOM edge (max_distance=30mm, score = 1 - d/30, so 0.7 → d=9mm). Four weight sweeps with thermal weight up to 3000 at 10K epochs failed to exceed 0.41.

The root cause was not insufficient weight or epochs — it was that the target itself was unrealistic. Running the human-designed reference placement through the same metric revealed `thermal_score = 0.5` (Q1/Q2 at y=15mm, 15mm from BOTTOM). The human designer — who knew the mechanical constraints — placed the IGBTs 15mm from the bottom edge, not 9mm. Asking the optimizer to beat the human on thermal while also satisfying clearance and loop area was asking it to solve a hard multi-objective problem that even the domain expert didn't achieve.

The optimizer WAS responding — it moved Q1/Q2 122mm downhill (from y=140 to y≈24) — but stalled before reaching the human baseline because the clearance and loop area losses fought back.

## Guidance

Before setting target scores for any physics metric, compute the metric on the human reference placement first. The human placement is not perfect, but it is a calibrated floor: it represents what a domain expert achieved given the same board, components, and constraints.

```python
# Always run this before setting targets:
from temper_placer.metrics.quality import compute_quality_report
# ... run on human placement (temper.kicad_pcb) ...

human_clearance = report["hv_lv_clearance_score"]   # 0.91 on temper
human_thermal   = report["thermal_score"]            # 0.50 on temper (BOTTOM edge)
human_loop      = report["loop_area_score"]          # 0.00 on temper (not a design goal)

# Targets should beat human, not beat physics:
target_clearance = max(0.85, human_clearance)  # match or exceed human
target_thermal   = max(0.45, human_thermal)    # match or exceed human
target_loop      = 0.85                         # human didn't optimize loops at all
```

Rule of thumb: if the human placement already satisfies a constraint (score ≥ 0.8), the optimizer only needs to maintain it. If the human placement fails a constraint (score < 0.5), the optimizer needs to improve it — but set the target to match human first, then push incrementally.

## Why This Matters

Setting arbitrary targets ("let's target 0.7") wastes tuning iterations chasing a number that may be physically impossible given component sizes, board dimensions, and competing constraints. The optimizer can't put Q1 and Q2 at y=0mm if their own half-width is 7mm (they'd overlap the board edge). With max_distance=30mm and component half-height≈2mm, the minimum achievable distance is ~2mm → best possible thermal_score = 1 - 2/30 = 0.93. But with clearance pushing them apart, the practical floor is closer to 0.5-0.6.

Calibrating against human placement also gives you a sanity check: if the human score is 0.5 and the optimizer can't exceed 0.41 after 10K epochs with weight 3000, either the metric is broken or the loss term isn't wired correctly. In this case, the metric was correct (KiCad DRC confirmed the clearance violations too), and the optimizer WAS moving components — it just couldn't overcome the competing constraints.

## When to Apply

- Before running the first weight sweep on any new physics metric
- When a tuning run stalls and you can't tell if the weight is wrong or the target is impossible
- After adding a new loss term that competes with existing ones
- Whenever you find yourself typing an arbitrary target number (0.7, 0.8, 0.9) without first checking what the human placement achieves

## Examples

### Wrong: arbitrary target
```python
# "0.7 seems reasonable" — 70% of max score
target_thermal = 0.7
# Four sweeps later, thermal stuck at 0.41. Is the weight too low?
# Is the metric broken? Did the optimizer converge?
```

### Right: human-calibrated target
```python
# First: measure what the human achieved
human_thermal = 0.5  # on temper, BOTTOM edge, max_distance=30mm

# Then: set target at or above human
target_thermal = max(0.5, human_thermal)  # 0.5 — match human
# If optimizer hits 0.41, it's close but not there.
# Push thermal weight OR accept that competing constraints set a lower floor.
```

### Temper board actuals:
| Metric | Human score | Arbitrary target | Calibrated target | Optimizer achieved |
|--------|------------|------------------|-------------------|-------------------|
| Clearance | 0.91 | 0.80 | 0.85 | 0.88 ✓ |
| Thermal | 0.50 | 0.70 | 0.40 | 0.41 ~ |
| Loop area | 0.00 | 0.90 | 0.85 | 0.99 ✓ |
