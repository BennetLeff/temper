"""VERBATIM pin of the net-code lookup and the Segment/Via constructions
embedded in ``temper_placer/io/kicad_exporter.py`` at origin/main
``5e528b8aa`` (the Wave-4 Phase-3 formats/IO migration base).

The sibling oracle ``_kicad_exporter_py_oracle.py`` pins the two GEOMETRY
kernels of ``kicad_exporter.py`` (snap_to_nearest_pad,
_generate_connector_segments) and is itself a frozen pin — this file pins
the additional board-item additions from ``add_segments_to_board`` /
``add_vias_to_board`` as a separate, second oracle so neither pin ever needs
editing. Each function is a STATEMENT-FOR-STATEMENT extraction with the
originating line range cited, and the random ``tstamp=str(uuid.uuid4())`` is
parameterized (the pre-migration exporter tstamps are random and are NOT
determinized — see ``kicad_write_geometry.rs``'s module docstring). DO NOT
"improve", reformat, or keep these in sync with the post-migration source:
their whole value is that they are frozen.

``test_kicad_exporter_items_rust_differential.py`` asserts the migrated Rust
implementation (``temper_io_types.kicad_write_geometry.find_net_code_py`` /
``segment_sexpr_py`` / ``via_sexpr_py``) reproduces this file's output
byte-for-byte through kiutils' own round-trip
(``Segment.from_sexpr(rust).to_sexpr()`` / ``Via.from_sexpr(rust).to_sexpr()``).
"""

from __future__ import annotations

from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position


def find_net_code(nets: list, net_name: str) -> int:
    """Verbatim extraction of ``add_segments_to_board``'s net-code lookup
    (lines 321-326; the identical loop opens ``add_vias_to_board`` at lines
    362-367):

        net_code = 0  # Default to unconnected
        for net in board.nets:
            if net.name == seg.net:
                net_code = net.number
                break
    """
    net_code = 0  # Default to unconnected
    for net in nets:
        if net.name == net_name:
            net_code = net.number
            break
    return net_code


def segment_to_sexpr(
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
    layer: str,
    net: int,
    tstamp: str,
) -> str:
    """Verbatim extraction of ``add_segments_to_board``'s segment
    construction (lines 329-336):

        kicad_seg = Segment(
            start=Position(X=seg.start[0], Y=seg.start[1]),
            end=Position(X=seg.end[0], Y=seg.end[1]),
            width=seg.width,
            layer=seg.layer,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )
    """
    kicad_seg = Segment(
        start=Position(X=start[0], Y=start[1]),
        end=Position(X=end[0], Y=end[1]),
        width=width,
        layer=layer,
        net=net,
        tstamp=tstamp,
    )
    return kicad_seg.to_sexpr()


def via_to_sexpr(
    position: tuple[float, float],
    size: float,
    drill: float,
    layers: list[str],
    net: int,
    tstamp: str,
) -> str:
    """Verbatim extraction of ``add_vias_to_board``'s via construction
    (lines 370-377):

        kicad_via = Via(
            position=Position(X=via.position[0], Y=via.position[1]),
            size=via.size,
            drill=via.drill,
            layers=via.layers,
            net=net_code,
            tstamp=str(uuid.uuid4()),
        )
    """
    kicad_via = Via(
        position=Position(X=position[0], Y=position[1]),
        size=size,
        drill=drill,
        layers=layers,
        net=net,
        tstamp=tstamp,
    )
    return kicad_via.to_sexpr()
