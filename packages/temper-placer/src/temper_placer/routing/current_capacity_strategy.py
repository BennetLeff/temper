"""
Current capacity routing strategy selection.

Automatically selects appropriate routing method based on net current requirements:
- High current (>10A): Plane connection only
- Medium current (5-10A): Wide traces with via arrays
- Low current (<5A): Standard maze routing
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.io.config_loader import Zone


class CurrentCapacityStrategy(Enum):
    """Routing strategy based on current capacity requirements."""
    
    PLANE_VIA_ONLY = "plane_via_only"
    """High-current nets (>10A): Connect to copper plane via direct vias.
    
    No traced routing - plane carries current, vias provide redundant connections.
    Used for: AC mains, DC bus, high-power distribution
    """
    
    WIDE_TRACE_WITH_VIA_ARRAY = "wide_trace_via_array"
    """Medium-current nets (5-10A): Wide traces with via arrays for layer transitions.
    
    Uses via templates (Via2x2, Via3x3) for adequate current capacity.
    Used for: Power delivery, ground distribution, gate drive
    """
    
    STANDARD_MAZE = "standard_maze"
    """Low-current nets (<5A): Standard A* maze routing with single vias.
    
    Normal routing - minimal special handling.
    Used for: Signals, low-power traces, control lines
    """


def select_current_capacity_strategy(
    net_name: str,
    design_rules: "DesignRules",
    zones: list["Zone"],
) -> CurrentCapacityStrategy:
    """
    Select routing strategy based on current requirements and zone assignment.
    
    Decision matrix:
        Current > 10A + Zone     → PLANE_VIA_ONLY
        Current > 10A + No Zone  → ERROR (caught in config validation)
        Current 5-10A + Zone     → PLANE_VIA_ONLY (preferred for thermal)
        Current 5-10A + No Zone  → WIDE_TRACE_WITH_VIA_ARRAY
        Current < 5A             → STANDARD_MAZE
    
    Args:
        net_name: Net to route
        design_rules: Design rules containing net class assignments
        zones: List of zones/pours for plane detection
        
    Returns:
        CurrentCapacityStrategy enum value
        
    Raises:
        RuntimeError: If high-current net has no zone (should be caught in config validation)
        
    Examples:
        >>> strategy = select_current_capacity_strategy("AC_L", design_rules, zones)
        >>> if strategy == CurrentCapacityStrategy.PLANE_VIA_ONLY:
        ...     return plane_router.route_to_plane(net, pins, zone)
        >>> elif strategy == CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY:
        ...     return maze_router.route_rrr(net, pins)  # Uses via arrays
        >>> else:
        ...     return maze_router.route(net, pins)  # Standard
    """
    from temper_placer.core.ipc2221 import estimate_current_from_net_class
    
    # Get net class and rules
    rules = design_rules.get_rules_for_net(net_name)
    
    # Determine current capacity
    if hasattr(rules, 'max_current_rating') and rules.max_current_rating is not None:
        current_a = rules.max_current_rating
    else:
        # Estimate from trace width
        current_a = estimate_current_from_net_class(rules.trace_width)
    
    # Check if net class assigned to zone/pour
    net_class_name = design_rules.net_class_assignments.get(net_name, "Signal")
    has_zone = any(
        net_class_name in zone.net_classes
        for zone in zones
    )
    
    # Strategy selection
    if current_a > 10.0:
        if has_zone:
            return CurrentCapacityStrategy.PLANE_VIA_ONLY
        else:
            # This should have been caught in config validation
            raise RuntimeError(
                f"Cannot route high-current net '{net_name}' ({current_a:.1f}A): "
                f"No zone assignment. This should have been caught during config loading."
            )
    
    elif current_a > 5.0:
        # Medium current: prefer plane if available, otherwise wide trace
        if has_zone:
            return CurrentCapacityStrategy.PLANE_VIA_ONLY  # Use plane for better thermal
        else:
            return CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY
    
    else:
        # Low current: standard routing
        return CurrentCapacityStrategy.STANDARD_MAZE


def get_strategy_description(strategy: CurrentCapacityStrategy) -> str:
    """Get human-readable description of routing strategy."""
    descriptions = {
        CurrentCapacityStrategy.PLANE_VIA_ONLY: "Plane connection (direct vias to copper pour)",
        CurrentCapacityStrategy.WIDE_TRACE_WITH_VIA_ARRAY: "Wide trace routing with via arrays",
        CurrentCapacityStrategy.STANDARD_MAZE: "Standard A* maze routing",
    }
    return descriptions[strategy]
