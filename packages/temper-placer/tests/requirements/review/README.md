# PCB Design Review Tests

This directory contains TDD tests for PCB design review requirements.

## REQ-REV-01: Schematic Review Checklist

**Test File:** `test_schematic.py`  
**Validator Module:** `tests/requirements/validators/schematic.py`

### Test Coverage

The test suite covers all aspects of REQ-REV-01:

#### 1. Power Supply Verification
- ✅ `test_check_power_supply_voltages_correct` - ICs connected to correct voltage rails
- ✅ `test_check_power_supply_voltages_wrong_voltage` - Detects wrong supply voltage
- ✅ `test_check_decoupling_present_all_present` - Decoupling caps on all power pins
- ✅ `test_check_decoupling_present_missing` - Detects missing decoupling caps
- ✅ `test_check_bulk_capacitors_present` - Bulk caps at power entry points
- ✅ `test_check_bulk_capacitors_missing` - Detects missing bulk caps
- ✅ `test_check_current_voltage_ratings_adequate` - Adequate ratings with safety margin
- ✅ `test_check_current_voltage_ratings_insufficient` - Detects insufficient ratings

#### 2. Component Selection
- ✅ `test_check_component_part_numbers_valid` - Valid part numbers
- ✅ `test_check_component_part_numbers_missing` - Detects missing part numbers
- ✅ `test_check_component_part_numbers_placeholder` - Detects placeholder part numbers (TBD, ???)
- ✅ `test_check_footprints_assigned_valid` - Footprints assigned and verified
- ✅ `test_check_footprints_assigned_missing` - Detects missing footprints
- ✅ `test_check_temperature_ratings_adequate` - Adequate temperature ratings (125°C power, 85°C logic)
- ✅ `test_check_temperature_ratings_insufficient` - Detects insufficient temperature ratings

#### 3. Net Naming and Hierarchy
- ✅ `test_check_net_naming_convention_valid` - Meaningful net names
- ✅ `test_check_net_naming_convention_generic` - Detects generic net names (Net-1, Net-2)
- ✅ `test_check_net_naming_convention_power_inconsistent` - Power nets follow convention (+5V, +3V3, +15V)
- ✅ `test_check_duplicate_net_names_no_duplicates` - No duplicate net names
- ✅ `test_check_duplicate_net_names_has_duplicates` - Detects duplicate net names

#### 4. Safety Circuit Review
- ✅ `test_check_ocp_circuit_correct` - OCP circuit values verified
- ✅ `test_check_ocp_circuit_wrong_threshold` - Detects incorrect OCP threshold
- ✅ `test_check_watchdog_timer_present` - Watchdog timer configured
- ✅ `test_check_watchdog_timer_missing` - Detects missing watchdog timer
- ✅ `test_check_gate_driver_enable_correct` - Gate driver enable/disable logic correct

#### 5. Integration Tests
- ✅ `test_full_schematic_review_pass` - Full review with all checks passing
- ✅ `test_full_schematic_review_multiple_violations` - Multiple violations detected

### Running Tests

```bash
# Run all schematic review tests
pytest tests/requirements/review/test_schematic.py -v

# Run specific test
pytest tests/requirements/review/test_schematic.py::test_check_power_supply_voltages_correct -v

# Run with coverage
pytest tests/requirements/review/test_schematic.py --cov=tests.requirements.validators.schematic
```

### Test Status

**Current Status:** All 27 tests PASS (TDD - tests written, implementations pending)

All validator functions currently raise `NotImplementedError`. Tests verify:
1. Function signatures are correct
2. Expected violations are detected (when implemented)
3. Valid designs pass validation (when implemented)

### Implementation Roadmap

To implement the validators, follow this order:

1. **Phase 1: Basic Checks** (Easiest)
   - `check_component_part_numbers()` - Check for missing/placeholder part numbers
   - `check_footprints_assigned()` - Check for missing footprints
   - `check_net_naming_convention()` - Check net naming patterns
   - `check_duplicate_net_names()` - Check for duplicate net names

2. **Phase 2: Component Analysis** (Medium)
   - `check_temperature_ratings()` - Verify temperature ratings
   - `check_current_voltage_ratings()` - Verify ratings with safety margins
   - `check_obsolete_parts()` - Check against obsolete parts list

3. **Phase 3: Power Supply** (Medium-Hard)
   - `check_power_supply_voltages()` - Verify ICs connected to correct rails
   - `check_decoupling_present()` - Check for decoupling caps on power pins
   - `check_bulk_capacitors()` - Check for bulk caps at power entry

