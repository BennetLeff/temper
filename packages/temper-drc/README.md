# temper-drc

Composable design rule checking (DRC + ERC) for PCB designs using the PCL (Placement Constraint Language) YAML DSL.

## Overview

temper-drc provides standalone validation for PCB component placements against electrical, safety, and EMC requirements. It enables fast feedback loops for placement optimization without requiring full KiCad DRC invocation.

**Key Features:**
- **Fast Validation** - Check placements in seconds vs. minutes (KiCad DRC)
- **Programmable Rules** - Define custom checks in Python for project-specific requirements
- **Safety Compliance** - Verify IEC 60335 HV/LV separation, creepage, and isolation
- **EMC Awareness** - Check loop areas, ground plane continuity, and noise coupling
- **Multiple Formats** - Output text, JSON, or HTML reports

## Installation

```bash
# From repository root
uv pip install -e packages/temper-drc

# Or with pip
pip install -e packages/temper-drc

# With development dependencies
uv pip install -e "packages/temper-drc[dev]"
```

## Quick Start

### CLI Usage

```bash
# List all available checks
temper-drc list-checks

# Run all checks with text output
temper-drc check placement.yaml -c constraints.yaml

# Run specific check categories
temper-drc check placement.yaml -c constraints.yaml --category safety emc

# Generate JSON report
temper-drc check placement.yaml -c constraints.yaml --format json -o report.json

# Generate HTML report
temper-drc check placement.yaml -c constraints.yaml --format html -o report.html

# Generate metrics summary
temper-drc summary placement.yaml -c constraints.yaml

# Create template files
temper-drc init-placement template_placement.yaml --board-width 100 --board-height 80
temper-drc init-constraints template_constraints.yaml --hv-clearance 10.0

# Verbose output for debugging
temper-drc check placement.yaml -c constraints.yaml --verbose
```

### Python API Usage

```python
from temper_drc.core.runner import CheckRunner
from temper_drc.checks.drc.clearance import ClearanceCheck
from temper_drc.checks.safety.hv_lv_separation import HVLVSeparationCheck
from temper_drc.input.placement import Placement
from temper_drc.input.constraints import ConstraintSet

# Load inputs
placement = Placement.from_yaml("placement.yaml")
constraints = ConstraintSet.from_yaml("constraints.yaml")

# Create runner and add checks
runner = CheckRunner()
runner.add_check(ClearanceCheck())
runner.add_check(HVLVSeparationCheck())

# Run checks
result = runner.run(placement, constraints)

# Check results
print(f"Passed: {result.passed}")
print(f"Total issues: {len(result.all_issues)}")
print(f"Execution time: {result.elapsed_ms:.1f}ms")

# Iterate through issues
for issue in result.all_issues:
    print(f"{issue.severity.name}: {issue.message}")
    print(f"  Location: ({issue.location.x:.2f}, {issue.location.y:.2f})")
    print(f"  Affected: {', '.join(issue.affected_items)}")
```

### Creating Custom Checks

```python
from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity, Location
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement

class MyCustomCheck(Check):
    """Custom check for project-specific requirements."""
    
    @property
    def name(self) -> str:
        return "my_custom_check"
    
    @property
    def category(self) -> str:
        return "drc"  # or "erc", "safety", "emc"
    
    @property
    def description(self) -> str:
        return "Verify custom project-specific rule."
    
    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        
        # Iterate through all components
        for ref, component in placement.components.items():
            # Check your custom rule
            if component.x < 10.0:  # Example: components must be >10mm from origin
                issues.append(Issue(
                    severity=Severity.WARNING,
                    code=f"{self.code_prefix}001",
                    message=f"Component {ref} too close to board edge",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref],
                    location=Location(x=component.x, y=component.y, layer=component.layer),
                    details={"distance_mm": component.x}
                ))
        
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )

# Use the custom check
runner = CheckRunner()
runner.add_check(MyCustomCheck())
result = runner.run(placement, constraints)
```

## Check Categories

temper-drc organizes checks into four categories:

### DRC (Design Rule Checks)
- **drc_clearance** - Component-to-component clearance verification
- **drc_component_overlap** - Detect overlapping component bodies
- **drc_courtyard** - Courtyard clearance violations
- **drc_zone_containment** - Verify components are within their designated zones

