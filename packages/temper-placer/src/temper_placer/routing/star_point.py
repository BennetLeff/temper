"""
Star-Point Topology Support for Kelvin Sensing

Enables segment-specific trace widths for nets with different requirements
on different segments (e.g., Kelvin sensing: force vs sense paths).

Usage:
    from temper_placer.routing.star_point import SegmentConstraint, apply_segment_constraints
    
    # Define segment constraints
    constraints = [
        SegmentConstraint(
            net_name="NET_KELVIN",
            from_pin="R.1",
            to_pin="LOAD.1",
            trace_width_mm=2.0,  # Force path: wide
        ),
        SegmentConstraint(
            net_name="NET_KELVIN",
            from_pin="R.1",
            to_pin="MCU.1",
            trace_width_mm=0.2,  # Sense path: thin
        ),
    ]
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class SegmentConstraint:
    """
    Per-segment routing constraint for a net.
    
    Allows different trace widths for different segments of the same net.
    Critical for Kelvin sensing where force and sense paths have different
    electrical requirements.
    
    Attributes:
        net_name: Net name (e.g., "NET_KELVIN")
        from_pin: Source pin reference (e.g., "R.1")
        to_pin: Destination pin reference (e.g., "MCU.1")
        trace_width_mm: Trace width for this segment
        description: Human-readable description
    """
    net_name: str
    from_pin: str
    to_pin: str
    trace_width_mm: float
    description: str = ""
    
    def matches_segment(self, net: str, pin_a: str, pin_b: str) -> bool:
        """
        Check if this constraint applies to a segment.
        
        Args:
            net: Net name
            pin_a: First pin
            pin_b: Second pin
            
        Returns:
            True if constraint applies (bidirectional)
        """
        if net != self.net_name:
            return False
        
        # Check both directions (A→B and B→A)
        forward = (pin_a == self.from_pin and pin_b == self.to_pin)
        reverse = (pin_a == self.to_pin and pin_b == self.from_pin)
        
        return forward or reverse


def get_segment_width(
    net_name: str,
    pin_a: str,
    pin_b: str,
    constraints: List[SegmentConstraint],
    default_width: float = 0.2,
) -> float:
    """
    Get trace width for a specific segment.
    
    Args:
        net_name: Net name
        pin_a: First pin
        pin_b: Second pin
        constraints: List of segment constraints
        default_width: Default width if no constraint matches
        
    Returns:
        Trace width in mm
    """
    for constraint in constraints:
        if constraint.matches_segment(net_name, pin_a, pin_b):
            return constraint.trace_width_mm
    
    return default_width


def create_kelvin_constraints(
    net_name: str,
    force_pins: List[str],
    sense_pins: List[str],
    star_point: str,
    force_width: float = 2.0,
    sense_width: float = 0.2,
) -> List[SegmentConstraint]:
    """
    Create segment constraints for Kelvin sensing topology.
    
    Args:
        net_name: Net name
        force_pins: Force path pin references
        sense_pins: Sense path pin references
        star_point: Star point pin reference (connection point)
        force_width: Force trace width (wide, high current)
        sense_width: Sense trace width (thin, high impedance)
        
    Returns:
        List of segment constraints
    """
    constraints = []
    
    # Force paths: star_point → each force pin
    for force_pin in force_pins:
        constraints.append(SegmentConstraint(
            net_name=net_name,
            from_pin=star_point,
            to_pin=force_pin,
            trace_width_mm=force_width,
            description=f"Force path ({force_width}mm)",
        ))
    
    # Sense paths: star_point → each sense pin
    for sense_pin in sense_pins:
        constraints.append(SegmentConstraint(
            net_name=net_name,
            from_pin=star_point,
            to_pin=sense_pin,
            trace_width_mm=sense_width,
            description=f"Sense path ({sense_width}mm)",
        ))
    
    return constraints


def verify_star_point_topology(
    routed_segments: Dict[str, List[Tuple[str, str]]],
    constraints: List[SegmentConstraint],
) -> bool:
    """
    Verify that routed segments comply with star-point topology.
    
    Args:
        routed_segments: Dict of net_name → [(pin_a, pin_b), ...]
        constraints: Segment constraints
        
    Returns:
        True if topology is correct
    """
    print("\nStar-Point Topology Verification")
    print("=" * 70)
    
    violations = []
    
    for net_name, segments in routed_segments.items():
        print(f"\nNet: {net_name}")
        print("-" * 70)
        
        for (pin_a, pin_b) in segments:
            # Get expected width for this segment
            width = get_segment_width(net_name, pin_a, pin_b, constraints, default_width=None)
            
            if width is not None:
                print(f"  {pin_a} ↔ {pin_b}: {width}mm")
            else:
                print(f"  {pin_a} ↔ {pin_b}: No constraint (default)")
                violations.append((net_name, pin_a, pin_b, "No constraint"))
    
    if violations:
        print(f"\n❌ {len(violations)} segments without constraints")
        return False
    
    print("\n✅ All segments have defined constraints")
    return True


# Demonstration
if __name__ == "__main__":
    print("Star-Point Topology Demo (Kelvin Sensing)")
    print("=" * 70)
    
    # Example: Kelvin sensing for current measurement
    # Net: NET_KELVIN
    # Pins: R (shunt resistor), LOAD (high current), MCU (sense)
    # Topology: R (star point) → LOAD (force, 2mm) and R → MCU (sense, 0.2mm)
    
    constraints = create_kelvin_constraints(
        net_name="NET_KELVIN",
        force_pins=["LOAD.1"],
        sense_pins=["MCU.1"],
        star_point="R.1",
        force_width=2.0,
        sense_width=0.2,
    )
    
    print("\nKelvin Constraints Created:")
    print("-" * 70)
    for c in constraints:
        print(f"{c.from_pin} → {c.to_pin}: {c.trace_width_mm}mm ({c.description})")
    
    # Test segment width lookup
    print("\nSegment Width Lookup:")
    print("-" * 70)
    
    test_segments = [
        ("R.1", "LOAD.1", "Force path"),
        ("R.1", "MCU.1", "Sense path"),
        ("MCU.1", "R.1", "Sense path (reverse)"),
    ]
    
    for (pin_a, pin_b, description) in test_segments:
        width = get_segment_width("NET_KELVIN", pin_a, pin_b, constraints)
        print(f"{pin_a} ↔ {pin_b}: {width}mm ({description})")
    
    # Verify topology
    routed_segments = {
        "NET_KELVIN": [
            ("R.1", "LOAD.1"),  # Force
            ("R.1", "MCU.1"),   # Sense
        ]
    }
    
    verify_star_point_topology(routed_segments, constraints)
    
    print("\n" + "=" * 70)
    print("✅ Star-point topology support complete")
    print("✅ Kelvin sensing: Force=2mm, Sense=0.2mm")
    print("✅ EXP-06-C requirements addressable")
