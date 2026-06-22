"""Benders placement wrapper with strategy pattern.

Provides `benders_placement(parsed, seed, *, strategy)` that delegates to
deterministic template placement. Strategy slot reserved for future Benders
decomposition algorithm.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist
from temper_placer.placer.deterministic import place_power_stage_template
from temper_placer.placer.template import HalfBridgeTemplate

logger = logging.getLogger(__name__)


@dataclass
class BendersPlacementResult:
    """Result from benders_placement call.

    Attributes:
        placements: Dict mapping component ref -> (x, y) position in mm.
        iterations: Number of Benders iterations (1 for template strategy).
        cuts: Number of feasibility cuts (0 for template strategy).
    """

    placements: dict[str, tuple[float, float]] = field(default_factory=dict)
    iterations: int = 0
    cuts: int = 0


def benders_placement(
    parsed: Any,
    seed: int,
    *,
    strategy: str = "template",
) -> BendersPlacementResult:
    """Run component placement using the selected strategy.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6.
        seed: Random seed for placement reproducibility.
        strategy: Placement strategy name. Currently supports "template" (default).
            Unknown strategy names log a warning and return empty placements.

    Returns:
        BendersPlacementResult with placements dict and iteration counts.

    Raises:
        ValueError: If parsed data is missing required netlist or board data.
    """
    if strategy == "template":
        return _template_strategy(parsed, seed)

    logger.warning(
        "Unknown placement strategy '%s', returning empty placements.", strategy
    )
    return BendersPlacementResult()


def _template_strategy(
    parsed: Any,
    seed: int,  # noqa: ARG001
) -> BendersPlacementResult:
    """Run deterministic template-based placement using HalfBridgeTemplate.

    If the board lacks a 'power_zone', a fallback zone covering the full
    board area is injected so placement can proceed.
    """
    netlist = _extract_netlist(parsed)
    board = _extract_board(parsed)

    if netlist is None or board is None:
        raise ValueError("ParsedPCB must contain valid netlist and board data")

    board = _ensure_power_zone(board)

    template = HalfBridgeTemplate.create_vertical()
    result = place_power_stage_template(netlist, board, template)

    placements: dict[str, tuple[float, float]] = {}
    for i, ref in enumerate(result.placed_refs):
        placements[ref] = (
            float(result.positions[i][0]),
            float(result.positions[i][1]),
        )

    return BendersPlacementResult(placements=placements, iterations=1, cuts=0)


def _ensure_power_zone(board: Board) -> Board:
    """Ensure the board has a 'power_zone'. Creates one if missing."""
    for zone in board.zones:
        if zone.name == "power_zone":
            return board
    fallback = Zone(
        "power_zone",
        (0, 0, board.width, board.height),
    )
    board.zones.append(fallback)
    return board


def _extract_netlist(parsed: Any) -> Netlist | None:
    """Extract a Netlist from ParsedPCB components and nets."""
    components = getattr(parsed, "components", None)
    nets = getattr(parsed, "nets", None)
    if components is None or nets is None:
        return None
    return Netlist(components=list(components), nets=list(nets))


def _extract_board(parsed: Any) -> Board | None:
    """Extract the Board from ParsedPCB."""
    return getattr(parsed, "board", None)
