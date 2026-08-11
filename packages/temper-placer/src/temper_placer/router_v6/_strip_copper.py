"""Paren-balanced removal of committed copper s-expression blocks (U3, R7).

R7 requires that copper pours become *derived output*, regenerated from the
routed result after routing -- and that the zones a board file already
carries stop being treated as authoritative input. Two different call sites
need the same removal primitive:

1. ``scripts/route_board.py`` -- to hand the router a board whose committed
   zones are not present as input (measurement/CLI "clean re-route" path).
2. ``router_v6._adapter_convert._write_routes_to_content`` -- to replace a
   board's stored zones with the regenerated set rather than appending to
   them (the general production write path, exercised regardless of which
   caller invoked ``route_pcb``).

Both used to risk re-deriving this independently. This module is the single
implementation both import, so "which blocks count as committed copper" is
answered in exactly one place.

``(segment ...)`` and ``(via ...)`` elements are always single KiCad-written
lines, which is why the prior implementation in ``route_board.py`` could get
away with a single-line ``re.MULTILINE`` regex. ``(zone ...)`` elements are
not: a real zone (see ``pcb/temper.kicad_pcb``) spans dozens of lines --
``priority``, ``connect_pads``, ``min_thickness``, ``fill``, and a nested
``(polygon (pts (xy ..) (xy ..) ...))`` block with one point per line. A
line-anchored regex simply never matches a zone's opening line (it is not
the whole line), so the old function silently left every zone untouched --
it was never a zone-shaped bug fix, just an unexercised gap for zones
specifically. The strip logic removes all three block kinds uniformly by
tracking parenthesis depth from each block's opening line to the line where
that depth returns to zero, which is correct for both single-line and
arbitrarily-nested multi-line blocks.

Wave 4 (PORT): the strip kernel now lives in Rust --
``temper-io-types``'s ``strip_copper`` module (pure-Rust ``strip_blocks``,
exposed as ``temper_io_types.strip_existing_copper`` /
``strip_existing_zones``), ported verbatim from this module's pre-migration
body. This file is a pure-delegation shim re-exporting the Rust compute; the
pre-migration implementation is pinned verbatim as the differential oracle in
``tests/router_v6/test_strip_copper_rust_differential.py`` (see the crate
``VERIFICATION.md`` for the parity proof). ``strip_existing_copper`` /
``strip_existing_zones`` are the only public names, unchanged.
"""

from __future__ import annotations

import temper_io_types as _rs

__all__ = ["strip_existing_copper", "strip_existing_zones"]


def strip_existing_copper(content: str) -> tuple[str, int]:
    """Remove every committed ``(segment ...)``, ``(via ...)``, and
    ``(zone ...)`` top-level s-expression block from *content*.

    Routing an already-routed, already-poured board is not the same
    experiment as routing a bare one. This is the routing-*input* half of
    R7: a board handed to ``route_pcb`` through this function no longer
    carries its committed zones as data the router (or anything reading
    its output) could mistake for authoritative.

    Returns ``(cleaned_content, blocks_removed)`` where ``blocks_removed``
    counts segments + vias + zones together.

    Delegates to ``temper_io_types.strip_existing_copper``.
    """
    return _rs.strip_existing_copper(content)


def strip_existing_zones(content: str) -> tuple[str, int]:
    """Remove only ``(zone ...)`` blocks from *content*, leaving any
    ``(segment ...)``/``(via ...)`` entries untouched.

    This is the routing-*output* half of R7: called immediately before a
    regenerated set of pours is written, so the written board's zones are
    exactly this run's regenerated set -- never the stale carryover from
    whatever the input board happened to have -- regardless of whether the
    caller already stripped zones from the routing input.

    Returns ``(cleaned_content, zones_removed)``.

    Delegates to ``temper_io_types.strip_existing_zones``.
    """
    return _rs.strip_existing_zones(content)
