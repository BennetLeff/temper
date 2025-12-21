# Hypothesis Template for Experiments and Validation

**Purpose:** This template ensures scientific rigor for all issues labeled `experiment` or `validation`. Use this structure when investigating unknowns, comparing options, or validating system behavior.

**Reference:** See `docs/MEMORY_OPTIMIZATION_FINDINGS.md` for an exemplary application of this template.

---

## Template

Copy and adapt the following structure for your experiment/validation issue:

```markdown
# [Title]: [Brief Description]

**Epic/Issue:** [temper-XXX]  
**Date:** [YYYY-MM-DD]  
**Status:** [Planning | In Progress | Complete]  
**Labels:** experiment, validation (as applicable)

## Executive Summary

[1-3 sentences summarizing the key finding. Write this AFTER completing the experiment.]

## Hypotheses

### Null Hypothesis (H0)
[State what you expect to be true if there is NO effect. Be specific and measurable.]

Example: "Reducing spread_loss weight from 1.0 to 0.3 will have no significant effect on routing completion rate."

### Alternative Hypothesis (H1)
[State what you expect to be true if there IS an effect. Include direction if known.]

Example: "Reducing spread_loss weight from 1.0 to 0.3 will increase routing completion rate by at least 10%."

### Expected Effect Size
[Quantify the minimum meaningful change you're looking for.]

Example: "We consider a routing completion improvement of >=5% to be practically significant."

## Pre-Registration

**IMPORTANT:** Complete this section BEFORE running experiments. This prevents p-hacking and HARKing (Hypothesizing After Results are Known).

### Predictions
1. [Specific, testable prediction 1]
2. [Specific, testable prediction 2]
3. [Specific, testable prediction 3]

### Decision Criteria
- **Accept H1 if:** [specific threshold, e.g., "p < 0.05 AND effect size > 5%"]
- **Accept H0 if:** [specific threshold, e.g., "p >= 0.05 OR effect size < 5%"]
- **Inconclusive if:** [conditions for needing more data]

## Methodology

### Control Conditions
[What variables are held constant across all tests?]

| Variable | Constant Value | Rationale |
|----------|---------------|-----------|
| [var1]   | [value]       | [why]     |
| [var2]   | [value]       | [why]     |

### Independent Variables
[What are you manipulating?]

| Variable | Levels | Description |
|----------|--------|-------------|
| [var1]   | [A, B, C] | [what each level means] |

### Dependent Variables (Metrics)
[What are you measuring?]

| Metric | Definition | Source | Target |
|--------|------------|--------|--------|
| [metric1] | [precise definition] | [how measured] | [success threshold] |
| [metric2] | [precise definition] | [how measured] | [success threshold] |

### Test Cases
[Enumerate specific test scenarios]

| # | Scenario | Inputs | Expected Output |
|---|----------|--------|-----------------|
| 1 | [name]   | [specific inputs] | [expected result] |
| 2 | [name]   | [specific inputs] | [expected result] |

### Sample Size & Power
[How many runs/samples will you collect?]

- **Planned sample size:** [N runs per condition]
- **Power analysis:** [If applicable, justify sample size based on expected effect size]
- **Random seeds:** [List specific seeds for reproducibility, e.g., 42, 123, 456, ...]

## Results

### Raw Data
[Present unprocessed results in tables]

| Condition | Run | [Metric1] | [Metric2] |
|-----------|-----|-----------|-----------|
| Baseline  | 1   | [value]   | [value]   |
| Baseline  | 2   | [value]   | [value]   |
| Treatment | 1   | [value]   | [value]   |

### Summary Statistics
[Aggregate results with measures of central tendency and variability]

| Condition | N | Mean | Std Dev | 95% CI |
|-----------|---|------|---------|--------|
| Baseline  | [n] | [mean] | [std] | [[lo], [hi]] |
| Treatment | [n] | [mean] | [std] | [[lo], [hi]] |

### Statistical Tests
[Report test results with effect sizes and confidence intervals]

| Comparison | Test | Statistic | p-value | Effect Size | 95% CI |
|------------|------|-----------|---------|-------------|--------|
| Base vs Treatment | [test type] | [stat] | [p] | [d/r/eta] | [[lo], [hi]] |

**Multiple comparison correction:** [Bonferroni/Holm/FDR-BH if >3 comparisons]

## Analysis

### Key Insights
1. [Insight 1 with supporting data]
2. [Insight 2 with supporting data]
3. [Unexpected finding, if any]

### Comparison to Predictions
| Prediction | Observed | Match? |
|------------|----------|--------|
| [prediction 1] | [what happened] | Yes/No/Partial |
| [prediction 2] | [what happened] | Yes/No/Partial |

### Threats to Validity
- **Internal validity:** [confounds, selection bias, etc.]
- **External validity:** [generalizability limitations]
- **Construct validity:** [are we measuring what we think?]

## Conclusion

### Hypothesis Verdict
- [ ] **H0 Accepted:** [explanation]
- [ ] **H1 Accepted:** [explanation]
- [ ] **Inconclusive:** [what additional data is needed]

### Recommendations
1. [Actionable recommendation based on findings]
2. [Configuration/code changes, if any]
3. [Follow-up experiments needed]

### Limitations
[What can't we conclude from this experiment?]

## Implementation Summary

### Changes Made
[If experiment led to code changes, list them]

1. **[filename]**
   - [change description]

### Files Modified
- `path/to/file1.py`
- `path/to/file2.yaml`

## References

- [Related issue: temper-XXX]
- [Prior art or literature]
- [Relevant documentation]
```

