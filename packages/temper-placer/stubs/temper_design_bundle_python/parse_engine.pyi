"""Type stubs for `temper_design_bundle_python.parse_engine`.

Compiled from `packages/temper-design-bundle/src/parse_engine.rs` -- the
Wave 4 Phase 3 candidate-3 migration of the KiCad parse engine
(`temper_placer/io/{kicad_parser,_parse_*,kicad_metadata}.py`). Keep in sync
with that file.

The pyclasses mirror the dataclasses they replace (eq/repr/hash semantics,
field types as stored -- ints stay ints, floats stay floats). The pyfunctions
take raw `.kicad_pcb` text (the Python shims read the files).
"""

from __future__ import annotations

from dataclasses import Field
from typing import Any, ClassVar

class TraceData:
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str | None

    def __init__(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        width: float,
        layer: str,
        net: str | None = ...,
    ) -> None: ...


class PadData:
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    position: tuple[float, float]
    size: tuple[float, float]
    shape: str
    drill: float | DrillDefinition
    rotation: float
    layer: str
    number: str
    net: str | None
    component_ref: str | None

    def __init__(
        self,
        position: tuple[float, float],
        size: tuple[float, float],
        shape: str,
        drill: float | DrillDefinition = ...,
        rotation: float = ...,
        layer: str = ...,
        number: str = ...,
        net: str | None = ...,
        component_ref: str | None = ...,
    ) -> None: ...


class ViaData:
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    position: tuple[float, float]
    diameter: float
    drill: float
    net: str | None
    layers: tuple[str, ...]

    def __init__(
        self,
        position: tuple[float, float],
        diameter: float,
        drill: float,
        net: str | None = ...,
        layers: tuple[str, ...] = ...,
    ) -> None: ...


class DrillDefinition:
    """kiutils' `DrillDefinition` dataclass, reproduced so pads with a
    `(drill ...)` token carry the same object shape into `Pin.drill` /
    `PadData.drill` (the oracle's through-hole pads carry these objects)."""

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    oval: bool
    diameter: float | list[Any]  # the offset-list quirk: no-diameter drills
    width: float | list[Any] | None
    offset: Position | None

    def __init__(
        self,
        oval: bool = ...,
        diameter: float | list[Any] = ...,
        width: float | list[Any] | None = ...,
        offset: Position | None = ...,
    ) -> None: ...


class Position:
    """kiutils' `Position` dataclass (X/Y uppercase), reproduced for
    `DrillDefinition.offset` repr parity."""

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    X: float
    Y: float
    angle: float | None
    unlocked: bool

    def __init__(
        self,
        x: float = ...,
        y: float = ...,
        angle: float | None = ...,
        unlocked: bool = ...,
    ) -> None: ...


class ParseResult:
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    netlist: Any  # Netlist (temper_design_bundle_python.netlist_contracts)
    board: Any  # Board | None (temper_design_bundle_python.board_contracts)
    warnings: list[str]
    traces: list[TraceData]
    vias: list[ViaData]
    pads: list[PadData]

    def __init__(
        self,
        netlist: Any,
        board: Any,
        warnings: list[str],
        traces: list[TraceData] = ...,
        vias: list[ViaData] = ...,
        pads: list[PadData] = ...,
    ) -> None: ...

    @property
    def has_warnings(self) -> bool: ...


def parse_kicad_pcb(pcb_content: str, normalize: bool = ...) -> ParseResult: ...
def extract_footprint_positions(content: str) -> dict[str, dict[str, float]]: ...
def extract_net_classes(content: str) -> dict[str, dict[str, Any]]: ...
def extract_stackup_raw(content: str) -> dict[str, Any]: ...
def extract_metadata_raw(content: str) -> dict[str, Any]: ...
def tokenize(content: str) -> Any:
    """Tokenize `content` with the kiutils-exact tokenizer and return the
    top-level s-expression (the same shape `kiutils.utils.sexpr.parse_sexp`
    returns -- its `out[0]`). Conformance-test surface for the
    'kiutils-exact' tokenizer claim."""
