from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import math

class EscapeDirection(Enum):
    NORTH = auto()
    SOUTH = auto()
    EAST = auto()
    WEST = auto()
    NORTH_EAST = auto()
    NORTH_WEST = auto()
    SOUTH_EAST = auto()
    SOUTH_WEST = auto()

@dataclass
class PinInfo:
    id: str  # Pin name or ID
    x: float
    y: float
    # Optional: could add net name, etc.

@dataclass
class EscapeAssignment:
    pin_id: str
    direction: EscapeDirection
    ring_index: int  # 0 = outermost
    distance_to_edge: float

class RingClassifier:
    """
    Classifies pins into concentric rings and assigns escape directions.
    """
    def __init__(self, pins: List[PinInfo]):
        self.pins = pins
        self.pin_map = {p.id: p for p in pins}

    def analyze(self) -> Dict[str, EscapeAssignment]:
        """
        Analyze all pins and return assignments.
        """
        remaining_pins = list(self.pins)
        assignments = {}
        current_ring = 0

        while remaining_pins:
            # 1. Determine bounds of remaining pins
            xs = [p.x for p in remaining_pins]
            ys = [p.y for p in remaining_pins]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            # Tolerance for "on the edge" (floating point)
            tol = 1e-5

            current_ring_pins = []
            next_remaining = []

            for p in remaining_pins:
                on_left = abs(p.x - min_x) < tol
                on_right = abs(p.x - max_x) < tol
                on_top = abs(p.y - min_y) < tol
                on_bottom = abs(p.y - max_y) < tol
                
                is_edge = on_left or on_right or on_top or on_bottom
                
                if is_edge:
                    current_ring_pins.append(p)
                    # Determine direction
                    direction = self._determine_direction(on_left, on_right, on_top, on_bottom)
                    
                    # Distance to edge is effectively 0 relative to THIS ring's bounds
                    # But maybe we want distance to GLOBAL edge?
                    # The requirement says "Inner ring pins escape toward the nearest edge".
                    # By peeling rings, we essentially find the "nearest edge" of the remaining block,
                    # which correlates to the global nearest edge usually.
                    
                    # Let's calculate distance to the local bounds for now, or just use the boolean logic.
                    assignments[p.id] = EscapeAssignment(
                        pin_id=p.id,
                        direction=direction,
                        ring_index=current_ring,
                        distance_to_edge=0.0 # Placeholder
                    )
                else:
                    next_remaining.append(p)
            
            remaining_pins = next_remaining
            current_ring += 1
            
        return assignments

    def _determine_direction(self, left: bool, right: bool, top: bool, bottom: bool) -> EscapeDirection:
        # Corner cases
        if left and top: return EscapeDirection.NORTH_WEST
        if right and top: return EscapeDirection.NORTH_EAST
        if left and bottom: return EscapeDirection.SOUTH_WEST
        if right and bottom: return EscapeDirection.SOUTH_EAST
        
        # Edge cases
        if left: return EscapeDirection.WEST
        if right: return EscapeDirection.EAST
        if top: return EscapeDirection.NORTH
        if bottom: return EscapeDirection.SOUTH
        
        # Should not happen if logic is correct
        return EscapeDirection.NORTH 
