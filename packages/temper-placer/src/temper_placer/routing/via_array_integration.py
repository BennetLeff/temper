"""
Automatic Via Array Integration

Wrapper that adds automatic via array detection and placement to routing results.
Integrates via_array.py module with routing pipeline.

Usage:
    from temper_placer.routing.via_array_integration import apply_via_arrays
    
    # After routing
    routing_result = router.route_all_nets()
    routing_result = apply_via_arrays(routing_result, design_rules)
"""

from typing import List, Tuple
from dataclasses import dataclass

from temper_placer.routing.via_array import (
    calculate_via_array,
    should_use_via_array,
    ViaArrayTemplate,
)


@dataclass
class ViaPlacement:
    """Single via or via array placement."""
    x_mm: float
    y_mm: float
    from_layer: int
    to_layer: int
    net_name: str
    is_array: bool = False
    array_template: ViaArrayTemplate | None = None


def detect_layer_transitions(cells: List[Tuple[int, int, int]], cell_size_mm: float) -> List[Tuple[float, float, int, int]]:
    """
    Detect layer transitions in routed path.
    
    Args:
        cells: List of (x, y, layer) grid cells
        cell_size_mm: Grid cell size
        
    Returns:
        List of (x_mm, y_mm, from_layer, to_layer) via positions
    """
    transitions = []
    
    for i in range(len(cells) - 1):
        curr_cell = cells[i]
        next_cell = cells[i + 1]
        
        if curr_cell[2] != next_cell[2]:  # Layer change
            # Via position (use current cell position)
            x_mm = curr_cell[0] * cell_size_mm
            y_mm = curr_cell[1] * cell_size_mm
            from_layer = curr_cell[2]
            to_layer = next_cell[2]
            
            transitions.append((x_mm, y_mm, from_layer, to_layer))
    
    return transitions


def get_net_current(net_name: str, design_rules) -> float:
    """
    Extract current rating for a net from design rules.
    
    Args:
        net_name: Net name
        design_rules: DesignRules object
        
    Returns:
        Net current in amperes (0.0 if unknown)
    """
    # Try to get net class
    if hasattr(design_rules, 'get_rules_for_net'):
        rules = design_rules.get_rules_for_net(net_name)
        if hasattr(rules, 'current_capacity_a'):
            return rules.current_capacity_a
    
    # Heuristic fallback: High-power nets
    if 'PWR' in net_name.upper() or '_20A' in net_name or '_10A' in net_name:
        # Extract current from name
        if '_20A' in net_name:
            return 20.0
        if '_10A' in net_name:
            return 10.0
        if '_5A' in net_name:
            return 5.0
        # Default high-power
        return 10.0
    
    # Default: Low current
    return 1.0


def apply_via_arrays(
    routing_result,
    design_rules,
    cell_size_mm: float = 0.1,
) -> List[ViaPlacement]:
    """
    Apply via array logic to routing result.
    
    For each routed net:
    1. Detect layer transitions
    2. Check net current rating
    3. Use via array if current ≥5A
    
    Args:
        routing_result: Routing result with cells per net
        design_rules: Design rules with current ratings
        cell_size_mm: Grid cell size
        
    Returns:
        List of via placements (single or array)
    """
    via_placements = []
    
    # Iterate over routed nets
    for net_name, net_path in routing_result.items():
        if not net_path.success:
            continue
        
        # Get net current
        net_current = get_net_current(net_name, design_rules)
        
        # Detect layer transitions
        transitions = detect_layer_transitions(net_path.cells, cell_size_mm)
        
        for (x_mm, y_mm, from_layer, to_layer) in transitions:
            # Check if via array needed
            if should_use_via_array(net_current):
                # Calculate via array
                template = calculate_via_array(net_current)
                
                via_placements.append(ViaPlacement(
                    x_mm=x_mm,
                    y_mm=y_mm,
                    from_layer=from_layer,
                    to_layer=to_layer,
                    net_name=net_name,
                    is_array=True,
                    array_template=template,
                ))
            else:
                # Single via
                via_placements.append(ViaPlacement(
                    x_mm=x_mm,
                    y_mm=y_mm,
                    from_layer=from_layer,
                    to_layer=to_layer,
                    net_name=net_name,
                    is_array=False,
                ))
    
    return via_placements


def export_vias_to_kicad(via_placements: List[ViaPlacement], output_path: str):
    """
    Export via placements to KiCad format (S-expression snippet).
    
    Args:
        via_placements: List of via placements
        output_path: Output file path
    """
    lines = []
    
    for via in via_placements:
        if via.is_array:
            # Export N×M array
            positions = via.array_template.get_via_positions(via.x_mm, via.y_mm)
            for (x, y) in positions:
                lines.append(f"  (via (at {x} {y}) (size {via.array_template.via_drill_mm}) (drill {via.array_template.via_drill_mm}) (layers {via.from_layer} {via.to_layer}) (net \"{via.net_name}\"))")
        else:
            # Export single via
            lines.append(f"  (via (at {via.x_mm} {via.y_mm}) (size 0.6) (drill 0.3) (layers {via.from_layer} {via.to_layer}) (net \"{via.net_name}\"))")
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))


# Demonstration
if __name__ == "__main__":
    print("Via Array Integration Demo")
    print("=" * 60)
    
    # Simulate routing result
    class MockPath:
        def __init__(self, cells, success=True):
            self.cells = cells
            self.success = success
    
    # Example: 10A net with layer transition
    routing_result = {
        "NET_PWR_10A": MockPath([
            (20, 50, 0),  # Layer 0
            (21, 50, 0),
            (22, 50, 0),
            (22, 50, 1),  # Transition to Layer 1
            (23, 50, 1),
            (24, 50, 1),
        ]),
        "NET_LOGIC_3V3": MockPath([
            (10, 10, 0),
            (11, 10, 0),
            (11, 10, 1),  # Transition
            (12, 10, 1),
        ]),
    }
    
    # Mock design rules
    class MockDesignRules:
        pass
    
    # Apply via arrays
    via_placements = apply_via_arrays(routing_result, MockDesignRules(), cell_size_mm=0.1)
    
    print(f"\nDetected {len(via_placements)} via placements:\n")
    
    for via in via_placements:
        if via.is_array:
            print(f"✅ {via.net_name}: Via Array at ({via.x_mm:.1f}, {via.y_mm:.1f})")
            print(f"   {via.array_template.rows}×{via.array_template.cols} = {via.array_template.via_count} vias")
        else:
            print(f"  {via.net_name}: Single Via at ({via.x_mm:.1f}, {via.y_mm:.1f})")
    
    print("\n" + "=" * 60)
    print("✅ Automatic via array detection working")