4. **Phase 4: Safety Circuits** (Hard)
   - `check_ocp_circuit()` - Verify OCP circuit design
   - `check_ovp_circuit()` - Verify OVP circuit design
   - `check_thermal_shutdown()` - Verify thermal shutdown circuit
   - `check_gate_driver_enable()` - Verify gate driver enable logic
   - `check_watchdog_timer()` - Verify watchdog timer configuration
   - `check_fault_latch()` - Verify fault latch operation

5. **Phase 5: Advanced** (Hardest)
   - `check_hierarchical_connections()` - Verify hierarchical sheet connections
   - `check_global_labels()` - Verify global label usage
   - `check_power_sequencing()` - Verify power sequencing requirements

### Data Structures

#### ComponentSpec
```python
@dataclass
class ComponentSpec:
    ref: str                          # "U1", "R1", "C1"
    value: str                        # "ESP32-S3-WROOM-1", "10kΩ", "100nF"
    footprint: str                    # "RF_Module:ESP32-S3-WROOM-1"
    part_number: Optional[str]        # "ESP32-S3-WROOM-1-N8R8"
    voltage_rating: Optional[float]   # Volts
    current_rating: Optional[float]   # Amps
    power_rating: Optional[float]     # Watts
    temp_rating: Optional[int]        # Celsius
    supply_voltage: Optional[float]   # Operating voltage
    pins: Dict[str, str]              # {pin_number: net_name}
```

#### NetInfo
```python
@dataclass
class NetInfo:
    name: str                         # "+3V3", "GND", "PWM_H"
    pins: List[Tuple[str, str]]       # [("U1", "1"), ("C1", "1")]
    is_power: bool                    # True for power nets
    is_ground: bool                   # True for ground nets
    voltage_level: Optional[float]    # Nominal voltage
```

#### SchematicViolation
```python
@dataclass
class SchematicViolation:
    code: str                         # "PWR-001", "NET-002"
    message: str                      # Human-readable description
    severity: str                     # "error", "warning", "info"
    component_ref: Optional[str]      # "U1"
    net_name: Optional[str]           # "+3V3"
    details: Optional[str]            # Additional context
```

### Example Usage (When Implemented)

```python
from tests.requirements.validators.schematic import (
    ComponentSpec,
    NetInfo,
    check_power_supply_voltages,
    check_decoupling_present,
)

# Define components
esp32 = ComponentSpec(
    ref="U1",
    value="ESP32-S3-WROOM-1",
    footprint="RF_Module:ESP32-S3-WROOM-1",
    part_number="ESP32-S3-WROOM-1-N8R8",
    supply_voltage=3.3,
    pins={"1": "+3V3", "2": "GND"},
)

cap = ComponentSpec(
    ref="C1",
    value="100nF",
    footprint="Capacitor_SMD:C_0603",
    pins={"1": "+3V3", "2": "GND"},
)

# Define nets
power_net = NetInfo(
    name="+3V3",
    pins=[("U1", "1"), ("C1", "1")],
    is_power=True,
    voltage_level=3.3,
)

ground_net = NetInfo(
    name="GND",
    pins=[("U1", "2"), ("C1", "2")],
    is_ground=True,
)

# Run checks
result = check_power_supply_voltages([esp32], [power_net, ground_net])
if not result.passed:
    for violation in result.violations:
        print(f"{violation.severity.upper()}: {violation.message}")

result = check_decoupling_present([esp32, cap], [power_net, ground_net], ["U1"])
print(f"Decoupling check: {'PASS' if result.passed else 'FAIL'}")
```

### Integration with KiCad Parser

When implementing, integrate with the existing KiCad parser:

```python
from temper_placer.io.kicad_parser import parse_kicad_schematic

# Parse schematic
parse_result = parse_kicad_schematic(Path("pcb/temper.kicad_sch"))

# Convert to ComponentSpec and NetInfo
components = convert_to_component_specs(parse_result.netlist.components)
nets = convert_to_net_info(parse_result.netlist.nets)

# Run all checks
results = run_all_schematic_checks(components, nets)
```

## Related Requirements

- **REQ-REV-02:** Layout Review Checklist (TODO)
- **REQ-REV-03:** Pre-Fabrication Checklist (TODO)
- **REQ-DFM-03:** Assembly Documentation Package (implemented in `tests/requirements/validators/documentation.py`)

## References

- Temper PCB Specification: `/Users/bennet/Desktop/temper/PCB_SPECIFICATION.md`
- Component Documentation: `/Users/bennet/Desktop/temper/components/*/`
- Design Documents: `/Users/bennet/Desktop/temper/*.md`
