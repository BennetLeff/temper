"""
KiCad footprint parser - extract courtyard bounds from .kicad_mod files.

Re-exported from temper_io_types (Rust / pyo3).
"""

from temper_io_types import (
    FootprintBounds,
    FootprintParseError,
    parse_footprint_courtyard,
    parse_footprint_directory,
)

__all__ = [
    "FootprintParseError",
    "FootprintBounds",
    "parse_footprint_courtyard",
    "parse_footprint_directory",
]
