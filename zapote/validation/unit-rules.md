# Recorded checks by unit

These are the checked IDs in retained unit reports, not a fresh full-suite replay. The dated [inventory](inventory-2026-09-12.json) pins reports and current sources. See the [scope and execution limits](README.md#evidence-and-counting). A source reference establishes ownership, not independent correctness.

An empty finding-status list is represented as **declared checked; no individual finding**. It is not upgraded to a measured PASS. Multiple occurrences of a rule ID are deduplicated only in this display; the raw list is preserved in JSON.

## rtd

Entry: `run_unit` in [harness source](../../zapote/packages/zapote-harness/src/lib.rs). Retained [report](../../zapote/rtd/unit/evidence/acceptance-final/report.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `DRC.RTD.DOMAIN_BOUNDARY_CONNECTIONS` | pass | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `DRC.RTD.FERRITE_SEMANTICS` | declared checked; no individual finding | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `DRC.RTD.LOCAL_DECOUPLING` | declared checked; no individual finding | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY` | pass | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `DRC.RTD.NATIVE_GEOMETRY` | declared checked; no individual finding | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY` | declared checked; no individual finding | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `DRC.RTD.UPSTREAM_POST_FERRITE_RAILS` | declared checked; no individual finding | [zapote-drc/src/lib.rs](../../zapote/packages/zapote-drc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.ADC_PIN_NETS` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.BOARD_COMPONENT_BINDING` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.EXACT_COMPONENTS` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.FAULT_CORNERS` | indeterminate, pass | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.FAULT_OUTPUT` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.FIRMWARE_THRESHOLD_ENCODING` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.FORCE_SENSE_SEPARATION` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.FOUR_WIRE_PINOUT` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.NATIVE_CONNECTIVITY` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.RREF_IDENTITY` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.RREF_TO_REFERENCE_NETWORK` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.SHARED_REFERENCE` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.SPI_SERIES_PLACEMENT` | declared checked; no individual finding | [zapote-erc/src/lib.rs](../../zapote/packages/zapote-erc/src/lib.rs), [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.UNIT_COMPONENT_MPN` | declared checked; no individual finding | [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.UNIT_CONNECTIONS` | declared checked; no individual finding | [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.UNIT_FIRMWARE` | declared checked; no individual finding | [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.UNIT_INTERFACE` | declared checked; no individual finding | [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.UNIT_MODEL` | pass | [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |
| `ERC.RTD.UNIT_SOURCE_BINDING` | declared checked; no individual finding | [zapote-harness/src/lib.rs](../../zapote/packages/zapote-harness/src/lib.rs) |

Coverage-gap strings: 1; nonpassing findings: 1. Full messages are retained in the inventory and report.

## current-sense

Entry: `run_current_sense` in [harness source](../../zapote/packages/zapote-harness/src/current_sense.rs). Retained [report](../../zapote/current-sense/evidence/acceptance-stackup-v2/report.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `DRC.BOARD.STACKUP` | pass | [zapote-drc/src/stackup.rs](../../zapote/packages/zapote-drc/src/stackup.rs) |
| `DRC.CURRENT_SENSE.CLEARANCE` | declared checked; no individual finding | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `DRC.CURRENT_SENSE.LOCALITY` | declared checked; no individual finding | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `DRC.CURRENT_SENSE.NATIVE_GEOMETRY` | declared checked; no individual finding | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `DRC.CURRENT_SENSE.PRIMARY_SECONDARY_SEPARATION` | declared checked; no individual finding | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `DRC.CURRENT_SENSE.REQUIRED_COPPER` | declared checked; no individual finding | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `ERC.CURRENT_SENSE.APPLICABILITY` | indeterminate | [zapote-erc/src/current_sense.rs](../../zapote/packages/zapote-erc/src/current_sense.rs) |
| `ERC.CURRENT_SENSE.COMPONENT_ROLES` | declared checked; no individual finding | [zapote-erc/src/current_sense.rs](../../zapote/packages/zapote-erc/src/current_sense.rs) |
| `ERC.CURRENT_SENSE.ELECTRICAL_MODEL` | declared checked; no individual finding | [zapote-erc/src/current_sense.rs](../../zapote/packages/zapote-erc/src/current_sense.rs) |
| `ERC.CURRENT_SENSE.INPUT` | declared checked; no individual finding | [zapote-erc/src/current_sense.rs](../../zapote/packages/zapote-erc/src/current_sense.rs), [zapote-harness/src/current_sense.rs](../../zapote/packages/zapote-harness/src/current_sense.rs) |
| `ERC.CURRENT_SENSE.INTERFACES` | declared checked; no individual finding | [zapote-erc/src/current_sense.rs](../../zapote/packages/zapote-erc/src/current_sense.rs) |
| `ERC.CURRENT_SENSE.NATIVE_CONNECTIVITY` | declared checked; no individual finding | [zapote-erc/src/current_sense.rs](../../zapote/packages/zapote-erc/src/current_sense.rs) |

Coverage-gap strings: 7; nonpassing findings: 7. Full messages are retained in the inventory and report.

## voltage-sense

Entry: `run_voltage_sense` in [harness source](../../zapote/packages/zapote-harness/src/voltage_sense.rs). Retained [report](../../zapote/voltage-sense/evidence/rust-final.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `ERC.VOLTAGE.ADC_RANGE` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.CONNECTIVITY` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.OVP_APPLICABILITY` | indeterminate | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.OVP_MODEL` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.PARTS` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.QUALIFICATION` | indeterminate | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.SOURCE` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.STRESS` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `ERC.VOLTAGE.TOPOLOGY` | pass | [zapote-erc/src/voltage_sense.rs](../../zapote/packages/zapote-erc/src/voltage_sense.rs) |
| `DRC.BOARD.STACKUP` | pass | [zapote-drc/src/stackup.rs](../../zapote/packages/zapote-drc/src/stackup.rs) |
| `DRC.NATIVE.DOCUMENT_BINDING` | pass | [zapote-drc/src/native_binding.rs](../../zapote/packages/zapote-drc/src/native_binding.rs) |
| `DRC.VOLTAGE.LOCALITY` | pass | [zapote-harness/src/voltage_sense.rs](../../zapote/packages/zapote-harness/src/voltage_sense.rs) |
| `DRC.NATIVE.CLEARANCE` | pass | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |

Coverage-gap strings: 0; nonpassing findings: 6. Full messages are retained in the inventory and report.

## thermal-sense

Entry: `run_thermal_sense` in [harness source](../../zapote/packages/zapote-harness/src/thermal_sense.rs). Retained [report](../../zapote/thermal-sense/evidence/rust-final-revb.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `ERC.THERMAL.ANALOG_FAULT_CASES` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.CONNECTIVITY` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.FAULT_CASES` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.FAULT_LOGIC` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.GATE_PIN_MAP` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.NATIVE_COMPONENTS` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.OPEN_CONTRACT` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.OPEN_MARGIN` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.OPEN_SETTLING` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.PARTS` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.QUALIFICATION` | indeterminate | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.SENSOR_CONTRACT` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.SOURCE` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.STRICT_PIN_MAP` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.THRESHOLDS` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.THRESHOLD_CORNERS` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `ERC.THERMAL.TOPOLOGY` | pass | [zapote-erc/src/thermal_sense.rs](../../zapote/packages/zapote-erc/src/thermal_sense.rs) |
| `DRC.BOARD.STACKUP` | pass | [zapote-drc/src/stackup.rs](../../zapote/packages/zapote-drc/src/stackup.rs) |
| `DRC.NATIVE.DOCUMENT_BINDING` | pass | [zapote-drc/src/native_binding.rs](../../zapote/packages/zapote-drc/src/native_binding.rs) |
| `DRC.THERMAL.LOCALITY` | pass | [zapote-harness/src/thermal_sense.rs](../../zapote/packages/zapote-harness/src/thermal_sense.rs) |
| `DRC.NATIVE.CLEARANCE` | pass | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |

Coverage-gap strings: 0; nonpassing findings: 7. Full messages are retained in the inventory and report.

## interlock

Entry: `run_interlock` in [harness source](../../zapote/packages/zapote-harness/src/interlock.rs). Retained [report](../../zapote/interlock/evidence/rust-final.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `ERC.INTERLOCK.CONNECTIVITY` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.DIGITAL_MODEL` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.NATIVE_COMPONENTS` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.OPEN_MARGIN` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.PARTS` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.QUALIFICATION` | indeterminate | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.SOURCE` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.STRICT_PIN_MAP` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `ERC.INTERLOCK.TOPOLOGY` | pass | [zapote-erc/src/interlock.rs](../../zapote/packages/zapote-erc/src/interlock.rs) |
| `DRC.BOARD.STACKUP` | pass | [zapote-drc/src/stackup.rs](../../zapote/packages/zapote-drc/src/stackup.rs) |
| `DRC.NATIVE.DOCUMENT_BINDING` | pass | [zapote-drc/src/native_binding.rs](../../zapote/packages/zapote-drc/src/native_binding.rs) |
| `DRC.INTERLOCK.LOCALITY` | pass | [zapote-harness/src/interlock.rs](../../zapote/packages/zapote-harness/src/interlock.rs) |
| `DRC.NATIVE.CLEARANCE` | pass | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `ERC.INTERLOCK.INTERFACE_CONTRACT` | pass | [zapote-harness/src/interlock.rs](../../zapote/packages/zapote-harness/src/interlock.rs) |

Coverage-gap strings: 0; nonpassing findings: 5. Full messages are retained in the inventory and report.

## gate-drive

Entry: `run` in [harness source](../../zapote/packages/zapote-harness/src/gate_drive.rs). Retained [report](../../zapote/gate-drive/evidence/rust-09.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `ERC.GATE_DRIVE.PACKAGE_GRAPH` | pass | [zapote-harness/src/gate_drive.rs](../../zapote/packages/zapote-harness/src/gate_drive.rs) |
| `DRC.BOARD.STACKUP` | pass | [zapote-drc/src/stackup.rs](../../zapote/packages/zapote-drc/src/stackup.rs) |
| `DRC.NATIVE.DOCUMENT_BINDING` | pass | [zapote-drc/src/native_binding.rs](../../zapote/packages/zapote-drc/src/native_binding.rs) |
| `DRC.GATE_DRIVE.SAVED_BYTES` | pass | [zapote-harness/src/gate_drive.rs](../../zapote/packages/zapote-harness/src/gate_drive.rs) |
| `DRC.NATIVE.CLEARANCE` | pass | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `DRC.NATIVE.DOMAIN_SEPARATION` | pass | [zapote-drc/src/domain_clearance.rs](../../zapote/packages/zapote-drc/src/domain_clearance.rs) |
| `DRC.GATE_DRIVE.BYPASS_LOCALITY` | pass | [zapote-harness/src/gate_drive.rs](../../zapote/packages/zapote-harness/src/gate_drive.rs) |

Coverage-gap strings: 5; nonpassing findings: 0. Full messages are retained in the inventory and report.

## power-entry

Entry: `run` in [harness source](../../zapote/packages/zapote-harness/src/power_entry.rs). Retained [report](../../zapote/power-entry/evidence/rust-11.json): **indeterminate**.

| Recorded rule ID | Finding statuses | Current implementation sources |
|---|---|---|
| `ERC.POWER_ENTRY.SOURCE_GRAPH` | pass | [zapote-harness/src/power_entry.rs](../../zapote/packages/zapote-harness/src/power_entry.rs) |
| `DRC.BOARD.STACKUP` | pass | [zapote-drc/src/stackup.rs](../../zapote/packages/zapote-drc/src/stackup.rs) |
| `DRC.NATIVE.DOCUMENT_BINDING` | pass | [zapote-drc/src/native_binding.rs](../../zapote/packages/zapote-drc/src/native_binding.rs) |
| `DRC.POWER_ENTRY.SAVED_BYTES` | pass | [zapote-harness/src/power_entry.rs](../../zapote/packages/zapote-harness/src/power_entry.rs) |
| `DRC.POWER_ENTRY.CONNECTIVITY` | pass | [zapote-harness/src/power_entry.rs](../../zapote/packages/zapote-harness/src/power_entry.rs) |
| `DRC.NATIVE.CLEARANCE_PROFILE` | pass | [zapote-drc/src/current_sense.rs](../../zapote/packages/zapote-drc/src/current_sense.rs) |
| `ERC.POWER_ENTRY.NOMINAL_MODEL` | pass | [zapote-harness/src/power_entry.rs](../../zapote/packages/zapote-harness/src/power_entry.rs) |

Coverage-gap strings: 3; nonpassing findings: 0. Full messages are retained in the inventory and report.
