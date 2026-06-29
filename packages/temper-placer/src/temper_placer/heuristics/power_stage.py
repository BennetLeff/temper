"""
Power stage template heuristic for priority-based placement.

Places power stage components using fixed templates that encode
correct topology for common power converter configurations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.core.priority import POWER_STAGE_TEMPLATES, PlacementPhaseConfig, PlacementPriority
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PowerStageTemplateHeuristic(Heuristic):
    """
    Place power stage components using fixed templates.

    This heuristic encodes correct power electronics topologies:
    - Half-bridge (vertical/horizontal variants)
    - Full-bridge
    - Custom templates from config

    Components are placed at fixed positions relative to an anchor point.
    """

    @property
    def name(self) -> str:
        return "power_stage_template"

    @property
    def priority(self) -> HeuristicPriority:
        # Run before everything else - INITIALIZATION priority
        return HeuristicPriority.INITIALIZATION

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply power stage template placement."""
        result = HeuristicResult()

        # Get power stage config from constraints
        phase_config = self._get_phase_config(context)
        if phase_config is None:
            logger.debug("No power stage config found, skipping template heuristic")
            result.message = "No power stage config found"
            return result

        # Get template
        template_name = phase_config.template or "half_bridge_vertical"
        template = POWER_STAGE_TEMPLATES.get(template_name)
        if template is None:
            logger.warning(f"Unknown template '{template_name}', using half_bridge_vertical")
            template = POWER_STAGE_TEMPLATES["half_bridge_vertical"]

        # Get anchor point
        anchor = phase_config.anchor
        if anchor is None:
            # Default to center-right of board
            anchor = (context.board.width * 0.75, context.board.height * 0.75)
            logger.info(f"No anchor specified, using default ({anchor[0]:.1f}, {anchor[1]:.1f})")

        # Place components from template
        for ref, offset in template.items():
            # Check if component exists in netlist
            try:
                comp = context.netlist.get_component(ref)
            except (KeyError, ValueError):
                logger.debug(f"Component {ref} not found in netlist, skipping")
                continue

            # Skip if already placed
            if ref in context.current_placements:
                continue

            # Use fixed_position from config if available, otherwise use template
            if comp.initial_position is not None:
                # Use exact position from fixed_positions in config
                x, y = comp.initial_position
                logger.debug(f"Using fixed_position for {ref}: ({x:.1f}, {y:.1f})")
            else:
                # Calculate position from template + anchor
                x = anchor[0] + offset[0]
                y = anchor[1] + offset[1]

            # Clamp to board bounds
            margin = context.constraints.board_margin_mm
            half_w = comp.width / 2
            half_h = comp.height / 2
            x = np.clip(x, margin + half_w, context.board.width - margin - half_w)
            y = np.clip(y, margin + half_h, context.board.height - margin - half_h)

            # Create placement
            placement = ComponentPlacement(
                ref=ref,
                position=(float(x), float(y)),
                rotation=0,
                confidence=1.0,
                placed_by=self.name,
            )
            result.placements[ref] = placement
            logger.debug(f"Placed {ref} at ({x:.1f}, {y:.1f})")

        result.message = f"Placed {len(result.placements)} components using '{template_name}'"
        logger.info(f"Power stage template: {result.message}")
        return result

    def _get_phase_config(self, context: PlacementContext) -> PlacementPhaseConfig | None:
        """Extract power phase config from constraints."""
        if not hasattr(context, 'constraints') or context.constraints is None:
            return None

        # Fall back to placement_priority dict
        if hasattr(context.constraints, 'placement_priority'):
            power_cfg = context.constraints.placement_priority.get('power')
            if power_cfg:
                anchor = power_cfg.get('anchor')
                return PlacementPhaseConfig(
                    name="power",
                    priority=PlacementPriority.POWER,
                    components=power_cfg.get('components', []),
                    method=power_cfg.get('method', 'template'),
                    template=power_cfg.get('template', 'half_bridge_vertical'),
                    anchor=tuple(anchor) if anchor else None,
                )

        return None


