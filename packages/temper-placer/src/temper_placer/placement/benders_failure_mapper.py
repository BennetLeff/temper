"""
Map routing failures to blocking component pairs.

Converts spatial routing failures into component pairs that need
more spacing, which can then be converted to ILP cuts.
"""

from __future__ import annotations
import math
from typing import TYPE_CHECKING

from temper_placer.placement.router_failure_types import BlockingPair, SpatialFailureInfo

if TYPE_CHECKING:
    from temper_placer.router_v6.astar_pathfinding import RoutingFailureReport
    from temper_placer.router_v6.stage0_data import ParsedPCB


def map_failures_to_components(
    failures: list[RoutingFailureReport],
    pcb: ParsedPCB,
    component_positions: dict[str, tuple[float, float]],
    verbose: bool = False,
) -> list[BlockingPair]:
    """
    Map routing failures to component pairs that need more spacing.
    
    ENHANCED STRATEGY (Phase 5):
    - Use precise diagnostics when available (blocking_components, suggested_spacing_mm)
    - Fall back to heuristics for legacy failures
    - Prioritize high-confidence data from router
    
    Strategy:
    1. Check if failure has enhanced diagnostics (blocking_components, suggested_spacing_mm)
    2. If yes: Use precise data with high confidence
    3. If no: Fall back to heuristics (proximity, blocking nets, topology)
    
    Args:
        failures: List of routing failure reports from router
        pcb: Parsed PCB data with nets and components
        component_positions: Current component positions {ref: (x, y)}
        verbose: Print debug information
        
    Returns:
        List of BlockingPair objects with confidence scores
    """
    blocking_pairs = []
    
    for failure in failures:
        # ENHANCED: Check if router provided precise diagnostics
        if failure.blocking_components and failure.suggested_spacing_mm and failure.confidence > 0:
            if verbose:
                print(f"\n🎯 Using PRECISE diagnostics for {failure.net_name}")
                print(f"   Blocking: {failure.blocking_components}")
                print(f"   Suggested spacing: {failure.suggested_spacing_mm}mm")
                print(f"   Confidence: {failure.confidence:.0%}")
            
            # Get components on this net
            net_components = set()
            for net in pcb.nets:
                if net.name == failure.net_name:
                    for ref, pin in net.pins:
                        net_components.add(ref)
                    break
            
            # Create pairs between net components and blocking components
            for net_comp in net_components:
                for blocking_comp in failure.blocking_components:
                    if net_comp == blocking_comp:
                        continue
                    
                    pos_a = component_positions.get(net_comp)
                    pos_b = component_positions.get(blocking_comp)
                    
                    if not pos_a or not pos_b:
                        continue
                    
                    distance = math.sqrt(
                        (pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2
                    )
                    
                    blocking_pairs.append(
                        BlockingPair(
                            component_a=net_comp,
                            component_b=blocking_comp,
                            failed_net=failure.net_name,
                            current_spacing=distance,
                            required_spacing=distance + failure.suggested_spacing_mm,
                            confidence=failure.confidence,  # Use router's confidence
                            reason="router_precise_diagnostics",
                        )
                    )
            
            continue  # Skip heuristics for this failure
        
        # FALLBACK: Use heuristics for legacy failures
        if verbose:
            print(f"\n🔍 Analyzing failure: {failure.net_name}")
            print(f"   Reason: {failure.failure_reason}")
            print(f"   Blocking nets: {failure.blocking_nets}")
        
        # Find the net in PCB data
        net = None
        for n in pcb.nets:
            if n.name == failure.net_name:
                net = n
                break
        
        if not net:
            if verbose:
                print(f"   ⚠️  Net not found in PCB data")
            continue
        
        # Get components on this net
        net_components = set()
        for ref, pin in net.pins:
            net_components.add(ref)
        
        if verbose:
            print(f"   Components on net: {sorted(net_components)}")
        
        # Strategy 1: Blocking nets indicate nearby components
        if failure.blocking_nets:
            pairs = _find_pairs_via_blocking_nets(
                net_components=net_components,
                blocking_nets=failure.blocking_nets,
                pcb=pcb,
                component_positions=component_positions,
                failed_net=failure.net_name,
                verbose=verbose,
            )
            blocking_pairs.extend(pairs)
        
        # Strategy 2: Congestion region indicates spatial proximity
        if failure.congestion_region:
            pairs = _find_pairs_via_congestion_region(
                net_components=net_components,
                congestion_region=failure.congestion_region,
                component_positions=component_positions,
                failed_net=failure.net_name,
                verbose=verbose,
            )
            blocking_pairs.extend(pairs)
        
        # Strategy 3: For multi-pin nets, check all pairwise distances
        if len(net_components) > 2:
            pairs = _find_pairs_via_topology(
                net_components=net_components,
                component_positions=component_positions,
                failed_net=failure.net_name,
                verbose=verbose,
            )
            blocking_pairs.extend(pairs)
    
    # Deduplicate and merge confidence scores
    merged = _merge_blocking_pairs(blocking_pairs, verbose=verbose)
    
    # Sort by confidence (highest first)
    merged.sort(key=lambda p: p.confidence, reverse=True)
    
    if verbose:
        print(f"\n📊 Found {len(merged)} unique blocking pairs")
        for pair in merged[:5]:  # Show top 5
            print(f"   {pair}")
    
    return merged


def _find_pairs_via_blocking_nets(
    net_components: set[str],
    blocking_nets: list[str],
    pcb: ParsedPCB,
    component_positions: dict[str, tuple[float, float]],
    failed_net: str,
    verbose: bool,
) -> list[BlockingPair]:
    """Find blocking pairs based on which nets are blocking."""
    pairs = []
    
    # Find components on blocking nets
    blocking_components = set()
    for net_name in blocking_nets:
        for net in pcb.nets:
            if net.name == net_name:
                for ref, pin in net.pins:
                    blocking_components.add(ref)
                break
    
    if verbose:
        print(f"   Blocking components: {sorted(blocking_components)}")
    
    # Create pairs between net components and blocking components
    for comp_a in net_components:
        for comp_b in blocking_components:
            if comp_a == comp_b:
                continue
            
            pos_a = component_positions.get(comp_a)
            pos_b = component_positions.get(comp_b)
            
            if not pos_a or not pos_b:
                continue
            
            distance = math.sqrt(
                (pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2
            )
            
            # Heuristic: if components are close (<20mm), they might be blocking
            if distance < 20.0:
                # Confidence based on distance (closer = higher confidence)
                confidence = max(0.3, 1.0 - (distance / 20.0))
                
                # Estimate required spacing (add 5mm buffer)
                required = distance + 5.0
                
                pairs.append(
                    BlockingPair(
                        component_a=comp_a,
                        component_b=comp_b,
                        failed_net=failed_net,
                        current_spacing=distance,
                        required_spacing=required,
                        confidence=confidence,
                        reason="blocking_net_proximity",
                    )
                )
    
    return pairs


def _find_pairs_via_congestion_region(
    net_components: set[str],
    congestion_region: tuple[float, float],
    component_positions: dict[str, tuple[float, float]],
    failed_net: str,
    verbose: bool,
) -> list[BlockingPair]:
    """Find blocking pairs based on congestion region."""
    pairs = []
    
    cx, cy = congestion_region
    search_radius = 15.0  # mm
    
    # Find all components near congestion point
    nearby = []
    for ref, (x, y) in component_positions.items():
        distance = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if distance < search_radius:
            nearby.append((ref, distance))
    
    nearby.sort(key=lambda x: x[1])  # Sort by distance
    
    if verbose:
        print(f"   Components near congestion ({cx:.1f}, {cy:.1f}): {[r for r, _ in nearby[:5]]}")
    
    # Create pairs between net components and nearby components
    for comp_a in net_components:
        pos_a = component_positions.get(comp_a)
        if not pos_a:
            continue
        
        for comp_b, dist_to_congestion in nearby:
            if comp_a == comp_b:
                continue
            
            pos_b = component_positions.get(comp_b)
            if not pos_b:
                continue
            
            distance = math.sqrt(
                (pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2
            )
            
            if distance < 15.0:
                # Confidence based on proximity to congestion point
                confidence = max(0.2, 1.0 - (dist_to_congestion / search_radius))
                
                required = distance + 4.0
                
                pairs.append(
                    BlockingPair(
                        component_a=comp_a,
                        component_b=comp_b,
                        failed_net=failed_net,
                        current_spacing=distance,
                        required_spacing=required,
                        confidence=confidence,
                        reason="congestion_region_proximity",
                    )
                )
    
    return pairs


def _find_pairs_via_topology(
    net_components: set[str],
    component_positions: dict[str, tuple[float, float]],
    failed_net: str,
    verbose: bool,
) -> list[BlockingPair]:
    """
    For complex multi-pin nets, check all pairwise distances.
    
    If components on the same net are too far apart, routing becomes difficult.
    """
    pairs = []
    
    components = list(net_components)
    
    # Check all pairs
    for i, comp_a in enumerate(components):
        for comp_b in components[i + 1 :]:
            pos_a = component_positions.get(comp_a)
            pos_b = component_positions.get(comp_b)
            
            if not pos_a or not pos_b:
                continue
            
            distance = math.sqrt(
                (pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2
            )
            
            # For multi-pin nets, long distances are problematic
            if distance > 30.0:
                # Low confidence - just a heuristic
                confidence = 0.15
                
                # Suggest bringing them closer
                required = distance * 0.7  # Reduce by 30%
                
                pairs.append(
                    BlockingPair(
                        component_a=comp_a,
                        component_b=comp_b,
                        failed_net=failed_net,
                        current_spacing=distance,
                        required_spacing=required,
                        confidence=confidence,
                        reason="topology_distance",
                    )
                )
    
    return pairs


def _merge_blocking_pairs(
    pairs: list[BlockingPair],
    verbose: bool,
) -> list[BlockingPair]:
    """
    Merge duplicate blocking pairs, combining confidence scores.
    
    If the same component pair appears multiple times (from different
    strategies), merge them and boost confidence.
    """
    # Group by (comp_a, comp_b) tuple (order-independent)
    groups: dict[tuple[str, str], list[BlockingPair]] = {}
    
    for pair in pairs:
        # Normalize order
        key = tuple(sorted([pair.component_a, pair.component_b]))
        if key not in groups:
            groups[key] = []
        groups[key].append(pair)
    
    merged = []
    for key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
        else:
            # Merge multiple observations
            # Use max confidence and max required spacing
            best = max(group, key=lambda p: p.confidence)
            
            # Boost confidence if multiple strategies agree
            confidence_boost = min(0.3, 0.1 * (len(group) - 1))
            merged_confidence = min(1.0, best.confidence + confidence_boost)
            
            # Use most conservative spacing requirement
            max_required = max(p.required_spacing for p in group)
            
            reasons = ", ".join(set(p.reason for p in group))
            
            merged.append(
                BlockingPair(
                    component_a=best.component_a,
                    component_b=best.component_b,
                    failed_net=best.failed_net,
                    current_spacing=best.current_spacing,
                    required_spacing=max_required,
                    confidence=merged_confidence,
                    reason=f"multiple_strategies: {reasons}",
                )
            )
    
    return merged
