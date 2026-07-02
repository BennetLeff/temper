---
module: temper-placer
date: 2026-07-02
problem_type: architecture_pattern
component: tooling
severity: medium
tags:
  - dark-metrics
  - physics-oracle
  - quality-report
  - dead-code-activation
  - chain-of-proof
  - tdd
  - pbt
---

# Wiring Dark Physics Metrics to Live: The Chain-of-Proof Pattern

## Context

The temper-placer had five power-electronics score functions (`thermal_score`, `zone_compliance_score`, `hv_lv_clearance_score`, `loop_area_score`, `congestion_score`) that each returned `1.0` (perfect score) when their input set was empty — and the input sets were empty because the physics infrastructure existed but was never wired into the optimizer. `ClearanceLoss` had weight `100.0` but `hv_indices` was always empty. `loop_area_score` returned `1.0` because `loop_components` was `[]`. The corpus regression gate blessed zeros on every PR.

The remedy was a pattern proven across three distinct chain shapes: wire each link in the chain (classify → derive → populate → measure → threshold → loss-term), TDD each metric's dynamic range, and A/B diff to prove the constraint has teeth.

See also: `docs/solutions/workflow-issues/quality-metrics-modules-never-connected-2026-07-01.md` (the three modules that were built but never called), `docs/solutions/workflow-issues/dead-code-from-features-with-no-activation-surface-2026-07-01.md` (config flags with no activation surface).

## Guidance

Every dark physics metric follows the same six-link chain. If any link is broken, the metric returns a default value that can't fail.

### The chain

```
config/spec  -->  derive  -->  populate quality_config  -->  measure  -->  threshold  -->  loss term
(pcb_spec)     (derive_     (infer_quality_config +       (compute_      (IPC-2221/     (ClearanceLoss,
                constraints_  override from spec)          quality_       IEC-60335/     ThermalLoss,
                from_spec)                                report)        spec value)    ComponentLoopAreaLoss)
```

### Link 1: Declare component roles in the spec

Physics metrics need to know *which* components participate. The SSOT is `pcb_spec.yaml`:

```yaml
# Minimal additions to make three metrics live
thermal:
  max_junction_temp_c: 110.0
  ambient_temp_c: 40.0
  target_edge: "BOTTOM"          # NEW: which edge for heatsink
  max_heatspread_mm: 30.0        # NEW: acceptable edge distance
  power_dissipation:
    Q1: 15.0
    Q2: 15.0

emi:
  max_loop_area_mm2:
    commutation_loop: 80.0
    gate_drive_loop: 30.0
  loop_components:                # NEW: which components form each loop
    commutation_loop: [C_BUS1, Q1, Q2, C_BUS2]
    gate_drive_high: [U_GATE_DRV, R_GATE_H, Q1]
    gate_drive_low: [U_GATE_DRV, R_GATE_L, Q2]

safety:
  mains_voltage_v: 230.0
  pollution_degree: 2
```

### Link 2: Derive constraints from the spec

`derive_constraints_from_spec` turns spec values into concrete thresholds that don't reference the placer's own output:

```python
# derivation.py
if spec.safety is not None:
    vc = _mains_voltage_to_class(spec.safety.mains_voltage_v)
    derived["hv_lv_isolation_mm"] = vc.get_clearance_mm(
        pollution_degree=spec.safety.pollution_degree
    )
# 230V, PD2 → MAINS_240V → 3.0mm (IEC 60335-1 Table 16)
```

The threshold must be an absolute physics-derived number (IPC-2221, IEC 60335-1), not a default constant like `6.5` or `10.0`.

### Link 3: Populate the quality config

`infer_quality_config()` provides heuristic defaults (footprint-based thermal/HV/LV detection, net-name-based loop detection). Classification-driven overrides from Link 2 are more authoritative:

```python
# In the physics oracle runner:
quality_config = infer_quality_config(design)

# Override with classification-driven values (more authoritative)
hv_from_class = {c.ref for c in netlist.components
                 if c.net_class in ("HighVoltage", "ACMains")}
lv_from_class = {c.ref for c in netlist.components
                 if c.net_class == "Signal"}
if hv_from_class:
    quality_config["hv_components"] = hv_from_class
if lv_from_class:
    quality_config["lv_components"] = lv_from_class

# Wire spec-derived thresholds
quality_config["thermal_target_edge"] = spec.thermal.target_edge
quality_config["thermal_max_distance"] = spec.thermal.max_heatspread_mm
quality_config["min_hv_lv_clearance"] = derived["hv_lv_isolation_mm"]
```

### Link 4: Measure — the score function

Each metric gets a normalized `[0, 1]` score function that:
- Returns `1.0` when input set is empty (nothing to check)
- Returns `0.0` for severe violations (overlapping, zero area, far from edge)
- Returns proportional values in between
- Is called by `compute_quality_report` with the config from Link 3

```python
# quality.py: compute_quality_report extracts from config
thermal_comps = config.get("thermal_components", set())
hv_comps = config.get("hv_components", set())
loop_comps = config.get("loop_components", [])

thermal = thermal_score(state, netlist, board, thermal_comps,
                        target_edge=config.get("thermal_target_edge", "TOP"),
                        max_distance=config.get("thermal_max_distance", 10.0))
clearance = hv_lv_clearance_score(state, netlist, hv_comps, lv_comps,
                                  config.get("min_hv_lv_clearance", 8.0))
loop = loop_area_score(state, netlist, context, loop_comps)
```

### Link 5: Threshold — compare against the spec

The derived threshold from Link 2 becomes the pass/fail boundary. A score of `0.95` means "clearance ≥ 95% of required" — the boundary should be physics-derived, not a heuristically chosen constant.

