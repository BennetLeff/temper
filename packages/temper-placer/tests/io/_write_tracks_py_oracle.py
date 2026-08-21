"""VERBATIM pin of the Segment/Via constructions embedded in
``temper_placer/io/_write_tracks.py`` at origin/main ``5e528b8aa`` (the
Wave-4 Phase-3 formats/IO migration base).

This file is the pre-migration oracle for the ``_write_tracks.py`` track/via
construction migration. Each function is a STATEMENT-FOR-STATEMENT extraction
of the construction embedded in ``write_routes_to_pcb``'s loops, with the
originating line range cited. DO NOT "improve", reformat, or keep these in
sync with the post-migration source: their whole value is that they are
frozen.

``test_write_tracks_rust_differential.py`` asserts the migrated Rust
implementation (``temper_io_types.kicad_write_geometry.segment_sexpr_py`` /
``via_sexpr_py``) reproduces this file's output byte-for-byte through
kiutils' own round-trip (``Segment.from_sexpr(rust).to_sexpr()`` /
``Via.from_sexpr(rust).to_sexpr()``).
"""

from __future__ import annotations

from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position


def segment_to_sexpr(
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
    layer: str,
    net: int,
    tstamp: str,
) -> str:
    """Verbatim extraction of ``write_routes_to_pcb``'s segment construction
    (lines 341-350):

        segment = Segment(
            start=Position(X=route.start[0], Y=route.start[1]),
            end=Position(X=route.end[0], Y=route.end[1]),
            width=route.width,
            layer=route.layer,
            net=net_index,
            tstamp=_stable_tstamp("segment", route_key),
        )
    """
    segment = Segment(
        start=Position(X=start[0], Y=start[1]),
        end=Position(X=end[0], Y=end[1]),
        width=width,
        layer=layer,
        net=net,
        tstamp=tstamp,
    )
    return segment.to_sexpr()


def via_to_sexpr(
    position: tuple[float, float],
    size: float,
    drill: float,
    layers: list[str],
    net: int,
    tstamp: str,
) -> str:
    """Verbatim extraction of ``write_routes_to_pcb``'s via construction
    (lines 367-374):

        kicad_via = Via(
            position=Position(X=via.position[0], Y=via.position[1]),
            size=via.width,
            drill=via.drill,
            layers=list(via.layers),
            net=net_index,
            tstamp=_stable_tstamp("via", via_key),
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
