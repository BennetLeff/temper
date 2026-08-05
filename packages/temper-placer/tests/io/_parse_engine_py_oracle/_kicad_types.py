# VERBATIM pre-migration oracle: _kicad_types.py (Wave 4 Phase 3 candidate 3, parse engine).
# Copied from packages/temper-placer/src/temper_placer/io/_kicad_types.py at commit 79ab9bd0e.
# Only edits vs the source: intra-oracle imports rewritten (temper_placer.io.X -> .X)
# so the oracle package is self-contained. Extraction bodies, dataclasses and
# kiutils usage are byte-identical to the pre-migration source. This is the pinned
# Python arm of the Rust parse-engine differential (R1a).

"""Pure dataclass types used by KiCad parsing — no temper_placer deps at runtime.

Extracting ``ParseResult``, ``ViaData``, ``TraceData``, and ``PadData`` here
breaks the ``router_v6 → io`` cycle: router_v6 modules can import these types
from ``io._kicad_types`` without pulling in ``io.kicad_parser`` (which has
lazy imports from ``router_v6.stage0_data``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


@dataclass
class TraceData:
    """Data for a PCB trace segment."""

    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str | None = None


@dataclass
class PadData:
    """Data for a component pad."""

    position: tuple[float, float]
    size: tuple[float, float]
    shape: str
    drill: float = 0.0
    rotation: float = 0.0
    layer: str = "F.Cu"
    number: str = ""
    net: str | None = None
    component_ref: str | None = None


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
