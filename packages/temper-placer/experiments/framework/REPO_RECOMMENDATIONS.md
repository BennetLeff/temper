# Repository Modification Recommendations

Based on the correctness framework research, here are recommended modifications to the temper-placer repository structure, code organization, and development practices.

---

## 1. Directory Structure Changes

### Current Structure (Simplified)
```
packages/temper-placer/
├── src/temper_placer/
│   ├── losses/           # 38 loss functions
│   ├── optimizer/        # Training, NSGA-II
│   ├── core/             # Data structures
│   ├── io/               # KiCad I/O
│   ├── validation/       # Some validators (incomplete)
│   └── experiments/      # Weight search
├── tests/
├── configs/
└── docs/
```

### Recommended Structure
```
packages/temper-placer/
├── src/temper_placer/
│   ├── losses/           # Keep as-is
│   ├── optimizer/        # Keep as-is
│   ├── core/             # Keep as-is
│   ├── io/               # Keep as-is
│   ├── physics/          # NEW: Physical models
│   │   ├── __init__.py
│   │   ├── inductance.py # Loop inductance estimation
│   │   ├── thermal.py    # Junction temperature estimation
│   │   └── emi.py        # EMI prediction (future)
│   ├── validation/       # EXPAND: Correctness validation
│   │   ├── __init__.py
│   │   ├── geometric/    # Level 2 validators
│   │   │   ├── overlap.py
│   │   │   ├── boundary.py
│   │   │   ├── creepage.py    # NEW
│   │   │   └── clearance.py
│   │   ├── electrical/   # Level 3 validators
│   │   │   ├── loop_inductance.py  # NEW
│   │   │   ├── thermal.py          # NEW
│   │   │   └── spice_pipeline.py   # NEW
│   │   ├── manufacturing/  # Level 4 validators
│   │   │   ├── dfm.py      # NEW
│   │   │   └── dfa.py      # NEW
│   │   ├── gates.py       # NEW: Validation gates
│   │   └── baseline.py    # NEW: Baseline extraction
│   ├── routing/          # NEW: Routing integration
│   │   ├── __init__.py
│   │   ├── freerouting.py # Freerouting integration
│   │   ├── analyzer.py    # Routing analysis
│   │   └── correlation.py # Routing correlation
│   └── metrics/          # NEW: Metrics infrastructure
│       ├── __init__.py
│       ├── tracker.py     # MetricsTracker
│       ├── baseline.py    # BaselineMetrics
│       └── correlation.py # Proxy correlation
├── experiments/
│   ├── framework/        # NEW: Scientific framework (created)
│   │   ├── SUCCESS_CRITERIA.yaml
│   │   ├── MEASUREMENT_SPEC.yaml
│   │   ├── CORRECTNESS_FRAMEWORK.md
│   │   └── ...
│   └── results/          # NEW: Experiment results
│       ├── ablation_v1/
│       └── routing_correlation_v1/
├── tests/
│   ├── physics/          # NEW
│   ├── routing/          # NEW
│   └── metrics/          # NEW
└── configs/
    └── validation/       # NEW: Validation configs
        └── production_ready.yaml
```

---

## 2. New Modules to Create

### Priority 0 (This Week)

#### `src/temper_placer/physics/inductance.py`
```python
"""Loop inductance estimation from geometry."""

def estimate_loop_inductance(
    loop_area_mm2: float,
    layer_separation_mm: float = 0.4,
    routing_factor: float = 1.3,
) -> float:
    """Convert loop area to estimated inductance in nH."""
    ...
```

#### `src/temper_placer/validation/geometric/creepage.py`
```python
"""Creepage distance estimation and validation."""

class CreepageEstimator:
    """Estimate creepage between HV and LV components."""
    ...

class CreepageLoss(LossFunction):
    """Loss function for creepage optimization."""
    ...
```

#### `src/temper_placer/validation/gates.py`
```python
"""Validation gates for pipeline progression."""

@dataclass
class ValidationGate:
    name: str
    required_metrics: list[str]
    thresholds: dict[str, float]

    def check(self, metrics: RunMetrics) -> GateResult:
        ...

PLACEMENT_COMPLETE = ValidationGate(...)
PRODUCTION_READY = ValidationGate(...)
```

