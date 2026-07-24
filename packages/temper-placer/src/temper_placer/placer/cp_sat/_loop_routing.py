"""PCB construction and routing integration for the place-route loop.

Extracted from ``loop.py``: ``_build_minimal_pcb`` (standalone) plus the
``_LoopRoutingMixin`` that provides ``_route_placement`` and
``_get_placement_pcb_path``.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from temper_placer.router_v6.adapter import RoutingResult

logger = logging.getLogger(__name__)


def _build_minimal_pcb(netlist, board, netclass_rules=None) -> str:
    """Build a minimal KiCad PCB file for routing."""
    width_mm = getattr(board, "width", 100)
    height_mm = getattr(board, "height", 100)

    lines = [
        "(kicad_pcb (version 20221018) (generator temper-placer)",
        "  (general (thickness 1.6))",
        "  (paper A4)",
        '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" edge))',
        "  (setup (pad_to_mask_clearance 0.1))",
    ]

    if netclass_rules is not None:
        dr = netclass_rules.design_rules
        for nc in sorted(dr.net_classes.values(), key=lambda nc: nc.name):
            lines.append(
                f'  (net_class "{nc.name}"'
                f" (clearance {nc.clearance})"
                f" (trace_width {nc.trace_width})"
                f" (via_dia {nc.via_diameter})"
                f" (via_drill {nc.via_drill}))"
            )

    # Board outline
    lines.append(f'  (gr_line (start 0 0) (end {width_mm} 0) (layer "Edge.Cuts") (width 0.1))')
    lines.append(
        f'  (gr_line (start {width_mm} 0) (end {width_mm} {height_mm}) (layer "Edge.Cuts") (width 0.1))'
    )
    lines.append(
        f'  (gr_line (start {width_mm} {height_mm}) (end 0 {height_mm}) (layer "Edge.Cuts") (width 0.1))'
    )
    lines.append(f'  (gr_line (start 0 {height_mm}) (end 0 0) (layer "Edge.Cuts") (width 0.1))')

    # Nets
    if netlist and hasattr(netlist, "nets"):
        for i, net in enumerate(netlist.nets):
            lines.append(f'  (net {i + 1} "{net.name}")')

    # Components
    if netlist and hasattr(netlist, "components"):
        for comp in netlist.components:
            footprint = getattr(comp, "footprint", "Resistor_SMD:R_0805_2012Metric")
            ref = (
                getattr(comp, "ref", comp.__class__.__name__)
                if hasattr(comp, "__class__")
                else "U1"
            )
            lines.append(f'  (footprint "{footprint}" (layer "F.Cu")')
            lines.append("    (attr smd)")
            lines.append(f'    (property "Reference" "{ref}")')
            # Include pin pads so the router has pin positions to route.
            pins = getattr(comp, "pins", [])
            if pins:
                for pin in pins:
                    pin_num = getattr(pin, "number", "1")
                    pin_x = getattr(pin, "position", (0.0, 0.0))[0]
                    pin_y = getattr(pin, "position", (0.0, 0.0))[1]
                    pin_net = getattr(pin, "net", "")
                    net_idx = 0
                    if netlist and hasattr(netlist, "nets"):
                        for ni, n in enumerate(netlist.nets):
                            if getattr(n, "name", "") == pin_net:
                                net_idx = ni + 1
                                break
                    lines.append(
                        f'    (pad "{pin_num}" smd rect'
                        f" (at {pin_x:.4f} {pin_y:.4f})"
                        f' (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask")'
                        f' (net {net_idx} "{pin_net}"))'
                    )
            lines.append("    (at 0 0)")
            lines.append("  )")

    lines.append(")")
    return "\n".join(lines)


class _LoopRoutingMixin:
    """Routing integration methods for the PlaceRouteLoop.

    Provides ``_route_placement`` for running router_v6 on a placement,
    and ``_get_placement_pcb_path`` for exporting a placement-only PCB
    for PLACEMENT-stage gate checks.
    """

    def _route_placement(
        self,
        placement,
        netlist,
        board,
        _seed: int,
        thermal_flat=None,
        thermal_weight=0.0,
    ) -> RoutingResult:
        """Route a placement through router_v6.

        U9: optional ``thermal_flat`` / ``thermal_weight`` thread
        the continuous field from the previous round into the
        A* kernel.  When ``thermal_weight=0.0`` the field-off
        path is byte-identical to today's routing.

        ``_seed`` is accepted for call-site compatibility but unused: the
        router_v6 A* engine and net-ordering algorithm are deliberately
        deterministic (same board + config -> same output, always -- see
        ``_astar_ordering.py``'s hardening against accidental
        ``PYTHONHASHSEED`` nondeterminism). ``route_pcb()`` itself no
        longer accepts a seed parameter as of 2026-07-24.
        """
        from temper_placer.router_v6.adapter import RoutingResult, route_pcb

        placements_dict = placement.to_placements_dict()
        if not placements_dict:
            return RoutingResult(completion_rate=0.0)

        netclass_rules = getattr(self, "_netclass_rules", None)
        source_pcb_path = getattr(self, "_source_pcb_path", None)
        if source_pcb_path is not None:
            # CP-SAT coordinates are origin-relative; KiCad coordinates are
            # absolute.  Preserve the authoritative board's existing
            # footprints, pad geometry, layers, zones, and net identities.
            origin_x, origin_y = getattr(board, "origin", (0.0, 0.0))
            absolute_placements = {
                ref: (x + origin_x, y + origin_y) for ref, (x, y) in placements_dict.items()
            }
            parsed = type("ParsedPCB", (), {"source_path": source_pcb_path})()
            return route_pcb(
                parsed,
                absolute_placements,
                design_rules=netclass_rules.design_rules if netclass_rules is not None else None,
                thermal_flat=thermal_flat,
                thermal_weight=thermal_weight,
            )

        # Compatibility fallback for non-KiCad unit callers. Production board
        # flows must provide ``source_pcb_path`` above.
        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_build_minimal_pcb(netlist, board, netclass_rules))
            parsed = type("ParsedPCB", (), {"source_path": temp_path})()
            return route_pcb(
                parsed,
                placements_dict,
                design_rules=netclass_rules.design_rules if netclass_rules is not None else None,
                thermal_flat=thermal_flat,
                thermal_weight=thermal_weight,
            )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)

    def _get_placement_pcb_path(
        self,
        placement,
        netlist,
        board,
        _seed: int,
    ) -> Path | None:
        """Write a placement-only PCB to a temp file and return its path.

        Returns None if the placement or netlist is missing data.
        """
        from pathlib import Path as _Path

        placements_dict = getattr(placement, "to_placements_dict", None)
        if placements_dict is None:
            return None
        placements = placements_dict()
        if not placements:
            return None

        raw_pcb = _build_minimal_pcb(
            netlist,
            board,
            getattr(self, "_netclass_rules", None),
        )
        try:
            from temper_placer.router_v6.adapter import (
                _apply_placements_to_pcb,
            )

            placed = _apply_placements_to_pcb(raw_pcb, placements)
        except ImportError:
            placed = raw_pcb

        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(placed)
        return _Path(temp_path)