### Link 6: Loss term — prove constraint has teeth

A metric is only a reporter until the optimizer has a loss term pushing in the right direction. Without a loss term, the metric flips from `1.0` (dark) to some fixed value, but the optimizer doesn't respond. With a loss term, the optimizer pushes toward the target and the score changes.

Each loss term needs a different chain shape:
- **ClearanceLoss**: pairwise box-to-box distance, softplus penalty when below threshold
- **ComponentLoopAreaLoss**: shoelace polygon area from component centers, ReLU penalty above max
- **ThermalLoss**: 1D edge distance, softplus penalty beyond max_distance

### Proof: A/B diff

The defining proof that a constraint has teeth is whether wiring it changes the placer's output. Run twice — once without the loss term active (dark), once with:

```
Run A: no HV/LV classification → hv_indices empty → ClearanceLoss returns 0
Run B: with classification → hv_indices populated → ClearanceLoss active
Diff: mean component delta 5.43mm, min HV-LV distance +23% (3.96→4.87mm)
Conclusion: constraint has teeth
```

### TDD: prove the metric can fail

Before wiring any metric, prove it has full dynamic range [0, 1]:

```python
# Base case: overlapping → score 0.0
# Base case: at max_distance → score 0.0
# Base case: half max → score 0.5
# Base case: at edge → score 1.0
# Base case: two components → average of individual scores
# PBT: monotonicity — score decreases strictly with distance
```

A metric that returns `0.79` instead of `1.0` is better than dark, but without a fail-case proving it can hit `0.0`, you've just replaced `return 1.0` with `return 0.79` — a more-sophisticated dark metric.

## Why This Matters

Before this pattern, physics constraints were a black box: we knew loss functions computed gradients, but we couldn't answer "did constraint X actually improve the placement?" The quality report measured geometric drift (wirelength, overlap, boundary) — proxies that spread regularization already optimizes.

Three impacts of making metrics live:

1. **Verifiable constraint teeth**: Each loss can be A/B diffed — is the optimizer responding? A `ClearanceLoss` with weight `100.0` and empty `hv_indices` produces zero gradient. After wiring, it produces 5.43mm mean position delta. Without the score, no one can tell if the weight is too low or the constraint is already satisfied.

2. **Multi-objective competition**: Three active loss terms reveal real trade-offs. On the temper board: `ClearanceLoss` pushes Q1/Q2 away from LV components (clearance_score `0.43`), `ComponentLoopAreaLoss` pulls commutation components together (loop_area_score `0.9996`), `ThermalLoss` pushes Q1/Q2 to the BOTTOM edge (thermal_score `0.14`). The optimizer navigates the trade-off space with real gradients — this is what a physics oracle is for.

3. **Trustworthy baselines**: A metric that can't fail makes every regression run a pass. The corpus gate was blessing zeros on every PR because `hpwl_val = 0.0` never exceeded any positive baseline. Fixing it required: correct HPWL function, no swallowed `try/except`, measured (not hardcoded) overlap/boundary, and reasonable `margin_abs` values.

## When to Apply

- Adding a new physics-based loss function to the optimizer (not just geometric)
- Finding any `return 1.0` or `return 0.0` when an input set is empty — check whether the upstream wiring populates it
- Any `try: ... except Exception: pass` in a measurement or gate code path
- Debugging whether a constraint weight is effective or just producing noise
- Adding a metric where component *roles* matter (not all components participate equally)

## Examples

### Before/After: HV/LV Clearance

| Stage | Score | What changed |
|-------|-------|-------------|
| Dark | `1.0` | `hv_components` empty — nothing to measure |
| Live | `0.91` | 10 HV + 23 LV classified via `TEMPER_NET_CLASSES` |
| With loss | `0.43` | `ClearanceLoss` pushing HV/LV apart, competing with loop-area loss |

### Before/After: Loop Area

| Stage | Score | What changed |
|-------|-------|-------------|
| Dark | `1.0` | `loop_components` empty |
| Live | `0.00` | Commutation loop detected, 1012mm² vs 80mm² spec |
| With loss | `0.9996` | `ComponentLoopAreaLoss` collapsing loop to near-zero |

### Before/After: Thermal Edge

| Stage | Score | What changed |
|-------|-------|-------------|
| Dark | `1.0` | `thermal_components` empty (wrong edge config) |
| Live | `0.00` | Q1/Q2 detected, BOTTOM edge, max=30mm — 15mm away |
| With loss | `0.14` | `ThermalLoss` pushing to edge, competing with clearance |

### Before/After: Corpus Regression Gate (R16)

```python
# BEFORE: five bugs — wrong function, swallowed try/except, hardcoded zeros
hpwl_val = 0.0
try:
    hpwl_val = float(compute_hpwl(result.final_state, netlist))  # nonexistent function
except Exception:
    pass  # silently hides failure → 0.0 passes any baseline

return {
    "wirelength_final": {"mean": float(result.final_loss), ...},  # aliased to composite loss
    "overlap_loss_final": {"mean": 0.0, ...},                     # hardcoded
    "boundary_loss_final": {"mean": 0.0, ...},                    # hardcoded
}

# AFTER: real metrics from composite loss breakdown
rotations = jax.nn.softmax(result.final_state.rotation_logits, axis=-1)
composite = make_loss(weights)
loss_result = composite(result.final_state.positions, rotations, context)
breakdown = loss_result.breakdown or {}

overlap_val = float(breakdown.get("overlap", 0.0))
wirelength_val = float(breakdown.get("wirelength", 0.0))
boundary_val = float(breakdown.get("boundary", 0.0))
hpwl_val = float(compute_total_hpwl(result.final_state.positions, rotations, context))
```
