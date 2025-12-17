"""
IO layer for temper-placer.

This module handles all input/output operations:
- KiCad file parsing (.kicad_pcb, .kicad_sch) via kiutils
- Constraint configuration loading (YAML)
- Footprint library parsing for component dimensions
- Placement export back to KiCad format

The IO layer converts between external formats and internal data structures.
"""

from temper_placer.io.kicad_parser import (
    parse_kicad_pcb,
    parse_kicad_schematic,
    ParseResult,
)
from temper_placer.io.config_loader import (
    load_constraints,
    create_board_from_constraints,
    PlacementConstraints,
    ClearanceRule,
    CriticalLoop,
    ThermalConstraint,
    ComponentGroup,
)
from temper_placer.io.kicad_writer import (
    write_placements_to_pcb,
    state_to_placements,
    placements_to_json,
    placements_from_json,
    export_placements,
    validate_output_pcb,
    WriteResult,
    PlacementUpdate,
)
from temper_placer.io.placement_exporter import (
    soft_to_discrete_rotations,
    rotation_index_to_degrees,
    positions_to_placements,
    export_positions_to_temp_pcb,
    create_pcb_exporter,
    cleanup_temp_pcb,
    PCBExporterFn,
)
from temper_placer.io.reference_loader import (
    load_reference_pcb,
    netlist_to_placement_state,
    compute_design_stats,
    filter_components,
    infer_quality_config,
    list_reference_designs,
    ReferenceDesign,
)

__all__ = [
    # Parser
    "parse_kicad_pcb",
    "parse_kicad_schematic",
    "ParseResult",
    # Config
    "load_constraints",
    "create_board_from_constraints",
    "PlacementConstraints",
    "ClearanceRule",
    "CriticalLoop",
    "ThermalConstraint",
    "ComponentGroup",
    # Writer
    "write_placements_to_pcb",
    "state_to_placements",
    "placements_to_json",
    "placements_from_json",
    "export_placements",
    "validate_output_pcb",
    "WriteResult",
    "PlacementUpdate",
    # Placement exporter (for DRC validation)
    "soft_to_discrete_rotations",
    "rotation_index_to_degrees",
    "positions_to_placements",
    "export_positions_to_temp_pcb",
    "create_pcb_exporter",
    "cleanup_temp_pcb",
    "PCBExporterFn",
    # Reference loader (for benchmarking)
    "load_reference_pcb",
    "netlist_to_placement_state",
    "compute_design_stats",
    "filter_components",
    "infer_quality_config",
    "list_reference_designs",
    "ReferenceDesign",
]
