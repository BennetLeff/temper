"""
Power stage template heuristic for priority-based placement.

Places power stage components using fixed templates that encode
correct topology for common power converter configurations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.core.priority import POWER_STAGE_TEMPLATES, PlacementPhaseConfig
from temper_placer.heuristics.base import BaseHeuristic, PlacementContext

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PowerStageTemplateHeuristic(BaseHeuristic):
    """
    Place power stage components using fixed templates.
    
    This heuristic encodes correct power electronics topologies:
    - Half-bridge (vertical/horizontal variants)
    - Full-bridge
    - Custom templates from config
    
    Components are placed at fixed positions relative to an anchor point,
    and marked as fixed to prevent optimizer from moving them.
    """
    
    name: str = "power_stage_template"
    
    def run(self, ctx: PlacementContext) -> PlacementContext:
        """Apply power stage template placement."""
        # Get power stage config from constraints
        phase_config = self._get_phase_config(ctx)
        if phase_config is None:
            logger.debug("No power stage config found, skipping template heuristic")
            return ctx
        
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
            anchor = (ctx.board.width * 0.75, ctx.board.height * 0.5)
            logger.info(f"No anchor specified, using default ({anchor[0]:.1f}, {anchor[1]:.1f})")
        
        # Place components from template
        placed_count = 0
        for ref, offset in template.items():
            # Check if component exists in netlist
            try:
                idx = ctx.netlist.get_component_index(ref)
            except (KeyError, ValueError):
                logger.debug(f"Component {ref} not found in netlist, skipping")
                continue
            
            # Calculate position
            x = anchor[0] + offset[0]
            y = anchor[1] + offset[1]
            
            # Clamp to board bounds
            comp = ctx.netlist.components[idx]
            half_w = comp.width / 2
            half_h = comp.height / 2
            x = np.clip(x, half_w, ctx.board.width - half_w)
            y = np.clip(y, half_h, ctx.board.height - half_h)
            
            # Apply position
            ctx.positions[idx] = (x, y)
            ctx.placed[idx] = True
            
            # Mark as fixed so optimizer doesn't move it
            if hasattr(ctx, 'fixed_mask') and ctx.fixed_mask is not None:
                ctx.fixed_mask[idx] = True
            
            placed_count += 1
            logger.debug(f"Placed {ref} at ({x:.1f}, {y:.1f})")
        
        # Record stats
        ctx.heuristic_stats[self.name] = {
            "placed": placed_count,
            "template": template_name,
            "anchor": anchor,
        }
        
        logger.info(f"Power stage template: placed {placed_count} components using '{template_name}'")
        return ctx
    
    def _get_phase_config(self, ctx: PlacementContext) -> PlacementPhaseConfig | None:
        """Extract power phase config from constraints."""
        if not hasattr(ctx, 'constraints') or ctx.constraints is None:
            return None
        
        # Check for priority_config
        if hasattr(ctx.constraints, 'priority_config'):
            from temper_placer.core.priority import PlacementPriority
            return ctx.constraints.priority_config.get_placement_phase(PlacementPriority.POWER)
        
        # Fall back to placement_priority dict
        if hasattr(ctx.constraints, 'placement_priority'):
            power_cfg = ctx.constraints.placement_priority.get('power')
            if power_cfg:
                return PlacementPhaseConfig(
                    name="power",
                    priority=1,
                    components=power_cfg.get('components', []),
                    method=power_cfg.get('method', 'template'),
                    template=power_cfg.get('template', 'half_bridge_vertical'),
                    anchor=tuple(power_cfg.get('anchor', [])) if power_cfg.get('anchor') else None,
                )
        
        return None


@dataclass  
class DriverProximityHeuristic(BaseHeuristic):
    """
    Place gate driver components near the power stage.
    
    This heuristic places driver components (gate driver IC, bootstrap,
    gate resistors) within a specified distance of the power stage.
    """
    
    name: str = "driver_proximity"
    
    def run(self, ctx: PlacementContext) -> PlacementContext:
        """Apply driver proximity placement."""
        # Get driver phase config
        phase_config = self._get_phase_config(ctx)
        if phase_config is None:
            logger.debug("No driver config found, skipping proximity heuristic")
            return ctx
        
        # Find reference component (usually Q1 or center of power stage)
        ref_name = phase_config.reference or "Q1"
        try:
            ref_idx = ctx.netlist.get_component_index(ref_name)
            ref_pos = ctx.positions[ref_idx]
        except (KeyError, ValueError):
            logger.warning(f"Reference component {ref_name} not found, using board center")
            ref_pos = (ctx.board.width / 2, ctx.board.height / 2)
        
        # Place driver components in a cluster near reference
        max_dist = phase_config.max_distance_mm or 20.0
        placed_count = 0
        
        for ref in phase_config.components:
            try:
                idx = ctx.netlist.get_component_index(ref)
            except (KeyError, ValueError):
                continue
            
            if ctx.placed[idx]:
                continue
            
            # Place at offset from reference
            # Gate driver goes to the control side, resistors between driver and IGBTs
            comp = ctx.netlist.components[idx]
            
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
                offset = (-max_dist * 0.6, np.random.uniform(-5, 5))
            
            x = ref_pos[0] + offset[0]
            y = ref_pos[1] + offset[1]
            
            # Clamp to board
            half_w = comp.width / 2
            half_h = comp.height / 2
            x = np.clip(x, half_w, ctx.board.width - half_w)
            y = np.clip(y, half_h, ctx.board.height - half_h)
            
            ctx.positions[idx] = (x, y)
            ctx.placed[idx] = True
            placed_count += 1
        
        ctx.heuristic_stats[self.name] = {
            "placed": placed_count,
            "reference": ref_name,
            "max_distance_mm": max_dist,
        }
        
        logger.info(f"Driver proximity: placed {placed_count} components near {ref_name}")
        return ctx
    
    def _get_phase_config(self, ctx: PlacementContext) -> PlacementPhaseConfig | None:
        """Extract driver phase config from constraints."""
        if not hasattr(ctx, 'constraints') or ctx.constraints is None:
            return None
        
        if hasattr(ctx.constraints, 'priority_config'):
            from temper_placer.core.priority import PlacementPriority
            return ctx.constraints.priority_config.get_placement_phase(PlacementPriority.DRIVER)
        
        if hasattr(ctx.constraints, 'placement_priority'):
            driver_cfg = ctx.constraints.placement_priority.get('driver')
            if driver_cfg:
                return PlacementPhaseConfig(
                    name="driver",
                    priority=2,
                    components=driver_cfg.get('components', []),
                    method=driver_cfg.get('method', 'proximity'),
                    reference=driver_cfg.get('reference'),
                    max_distance_mm=driver_cfg.get('max_distance_mm', 20.0),
                )
        
        return None
