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
specifically. This module strips all three block kinds uniformly by
tracking parenthesis depth from each block's opening line to the line where
that depth returns to zero, which is correct for both single-line and
arbitrarily-nested multi-line blocks.
"""

from __future__ import annotations

import re

__all__ = ["strip_existing_copper", "strip_existing_zones"]


def _strip_blocks(content: str, keywords: tuple[str, ...]) -> tuple[str, int]:
    """Remove every top-level ``(keyword ...)`` block for each *keywords*
    entry, tracking paren depth from each block's opening line.

    A block "opens" on the first line (after leading whitespace) that
    matches ``(keyword ``. From there, every ``(``/``)`` on subsequent
    lines (including the opening line itself) adjusts a running depth
    counter; the block ends on the line where that counter returns to
    zero (or below, defensively). This is correct whether the whole block
    is on one line (``(segment ...)``, ``(via ...)``) or spans many
    (``(zone ...)``).

    Returns ``(cleaned_content, blocks_removed)``.
    """
    pattern = re.compile(r"^\s*\((" + "|".join(re.escape(k) for k in keywords) + r")\s")
    lines = content.split("\n")
    out: list[str] = []
    removed = 0
    depth = 0
    in_block = False
    for line in lines:
        if not in_block and pattern.match(line):
            in_block = True
            depth = 0
            removed += 1
        if in_block:
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                in_block = False
            continue
        out.append(line)
    return "\n".join(out), removed


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
    """
    return _strip_blocks(content, ("segment", "via", "zone"))


def strip_existing_zones(content: str) -> tuple[str, int]:
    """Remove only ``(zone ...)`` blocks from *content*, leaving any
    ``(segment ...)``/``(via ...)`` entries untouched.

    This is the routing-*output* half of R7: called immediately before a
    regenerated set of pours is written, so the written board's zones are
    exactly this run's regenerated set -- never the stale carryover from
    whatever the input board happened to have -- regardless of whether the
    caller already stripped zones from the routing input.

    Returns ``(cleaned_content, zones_removed)``.
    """
    return _strip_blocks(content, ("zone",))
