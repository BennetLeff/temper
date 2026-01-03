"""
Routing feedback generator for the Hypergraph Routing Bridge.

This module translates routing failures (blockages, unrouted nets)
into spatial penalties that can be injected back into the Placer.
"""

from __future__ import annotations

import jax.numpy as jnp
from jax import Array


def generate_feedback_penalties(
    routing_results: dict[str, "RoutePath"],
    netlist: "Netlist",
    positions: Array,
) -> Array:
    """
    Generate a set of spatial penalties from routing failures.
    
    Returns:
        (K, 3) Array: [x, y, magnitude]
    """
    penalties = []
    
    for net_name, res in routing_results.items():
        if not res.success:
            # For each failed net, identify the 'congestion center'
            # For now, use the midpoint of the net's pins
            try:
                net = netlist.get_net(net_name)
                pin_coords = []
                for comp_ref, _ in net.pins:
                    idx = netlist.get_component_index(comp_ref)
                    pin_coords.append(positions[idx])
                
                if pin_coords:
                    coords = jnp.stack(pin_coords)
                    midpoint = jnp.mean(coords, axis=0)
                    
                    # Magnitude could be proportional to net importance or fail reason
                    magnitude = 1.0 
                    
                    penalties.append([float(midpoint[0]), float(midpoint[1]), magnitude])
            except (KeyError, ValueError):
                continue
                
    if not penalties:
        return jnp.empty((0, 3), dtype=jnp.float32)
        
    return jnp.array(penalties, dtype=jnp.float32)
