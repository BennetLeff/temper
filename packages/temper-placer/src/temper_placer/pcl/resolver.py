"""
Reference resolver for PCL constraint component references.

Resolves component ref strings (e.g., 'Q1') and zone names (e.g., 'HV_ZONE')
to component indices in a netlist. Pure-Python; no JAX dependency.

This module exists independently of loss_bridge.py so the SAT bridge and
PCL parser can resolve references after the JAX loss bridge is deleted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


def _resolve_to_indices(
    name: str,
    netlist: Netlist,
    board: Board | None = None,
) -> list[int]:
    """Resolve a name (component ref or zone name) to component indices.

    Args:
        name: Component reference (e.g., 'Q1') or zone name (e.g., 'HV_ZONE').
        netlist: Netlist for component lookup.
        board: Optional board for zone component lookup.

    Returns:
        List of component indices.

    Raises:
        ValueError: If the name cannot be resolved to any component.
    """
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    if name in ref_to_idx:
        return [ref_to_idx[name]]

    if board and board.zones:
        for zone in board.zones:
            if zone.name == name:
                indices = []
                for comp_ref in zone.components:
                    if comp_ref in ref_to_idx:
                        indices.append(ref_to_idx[comp_ref])
                return indices

    if "_ZONE" in name:
        return []

    raise ValueError(
        f"Could not resolve '{name}' to any components in netlist or board zones"
    )
