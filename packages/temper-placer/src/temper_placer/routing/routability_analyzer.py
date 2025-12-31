"""
Routability Analysis Pre-Check for PCB Design.

Analyzes component pins for escape route feasibility BEFORE routing begins.
Reports DFM (Design for Manufacturing) issues and suggests solutions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Dict
import math


class RoutabilityIssue(Enum):
    """Types of routability issues."""
    TRAPPED_PIN = "trapped_pin"  # Pin has no escape route
    DENSE_CLUSTER = "dense_cluster"  # Pins too close, DRC violations likely
    BLOCKED_ESCAPE = "blocked_escape"  # Escape path blocked by other components
    INSUFFICIENT_CLEARANCE = "insufficient_clearance"  # Spacing violates DRC
    CENTER_PIN_NO_CHANNEL = "center_pin_no_channel"  # Center pin in saturated grid


class RoutabilitySeverity(Enum):
    """Severity levels for routability issues."""
    ERROR = "error"  # Will definitely fail routing
    WARNING = "warning"  # May fail routing
    INFO = "info"  # Suboptimal but routable


@dataclass
class RoutabilityReport:
    """Result of routability analysis for a single pin."""
    component_ref: str
    pin_name: str
    position: Tuple[float, float]
    issue: RoutabilityIssue | None
    severity: RoutabilitySeverity
    message: str
    suggested_solution: str | None = None
    
    @property
    def is_routable(self) -> bool:
        """Check if pin is routable (no ERROR severity issues)."""
        return self.severity != RoutabilitySeverity.ERROR


def analyze_pin_escape_routes(
    pin_positions: List[Tuple[str, str, float, float]],  # (component_ref, pin_name, x, y)
    component_bounds: Dict[str, Tuple[float, float, float, float]],  # ref -> (x, y, w, h)
    min_clearance: float = 0.2,  # mm
    min_trace_width: float = 0.1,  # mm
    grid_cell_size: float = 0.5,  # mm
) -> List[RoutabilityReport]:
    """Analyze escape routes for all pins.
    
    Args:
        pin_positions: List of (component_ref, pin_name, x, y)
        component_bounds: Bounding boxes for each component
        min_clearance: Minimum clearance for DRC (mm)
        min_trace_width: Minimum trace width (mm)
        grid_cell_size: Router grid resolution (mm)
        
    Returns:
        List of RoutabilityReport objects (one per issue found)
    """
    reports = []
    
    # Required space = trace_width/2 + clearance
    required_space = (min_trace_width / 2) + min_clearance
    
    for comp_ref, pin_name, px, py in pin_positions:
        # Check for nearby pins (potential trapped situation)
        nearby_pins = []
        for other_comp, other_pin, ox, oy in pin_positions:
            if (comp_ref, pin_name) == (other_comp, other_pin):
                continue
            distance = math.sqrt((px - ox)**2 + (py - oy)**2)
            # Check wider radius for potential blockage
            if distance < 5.0:  # Within 5mm
                nearby_pins.append((other_comp, other_pin, ox, oy, distance))
        
        # Check if pin is surrounded on all 4 sides
        # A direction is "blocked" if there's a pin within required_space in that direction
        directions = {
            "N": False,  # North blocked?
            "S": False,  # South blocked?
            "E": False,  # East blocked?
            "W": False,  # West blocked?
        }
        
        blocking_threshold = required_space * 2  # Pin is blocking if within 2x required space
        
        for _, _, ox, oy, dist in nearby_pins:
            if dist > blocking_threshold:
                continue
                
            dx = ox - px
            dy = oy - py
            
            # Determine primary direction
            if abs(dx) > abs(dy):
                if dx > 0:
                    directions["E"] = True
                else:
                    directions["W"] = True
            else:
                if dy > 0:
                    directions["N"] = True
                else:
                    directions["S"] = True
        
        # Check if trapped (all directions blocked)
        blocked_count = sum(directions.values())
        
        if blocked_count >= 4:
            reports.append(RoutabilityReport(
                component_ref=comp_ref,
                pin_name=pin_name,
                position=(px, py),
                issue=RoutabilityIssue.TRAPPED_PIN,
                severity=RoutabilitySeverity.ERROR,
                message=f"Pin {pin_name} on {comp_ref} is trapped with no escape route",
                suggested_solution="Use via-in-pad, depopulate adjacent pins, or increase pitch",
            ))
        elif blocked_count == 3:
            reports.append(RoutabilityReport(
                component_ref=comp_ref,
                pin_name=pin_name,
                position=(px, py),
                issue=RoutabilityIssue.BLOCKED_ESCAPE,
                severity=RoutabilitySeverity.WARNING,
                message=f"Pin {pin_name} on {comp_ref} has only 1 escape direction",
                suggested_solution="Consider adding fanout via or adjusting placement",
            ))
        
        # Check for dense clusters (>= 4 pins within 2mm)
        if len(nearby_pins) >= 4:
            avg_distance = sum(d for _, _, _, _, d in nearby_pins[:4]) / 4
            if avg_distance < 2.0:
                reports.append(RoutabilityReport(
                    component_ref=comp_ref,
                    pin_name=pin_name,
                    position=(px, py),
                    issue=RoutabilityIssue.DENSE_CLUSTER,
                    severity=RoutabilitySeverity.WARNING,
                    message=f"Pin {pin_name} on {comp_ref} is in a dense cluster (avg spacing {avg_distance:.2f}mm)",
                    suggested_solution="Enable escape routing with dog-bone fanouts",
                ))
    
    return reports


def check_center_pin_accessibility(
    pin_positions: List[Tuple[str, str, float, float]],
    component_center: Tuple[float, float],
    component_size: Tuple[float, float],  # (width, height)
) -> List[RoutabilityReport]:
    """Check if center pins in a grid have escape channels.
    
    This specifically checks for the "saturated grid" problem where
    center pins have no escape route.
    """
    reports = []
    cx, cy = component_center
    width, height = component_size
    
    # Define "center region" as inner 30% of component
    center_radius = min(width, height) * 0.15
    
    for comp_ref, pin_name, px, py in pin_positions:
        distance_from_center = math.sqrt((px - cx)**2 + (py - cy)**2)
        
        if distance_from_center < center_radius:
            # This is a center pin - check if it has an escape corridor
            # For now, just flag it as INFO
            reports.append(RoutabilityReport(
                component_ref=comp_ref,
                pin_name=pin_name,
                position=(px, py),
                issue=RoutabilityIssue.CENTER_PIN_NO_CHANNEL,
                severity=RoutabilitySeverity.INFO,
                message=f"Center pin {pin_name} may require channel reservation",
                suggested_solution="Reserve routing channel (depopulate row/col) or use escape phase",
            ))
    
    return reports


def generate_dfm_report(reports: List[RoutabilityReport]) -> str:
    """Generate human-readable DFM report.
    
    Args:
        reports: List of routability reports
        
    Returns:
        Formatted report string
    """
    if not reports:
        return "✓ No routability issues found. All pins are routable."
    
    lines = ["# Routability Analysis Report", ""]
    
    # Group by severity
    errors = [r for r in reports if r.severity == RoutabilitySeverity.ERROR]
    warnings = [r for r in reports if r.severity == RoutabilitySeverity.WARNING]
    infos = [r for r in reports if r.severity == RoutabilitySeverity.INFO]
    
    if errors:
        lines.append("## ERRORS (Will Fail Routing)")
        lines.append("")
        for r in errors:
            lines.append(f"- **{r.component_ref}.{r.pin_name}** at ({r.position[0]:.2f}, {r.position[1]:.2f})")
            lines.append(f"  - Issue: {r.message}")
            if r.suggested_solution:
                lines.append(f"  - Solution: {r.suggested_solution}")
        lines.append("")
    
    if warnings:
        lines.append("## WARNINGS (May Fail Routing)")
        lines.append("")
        for r in warnings:
            lines.append(f"- **{r.component_ref}.{r.pin_name}** at ({r.position[0]:.2f}, {r.position[1]:.2f})")
            lines.append(f"  - Issue: {r.message}")
            if r.suggested_solution:
                lines.append(f"  - Solution: {r.suggested_solution}")
        lines.append("")
    
    if infos:
        lines.append("## INFO (Suboptimal but Routable)")
        lines.append("")
        for r in infos:
            lines.append(f"- **{r.component_ref}.{r.pin_name}**: {r.message}")
        lines.append("")
    
    # Summary
    lines.append("## Summary")
    lines.append(f"- Errors: {len(errors)}")
    lines.append(f"- Warnings: {len(warnings)}")
    lines.append(f"- Info: {len(infos)}")
    lines.append("")
    
    if errors:
        lines.append("**Action Required**: Fix ERROR-level issues before routing.")
    elif warnings:
        lines.append("**Recommended**: Address WARNING issues to improve routing success rate.")
    else:
        lines.append("**Status**: No critical issues. Design is routable.")
    
    return "\n".join(lines)
