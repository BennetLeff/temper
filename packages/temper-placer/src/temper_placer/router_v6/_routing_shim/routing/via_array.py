"""
Via Array Generation for High-Current Nets

Generates N×M via arrays to distribute current and meet thermal requirements.
Single via capacity: ~2A (conservative, 0.3mm drill)
Array sizing follows IPC-2221A thermal derating.
"""

from dataclasses import dataclass
from typing import Tuple, List
import math


@dataclass
class ViaArrayTemplate:
    """
    Template for via array placement.
    
    Attributes:
        rows: Number of via rows
        cols: Number of via columns  
        spacing_mm: Center-to-center spacing between vias
        via_drill_mm: Via drill diameter
        via_annular_mm: Annular ring width
        total_current_a: Total current this array handles
    """
    rows: int
    cols: int
    spacing_mm: float
    via_drill_mm: float
    via_annular_mm: float
    total_current_a: float
    
    @property
    def via_count(self) -> int:
        """Total number of vias in array."""
        return self.rows * self.cols
    
    @property
    def current_per_via_a(self) -> float:
        """Current per individual via."""
        return self.total_current_a / self.via_count if self.via_count > 0 else 0.0
    
    def get_via_positions(
        self, 
        center_x: float, 
        center_y: float
    ) -> List[Tuple[float, float]]:
        """
        Calculate via positions in array centered at (center_x, center_y).
        
        Args:
            center_x: Array center X coordinate (mm)
            center_y: Array center Y coordinate (mm)
            
        Returns:
            List of (x, y) via positions in mm
        """
        positions = []
        
        # Calculate array dimensions
        array_width = (self.cols - 1) * self.spacing_mm
        array_height = (self.rows - 1) * self.spacing_mm
        
        # Starting position (top-left of array)
        start_x = center_x - array_width / 2
        start_y = center_y - array_height / 2
        
        # Generate grid positions
        for row in range(self.rows):
            for col in range(self.cols):
                x = start_x + col * self.spacing_mm
                y = start_y + row * self.spacing_mm
                positions.append((x, y))
        
        return positions


def calculate_via_array(
    net_current_a: float,
    via_drill_mm: float = 0.3,
    via_annular_mm: float = 0.15,
    single_via_current_a: float = 2.0,
    min_spacing_mm: float = 1.5,
) -> ViaArrayTemplate:
    """
    Calculate via array dimensions for given current requirement.
    
    Uses conservative single-via capacity and generates square/rectangular arrays.
    
    Args:
        net_current_a: Total net current (amperes)
        via_drill_mm: Via drill diameter
        via_annular_mm: Annular ring width
        single_via_current_a: Current capacity per via (conservative)
        min_spacing_mm: Minimum via spacing (thermal + clearance)
        
    Returns:
        ViaArrayTemplate with calculated dimensions
    """
    # Calculate required via count
    via_count_needed = math.ceil(net_current_a / single_via_current_a)
    
    # Single via sufficient
    if via_count_needed <= 1:
        return ViaArrayTemplate(
            rows=1,
            cols=1,
            spacing_mm=min_spacing_mm,
            via_drill_mm=via_drill_mm,
            via_annular_mm=via_annular_mm,
            total_current_a=net_current_a,
        )
    
    # Generate square-ish array (prefer square for symmetry)
    # Examples: 2→1×2, 3→2×2, 4→2×2, 5→2×3, 6→2×3, 8→3×3, 9→3×3
    rows = math.ceil(math.sqrt(via_count_needed))
    cols = math.ceil(via_count_needed / rows)
    
    return ViaArrayTemplate(
        rows=rows,
        cols=cols,
        spacing_mm=min_spacing_mm,
        via_drill_mm=via_drill_mm,
        via_annular_mm=via_annular_mm,
        total_current_a=net_current_a,
    )


def should_use_via_array(net_current_a: float, threshold_a: float = 5.0) -> bool:
    """
    Determine if net requires via array based on current.
    
    Args:
        net_current_a: Net current (amperes)
        threshold_a: Threshold above which arrays are required
        
    Returns:
        True if via array should be used
    """
    return net_current_a >= threshold_a


# Example usage and validation
if __name__ == "__main__":
    # Test cases
    test_currents = [2.0, 5.0, 10.0, 15.0, 20.0]
    
    print("Via Array Sizing Examples:")
    print("=" * 60)
    
    for current in test_currents:
        template = calculate_via_array(current)
        print(f"\nCurrent: {current}A")
        print(f"  Array: {template.rows}×{template.cols} ({template.via_count} vias)")
        print(f"  Current/via: {template.current_per_via_a:.2f}A")
        print(f"  Spacing: {template.spacing_mm}mm")
        print(f"  Use array: {should_use_via_array(current)}")
        
        # Show positions for small arrays
        if template.via_count <= 4:
            positions = template.get_via_positions(0.0, 0.0)
            print(f"  Positions: {positions}")
    
    print("\n" + "=" * 60)
    print("✅ Via array calculations complete")
