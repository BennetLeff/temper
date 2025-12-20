# temper-drc

Composable design rule checking (ERC + DRC) for the Temper project.

## Overview

temper-drc provides standalone design rule checking using the PCL (Placement Constraint Language) YAML DSL. It supports:

- **ERC** (Electrical Rule Checks) - Net connectivity, power domains, floating pins
- **DRC** (Design Rule Checks) - Clearance, courtyard overlap, zone containment
- **Safety** (IEC 60335) - Creepage distances, isolation barriers, HV-LV separation
- **EMC** - Loop area limits, noise coupling, decoupling placement

## Installation

```bash
uv pip install -e packages/temper-drc
```

## Usage

```python
from temper_drc.core.runner import CheckRunner
from temper_drc.core.check import Check
from temper_drc.input.placement import Placement

# Create runner and add checks
runner = CheckRunner()
runner.add_check(my_check)

# Run checks
result = runner.run(placement, constraints)
print(f"Passed: {result.passed}")
print(f"Issues: {result.all_issues}")
```

## CLI

```bash
# Run all checks
temper-drc check placement.json -c constraints.yaml

# Run specific categories
temper-drc check placement.json --category safety emc

# Output formats
temper-drc check placement.json -o report.json --format json
```

## Check Categories

| Category | Code Prefix | Description |
|----------|-------------|-------------|
| ERC | `ERC_*` | Electrical rule checks |
| DRC | `DRC_*` | Design rule checks |
| Safety | `SAF_*` | IEC 60335 safety checks |
| EMC | `EMC_*` | EMC compliance checks |

## Severity Levels

| Level | Weight | Description |
|-------|--------|-------------|
| INFO | 0.0 | Informational only |
| WARNING | 1.0 | Minor issue |
| ERROR | 10.0 | Must be fixed |
| CRITICAL | 100.0 | Safety-critical failure |

## Development

```bash
# Run tests
pytest packages/temper-drc/tests

# Type checking
mypy packages/temper-drc/src

# Linting
ruff check packages/temper-drc/src
```
