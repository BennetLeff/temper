# Wirelength Alpha Annealing Validation Experiment

**Objective:** Run experiment to validate that alpha annealing improves final wirelength outcomes.

## Background

Alpha annealing was implemented in temper-65nd.1. The LogSumExp smoothing parameter now anneals from 1.0 (smooth, good gradients) to 20.0 (sharp, close to true HPWL) during optimization.

## Hypothesis

**H0 (Null):** No significant difference in final HPWL between constant and annealed alpha  
**H1 (Alternative):** Annealed alpha produces significantly lower final HPWL (≥5% improvement)

## Experiment Setup

### Conditions (4 total, 30 runs each = 120 runs)

| Condition | Alpha Strategy | Config File |
|-----------|----------------|-------------|
| Baseline | Constant 10.0 | `config_baseline.yaml` |
| Annealed | 1.0→20.0, 20% warmup | `config_annealed.yaml` |
| Control High | Constant 20.0 | `config_control_high.yaml` |
| Control Low | Constant 1.0 | `config_control_low.yaml` |

### Parameters
- **Board:** `tests/fixtures/medium_board.kicad_pcb` (25 components, 18 nets)
- **Epochs:** 2000 per run
- **Sample Size:** 30 runs per condition
- **Random Seeds:** Use distinct seeds for each run (e.g., 0-29)

## Running the Experiment

```bash
cd packages/temper-placer

# Activate virtual environment
source ../../.venv/bin/activate

# Run experiment with Python script
python3 << 'EOF'
import yaml
from temper_placer.optimizer import optimize
import pandas as pd
import numpy as np
from scipy import stats

configs = [
    ('baseline', '../experiments/temper-65nd/config_baseline.yaml'),
    ('annealed', '../experiments/temper-65nd/config_annealed.yaml'),
    ('control_high', '../experiments/temper-65nd/config_control_high.yaml'),
    ('control_low', '../experiments/temper-65nd/config_control_low.yaml'),
]

results = []
for condition, config_path in configs:
    print(f"Running {condition}...")
    for seed in range(30):
        result = optimize(
            'tests/fixtures/medium_board.kicad_pcb',
            config=config_path,
            epochs=2000,
            seed=seed,
        )
        results.append({
            'condition': condition,
            'seed': seed,
            'final_hpwl': float(result.final_hpwl) if hasattr(result, 'final_hpwl') else None,
            'routing_completion': float(result.routing_completion) if hasattr(result, 'routing_completion') else None,
        })

# Save results
df = pd.DataFrame(results)
df.to_csv('../experiments/temper-65nd/results.csv', index=False)

print("\n=== Results Summary ===")
for condition in df['condition'].unique():
    subset = df[df['condition'] == condition]
    print(f"{condition}: {subset['final_hpwl'].mean():.2f} ± {subset['final_hpwl'].std():.2f}")

# Statistical Analysis
print("\n=== Statistical Analysis ===")
groups = [df[df['condition'] == c]['final_hpwl'].dropna() for c in df['condition'].unique()]
f_stat, p_value = stats.f_oneway(*groups)
print(f"ANOVA: F={f_stat:.3f}, p={p_value:.4f}")

# Pairwise: annealed vs baseline
annealed = df[df['condition'] == 'annealed']['final_hpwl'].dropna()
baseline = df[df['condition'] == 'baseline']['final_hpwl'].dropna()
t_stat, p_value_t = stats.ttest_ind(annealed, baseline)
cohens_d = (annealed.mean() - baseline.mean()) / np.sqrt((annealed.std()**2 + baseline.std()**2) / 2)
print(f"Annealed vs Baseline: t={t_stat:.3f}, p={p_value_t:.4f}, Cohen's d={cohens_d:.3f}")
EOF
```

## Metrics to Collect

1. **Primary:** Final HPWL (lower is better)
2. **Secondary:** Routing Completion Rate (%)
3. **Optional:** Gradient norms at epochs 1800-2000

## Success Criteria

- [ ] Annealed produces ≥5% lower HPWL than Baseline (p < 0.05)
- [ ] Effect size (Cohen's d) ≥ 0.5 (medium effect)
- [ ] Annealed HPWL variance ≤ Baseline variance

## Expected Outcomes

| If... | Then... |
|-------|---------|
| Annealed wins | Update default WirelengthLoss to use annealing |
| No difference | Consider abandoning or trying different schedules |
| Annealed loses | Revert to constant alpha |

## Output Files

- `experiments/temper-65nd/results.csv` - Raw results
- `experiments/temper-65nd/REPORT.md` - Updated with results and conclusions

## Related

- Parent epic: temper-65nd
- Implementation: temper-65nd.1
- Configs: `experiments/temper-65nd/config_*.yaml`
