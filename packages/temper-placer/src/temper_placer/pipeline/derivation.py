"""
Physics-based constraint derivation for PCB placement.

This module derives geometric placement constraints from high-level
physical performance specifications (EMI, Thermal, Signal Integrity).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.core.specification import PcbSpecification
    from temper_placer.core.netlist import Netlist


def derive_constraints_from_spec(
    spec: PcbSpecification,
    netlist: Netlist,
) -> dict[str, Any]:
    """
    Derive geometric constraints from physical specifications.
    
    Returns a dictionary of derived parameters (e.g. max distances).
    """
    derived = {}
    
    # 1. EMI -> Max Distance
    for loop_name, max_area in spec.emi.max_loop_area_mm2.items():
        # L = sqrt(Area). Max side length of a square loop.
        max_side = math.sqrt(max_area)
        # Conservative estimate for max component spacing (center-to-center)
        # Assuming 20% routing overhead
        derived[f"{loop_name}_max_dist"] = max_side * 0.8
        
    # 2. Thermal -> Min Spacing
    # Simple model: heat sources should be spaced to avoid thermal overlap
    # Required spacing proportional to power dissipation
    power_map = spec.thermal.power_dissipation
    for ref, power in power_map.items():
        # Heuristic: 2mm per Watt spacing
        derived[f"{ref}_min_clearance"] = power * 2.0
        
    # 3. Signal Integrity -> Max Length
    for net_name, max_len in spec.signal_integrity.max_length_mm.items():
        # Max placement distance should be less than max length
        # Assuming 1.5x routing overhead (Manhattan + detours)
        derived[f"{net_name}_max_placement_dist"] = max_len / 1.5
        
    # 4. Safety -> Isolation (Creepage/Clearance)
    # Default to 6.5mm for reinforced isolation (340V)
    derived["hv_lv_isolation_mm"] = 6.5
    
    return derived


def apply_derived_constraints(
    netlist: Netlist,
    derived: dict[str, Any],
    pcl_constraints: Any = None,
) -> Any:
    """
    Apply derived constraints back to PCL constraint collection.

    When pcl_constraints is provided, synthesized constraints from
    derivation are added to it. Returns the modified collection or
    netlist fallback.

    This resolves the TODO at derivation.py:65 — back-propagation
    of derived parameters to the PCL constraint IR.
    """
    if pcl_constraints is None:
        return netlist

    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

    for key, value in derived.items():
        if key.endswith("_min_clearance"):
            ref = key.replace("_min_clearance", "")
            pcl_constraints.add(
                SeparatedConstraint(
                    a=ref,
                    b="*",
                    min_distance_mm=float(value),
                    tier=ConstraintTier.STRONG,
                    because=f"Derived from thermal spec: {ref} min clearance {value}mm",
                )
            )

    return pcl_constraints
