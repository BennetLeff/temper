"""Pure dataclass types used by KiCad parsing — no temper_placer deps at runtime.

Extracting ``ParseResult`` and ``ViaData`` here breaks the ``router_v6 → io``
cycle: router_v6 modules can import these types from ``io._kicad_types``
without pulling in ``io.kicad_parser`` (which has lazy imports from
``router_v6.stage0_data``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.kicad_parser import PadData, TraceData


@dataclass
class ViaData:
    """Data for a PCB via."""

    position: tuple[float, float]  # (x, y) in mm, absolute
    diameter: float  # mm
    drill: float  # mm
    net: str | None = None  # net name
    layers: tuple[str, str] = ("F.Cu", "B.Cu")


@dataclass
class ParseResult:
    """
    Result of parsing KiCad files.

    Attributes:
        netlist: Parsed Netlist with components and nets.
        board: Extracted Board geometry.
        warnings: List of parsing warning messages.
        traces: List of PCB trace segments (for routed boards).
        pads: List of component pads with positions and nets.
    """

    netlist: Netlist
    board: Board | None
    warnings: list[str]
    traces: list[TraceData] = field(default_factory=list)
    vias: list[ViaData] = field(default_factory=list)
    pads: list[PadData] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        """True if any warnings were generated during parsing."""
        return len(self.warnings) > 0