### Priority 1 (This Month)

#### `src/temper_placer/routing/analyzer.py`
```python
"""Routing analysis and statistics collection."""

class RoutingAnalyzer:
    """Collect detailed routing statistics."""

    def analyze(self, placement: PlacementState) -> RoutingAnalysis:
        ...
```

#### `src/temper_placer/physics/thermal.py`
```python
"""Thermal estimation from placement."""

def estimate_junction_temp(
    power_W: float,
    edge_distance_mm: float,
    ambient_C: float = 40.0,
) -> float:
    """Estimate junction temperature."""
    ...
```

---

## 3. Configuration File Changes

### New: `configs/validation/production_ready.yaml`
```yaml
# Production-ready validation configuration
# Reference: experiments/framework/MEASUREMENT_SPEC.yaml

gates:
  placement_complete:
    overlap_loss: 0.0
    boundary_loss: 0.0
    zone_violations: 0
    hv_lv_clearance_mm: 10.0

  electrical_valid:
    gate_loop_inductance_nh: 10.0
    igbt_edge_distance_mm: 5.0
    creepage_mm: 6.5

  production_ready:
    drc_errors: 0
    routing_completion_percent: 90.0
    min_trace_width_mm: 0.15
```

### Modify: `configs/temper_constraints.yaml`
Add:
```yaml
# Safety validation thresholds
safety:
  creepage_min_mm: 6.5
  clearance_min_mm: 8.0
  isolation_class: "reinforced"

# Physics model parameters
physics:
  layer_separation_mm: 0.4
  routing_factor: 1.3
  thermal_ambient_c: 40.0
```

---

## 4. Loss Function Changes

### New Loss: `CreepageLoss`
Add to `src/temper_placer/losses/`:
```python
# losses/creepage.py
class CreepageLoss(LossFunction):
    """
    Penalize placements where creepage falls below safety threshold.

    Weight recommendation: 50.0 (safety-critical)
    """
    ...
```

### Update: Curriculum Learning
Modify `optimizer/curriculum.py` to include creepage:
```python
PHASE_WEIGHTS = {
    'spread': {1: 1.0, 2: 0.5, 3: 0.2, 4: 0.1, 5: 0.1},
    'overlap': {1: 50.0, 2: 100.0, 3: 150.0, 4: 200.0, 5: 200.0},
    'creepage': {1: 10.0, 2: 30.0, 3: 50.0, 4: 50.0, 5: 50.0},  # NEW
    ...
}
```

---

## 5. CLI Changes

### New Commands

```bash
# Validate placement against gate
temper-placer validate --gate production_ready --pcb output.kicad_pcb

# Extract baseline metrics
temper-placer baseline --pcb temper.kicad_pcb --output baselines/human.json

# Run routing analysis
temper-placer routing-analyze --pcb output.kicad_pcb --output routing_stats.json

# Run full validation pipeline
temper-placer validate-full --pcb output.kicad_pcb \
  --spice \
  --routing \
  --output validation_report.json
```

### Modify: `optimize` Command
Add flags:
```bash
temper-placer optimize \
  --input schematic.kicad_pcb \
  --config temper_constraints.yaml \
  --track-metrics                    # NEW: Enable metrics tracking
  --validate-gate placement_complete # NEW: Fail if gate fails
  --output-metrics metrics.json      # NEW: Export metrics
```

---

## 6. Test Structure Changes

### New Test Directories

```
tests/
├── physics/
│   ├── test_inductance.py
│   └── test_thermal.py
├── validation/
│   ├── test_creepage.py
│   ├── test_gates.py
│   └── test_baseline.py
├── routing/
│   ├── test_analyzer.py
│   └── test_correlation.py
└── integration/
    └── test_validation_pipeline.py
```

### New Test Fixtures