---

## Quick Checklist

Before marking an `experiment` or `validation` issue as complete, verify:

- [ ] **Hypotheses stated** before running experiment (H0 and H1)
- [ ] **Predictions pre-registered** before seeing data
- [ ] **Control conditions** documented
- [ ] **Sample size** justified (power analysis if applicable)
- [ ] **Random seeds** recorded for reproducibility
- [ ] **Confidence intervals** reported (not just point estimates)
- [ ] **Effect sizes** reported (not just p-values)
- [ ] **Multiple comparison correction** applied if >3 comparisons
- [ ] **Threats to validity** acknowledged
- [ ] **Clear verdict** on hypotheses
- [ ] **Actionable recommendations** provided

---

## When to Use This Template

**Required for:**
- Issues with label `experiment`
- Issues with label `validation`
- Any investigation comparing multiple approaches
- Performance optimization studies
- Configuration tuning work

**Optional but recommended for:**
- Bug investigations with unknown root cause
- "Spike" tasks exploring new technologies
- Refactoring with measurable quality goals

---

## Examples

### Good Hypothesis Statements

| Domain | H0 | H1 |
|--------|----|----|
| Placer | "EdgeAvoidanceLoss weight has no effect on routing completion" | "EdgeAvoidanceLoss weight=0.5 improves routing completion by >=5%" |
| Firmware | "PID gains {Kp=1.0, Ki=0.1, Kd=0.01} produce same settling time as {Kp=2.0, Ki=0.2, Kd=0.02}" | "Doubling PID gains reduces settling time by >=20%" |
| Memory | "Token budget for GATHER phase equals ~1000 tokens" | "GATHER phase exceeds 1500 token budget requiring optimization" |

### Bad Hypothesis Statements (Avoid These)

| Problem | Example | Why Bad |
|---------|---------|---------|
| Vague | "The optimizer works better" | No measurable outcome |
| No null | "Adding loss X improves placement" | No comparison baseline |
| Unfalsifiable | "The code might have a bug" | Can't be disproven |
| Post-hoc | "We found that X caused Y" | Hypothesis after seeing data |

---

## Integration with GPBM Workflow

This template aligns with the GPBM (Gather-Plan-Build-Measure) workflow:

| GPBM Phase | Template Section |
|------------|-----------------|
| **GATHER** | Background, Related issues |
| **HYPOTHESIZE** (new) | Hypotheses, Pre-Registration |
| **PLAN** | Methodology, Test Cases |
| **BUILD** | Implementation (if needed) |
| **MEASURE** | Results, Summary Statistics |
| **ANALYZE** (new) | Analysis, Comparison to Predictions |
| **CONCLUDE** (new) | Conclusion, Recommendations |

The extended GPBM workflow adds HYPOTHESIZE, ANALYZE, and CONCLUDE phases specifically for scientific rigor.
