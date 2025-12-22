# Placement Quality Validation Workflow

This document describes the systematic workflow for validating that the placement optimizer improvements translate to better routed boards. We use the **Ground-truth Placement Benchmark Model (GPBM)** to iteratively tune the optimizer based on empirical routing outcomes.

## Objectives

1. **Close the Loop**: Connect abstract loss function values to physical routing success.
2. **Quantify Quality**: Move beyond "it looks good" to objective 0-100 quality scores.
3. **Data-Driven Tuning**: Use correlation analysis to identify which loss functions matter most.
4. **Prevent Regressions**: Ensure new features don't break routability on existing designs.

---

## 1. Unified Quality Metrics

We track three categories of metrics to evaluate design quality:

### Placement Metrics (Fast)
Computed directly from component positions in JAX.
- **HPWL**: Total Half-Perimeter Wirelength (lower is better).
- **Overlap**: Sum of overlapping areas between components.
- **Boundary**: Magnitude of board edge violations.
- **Thermal Score**: Clustering of high-power components near edges.
- **Clearance**: Violations of net-class specific spacing rules.

### DRC Metrics (Medium)
Extracted from `kicad-cli` design rule checks.
- **Error Count**: Hard violations (unconnected items, shorts, overlaps).
- **Warning Count**: Potential issues (silkscreen overlap, courtyard issues).
- **Exclusion Count**: Explicitly ignored issues.

### Routing Metrics (Slow)
Requires running a router (MazeRouter) to completion.
- **Completion %**: Percentage of nets successfully routed.
- **Routed Length**: Real trace length (mm).
- **Via Count**: Number of layer-to-layer transitions.
- **Routable**: Binary flag indicating if 100% completion was achieved.

---

## 2. The Validation Loop

The validation loop follows these steps:

### Step 1: Optimize Placement
Run the optimizer with your current configuration:
```bash
temper-placer optimize design.kicad_pcb -c config.yaml -o optimized.kicad_pcb
```

### Step 2: Run Quality Report
Generate a comprehensive report including routing verification:
```bash
python3 scripts/placement_quality_report.py --pcb optimized.kicad_pcb --route
```

### Step 3: Correlation Analysis (Multi-run)
To see which losses are predictive of success, run a batch of optimizations with different seeds:
```bash
python3 scripts/correlation_analysis.py --pcb design.kicad_pcb --samples 30 --quick
```

### Step 4: Tune Weights
Update your `config.yaml` based on the analysis:
```bash
python3 scripts/tune_loss_weights.py --correlation-report correlation_report.json --config config.yaml
```

---

## 3. Composite Quality Score

The `quality_score.py` module combines multiple metrics into a single 0-100 score:

| Score | Interpretation | Meaning |
|-------|----------------|---------|
| 90-100 | **Excellent** | Production-ready, minimal or no DRC errors. |
| 80-89 | **Good** | Acceptable, may have minor warnings or sub-optimal wirelength. |
| 60-79 | **OK** | Functional but requires manual adjustment or tuning. |
| 0-59 | **Poor** | Significant violations, likely unroutable or unsafe. |

**Weighting Strategy:**
- **DRC (40%)**: Hard gate. Any error significantly reduces the score.
- **Routability (30%)**: 100% completion is mandatory for a high score.
- **Efficiency (20%)**: Wirelength and via count minimization.
- **Compliance (10%)**: Thermal and safety (HV-LV) clearances.

---

## 4. Integration with `bd`

The `bd-done` workflow automatically runs quality validation if your task description includes `measurement_targets`.

**Example `bd` description:**
```yaml
Improve gate driver clustering.

measurement_targets:
  - metric: placer_overlap_loss
    target: "< 0.5"
  - metric: router_completion_pct
    target: "== 100"
  - metric: placer_quality_score
    target: ">= 85"
```

When you close the task, `bd` will run the necessary scripts and verify that your changes met the targets before committing.

---

## 5. Reference Designs

We validate the optimizer against these benchmark PCBs:

| Name | Complexity | Key Challenge |
|------|------------|---------------|
| `piantor_left` | 36 components | Dense matrix layout |
| `bitaxe_ultra` | 82 components | High current, thermal |
| `libresolar_bms` | 54 components | Power/Signal isolation |
| `temper` | 92 components | Full system integration |

Placements are compared against human-designed "ground truth" baselines stored in `tests/fixtures/external/.cache/`.