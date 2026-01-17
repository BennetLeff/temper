# ROOT CAUSE IDENTIFIED: Zone Constraint Mismatch

## Critical Finding

The Benders optimizer IS enforcing zone constraints, but they're **hardcoded and out of sync** with the design intent in `temper_constraints.yaml`.

### Constraint Mismatch

**Source 1: `temper_constraints.yaml` (Design Intent)**
```yaml
zones:
  - control_zone: Y = 0-70mm    # MCU, low-voltage
  - driver_zone:  Y = 70-110mm  # Gate drivers, sensing
  - power_zone:   Y = 110-150mm # IGBTs, HV switching
```

**Source 2: `benders_master.py:541-552` (Hardcoded in ILP)**
```python
zone_constraints={
    "Q1": [(\"y\", \"min\", 90.0), (\"y\", \"max\", 140.0)],   # Y = 90-140mm
    "Q2": [(\"y\", \"min\", 90.0), (\"y\", \"max\", 140.0)],   # Y = 90-140mm
    "D1": [(\"y\", \"min\", 50.0), (\"y\", \"max\", 90.0)],    # Y = 50-90mm
    "D2": [(\"y\", \"min\", 50.0), (\"y\", \"max\", 90.0)],    # Y = 50-90mm
    "U_MCU": [(\"y\", \"min\", 60.0), (\"y\", \"max\", 110.0)], # Y = 60-110mm
    "U_GATE": [(\"y\", \"min\", 100.0), (\"y\", \"max\", 140.0)],# Y = 100-140mm
}
```

### Discrepancies

| Component | temper_constraints.yaml | benders_master.py | Delta |
|-----------|------------------------|-------------------|-------|
| Q1/Q2 (power) | Y ≥ 110mm | Y = 90-140mm | -20mm to -10mm |
| U_GATE (driver) | Y = 70-110mm | Y = 100-140mm | +30mm to +30mm |
| U_MCU (control) | Y < 70mm | Y = 60-110mm | +40mm allowed |

### Why This Causes Islands

1. **Overlapping zones**: U_GATE allowed Y=100-140, overlaps with Q1/Q2 at Y=90-140
2. **Missing components**: Most components have NO zone constraints in benders_master.py
3. **Wrong boundaries**: Hardcoded zones don't match the 70mm and 110mm design boundaries

When Benders solves with these loose/wrong constraints:
- Components drift to local optima satisfying proximity constraints
- Ignores the intended vertical stratification
- Creates unintended gaps (28mm) between component clusters

### Solution Required

Need to either:
1. **Sync the constraints**: Update benders_master.py to match temper_constraints.yaml
2. **Auto-generate benders_input.json**: Create script to export zones from YAML
3. **Manual quick fix**: Temporarily fix zone assignments to test hypothesis

Next: Implementing manual quick fix to validate that proper zone enforcement eliminates islands.
