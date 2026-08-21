"""VERBATIM pin of the zone-construction kernel embedded in
``temper_placer/io/_write_zones.py`` at origin/main ``5e528b8aa`` (the
Wave-4 Phase-3 formats/IO migration base).

This file is the pre-migration oracle for the ``_write_zones.py`` zone
migration. The zone construction is a STATEMENT-FOR-STATEMENT extraction of
``write_zones_to_pcb``'s loop body (lines 96-106 of the shipped module) with
one change: the random ``tstamp=str(uuid.uuid4())`` is parameterized, because
the pre-migration tstamp is deliberately NOT determinized (a behavior change
no bit-identical differential could pin — see
``packages/temper-io-types/src/kicad_write_geometry.rs``'s module docstring).
The extraction is otherwise verbatim; DO NOT "improve", reformat, or keep
these in sync with the post-migration source: the value is that they are
frozen.

``test_write_zones_rust_differential.py`` asserts the migrated Rust
implementation (``temper_io_types.kicad_write_geometry.zone_sexpr_py``)
reproduces this file's ``.to_sexpr()`` output byte-for-byte through kiutils'
own round-trip (``Zone.from_sexpr(rust).to_sexpr()``).
"""

from __future__ import annotations

from kiutils.items.common import Position
from kiutils.items.zones import Zone, ZonePolygon


def zone_to_sexpr(
    net_name: str,
    net_index: int,
    layer: str,
    tstamp: str,
    pts: list[tuple[float, float]],
) -> str:
    """Verbatim extraction of ``write_zones_to_pcb``'s zone construction
    (lines 96-106), with ``tstamp=str(uuid.uuid4())`` replaced by the
    ``tstamp`` parameter:

        zone = Zone(
            netName=net_name,
            net=net_index,
            layers=[layer],
            tstamp=str(uuid.uuid4()),
            polygons=[ZonePolygon(coordinates=[Position(p[0], p[1]) for p in pts])],
            # Default fill settings
            minThickness=0.254,
        )
    """
    zone = Zone(
        netName=net_name,
        net=net_index,
        layers=[layer],
        tstamp=tstamp,
        polygons=[ZonePolygon(coordinates=[Position(p[0], p[1]) for p in pts])],
        # Default fill settings
        minThickness=0.254,
    )
    return zone.to_sexpr()
