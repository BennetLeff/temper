"""
temper-placer: JAX-based PCB placement optimizer.

A standalone, modular tool for optimizing PCB component placement using
gradient-based optimization in JAX. Encodes expert PCB layout knowledge
into differentiable loss functions for the Temper induction cooker board.

Key features:
- Gumbel-Softmax for differentiable discrete rotation (0°/90°/180°/270°)
- Multi-objective loss function (wirelength, overlap, thermal, EMI, congestion)
- Curriculum learning with progressive constraint introduction
- Live browser-based visualization during optimization
- KiCad integration via kiutils for native file format support
- Validation-in-the-loop with KiCad DRC and ngspice

Usage:
    temper-placer optimize input.kicad_pcb -c constraints.yaml -o output.kicad_pcb

See TEMPER_PLACER_DESIGN.md for full specification.
"""

__version__ = "0.1.0"
__author__ = "Temper Project"

from temper_placer.core.state import PlacementState
from temper_placer.core.netlist import Component, Pin, Net, Netlist
from temper_placer.core.board import Board, Zone

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
