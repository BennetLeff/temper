"""Temper PCB placement and validation toolkit.

A modular tool for generating and validating PCB component placements using
engineering heuristics, CP-SAT, and Rust-backed geometry kernels.

Key features:
- deterministic topological and structural placement heuristics
- CP-SAT placement with Rust-backed geometry and DRC kernels
- KiCad integration and validation-in-the-loop with KiCad DRC and ngspice

Usage:
    temper-placer optimize input.kicad_pcb -c constraints.yaml -o output.kicad_pcb

See TEMPER_PLACER_DESIGN.md for full specification.
"""

from temper_placer._version import __version__

__author__ = "Temper Project"

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState

__all__ = [
    "__version__",
    "PlacementState",
    "Component",
    "Pin",
    "Net",
    "Netlist",
    "Board",
    "Zone",
]