### ERC (Electrical Rule Checks)
- **erc_net_connectivity** - Net connectivity verification
- **erc_power_domain** - Power domain isolation checks
- **erc_floating_pins** - Detect unconnected pins

### Safety (IEC 60335 Compliance)
- **safety_hv_lv_separation** - High-voltage to low-voltage separation (IEC 60335)
- **safety_creepage** - Creepage distance verification
- **safety_isolation** - Isolation barrier integrity

### EMC (Electromagnetic Compatibility)
- **emc_loop_area** - Critical loop area analysis
- **emc_noise_coupling** - Noise-sensitive component isolation
- **emc_ground_plane** - Ground plane continuity verification

## File Formats

### Placement YAML Format

```yaml
board_width: 100.0  # mm
board_height: 80.0  # mm

components:
  - ref: "U1"
    footprint: "SOIC-8"
    x: 50.0          # mm
    y: 40.0          # mm
    rotation: 0.0    # degrees
    layer: "F.Cu"
    width: 5.0       # mm
    height: 4.0      # mm
    net_class: "Signal"
    voltage_domain: "3V3"

  - ref: "C1"
    footprint: "C_0805"
    x: 45.0
    y: 40.0
    rotation: 90.0
    layer: "F.Cu"
    width: 2.0
    height: 1.25
    net_class: "Power"
    voltage_domain: "3V3"

nets:
  VCC: ["U1", "C1"]
  GND: ["U1", "C1"]

zones:
  - name: "Power"
    bounds: [0, 0, 40, 80]
  - name: "Digital"
    bounds: [40, 0, 100, 80]

net_classes:
  VCC: "Power"
  GND: "Power"

voltage_domains:
  VCC: "3V3"
  GND: "GND"
```

### Constraints YAML Format

```yaml
# Clearance rules by net class pairs
clearances:
  Signal-Signal: 0.2   # mm
  Signal-Power: 0.3    # mm
  Power-Power: 0.5     # mm
  HV-HV: 2.0           # mm
  HV-Signal: 10.0      # mm

# Safety compliance (IEC 60335)
hv_clearance_mm: 10.0    # HV/LV separation
creepage_mm: 8.0         # Creepage distance
isolation_mm: 6.0        # Isolation barrier

# Design rules
courtyard_clearance_mm: 0.25

# EMC constraints
max_loop_area_mm2: 100.0            # Critical loop area limit
noise_sensitive_clearance_mm: 5.0   # Isolation from noisy components
```

## Severity Levels

Issues are assigned severity levels that affect scoring and reporting:

| Level | Weight | Description | Use Case |
|-------|--------|-------------|----------|
| INFO | 0.0 | Informational only | Design suggestions, metrics |
| WARNING | 1.0 | Minor issue | Non-critical violations, optimizations |
| ERROR | 10.0 | Must be fixed | Rule violations, design errors |
| CRITICAL | 100.0 | Safety-critical | IEC 60335 violations, dangerous conditions |

## Integration with temper-placer

temper-drc integrates with the temper-placer optimization pipeline for validation-in-the-loop:

```python
from temper_placer.optimizer import train
from temper_drc.core.runner import CheckRunner
from temper_drc.checks.safety.hv_lv_separation import HVLVSeparationCheck

# Create DRC runner for validation
drc_runner = CheckRunner()
drc_runner.add_check(HVLVSeparationCheck())

# Run placement optimization with validation
def validate_callback(placement_state):
    """Called during optimization to validate placements."""
    result = drc_runner.run(placement_state.to_placement(), constraints)
    return result.passed

# Integrate with optimizer
final_state = train(
    initial_state,
    constraints,
    validation_fn=validate_callback,
    epochs=5000
)
```

## CLI Commands Reference

### check
Run DRC/ERC checks on a placement file.

```bash
temper-drc check PLACEMENT_FILE -c CONSTRAINTS_FILE [OPTIONS]

Options:
  --category TEXT        Run specific categories (drc, erc, safety, emc)
  --format TEXT          Output format: text, json, html (default: text)
  -o, --output PATH      Output file (stdout if not specified)
  --fail-on-error        Exit with non-zero code on failures (default: true)
  --verbose              Show detailed progress
```

