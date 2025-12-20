# Loop Templates for Induction Cooker

This directory contains pre-built loop templates for common induction cooker circuits.
These templates define current loops that are critical for EMI performance and switching behavior.

## Templates

| File | Loop Type | Priority | Description |
|------|-----------|----------|-------------|
| `commutation.yaml` | COMMUTATION | CRITICAL | Main power switching loop |
| `gate_drive_high.yaml` | GATE_DRIVE_HIGH | CRITICAL | High-side IGBT gate drive |
| `gate_drive_low.yaml` | GATE_DRIVE_LOW | CRITICAL | Low-side IGBT gate drive |
| `bootstrap.yaml` | BOOTSTRAP | HIGH | Bootstrap capacitor charging |
| `buck_15v.yaml` | BUCK_SWITCH | HIGH | 15V auxiliary buck converter |

## Usage

```python
from temper_placer.io.loop_loader import load_loop_template, load_loop_collection

# Load a single template
commutation = load_loop_template("configs/templates/loops/commutation.yaml")

# Load all templates in a directory
collection = load_loop_collection("configs/templates/loops/")
```

## Customization

These templates use generic component references. Map them to your actual design:

```yaml
# In your project constraints file
loop_mappings:
  commutation:
    Q1: Q_IGBT_HIGH
    Q2: Q_IGBT_LOW
    C_BUS1: C_DC_1
    C_BUS2: C_DC_2
```

## Physics Parameters

Each template includes physics metadata that affects optimization:

- **di_dt**: Current slew rate (A/s) - higher values need smaller loops
- **dv_dt**: Voltage slew rate (V/s) - affects EMI coupling
- **frequency_hz**: Switching frequency - affects EMI spectrum
- **peak_current_a**: Peak loop current - affects trace width requirements
- **max_area_mm2**: Maximum allowed loop area constraint

## Loop Priorities

- **CRITICAL**: Must be minimized. Violations block optimization completion.
- **HIGH**: Should be minimized. Violations generate warnings.
- **MEDIUM**: Nice to minimize. Best-effort optimization.
- **LOW**: Lowest priority. Optimized last.
