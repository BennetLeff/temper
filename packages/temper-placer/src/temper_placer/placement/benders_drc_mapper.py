"""
Map DRC violations to ILP cuts.

Converts KiCad DRC violations into component spacing constraints
for the Benders Master Problem.
"""

from __future__ import annotations
import math
from typing import TYPE_CHECKING

from temper_placer.placement.router_failure_types import BlockingPair

if TYPE_CHECKING:
    from temper_placer.io.kicad_drc import DRCViolation
    from temper_placer.router_v6.stage0_data import ParsedPCB


# DRC violation types that are actionable (can be fixed by placement)
ACTIONABLE_VIOLATION_TYPES = {
    "tracks_crossing",
    "clearance",
    "unconnected_items",
    "short",
    "track_dangling",
    "copper_edge_clearance",
}

# Cosmetic violations that should be ignored
COSMETIC_VIOLATION_TYPES = {
    "lib_footprint_issues",
    "silk_over_copper",
    "silk_overlap",
    "courtyards_overlap",  # Usually intentional
}


def is_actionable_violation(violation: DRCViolation) -> bool:
    """Check if a DRC violation is actionable (can be fixed by placement)."""
    return violation.type in ACTIONABLE_VIOLATION_TYPES


def map_drc_violations_to_components(
    violations: list[DRCViolation],
    pcb: ParsedPCB,
    component_positions: dict[str, tuple[float, float]],
    verbose: bool = False,
) -> list[BlockingPair]:
    """
    Map DRC violations to component pairs that need more spacing.
    
    Strategy:
    1. Filter to actionable violations only
    2. Extract component references from violation items
    3. Calculate required spacing increase
    4. Return BlockingPair objects
    
    Args:
        violations: List of DRC violations from kicad-cli
        pcb: Parsed PCB data
        component_positions: Current component positions
        verbose: Print debug info
        
    Returns:
        List of BlockingPair objects
    """
    blocking_pairs = []
    
    for violation in violations:
        if not is_actionable_violation(violation):
            continue
        
        if verbose:
            print(f"\n🔍 DRC Violation: {violation.type}")
            print(f"   Description: {violation.description}")
        
        # Extract component references from violation items
        components = _extract_components_from_violation(violation, verbose=verbose)
        
        if len(components) < 2:
            if verbose:
                print(f"   ⚠️  Could not identify component pair")
            continue
        
        # Create blocking pairs
        for i, comp_a in enumerate(components):
            for comp_b in components[i + 1 :]:
                pos_a = component_positions.get(comp_a)
                pos_b = component_positions.get(comp_b)
                
                if not pos_a or not pos_b:
                    continue
                
                distance = math.sqrt(
                    (pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2
                )
                
                # Estimate required spacing based on violation type
                required = _estimate_required_spacing(
                    violation.type, distance, violation.severity
                )
                
                # High confidence - this is a real DRC error
                confidence = 0.9 if violation.severity == "error" else 0.7
                
                blocking_pairs.append(
                    BlockingPair(
                        component_a=comp_a,
                        component_b=comp_b,
                        failed_net=f"DRC:{violation.type}",
                        current_spacing=distance,
                        required_spacing=required,
                        confidence=confidence,
                        reason=f"drc_{violation.type}",
                    )
                )
                
                if verbose:
                    print(
                        f"   → {comp_a} ↔ {comp_b}: "
                        f"current={distance:.1f}mm, need={required:.1f}mm"
                    )
    
    if verbose:
        print(f"\n📊 Mapped {len(blocking_pairs)} DRC violations to component pairs")
    
    return blocking_pairs


def _extract_components_from_violation(
    violation: DRCViolation, verbose: bool = False
) -> list[str]:
    """
    Extract component references from a DRC violation.
    
    DRC violations reference tracks, pads, vias, etc.
    We need to map these to component references.
    """
    components = set()
    
    # Parse the description to extract component references
    # KiCad format: "Items: U1 Pad 5, R3 Pad 1"
    # or: "Items: Track on F.Cu, U2 Pad 3"
    
    description = violation.description
    
    # Look for patterns like "U1 Pad", "R3 Pad", "C5 Pad"
    import re
    
    # Match component references (e.g., U1, R3, C5, Q2)
    # Common prefixes: U, R, C, L, Q, D, J, SW, etc.
    pattern = r'\b([A-Z]+\d+)\s+(?:Pad|pad)'
    matches = re.findall(pattern, description)
    
    components.update(matches)
    
    if verbose and components:
        print(f"   Components: {sorted(components)}")
    
    return list(components)


def _estimate_required_spacing(
    violation_type: str, current_distance: float, severity: str
) -> float:
    """
    Estimate required spacing based on violation type.
    
    Args:
        violation_type: Type of DRC violation
        current_distance: Current distance between components
        severity: Violation severity ("error", "warning", "exclusion")
        
    Returns:
        Required spacing in mm
    """
    # Base increases by violation type
    increases = {
        "tracks_crossing": 3.0,  # Need significant separation
        "clearance": 2.0,  # Add clearance margin
        "short": 5.0,  # Serious - need large separation
        "unconnected_items": 1.0,  # Routing issue, not spacing
        "copper_edge_clearance": 2.0,  # Edge clearance
    }
    
    base_increase = increases.get(violation_type, 2.0)
    
    # More severe violations need more spacing
    if severity == "error":
        base_increase *= 1.5
    
    return current_distance + base_increase
