"""
Plane Connection Router for high-current nets.

Routes high-current nets (>10A) by connecting component pads directly to
copper planes/pours via via arrays. No traced routing - the plane itself
carries the current load.

This is the professional PCB design approach for power distribution:
- AC mains (100-240VAC, 20A+)
- DC bus (high voltage, high current)
- Ground planes (return current)
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules, ViaTemplate
    from temper_placer.io.config_loader import Zone
    from temper_placer.routing.maze_router import GridCell


@dataclass
class PlaneConnection:
    """Result of connecting a pin to a plane."""
    
    pin_position: tuple[float, float]  # World coordinates
    zone_entry_point: tuple[float, float]  # Nearest point in zone
    via_positions: list[tuple[float, float]]  # Via array positions
    via_template: str  # Via template used (e.g., "Via4x4")
    success: bool
    failure_reason: str | None = None


class PlaneConnectionRouter:
    """
    Router for high-current nets that connect directly to copper planes.
    
    Instead of routing traces, this router:
    1. Validates component pads are within zone boundaries
    2. Places via arrays from pads to plane
    3. Optionally adds thermal relief spokes
    
    The copper plane carries the current - vias provide redundant connections.
    """
    
    def __init__(
        self,
        design_rules: "DesignRules",
        cell_size_mm: float = 0.1,
    ):
        """
        Initialize plane connection router.
        
        Args:
            design_rules: Design rules with via templates
            cell_size_mm: Grid cell size for via placement
        """
        self.design_rules = design_rules
        self.cell_size_mm = cell_size_mm
    
    def find_zone_for_net(
        self,
        net_name: str,
        zones: list["Zone"],
    ) -> "Zone | None":
        """
        Find the zone/pour assigned to a net.
        
        Args:
            net_name: Net to search for
            zones: List of available zones
            
        Returns:
            Zone if found, None otherwise
        """
        # Get net class for this net
        net_class = self.design_rules.net_class_assignments.get(net_name, "Signal")
        
        # Find zone that includes this net class
        for zone in zones:
            if net_class in zone.net_classes:
                return zone
        
        return None
    
    def validate_pin_in_zone(
        self,
        pin_position: tuple[float, float],
        zone: "Zone",
    ) -> tuple[bool, str | None]:
        """
        Validate that a pin is within zone boundaries.
        
        Args:
            pin_position: Pin position in world coordinates
            zone: Zone to check
            
        Returns:
            (is_valid, error_message)
        """
        # TODO: Implement actual polygon containment check
        # For now, assume pins are valid if zone exists
        # In production, would check zone.polygon.contains(pin_position)
        
        # Simple bounding box check as placeholder
        if hasattr(zone, 'bounds'):
            x, y = pin_position
            min_x, min_y, max_x, max_y = zone.bounds
            if not (min_x <= x <= max_x and min_y <= y <= max_y):
                return False, f"Pin at ({x:.2f}, {y:.2f}) outside zone bounds"
        
        return True, None
    
    def connect_pin_to_plane(
        self,
        pin_position: tuple[float, float],
        zone: "Zone",
        via_template_name: str,
    ) -> PlaneConnection:
        """
        Connect a single pin to a copper plane via via array.
        
        Args:
            pin_position: Pin position in world coordinates (mm)
            zone: Zone/pour to connect to
            via_template_name: Via array template (e.g., "Via4x4")
            
        Returns:
            PlaneConnection result
        """
        # 1. Validate pin is in zone
        is_valid, error = self.validate_pin_in_zone(pin_position, zone)
        if not is_valid:
            return PlaneConnection(
                pin_position=pin_position,
                zone_entry_point=pin_position,
                via_positions=[],
                via_template=via_template_name,
                success=False,
                failure_reason=error,
            )
        
        # 2. Get via template
        template = self.design_rules.via_templates.get(via_template_name)
        if template is None:
            return PlaneConnection(
                pin_position=pin_position,
                zone_entry_point=pin_position,
                via_positions=[],
                via_template=via_template_name,
                success=False,
                failure_reason=f"Via template '{via_template_name}' not found",
            )
        
        # 3. Calculate via array positions
        # Center the array on the pin position
        via_positions = self._calculate_via_array_positions(
            center=pin_position,
            template=template,
        )
        
        # 4. Zone entry point is the pin itself (direct connection)
        # In a real implementation, might find nearest zone edge for optimal connection
        zone_entry_point = pin_position
        
        return PlaneConnection(
            pin_position=pin_position,
            zone_entry_point=zone_entry_point,
            via_positions=via_positions,
            via_template=via_template_name,
            success=True,
            failure_reason=None,
        )
    
    def _calculate_via_array_positions(
        self,
        center: tuple[float, float],
        template: "ViaTemplate",
    ) -> list[tuple[float, float]]:
        """
        Calculate positions for via array centered on a point.
        
        Args:
            center: Center position (x, y) in mm
            template: Via template defining array pattern
            
        Returns:
            List of (x, y) positions for each via
        """
        positions = []
        cx, cy = center
        
        # Calculate grid of vias
        for row in range(template.rows):
            for col in range(template.cols):
                # Offset from center (center array on pin)
                offset_x = (col - (template.cols - 1) / 2.0) * template.pitch_mm
                offset_y = (row - (template.rows - 1) / 2.0) * template.pitch_mm
                
                via_x = cx + offset_x
                via_y = cy + offset_y
                
                positions.append((via_x, via_y))
        
        return positions
    
    def route_net_to_plane(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        zones: list["Zone"],
    ) -> list[PlaneConnection]:
        """
        Route a net by connecting all pins directly to assigned plane.
        
        Args:
            net_name: Net name
            pin_positions: List of pin positions in world coordinates
            zones: List of available zones
            
        Returns:
            List of PlaneConnection results (one per pin)
            
        Examples:
            >>> connections = router.route_net_to_plane("AC_L", pins, zones)
            >>> if all(c.success for c in connections):
            ...     print(f"Connected {len(connections)} pins to plane")
            >>> else:
            ...     failures = [c for c in connections if not c.success]
            ...     print(f"Failed: {[c.failure_reason for c in failures]}")
        """
        # 1. Find zone for this net
        zone = self.find_zone_for_net(net_name, zones)
        if zone is None:
            # Return failure for all pins
            return [
                PlaneConnection(
                    pin_position=pos,
                    zone_entry_point=pos,
                    via_positions=[],
                    via_template="Via1x1",
                    success=False,
                    failure_reason=f"No zone found for net '{net_name}'",
                )
                for pos in pin_positions
            ]
        
        # 2. Get via template for net class
        net_class = self.design_rules.net_class_assignments.get(net_name, "Signal")
        rules = self.design_rules.net_classes.get(net_class)
        via_template_name = rules.via_template if rules else "Via1x1"
        
        # 3. Connect each pin to plane
        connections = []
        for pin_pos in pin_positions:
            connection = self.connect_pin_to_plane(
                pin_position=pin_pos,
                zone=zone,
                via_template_name=via_template_name,
            )
            connections.append(connection)
        
        return connections
