"""
Crossing Repair - Post-route via insertion for control signal crossings

This module detects crossings after routing and suggests layer changes
to eliminate them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from temper_placer.router_v6.post_route_drc import CrossingViolation, detect_same_layer_crossings


@dataclass
class LayerChange:
    """Suggested layer change to fix a crossing."""
    net_name: str
    from_layer: str
    to_layer: str
    reason: str


def suggest_layer_changes(
    violations: list[CrossingViolation],
    current_assignments: dict[str, str],
    design_rules=None,
) -> list[LayerChange]:
    """
    Suggest layer changes to eliminate crossings that need vias.
    
    Strategy:
    - Only fix crossings marked as needs_via
    - Pick the net with fewer total crossings to move
    - Move to the alternate layer
    
    Args:
        violations: List of crossing violations
        current_assignments: Current net -> layer mapping
        design_rules: Design rules for category lookup
        
    Returns:
        List of suggested layer changes
    """
    # Only process crossings that need vias
    via_crossings = [v for v in violations if v.needs_via and not v.is_acceptable]
    
    if not via_crossings:
        return []
    
    # Count crossings per net
    crossing_count = defaultdict(int)
    for v in via_crossings:
        crossing_count[v.net1] += 1
        crossing_count[v.net2] += 1
    
    # Track which nets we've already suggested changes for
    changed_nets = set()
    suggestions = []
    
    # Process each crossing pair
    processed_pairs = set()
    for v in sorted(via_crossings, key=lambda x: min(crossing_count[x.net1], crossing_count[x.net2])):
        pair = tuple(sorted([v.net1, v.net2]))
        if pair in processed_pairs:
            continue
        processed_pairs.add(pair)
        
        # Skip if either net is already being changed
        if v.net1 in changed_nets or v.net2 in changed_nets:
            continue
        
        # Pick the net with fewer crossings to move
        if crossing_count[v.net1] <= crossing_count[v.net2]:
            net_to_move = v.net1
            other_net = v.net2
        else:
            net_to_move = v.net2
            other_net = v.net1
        
        # Skip power nets - they can't be moved
        if design_rules:
            cat = design_rules.get_net_category(net_to_move)
            if cat == "power":
                # Try the other net
                net_to_move = other_net
                cat = design_rules.get_net_category(net_to_move)
                if cat == "power":
                    continue  # Can't move either
        
        # Determine current and target layer
        current_layer = v.layer
        target_layer = "B.Cu" if current_layer == "F.Cu" else "F.Cu"
        
        suggestions.append(LayerChange(
            net_name=net_to_move,
            from_layer=current_layer,
            to_layer=target_layer,
            reason=f"Crossing with {other_net}",
        ))
        changed_nets.add(net_to_move)
    
    return suggestions


def print_repair_suggestions(suggestions: list[LayerChange]) -> None:
    """Print suggested layer changes."""
    if not suggestions:
        print("  ✅ No layer changes needed")
        return
    
    print(f"\n  Suggested Layer Changes ({len(suggestions)}):")
    for s in suggestions:
        print(f"    {s.net_name}: {s.from_layer} → {s.to_layer}")
        print(f"      Reason: {s.reason}")


def apply_layer_changes(
    suggestions: list[LayerChange],
    net_layer_assignments: dict[str, str],
) -> dict[str, str]:
    """
    Apply suggested layer changes to the assignment dict.
    
    Returns updated copy of net_layer_assignments.
    """
    updated = dict(net_layer_assignments)
    for s in suggestions:
        updated[s.net_name] = s.to_layer
    return updated
