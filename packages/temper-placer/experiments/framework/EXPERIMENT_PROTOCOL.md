# Temper-Placer Experiment Protocol

**Version:** 1.0.0
**Last Updated:** 2025-12-25

This document defines the standard protocol for running experiments in the temper-placer project. Following this protocol ensures reproducibility, statistical rigor, and clear documentation of findings.

---

## Table of Contents

1. [Pre-Experiment Checklist](#pre-experiment-checklist)
2. [Experiment Design Template](#experiment-design-template)
3. [Execution Protocol](#execution-protocol)
4. [Analysis Protocol](#analysis-protocol)
5. [Reporting Standards](#reporting-standards)
6. [Quick Reference](#quick-reference)

---

## Pre-Experiment Checklist

Before starting any experiment:

- [ ] **Define hypothesis**: Write a precise, falsifiable statement
- [ ] **Check registry**: Review `EXPERIMENT_REGISTRY.yaml` for prior related work
- [ ] **Define success criteria**: Reference `SUCCESS_CRITERIA.yaml` for targets
- [ ] **Estimate resources**: Calculate seeds × epochs × time per run
- [ ] **Create issue**: Track experiment in beads (`bd create`)
- [ ] **Query Eco**: Search for prior context on the topic

```bash
# Check for prior experiments
grep -i "your_topic" experiments/framework/EXPERIMENT_REGISTRY.yaml

# Create tracking issue
bd create --title "Experiment: Your Hypothesis" --epic temper-placer
```

---

## Experiment Design Template

Every experiment must have a design document. Use this template:

```yaml
# experiments/<experiment_id>/DESIGN.yaml

meta:
  experiment_id: "temper-xxxx"
  name: "Descriptive Name"
  created: "YYYY-MM-DD"
  author: "temper-agent"
  status: "planned"  # planned | running | completed | abandoned

hypothesis:
  statement: "If we [change X], then [outcome Y] because [mechanism Z]"
  null_hypothesis: "There is no difference between conditions"
  type: "superiority"  # superiority | non-inferiority | equivalence

design:
  type: "randomized_controlled"  # ablation | A/B | factorial | correlation

  independent_variables:
    - name: "variable_name"
      type: "categorical"  # categorical | continuous
      levels: ["control", "treatment"]

  dependent_variables:
    primary: "main_metric"
    secondary: ["other_metric_1", "other_metric_2"]

  controls:
    epochs: 2000
    learning_rate: 0.1
    test_case: "temper.kicad_pcb"

  sample_size:
    seeds_per_condition: 30
    justification: "Power analysis: 30 seeds gives 80% power to detect d=0.5"

success_criterion:
  metric: "primary_metric"
  direction: "lower"  # lower | higher
  threshold: 0.05  # 5% improvement
  significance_level: 0.05

execution:
  estimated_hours: 4
  parallel_workers: 4
  checkpoint_frequency: 10  # runs
```

---

## Execution Protocol

### Step 1: Setup

```bash
# Create experiment directory
mkdir -p experiments/<experiment_id>

# Copy design template
cp experiments/framework/_TEMPLATE_DESIGN.yaml experiments/<experiment_id>/DESIGN.yaml

# Edit design document
vim experiments/<experiment_id>/DESIGN.yaml
```

### Step 2: Validate Configuration

```bash
# Dry run to check configuration
python -m temper_placer.ablation.cli validate \
  --config experiments/<experiment_id>/DESIGN.yaml
```

### Step 3: Run Experiment

```bash
# Full run with checkpointing
python -m temper_placer.ablation.cli run \
  --config experiments/<experiment_id>/DESIGN.yaml \
  --output experiments/<experiment_id>/results/ \
  --workers 4 \
  --resume

# Monitor progress
watch -n 60 "ls experiments/<experiment_id>/results/*.json | wc -l"
```

### Step 4: Handle Failures

If runs fail:

1. Check logs: `experiments/<experiment_id>/results/failed/`
2. Identify pattern (same seed? same config?)
3. Fix and resume with `--resume` flag
4. Document failures in report

---

## Analysis Protocol

### Step 1: Data Quality Check

```python
from temper_placer.experiments import MetricsTracker

tracker = MetricsTracker("experiments/<experiment_id>/results")
summary = tracker.get_summary_statistics()

# Check for issues
print(f"Total runs: {summary['total_runs']}")
print(f"Failure rate: {summary['failure_rate']:.1%}")

# Identify outliers
runs = tracker.runs
for r in runs:
    if r.final_loss > 1000:  # Anomaly threshold
        print(f"Outlier: {r.run_id}")
```

### Step 2: Statistical Analysis

```python
import scipy.stats as stats

# For ablation studies: compare to baseline
baseline = [r.final_loss for r in tracker.filter_runs() if r.experiment_name == "baseline"]
treatment = [r.final_loss for r in tracker.filter_runs() if r.experiment_name == "treatment"]

# Independent samples t-test
t_stat, p_value = stats.ttest_ind(baseline, treatment)

# Effect size (Cohen's d)
cohens_d = (mean(baseline) - mean(treatment)) / pooled_std

# Report
print(f"t({len(baseline) + len(treatment) - 2}) = {t_stat:.3f}, p = {p_value:.4f}")
print(f"Cohen's d = {cohens_d:.3f}")
```

### Step 3: Visualization

Required visualizations:

1. **Box plot**: Compare conditions
2. **Loss trajectory**: Convergence over epochs
3. **Scatter matrix**: Correlation between metrics

```python
import matplotlib.pyplot as plt

# Box plot
fig, ax = plt.subplots()
ax.boxplot([baseline, treatment], labels=["Baseline", "Treatment"])
ax.set_ylabel("Final Loss")
plt.savefig("experiments/<experiment_id>/boxplot.png")
```

---

## Reporting Standards

Every experiment must produce a report. Use this structure:

```markdown
# Experiment Report: <experiment_id>

## Summary
- **Hypothesis**: [One sentence]
- **Result**: CONFIRMED | REJECTED | INCONCLUSIVE
- **Key Finding**: [One sentence takeaway]

## Design
[Copy from DESIGN.yaml or reference it]

## Results

### Primary Outcome
| Condition | N | Mean ± SD | 95% CI |
|-----------|---|-----------|--------|
| Baseline  | 30| 45.2 ± 5.1| [43.1, 47.3] |
| Treatment | 30| 41.8 ± 4.8| [39.9, 43.7] |

**Statistical Test**: t(58) = 2.65, p = 0.010
**Effect Size**: Cohen's d = 0.69 (medium)

### Secondary Outcomes
[Table for each secondary metric]

## Visualizations
![Box Plot](boxplot.png)
![Convergence](convergence.png)

## Discussion
- **Interpretation**: [What does this mean?]
- **Limitations**: [What might be wrong?]
- **Implications**: [What should we do next?]

## Follow-up Actions
- [ ] Update loss weights based on findings
- [ ] Design follow-up experiment for X
- [ ] File issue for Y

## Appendix
- Raw data: `results/runs.json`
- Analysis code: `analysis.py`
```

---

## Quick Reference

### Effect Size Interpretation (Cohen's d)

| d Value | Interpretation |
|---------|----------------|
| < 0.2   | Negligible     |
| 0.2-0.5 | Small          |
| 0.5-0.8 | Medium         |
| > 0.8   | Large          |

### Sample Size Guidelines

| Effect Size | Samples Needed (80% power) |
|-------------|----------------------------|
| Large (0.8) | 26 per group               |
| Medium (0.5)| 64 per group               |
| Small (0.2) | 394 per group              |

**Recommendation**: Use 30 seeds for most experiments (detects d ≥ 0.5)

### Checklist Before Publishing Results

- [ ] All runs completed without errors
- [ ] Statistical tests appropriate for data type
- [ ] Effect sizes reported (not just p-values)
- [ ] Visualizations clear and labeled
- [ ] Conclusions match the data
- [ ] Limitations acknowledged
- [ ] Follow-up actions identified
- [ ] Results added to EXPERIMENT_REGISTRY.yaml
- [ ] Reflection posted to Eco

### Common Commands

```bash
# Generate config from design
python -m temper_placer.ablation.cli generate --design DESIGN.yaml

# Run with 4 workers
python -m temper_placer.ablation.cli run --config config.yaml --workers 4

# Analyze results
python -m temper_placer.ablation.cli analyze --results results/

# Export to CSV
python -c "from temper_placer.experiments import MetricsTracker; \
  MetricsTracker('results').export_csv('results.csv')"

# Quick statistics
python -c "from temper_placer.experiments import MetricsTracker; \
  import json; print(json.dumps(MetricsTracker('results').get_summary_statistics(), indent=2))"
```

---

## Appendix: Statistical Decision Tree

```
Is your outcome continuous?
├── Yes
│   ├── Comparing 2 groups?
│   │   ├── Independent samples? → t-test
│   │   └── Paired samples? → paired t-test
│   └── Comparing >2 groups?
│       ├── Independent? → one-way ANOVA + post-hoc
│       └── Repeated measures? → repeated measures ANOVA
└── No (categorical)
    ├── 2×2 table? → Chi-square / Fisher's exact
    └── Other? → Chi-square test
```

---

*This protocol is a living document. Update it as we learn better practices.*
