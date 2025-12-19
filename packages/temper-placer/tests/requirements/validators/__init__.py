"""
Validators for PCB design requirements.

This module provides validation functions for:
- REQ-DFM-03: Assembly Documentation Package
- REQ-REV-01: Schematic Review Checklist
"""

from .documentation import (
    BOMEntry,
    CPLEntry,
    DocumentationValidationResult,
    GerberLayer,
    check_dnp_consistency,
    validate_bom_completeness,
    validate_cpl_coordinates,
    validate_gerber_layers,
)
from .schematic import (
    ComponentSpec,
    NetInfo,
    SchematicReviewResult,
    SchematicViolation,
    check_bulk_capacitors,
    check_component_part_numbers,
    check_current_voltage_ratings,
    check_decoupling_present,
    check_duplicate_net_names,
    check_fault_latch,
    check_footprints_assigned,
    check_gate_driver_enable,
    check_global_labels,
    check_hierarchical_connections,
    check_net_naming_convention,
    check_obsolete_parts,
    check_ocp_circuit,
    check_ovp_circuit,
    check_power_sequencing,
    check_power_supply_voltages,
    check_safety_circuit_values,
    check_temperature_ratings,
    check_thermal_shutdown,
    check_watchdog_timer,
)

__all__ = [
    # Documentation validators
    "validate_bom_completeness",
    "validate_cpl_coordinates",
    "validate_gerber_layers",
    "check_dnp_consistency",
    "BOMEntry",
    "CPLEntry",
    "GerberLayer",
    "DocumentationValidationResult",
    # Schematic validators
    "ComponentSpec",
    "NetInfo",
    "SchematicViolation",
    "SchematicReviewResult",
    "check_power_supply_voltages",
    "check_decoupling_present",
    "check_bulk_capacitors",
    "check_power_sequencing",
    "check_current_voltage_ratings",
    "check_component_part_numbers",
    "check_footprints_assigned",
    "check_temperature_ratings",
    "check_obsolete_parts",
    "check_net_naming_convention",
    "check_duplicate_net_names",
    "check_hierarchical_connections",
    "check_global_labels",
    "check_safety_circuit_values",
    "check_ocp_circuit",
    "check_ovp_circuit",
    "check_thermal_shutdown",
    "check_gate_driver_enable",
    "check_watchdog_timer",
    "check_fault_latch",
]
