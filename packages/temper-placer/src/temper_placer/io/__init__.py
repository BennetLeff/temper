"""
IO layer for temper-placer.

This module handles all input/output operations:
- KiCad file parsing (.kicad_pcb, .kicad_sch) via kiutils
- Constraint configuration loading (YAML)
- Footprint library parsing for component dimensions
- Placement export back to KiCad format

The IO layer converts between external formats and internal data structures.
"""

from temper_placer._constraint_types import (
    ClearanceRule,
    ComponentGroup,
    CriticalLoop,
    PlacementConstraints,
    ThermalConstraint,
)
from temper_placer.io.config_loader import (
    create_board_from_constraints,
    load_constraints,
)

# DSN/SES universal seam
from temper_placer.io.dsn_exporter import DSNExporter
from temper_placer.io.dsn_normalizer import is_dsn_normalized, normalize_dsn, strip_control_chars
from temper_placer.io.dsn_schema import (
    compute_dsn_schema_hash,
    embed_schema_header,
    extract_schema_hash,
)
from temper_placer.io.dsn_validator import (
    DSNVersionMismatchError,
    validate_dsn,
    validate_or_warn_dsn,
)
from temper_placer.io._kicad_types import ParseResult
from temper_placer.io.kicad_parser import (
    parse_kicad_pcb,
    parse_kicad_schematic,
)
from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    WriteResult,
    export_placements,
    placements_from_json,
    placements_to_json,
    state_to_placements,
    validate_output_pcb,
    write_placements_to_pcb,
)
from temper_placer.io.placement_exporter import (
    PCBExporterFn,
    cleanup_temp_pcb,
    create_pcb_exporter,
    export_positions_to_temp_pcb,
    positions_to_placements,
    rotation_index_to_degrees,
    soft_to_discrete_rotations,
)
from temper_placer.io.reference_loader import (
    ReferenceDesign,
    compute_design_stats,
    filter_components,
    infer_quality_config,
    list_reference_designs,
    load_reference_pcb,
    netlist_to_placement_state,
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
    # DSN/SES universal seam
    "DSNExporter",
    "normalize_dsn",
    "is_dsn_normalized",
    "strip_control_chars",
    "compute_dsn_schema_hash",
    "embed_schema_header",
    "extract_schema_hash",
    "validate_dsn",
    "validate_or_warn_dsn",
    "DSNVersionMismatchError",
]
