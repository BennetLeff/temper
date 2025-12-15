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

__all__ = [
    "parse_kicad_pcb",
    "parse_kicad_schematic",
    "ParseResult",
    "load_constraints",
    "create_board_from_constraints",
    "PlacementConstraints",
    "ClearanceRule",
    "CriticalLoop",
    "ThermalConstraint",
    "ComponentGroup",
]
