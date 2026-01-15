"""
Post-Route DRC Validation and Repair

Detects same-layer crossings and automatically repairs them by
reassigning one net to a different layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from shapely.geometry import LineString
from collections import defaultdict


@dataclass
class CrossingViolation:
    """A same-layer crossing between two nets."""
    net1: str
    net2: str
    layer: str
    crossing_point: tuple[float, float]


def detect_same_layer_crossings(
    routed_paths: dict,
    verbose: bool = False,
) -> list[CrossingViolation]:
    """
    Detect all same-layer crossings between routed paths.
    
    Args:
        routed_paths: Dict of net_name -> RoutePath or RoutePath3D
        verbose: Print debug info
        
    Returns:
        List of CrossingViolation objects
    """
    violations = []
    
    # Group paths by layer
    paths_by_layer: dict[str, dict[str, LineString]] = defaultdict(dict)
    
    for net_name, path in routed_paths.items():
        if hasattr(path, 'segments'):
            # RoutePath3D - group by layer
            layer_coords: dict[str, list] = defaultdict(list)
            for seg in path.segments:
                x, y, layer = seg
                layer_coords[layer].append((x, y))
            
            for layer, coords in layer_coords.items():
                if len(coords) >= 2:
                    paths_by_layer[layer][net_name] = LineString(coords)
        elif hasattr(path, 'coordinates') and hasattr(path, 'layer_name'):
            # RoutePath - single layer
            if len(path.coordinates) >= 2:
                paths_by_layer[path.layer_name][net_name] = LineString(path.coordinates)
    
    # Check for crossings on each layer
    for layer, layer_paths in paths_by_layer.items():
        net_names = list(layer_paths.keys())
        
        for i in range(len(net_names)):
            for j in range(i + 1, len(net_names)):
                net1 = net_names[i]
                net2 = net_names[j]
                
                ls1 = layer_paths[net1]
                ls2 = layer_paths[net2]
                
                try:
                    intersection = ls1.intersection(ls2)
                    
                    if intersection.is_empty:
                        continue
                    
                    # Count crossing points
                    if intersection.geom_type == 'Point':
                        violations.append(CrossingViolation(
                            net1=net1,
                            net2=net2,
                            layer=layer,
                            crossing_point=(intersection.x, intersection.y),
                        ))
                    elif intersection.geom_type == 'MultiPoint':
                        for pt in intersection.geoms:
                            violations.append(CrossingViolation(
                                net1=net1,
                                net2=net2,
                                layer=layer,
                                crossing_point=(pt.x, pt.y),
                            ))
                    elif intersection.geom_type in ['LineString', 'MultiLineString']:
                        # Overlapping segments - even worse!
                        centroid = intersection.centroid
                        violations.append(CrossingViolation(
                            net1=net1,
                            net2=net2,
                            layer=layer,
                            crossing_point=(centroid.x, centroid.y),
                        ))
                except Exception:
                    # Shapely geometry error - skip this pair
                    pass
    
    if verbose and violations:
        print(f"\n  ⚠️  Detected {len(violations)} same-layer crossings:")
        # Group by net pair
        pair_counts = defaultdict(int)
        for v in violations:
            pair = tuple(sorted([v.net1, v.net2]))
            pair_counts[pair] += 1
        
        for (n1, n2), count in sorted(pair_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"     {n1} ↔ {n2}: {count}x")
    
    return violations


def suggest_layer_reassignments(
    violations: list[CrossingViolation],
    current_assignments: dict[str, str],
    available_layers: list[str] = None,
) -> dict[str, str]:
    """
    Suggest which nets should be moved to different layers to eliminate crossings.
    
    Strategy:
    - For each crossing pair, move the net with fewer total crossings
    - Move to the layer with fewer nets assigned
    
    Args:
        violations: List of crossing violations
        current_assignments: Current net -> layer mapping
        available_layers: List of available routing layers
        
    Returns:
        Dict of net_name -> new_layer for suggested reassignments
    """
    if not available_layers:
        available_layers = ["F.Cu", "B.Cu"]
    
    if not violations:
        return {}
    
    # Count crossings per net
    crossing_count = defaultdict(int)
    for v in violations:
        crossing_count[v.net1] += 1
        crossing_count[v.net2] += 1
    
    # Count nets per layer
    nets_per_layer = defaultdict(int)
    for net, layer in current_assignments.items():
        nets_per_layer[layer] += 1
    
    # Suggest reassignments
    reassignments = {}
    processed_pairs = set()
    
    for v in sorted(violations, key=lambda x: -crossing_count[x.net1] - crossing_count[x.net2]):
        pair = tuple(sorted([v.net1, v.net2]))
        if pair in processed_pairs:
            continue
        processed_pairs.add(pair)
        
        # Choose the net with fewer crossings to move
        if crossing_count[v.net1] <= crossing_count[v.net2]:
            net_to_move = v.net1
        else:
            net_to_move = v.net2
        
        # Skip if already reassigned
        if net_to_move in reassignments:
            continue
        
        # Find a different layer
        current_layer = v.layer
        for alt_layer in available_layers:
            if alt_layer != current_layer:
                reassignments[net_to_move] = alt_layer
                break
    
    return reassignments


def print_crossing_summary(violations: list[CrossingViolation]) -> None:
    """Print a summary of crossing violations."""
    if not violations:
        print("  ✅ No same-layer crossings detected")
        return
    
    print(f"\n  ❌ {len(violations)} same-layer crossings detected:")
    
    # Group by layer
    by_layer = defaultdict(list)
    for v in violations:
        by_layer[v.layer].append(v)
    
    for layer, layer_violations in sorted(by_layer.items()):
        print(f"\n  {layer}:")
        
        # Group by net pair
        pair_counts = defaultdict(int)
        for v in layer_violations:
            pair = tuple(sorted([v.net1, v.net2]))
            pair_counts[pair] += 1
        
        for (n1, n2), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
            print(f"    {n1} ↔ {n2}: {count} crossing(s)")
