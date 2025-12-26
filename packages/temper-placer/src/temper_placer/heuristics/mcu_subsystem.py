"""
MCU Subsystem placement heuristic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.placer.template import load_template_from_yaml

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.deterministic import PlacementResult

logger = logging.getLogger(__name__)


class MCUSubsystemHeuristic:
    """Heuristic for MCU subsystem placement."""
    
    def __init__(self, template_path: Path | None = None):
        if template_path is None:
            template_path = Path(__file__).parent.parent / "templates" / "mcu_subsystem.yaml"
        self.template_path = template_path
        self.template = load_template_from_yaml(self.template_path)

    def apply(
        self,
        netlist: Netlist,
        board: Board,
        zone_name: str = "MCU_ZONE",
    ) -> PlacementResult:
        """Apply MCU subsystem template."""
        from temper_placer.placer.deterministic import place_power_stage_template
        logger.info(f"Applying MCU Subsystem template from {self.template_path}")
        return place_power_stage_template(
            netlist=netlist,
            board=board,
            template=self.template,
            zone_name=zone_name
        )
