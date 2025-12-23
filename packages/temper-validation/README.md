# temper-validation

Ground truth comparison package for PCB placement validation.

## Overview

`temper-validation` provides tools to compare optimized PCB placements against hand-placed reference layouts using quality metrics. It helps answer the question: **Is this placement actually GOOD?**

## Features

- **Wirelength Comparison**: Manhattan and Steiner tree wirelength analysis
- **DRC Compliance**: KiCad DRC integration with violation scoring
- **Routing Feasibility**: Routing completion rate estimation
- **Aggregate Quality Score**: Weighted combination of all metrics (0-100 scale)
- **Report Generation**: Markdown and HTML validation reports

## Installation

```bash
# Install from source
cd packages/temper-validation
pip install -e .

# Requires temper-placer for PCB loading
pip install -e ../temper-placer
```

## CLI Usage

### Compare Two Placements

Compare an optimized placement against a reference and generate a report:

```bash
temper-validate compare optimized.kicad_pcb reference.kicad_pcb \\
  --output report.html \\
  --format html
```

### Score a Placement

Get aggregate quality score for a placement:

```bash
temper-validate score optimized.kicad_pcb \\
  --reference reference.kicad_pcb
```

**Output:**
```
=== Placement Validation Score ===
Aggregate Score: 85.3/100.0
Verdict: PASS

Wirelength:
  Optimized: 245.67 mm
  Reference: 250.00 mm
  Ratio: 0.983
  Verdict: PASS

DRC Compliance:
  Score: 90.0/100.0
  Critical Violations: 0
  Warning Violations: 2
  Verdict: PASS

Routing Feasibility:
  Completion Rate: 100.0%
  Verdict: PASS
```

### Run DRC Check

Run KiCad DRC and get compliance score:

```bash
temper-validate drc design.kicad_pcb \\
  --kicad-path /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
```

## Metrics

### Wirelength (30% weight)

Compares total wirelength using Manhattan distance:
- **PASS**: Optimized wirelength within 10% of reference (ratio < 1.1)
- **FAIL**: Optimized wirelength >10% worse than reference

### DRC Compliance (40% weight)

Scores DRC violations from KiCad:
- Critical violations: -20 points each
- Warning violations: -5 points each
- **PASS**: Score >= 80/100
- **FAIL**: Score < 80/100

### Routing Feasibility (30% weight)

Estimates routing completion rate:
- **PASS**: >= 95% of nets routable
- **FAIL**: < 95% of nets routable

### Aggregate Score

Weighted average of all metrics:
- **PASS**: Total score >= 80/100
- **FAIL**: Total score < 80/100

## Python API

```python
from temper_validation.comparison.wirelength import compare_wirelength
from temper_validation.comparison.drc_compliance import run_kicad_drc, evaluate_drc_compliance
from temper_validation.metrics.quality_score import calculate_aggregate_score
from temper_placer.io.reference_loader import load_reference_pcb

# Load PCBs
optimized = load_reference_pcb("optimized.kicad_pcb")
reference = load_reference_pcb("reference.kicad_pcb")

# Run comparisons
wirelength_result = compare_wirelength(
    optimized.state,
    reference.state,
    optimized.netlist.nets
)

drc_raw = run_kicad_drc("optimized.kicad_pcb", kicad_path="kicad-cli")
drc_result = evaluate_drc_compliance(drc_raw.violations)

# Calculate aggregate score
aggregate = calculate_aggregate_score(
    wirelength_result,
    drc_result,
    routing_result
)

print(f"Score: {aggregate.total_score:.1f}/100.0 - {aggregate.verdict}")
```

## Reference Layouts

The package includes 23 reference PCB layouts in `data/reference_layouts/`:
- Simple (10-50 components)
- Medium (50-100 components)
- Complex (100-200 components)
- Very Complex (200+ components)

These are sourced from KiCad official examples, SparkFun, Adafruit, and popular open-source projects.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run specific test module
pytest tests/comparison/test_wirelength.py -v
```

## Architecture

```
temper-validation/
├── src/temper_validation/
│   ├── comparison/          # Comparison modules
│   │   ├── wirelength.py
│   │   ├── drc_compliance.py
│   │   └── routing_feasibility.py
│   ├── metrics/             # Scoring modules
│   │   └── quality_score.py
│   ├── reporting/           # Report generation
│   │   └── report.py
│   └── cli.py              # CLI interface
├── tests/                   # Test suite
└── data/reference_layouts/  # Reference PCBs
```

## License

Part of the Temper project.
