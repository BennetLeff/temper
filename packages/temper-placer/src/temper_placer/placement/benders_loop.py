"""Placement strategy module for the closure test pipeline.

Exposes benders_placement() — the single entry point the closure test
imports at temper_placer.placement.benders_loop.  The default strategy
delegates to the existing template-based deterministic placer; Benders
decomposition registers as a future strategy under the same interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BendersPlacementResult:
    """Placement result matching ClosureTest's expected interface."""

    placements: dict[str, tuple[float, float]]
    iterations: int
    cuts: int


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

_STRATEGIES: dict[str, Any] = {}


def register_strategy(name: str, fn):
    """Register a placement function under a strategy name."""
    _STRATEGIES[name] = fn


def _template_strategy(parsed, seed: int) -> BendersPlacementResult:
    """Default strategy: use the existing deterministic template placer."""
    try:
        from temper_placer.placer.deterministic import (
            place_power_stage_template,
            PlacementResult,
        )
        from temper_placer.placer.template import HalfBridgeTemplate
    except ImportError as exc:
        logger.warning("Template placer not available: %s", exc)
        return BendersPlacementResult(placements={}, iterations=0, cuts=0)

    netlist = _extract_netlist(parsed)
    board = _extract_board(parsed)
    if netlist is None or board is None:
        raise ValueError(
            "Parsed PCB missing netlist or board data — cannot place components"
        )

    template = HalfBridgeTemplate()
    result: PlacementResult = place_power_stage_template(
        netlist, board, template
    )

    placements: dict[str, tuple[float, float]] = {}
    positions = result.positions
    for i, ref in enumerate(result.placed_refs):
        x = float(positions[i][0])
        y = float(positions[i][1])
        placements[ref] = (x, y)

    return BendersPlacementResult(
        placements=placements,
        iterations=1,  # template placement is a single pass
        cuts=0,         # no Benders cuts in template mode
    )


def _extract_netlist(parsed) -> Any | None:
    """Extract netlist from a ParsedPCB object (attribute name varies)."""
    for attr in ("netlist", "net_list", "nets"):
        if hasattr(parsed, attr):
            return getattr(parsed, attr)
    return None


def _extract_board(parsed) -> Any | None:
    """Extract board from a ParsedPCB object (attribute name varies)."""
    for attr in ("board", "pcb", "layout"):
        if hasattr(parsed, attr):
            return getattr(parsed, attr)
    return None


# Register the default strategy
register_strategy("template", _template_strategy)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def benders_placement(
    parsed,
    seed: int,
    *,
    strategy: str = "template",
) -> BendersPlacementResult:
    """Run component placement.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6().
        seed: Random seed (passed through to strategies that use it).
        strategy: Placement strategy name. ``"template"`` (default) uses the
            existing deterministic placer.  ``"benders"`` is reserved for
            future Benders decomposition — calling it today produces a
            warning and empty placements.

    Returns:
        BendersPlacementResult with .placements dict, .iterations, .cuts.
    """
    fn = _STRATEGIES.get(strategy)
    if fn is None:
        logger.warning(
            "Placement strategy '%s' not registered — returning empty placements",
            strategy,
        )
        return BendersPlacementResult(placements={}, iterations=0, cuts=0)

    return fn(parsed, seed)
