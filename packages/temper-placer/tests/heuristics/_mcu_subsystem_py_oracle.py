"""Pinned Python oracle for Wave-4 heuristics/ -- mcu_subsystem.py.

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
Everything below the module docstring is a **verbatim** ``git show``
extraction of commit ``5a17025b15d01bf88116b569493d8ed483e1856f`` (the last commit that touched this file;
``origin/main`` at the time this migration was pulled remains at the same
text -- see ``test_oracle_is_verbatim_copy``, which re-extracts the pinned
commit via ``git show`` and compares byte-for-byte) of
``packages/temper-placer/src/temper_placer/heuristics/mcu_subsystem.py``.

Nothing below the marker line has been cleaned up, refactored,
reformatted, or fixed -- not even the module docstring the original file
itself carried (dropped here only because *this* file needs its own, to
record the pin). Any drift fails ``test_oracle_is_verbatim_copy`` instead
of passing quietly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.placer.deterministic import PlacementResult
from temper_placer.placer.template import load_template_from_yaml

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

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
            netlist=netlist, board=board, template=self.template, zone_name=zone_name
        )
