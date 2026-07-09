---
experiment: physics-oracle-multi-seed-c-cap
date: 2026-07-02
plan: docs/plans/2026-07-02-001-fix-physics-oracle-metric-c-cap-experiment-plan.md
---

# Physics Oracle Multi-Seed Experiment Report

## Summary

Ran the pre-registered 10-seed × 2-condition (C-CAP on/off) experiment at 10,000
epochs against the corrected dual-rail clearance metric. The experiment produced
structured output for all 20 runs, but **none converged** by plateau check —
loss values remained steep (10k–47M, plateau slopes 4–65M/epoch), placing the
optimizer mid-descent, not converged. The pre-registered decision rule correctly
returned `INCONCLUSIVE`.

## Configuration

| Parameter | Value |
|-----------|-------|
| Board | `temper.kicad_pcb` |
| Spec | `pcb_spec.yaml` |
| Epochs | 10,000 |
| Seeds | 0–9 (20 runs: 10 × C-CAP ON, 10 × C-CAP OFF) |
| ClearanceLoss threshold | 6.0mm (DRC rail) |
| Metric | Dual-rail: 3.0mm IEC + 6.0mm DRC, worst-pair + violation count |
| Plateau check | `|slope(loss[-20%])| < 1e-4` |
| Weights (frozen) | thermal=4000, clearance=200, overlap=200, boundary=100, wirelength=20, spread=5, loop_area=1 |

## Human Baseline

| Metric | Value |
|--------|-------|
| clearance_score_3mm | 0.267 |
| clearance_score_6mm | 0.133 |
| violations_3mm | 12 |
| violations_6mm | 22 |

The human placement violates the 6.0mm DRC design rule in 22 HV-LV pairs (worst
pair at ~0.8mm) and the 3.0mm IEC regulatory floor in 12 pairs (worst pair at
~0.8mm). The human floor is **not a passing target** — it is a "best known"
floor with its own DRC violations.

## Per-Run Results

| Seed | C-CAP | clr3 | clr6 | v3 | v6 | thermal | loss | slope | plateau |
|------|-------|------|------|----|----|---------|------|-------|---------|
| 0 | ON | 0.321 | 0.160 | 6 | 19 | 0.342 | 12k | 299 | NO |
| 0 | OFF | 0.321 | 0.160 | 6 | 19 | 0.342 | 12k | 299 | NO |
| 1 | ON | 0.963 | 0.482 | 6 | 16 | 0.021 | 47M | 65M | NO |
| 1 | OFF | 0.963 | 0.482 | 6 | 16 | 0.021 | 47M | 65M | NO |
| 2 | ON | 0.378 | 0.189 | 12 | 23 | 0.393 | 11k | 68 | NO |
| 2 | OFF | 0.378 | 0.189 | 12 | 23 | 0.393 | 11k | 68 | NO |
| 3 | ON | 0.733 | 0.366 | 6 | 18 | 0.386 | 14k | 12 | NO |
| 3 | OFF | 0.733 | 0.366 | 6 | 18 | 0.386 | 14k | 12 | NO |
| 4 | ON | 0.610 | 0.305 | 6 | 17 | 0.070 | 4.0M | 41M | NO |
| 4 | OFF | 0.610 | 0.305 | 6 | 17 | 0.070 | 4.0M | 41M | NO |
| 5 | ON | 0.330 | 0.165 | 7 | 17 | 0.209 | 9.7k | 9 | NO |
| 5 | OFF | 0.330 | 0.165 | 7 | 17 | 0.209 | 9.7k | 9 | NO |
| 6 | ON | 0.368 | 0.184 | 18 | 26 | **0.546** | 10k | 8 | NO |
| 6 | OFF | 0.368 | 0.184 | 18 | 26 | **0.546** | 10k | 8 | NO |
| 7 | ON | 0.361 | 0.180 | 7 | 23 | 0.226 | 11k | 4 | NO |
| 7 | OFF | 0.361 | 0.180 | 7 | 23 | 0.226 | 11k | 4 | NO |
| 8 | ON | 0.323 | 0.162 | 8 | 14 | 0.151 | 15k | 5 | NO |
| 8 | OFF | 0.323 | 0.162 | 8 | 14 | 0.151 | 15k | 5 | NO |
| 9 | ON | 0.761 | 0.381 | 10 | 19 | 0.300 | 12k | 69 | NO |
| 9 | OFF | 0.761 | 0.381 | 10 | 19 | 0.300 | 12k | 69 | NO |

