"""
MCU Subsystem placement heuristic.

This module provides a heuristic for placing MCU-related components
(crystal, decaps, debug header) in a standardized, signal-integrity
aware layout.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.placer.template import load_template_from_yaml
from temper_placer.placer.deterministic import PlacementResult

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.state import PlacementState

logger = logging.getLogger(__name__)


class MCUSubsystemHeuristic:
    """
    Heuristic for MCU subsystem placement.
    
    Uses a YAML template to define relative positions and applies them
    at the designated MCU zone center.
    """
    
    def __init__(self, template_path: Path | None = None):
        if template_path is None:
            # Default template in the same package
            template_path = Path(__file__).parent.parent / "templates" / "mcu_subsystem.yaml"
        self.template_path = template_path
        self.template = load_template_from_yaml(self.template_path)

    def apply(
        self,
        netlist: Netlist,
        board: Board,
        zone_name: str = "MCU",
    ) -> PlacementResult:
        """
        Apply MCU subsystem template to the netlist.
        """
        from temper_placer.placer.deterministic import place_power_stage_template
        
        logger.info(f"Applying MCU Subsystem template from {self.template_path}")
        
        # We reuse the place_power_stage_template logic as it's generic for ComponentTemplate
        return place_power_stage_template(
            netlist=netlist,
            board=board,
            template=self.template,
            zone_name=zone_name
        )
