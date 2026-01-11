"""
Router V6 Stage 1.3: Compute Escape Via Positions

Calculates via positions for dense packages using dog-bone or via-in-pad strategies.
Part of temper-ipar (Stage 1 - Pin Escape Planning)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from temper_placer.core.netlist import Component
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.stage0_data import DesignRules


@dataclass
class EscapeVia:
    """
    Computed escape via definition.

    Attributes:
        position: (x, y) absolute coordinates in mm.
        net_name: Name of the net.
        pin_number: Pin number being escaped.
        diameter: Via diameter in mm.
        drill: Via drill diameter in mm.
        via_type: "dog-bone" or "via-in-pad".
    """

    position: tuple[float, float]
    net_name: str
    pin_number: str
    diameter: float
    drill: float
    via_type: str


def generate_escape_vias(
    dense_pkg: DensePackage,
    design_rules: DesignRules,
    strategy: str = "dog-bone",
) -> list[EscapeVia]:
    """
    Generate escape vias for a dense package.

    Args:
        dense_pkg: The DensePackage to process.
        design_rules: Board design rules (clearance, via sizes).
        strategy: "dog-bone" (default) or "via-in-pad".

    Returns:
        List of EscapeVia objects.
    """
    escape_vias = []
    component = dense_pkg.component
    
    # Get component absolute position
    comp_x, comp_y = 0.0, 0.0
    if component.initial_position:
        comp_x, comp_y = component.initial_position
    
    # Get component rotation in radians
    # Component.initial_rotation is index 0-3 (0=0, 1=90, 2=180, 3=270)
    angle = 0.0
    if component.initial_rotation is not None:
        angle = float(component.initial_rotation) * math.pi / 2.0
    
    for pin in component.pins:
        if not pin.net:
            continue
            
        rules = design_rules.get_rules_for_net(pin.net)
        via_diameter = rules.via_diameter_mm
        via_drill = rules.via_drill_mm
        clearance = rules.clearance_mm
        
        # Determine via position
        if strategy == "via-in-pad":
            # Via in center of pad
            abs_pos = pin.absolute_position((comp_x, comp_y), angle)
            
            escape_vias.append(EscapeVia(
                position=abs_pos,
                net_name=pin.net,
                pin_number=pin.number,
                diameter=via_diameter,
                drill=via_drill,
                via_type="via-in-pad"
            ))
            
        elif strategy == "dog-bone":
            pin_abs_pos = pin.absolute_position((comp_x, comp_y), angle)
            
            # Valid candidates for BGA/Grid dogbone (relative to pin in component space)
            # We try 4 diagonals: (+half_pitch, +half_pitch), etc.
            half_pitch = dense_pkg.pitch_mm / 2.0
            
            # Note: For non-square grids or non-BGA, this pitch-based heuristic 
            # might need refinement, but it's a good robust start for "dense" packages.
            candidates = [
                (half_pitch, half_pitch),
                (half_pitch, -half_pitch),
                (-half_pitch, half_pitch),
                (-half_pitch, -half_pitch)
            ]
            
            chosen_pos = None
            
            for dx, dy in candidates:
                # Rotate the offset to match component rotation
                cos_r = math.cos(angle)
                sin_r = math.sin(angle)
                
                # Apply rotation
                rot_dx = dx * cos_r - dy * sin_r
                rot_dy = dx * sin_r + dy * cos_r
                
                # Candidate absolute position
                cand_x = pin_abs_pos[0] + rot_dx
                cand_y = pin_abs_pos[1] + rot_dy
                
                # Check collision with other pins
                if _is_position_valid(
                    cand_x, cand_y, 
                    via_diameter / 2.0, 
                    component, 
                    (comp_x, comp_y), 
                    angle, 
                    clearance,
                    ignore_net=pin.net # Ignore clearance to same net
                ):
                    chosen_pos = (cand_x, cand_y)
                    break
            
            if chosen_pos:
                escape_vias.append(EscapeVia(
                    position=chosen_pos,
                    net_name=pin.net,
                    pin_number=pin.number,
                    diameter=via_diameter,
                    drill=via_drill,
                    via_type="dog-bone"
                ))
            else:
                # Could not find valid dog-bone position. 
                # This happens if pitch is too tight for the via size.
                pass
                
    return escape_vias


def _is_position_valid(
    x: float, 
    y: float, 
    radius: float, 
    component: Component, 
    comp_pos: tuple[float, float],
    comp_angle: float,
    clearance: float,
    ignore_net: str | None = None
) -> bool:
    """
    Check if via at (x,y) with radius collides with any component pin.
    
    Args:
        x, y: Via center coordinates.
        radius: Via radius.
        component: Component to check against.
        comp_pos: Component absolute position.
        comp_angle: Component rotation angle.
        clearance: Required clearance.
        ignore_net: Net name to ignore (e.g. source pin's net).
    """
    
    for pin in component.pins:
        # If pin is on the same net, physical overlap is allowed/expected for connection.
        # However, for dog-bone, we ideally want separation. 
        # But strictly speaking, DRC allows overlap on same net.
        # Let's enforce separation even for same net to ensure "dog-bone" shape,
        # but maybe with reduced requirement? 
        # Actually, for dog-bone, the via IS separated. 
        # If we return False here, we say "invalid position".
        # If it overlaps source pin, it's effectively Via-in-Pad, not Dog-Bone.
        # So we SHOULD check collision even for same net to force separation.
        # BUT, standard BGA pitch might barely fit.
        # Let's check pure geometric overlap.
        
        p_pos = pin.absolute_position(comp_pos, comp_angle)
        
        # Approximate pin as circle with radius = max(width, height)/2
        # This is conservative for rectangular pads.
        pin_radius = max(pin.width, pin.height) / 2.0
        
        dist = math.sqrt((x - p_pos[0])**2 + (y - p_pos[1])**2)
        
        required_dist = radius + pin_radius + clearance
        
        # If on same net, we don't need electrical clearance, but we might want mechanical separation.
        # If ignore_net matches, we can relax the check?
        # Let's maintain strict check for now to ensure quality fanout.
        
        if dist < required_dist - 0.001: # epsilon tolerance
            return False
            
    return True