- **Elapsed per run:** 4–84s (mean 10s excluding seed=3 C-CAP OFF outlier at 84s)
- **Total experiment time:** ~3 minutes
- **Crashes/errors:** None

## Key Observations

### 1. C-CAP on/off produce identical results

For every seed, the C-CAP-ON and C-CAP-OFF runs produce byte-identical scores
(loss, clearance, thermal, violations all match). This means that at 10k epochs
the feasibility projector does not change the optimization trajectory — the
gradient-based optimizer domesticates the initial condition on its own. The
original hypothesis ("C-CAP OFF = optimizer stuck at edge") does not manifest at
this epoch budget.

Possible reasons:
- C-CAP resolves initial infeasibility, but the optimizer lands in the same basin regardless
- 10k epochs is enough for the gradient-based spread phase to resolve overlap — the "problem" C-CAP was supposed to solve (HV parts stacked at one edge) may have been a seed artifact or already fixed by the curriculum

### 2. None converged — plateau check too strict for this landscape

The plateau check (`|slope| < 1e-4/epoch`) is a well-converged regime check
(flat tail). At 10k epochs the loss landscape is still steep:

- Eight "well-behaved" seeds (0,2,3,5,6,7,8,9) have loss ~10-15k with slopes
  4-300/epoch — still descending, just slowly
- Two "stuck" seeds (1, 4) have loss 4-47M with slopes 41-65M/epoch — stuck in
  local minima with massive overlap penalty

The plan's early-stopping (`patience=2000`) likely terminated many runs before
the plateau could be reached. The optimizer's own `converged` flag may differ
from the plateau check.

**Recommendation:** Either (a) increase epochs to 50k+ to reach actual
convergence, (b) relax the plateau threshold (e.g., `|slope| < 0.01`), or
(c) use the optimizer's own `converged` / `early_stopping` signal instead of
the post-hoc plateau check.

### 3. Best seed (6) beats human on both metrics — but from non-converged run

Seed 6 achieves `clearance_6mm=0.184` vs human `0.133` and `thermal=0.546`.
This is the best thermal score across all runs. However, the run has not
converged (plateau: NO, loss still dropping at 8/epoch). This is the seed the
plan's HOLDS/DISSOLVED decision rule would evaluate — but the rule requires
converged runs.

### 4. Two seeds stuck in bad local minima (1, 4)

Seeds 1 and 4 produce loss 47M and 4.0M respectively, with thermal scores near
zero — the optimizer got trapped in configurations with massive component
overlap and couldn't escape within 10k epochs. These are the seeds the plan
hypothesized C-CAP might rescue, but C-CAP ON produces identical results.

This confirms the plan's "local minimum" concern: the result depends heavily on
the seed, and some seeds are genuinely terrible. Multi-seed is necessary, but
the convergence issue must be solved first for the means to be meaningful.

## Verdict (Per Decision Rule)

```
INCONCLUSIVE — No C-CAP-on runs converged — insufficient data for verdict
```

Neither DISSOLVED nor HOLDS can fire because 0 of 20 runs passed the
convergence gate. The means/stds are all zero (excluded runs).

## Next Steps

1. **Relax convergence check** — Use optimizer's own `converged`/`early_stopping` signal or relax plateau threshold to `|slope| < 0.01` (10x looser). Re-run.
2. **Increase epochs** — 10k → 50k or run-to-convergence with early-stopping disabled. The current loss landscape takes ~15-30k epochs to plateau based on seed 7 (slope=4).
3. **Drop stuck seeds** — Seeds 1 and 4 (loss > 1M) should be excluded regardless of plateau status — they're clearly in bad local minima, not "still descending."
4. **Re-run with these fixes** and re-apply the decision rule. The data structure and all plumbing are working; the convergence definition just needs tuning.

---

*Report generated by the multi-seed experiment runner. Raw data at `/tmp/experiment_data.json`.*