### summary
Generate metrics summary for a placement.

```bash
temper-drc summary PLACEMENT_FILE -c CONSTRAINTS_FILE [OPTIONS]

Options:
  --category TEXT        Summarize specific categories
```

### list-checks
List all available checks.

```bash
temper-drc list-checks
```

### init-placement
Create a template placement YAML file.

```bash
temper-drc init-placement OUTPUT_FILE [OPTIONS]

Options:
  --board-width FLOAT    Board width in mm (default: 100.0)
  --board-height FLOAT   Board height in mm (default: 100.0)
```

### init-constraints
Create a template constraints YAML file.

```bash
temper-drc init-constraints OUTPUT_FILE [OPTIONS]

Options:
  --hv-clearance FLOAT   HV/LV clearance in mm (default: 10.0)
```

## Development

### Running Tests

```bash
# Run all tests
pytest packages/temper-drc/tests

# Run with coverage
pytest packages/temper-drc/tests --cov=temper_drc --cov-report=html

# Run specific test categories
pytest packages/temper-drc/tests/checks/drc/ -v
pytest packages/temper-drc/tests/checks/safety/ -v

# Run with markers
pytest packages/temper-drc/tests -m integration
```

### Type Checking

```bash
mypy packages/temper-drc/src
```

### Linting

```bash
ruff check packages/temper-drc/src packages/temper-drc/tests
ruff format packages/temper-drc/src packages/temper-drc/tests
```

### Project Structure

```
packages/temper-drc/
├── src/temper_drc/
│   ├── checks/              # Check implementations
│   │   ├── drc/            # Design rule checks
│   │   ├── erc/            # Electrical rule checks
│   │   ├── safety/         # IEC 60335 safety checks
│   │   └── emc/            # EMC compliance checks
│   ├── core/               # Core abstractions
│   │   ├── check.py        # Check base class
│   │   ├── result.py       # Result types
│   │   ├── runner.py       # Check execution engine
│   │   ├── severity.py     # Severity levels
│   │   └── metrics.py      # Metrics collection
│   ├── input/              # Input parsers
│   │   ├── placement.py    # Placement data model
│   │   └── constraints.py  # Constraint data model
│   ├── report/             # Output formatters
│   │   ├── formatter.py    # Text/JSON/HTML formatters
│   │   └── summary.py      # Summary generator
│   └── cli.py              # Command-line interface
└── tests/                  # Test suite
    ├── checks/             # Check tests
    ├── core/               # Core tests
    └── integration/        # Integration tests
```

## Performance

Typical execution times on a modern laptop:

| Check Category | Components | Execution Time |
|---------------|-----------|----------------|
| Full suite    | 50        | ~50ms          |
| Full suite    | 200       | ~500ms         |
| Full suite    | 500       | ~2s            |

Performance tips:
- Use `--category` to run only needed checks
- Skip checks with `is_applicable()` override
- Use `--no-fail-on-error` for non-blocking validation

## Troubleshooting

### "No module named 'temper_drc'"
Ensure the package is installed: `uv pip install -e packages/temper-drc`

### "YAML file not found"
Use absolute paths or check your working directory.

### "Check failed with no issues"
Verify your constraints YAML has appropriate rules defined. Use `--verbose` to see which checks are running.

### "Clearance violations on same net"
Review your net class definitions in the placement YAML. Components on the same net class may still violate clearances.

## Contributing

When adding new checks:

1. Create check class in appropriate category directory (`drc/`, `erc/`, `safety/`, `emc/`)
2. Inherit from `Check` base class
3. Implement `name`, `category`, `description`, and `run()` methods
4. Add comprehensive unit tests in `tests/checks/<category>/`
5. Register the check in `cli.py` for CLI usage
6. Update this README with the new check documentation

## License

MIT License - See LICENSE file for details.

## Related Documentation

- **PCB_SPECIFICATION.md** - PCB design constraints and requirements
- **GROUNDING_EMI_STRATEGY.md** - EMC design guidelines
- **SAFETY_INTERLOCK_DESIGN.md** - Safety system specification
- **temper-placer** - JAX-based PCB placement optimizer that uses temper-drc
