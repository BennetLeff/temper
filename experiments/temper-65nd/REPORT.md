# temper-65nd Experiment Report: Wirelength Loss Alpha Annealing

**Date:** 2025-12-25  
**Experiment:** temper-65nd  
**Topic:** Evaluation of LogSumExp alpha annealing for wirelength loss optimization

## 1. Overview

This experiment evaluates whether annealing the LogSumExp alpha parameter from a low value (smooth approximation) to a high value (sharp approximation) during optimization improves final wirelength outcomes.

### Background

The `WirelengthLoss` function uses LogSumExp to approximate the max/min operations needed for HPWL computation. The alpha parameter controls the "sharpness" of this approximation:

- **Low alpha (1-5):** Smooth approximation with good gradient flow, but less accurate to true HPWL
- **High alpha (20+):** Sharp approximation close to true HPWL, but gradients can become small

**Hypothesis:** Annealing from low to high alpha provides the best of both worlds:
- Early training: Low alpha for smooth optimization landscape and broad exploration
- Late training: High alpha for precise wirelength minimization

## 2. Hypotheses

| Hypothesis | Statement |
|------------|-----------|
| **H0 (Null)** | No significant difference in final HPWL between conditions |
| **H1 (Primary)** | Annealed alpha produces significantly lower final HPWL than constant alpha |
| **H2 (Gradient)** | Annealed alpha maintains better gradient magnitudes in late epochs |

## 3. Methodology

### Test Fixture
- **Board:** `tests/fixtures/medium_board.kicad_pcb` (25 components, 18 nets)
- **Epochs:** 2000 per run
- **Sample Size:** 30 runs per condition (120 total)
- **Router:** Internal MazeRouter (A* pathfinding)

### Conditions

| Condition | Alpha Strategy | Purpose |
|-----------|----------------|---------|
| **Baseline** | Constant 10.0 | Current default behavior |
| **Annealed** | 1.0 → 20.0 (20% warmup) | Proposed new default |
| **Control High** | Constant 20.0 | Does sharpness alone help? |
| **Control Low** | Constant 1.0 | Does smoothness alone help? |

### Configuration

```yaml
# Baseline: constant alpha
wirelength:
  alpha: 10.0

# Annealed: dynamic alpha
wirelength:
  alpha_start: 1.0
  alpha_end: 20.0
  alpha_warmup: 0.2
```

### Metrics

| Metric | Description |
|--------|-------------|
| **Final HPWL** | Primary outcome - lower is better |
| **Routing Completion %** | Secondary - does better wirelength = better routing? |
| **Gradient Norms** | Track gradient magnitudes across training |
| **Convergence Curve** | HPWL trajectory over epochs |

## 4. Expected Results

| Condition | Expected HPWL | Rationale |
|-----------|---------------|-----------|
| Baseline | ~X units | Current behavior |
| Annealed | < X units | Smooth early + sharp late |
| Control High | ~X units | Sharp but poor gradients early |
| Control Low | > X units | Smooth but imprecise final |

## 5. Analysis Plan

### Statistical Tests

1. **Primary:** One-way ANOVA across all 4 conditions (HPWL)
2. **Pairwise:** t-test: Annealed vs Baseline (primary comparison)
3. **Effect Size:** Cohen's d for Annealed vs Baseline
4. **Gradient Analysis:** Compare gradient norms at epochs 1800-2000

### Success Criteria

- [ ] Annealed produces ≥5% lower HPWL than Baseline (p < 0.05)
- [ ] Annealed HPWL variance is ≤ Baseline variance
- [ ] Gradient norms remain non-vanishing in late epochs

## 6. Running the Experiment

```bash
# Install temper-placer
cd packages/temper-placer
pip install -e ".[dev]"

# Run experiment (example - implement run script)
python scripts/run_experiment.py \
    --config-base ../experiments/temper-65nd/config_baseline.yaml \
    --config-annealed ../experiments/temper-65nd/config_annealed.yaml \
    --config-control-high ../experiments/temper-65nd/config_control_high.yaml \
    --config-control-low ../experiments/temper-65nd/config_control_low.yaml \
    --runs 30 \
    --epochs 2000 \
    --output ../experiments/temper-65nd/results.csv
```

## 7. Recommendations (to be filled after experiment)

### If Annealed is Better:
- Update default WirelengthLoss to use annealing
- Consider making annealing the default behavior
- Document the recommended alpha_start/alpha_end/warmup values

### If No Difference:
- Consider abandoning alpha annealing
- Investigate other wirelength improvements (e.g., better layer awareness)

### If Annealed is Worse:
- Revert to constant alpha
- Try different annealing schedules (exponential, cosine, etc.)

## 8. References

- Original issue: temper-65nd
- Implementation: temper-65nd.1
- Test file: `tests/losses/test_weighted_wirelength.py`