class DriverProximityHeuristic(Heuristic):
    """
    Place gate driver components near the power stage.

    This heuristic places driver components (gate driver IC, bootstrap,
    gate resistors) within a specified distance of the power stage.
    """

    @property
    def name(self) -> str:
        return "driver_proximity"

    @property
    def priority(self) -> HeuristicPriority:
        # Run right after power stage template
        return HeuristicPriority.INITIALIZATION

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply driver proximity placement."""
        result = HeuristicResult()

        # Get driver phase config
        phase_config = self._get_phase_config(context)
        if phase_config is None:
            logger.debug("No driver config found, skipping proximity heuristic")
            result.message = "No driver config found"
            return result

        # Find reference component (usually Q1 or center of power stage)
        ref_name = phase_config.reference or "Q1"
        ref_pos = None

        if ref_name in context.current_placements:
            ref_pos = context.current_placements[ref_name].position
        else:
            # Try to get from netlist initial position
            try:
                comp = context.netlist.get_component(ref_name)
                if comp.initial_position:
                    ref_pos = comp.initial_position
            except (KeyError, ValueError):
                pass

        if ref_pos is None:
            logger.warning(f"Reference component {ref_name} not found, using board center")
            ref_pos = (context.board.width / 2, context.board.height / 2)

        # Place driver components in a cluster near reference
        max_dist = phase_config.max_distance_mm or 20.0

        for ref in phase_config.components:
            # Skip if already placed
            if ref in context.current_placements:
                continue

            try:
                comp = context.netlist.get_component(ref)
            except (KeyError, ValueError):
                continue

            # Place at offset from reference
            # Gate driver goes to the control side, resistors between driver and IGBTs
            if "U_GATE" in ref:
                # Gate driver IC - offset towards control zone
                offset = (-max_dist * 0.8, 0)
            elif "C_BOOT" in ref or "C_VCC" in ref:
                # Bootstrap/decoupling - very close to driver
                offset = (-max_dist * 0.8 + 3, 3 if "BOOT" in ref else -3)
            elif "R_GATE" in ref:
                # Gate resistors - between driver and IGBTs
                offset = (-max_dist * 0.4, 3 if "H" in ref else -3)
            else:
                # Default - cluster near driver
                offset = (-max_dist * 0.6, 0)

            x = ref_pos[0] + offset[0]
            y = ref_pos[1] + offset[1]

            # Clamp to board
            margin = context.constraints.board_margin_mm
            half_w = comp.width / 2
            half_h = comp.height / 2
            x = np.clip(x, margin + half_w, context.board.width - margin - half_w)
            y = np.clip(y, margin + half_h, context.board.height - margin - half_h)

            placement = ComponentPlacement(
                ref=ref,
                position=(float(x), float(y)),
                rotation=0,
                confidence=0.9,
                placed_by=self.name,
            )
            result.placements[ref] = placement

        result.message = f"Placed {len(result.placements)} driver components near {ref_name}"
        logger.info(f"Driver proximity: {result.message}")
        return result

    def _get_phase_config(self, context: PlacementContext) -> PlacementPhaseConfig | None:
        """Extract driver phase config from constraints."""
        if not hasattr(context, 'constraints') or context.constraints is None:
            return None

        if hasattr(context.constraints, 'placement_priority'):
            driver_cfg = context.constraints.placement_priority.get('driver')
            if driver_cfg:
                return PlacementPhaseConfig(
                    name="driver",
                    priority=PlacementPriority.DRIVER,
                    components=driver_cfg.get('components', []),
                    method=driver_cfg.get('method', 'proximity'),
                    reference=driver_cfg.get('reference'),
                    max_distance_mm=driver_cfg.get('max_distance_mm', 20.0),
                )

        return None