```python
# tests/conftest.py

@pytest.fixture
def production_gate():
    """Production-ready validation gate."""
    return ValidationGate.load("configs/validation/production_ready.yaml")

@pytest.fixture
def baseline_metrics():
    """Baseline metrics from human-designed PCB."""
    return BaselineMetrics.load("baselines/human_temper.json")
```

---

## 7. Documentation Changes

### Update: `AGENTS.md`
Add section on validation:
```markdown
## Validation Framework

All placements must pass validation gates before progression:

1. **placement_complete**: Geometric validity (overlap, boundary, zones)
2. **electrical_valid**: Electrical correctness (loop inductance, thermal)
3. **production_ready**: Manufacturing readiness (DRC, routing, DFM)

See `experiments/framework/CORRECTNESS_FRAMEWORK.md` for details.
```

### New: `docs/validation/README.md`
```markdown
# Validation System

## Hierarchy of Correctness
[Reference CORRECTNESS_FRAMEWORK.md]

## Validation Gates
[Document each gate and its requirements]

## Running Validation
[CLI commands and examples]
```

---

## 8. Development Workflow Changes

### Experiment Protocol
All experiments must follow `experiments/framework/EXPERIMENT_PROTOCOL.md`:
1. Create design document
2. Define success criteria
3. Run with sufficient seeds (≥30)
4. Analyze with statistical rigor
5. Document in EXPERIMENT_REGISTRY.yaml

### PR Checklist Addition
```markdown
## Validation Checklist
- [ ] New loss functions have unit tests
- [ ] New loss functions document expected correlation with actuals
- [ ] Changes don't regress existing validation gates
- [ ] Experiments use standard protocol
```

### CI Pipeline Addition
```yaml
# .github/workflows/validation.yml
validation:
  runs-on: ubuntu-latest
  steps:
    - name: Run validation gate tests
      run: pytest tests/validation/ -v

    - name: Check baseline regression
      run: |
        temper-placer optimize --quick-test
        temper-placer validate --gate placement_complete
```

---

## 9. Recommended Execution Order

### Week 1: Foundation
1. Create `physics/inductance.py` with tests
2. Create `validation/geometric/creepage.py` with tests
3. Create `validation/gates.py` with tests
4. Add `CreepageLoss` to losses

### Week 2: Routing Investigation
1. Create `routing/analyzer.py`
2. Run routing correlation study
3. Document findings

### Week 3: Integration
1. Integrate MetricsTracker into train.py
2. Add CLI validation commands
3. Extract baseline from temper.kicad_pcb

### Week 4: Validation Pipeline
1. Implement validation gate checking
2. Add SPICE pipeline integration
3. Create thermal estimator

---

## 10. Key Principles

### Measure Everything
```python
# Every optimization run should produce:
RunMetrics(
    overlap_loss=...,
    boundary_loss=...,
    creepage_mm=...,          # NEW
    gate_loop_inductance_nh=...,  # NEW
    thermal_junction_c=...,   # NEW
    routing_completion=...,   # NEW
    ...
)
```

### Validate Early, Validate Often
```python
# After placement optimization:
gate_result = PLACEMENT_COMPLETE.check(metrics)
if not gate_result.passed:
    raise ValidationError(gate_result.failures)
```

### Correlate Proxies with Actuals
```python
# Track proxy accuracy over time:
correlation_tracker.record(
    proxy_name="loop_area_loss",
    proxy_value=100.5,
    actual_name="measured_inductance_nh",
    actual_value=12.3,
)
```

### Document Success Criteria
```yaml
# Every metric has a target:
gate_loop_inductance:
  target: 10.0
  unit: nH
  tolerance: "+0%"
  criticality: blocking
```

---

## Summary

The key changes are:

1. **New `physics/` module** for physical models (inductance, thermal)
2. **Expanded `validation/` module** with geometric, electrical, manufacturing validators
3. **New `routing/` module** for routing analysis and integration
4. **New `metrics/` module** for systematic tracking
5. **Validation gates** that block pipeline progression
6. **CLI commands** for validation
7. **Experiment framework** for scientific rigor

These changes transform temper-placer from a placement optimizer into a **production-ready PCB generation system** with provable correctness guarantees.
