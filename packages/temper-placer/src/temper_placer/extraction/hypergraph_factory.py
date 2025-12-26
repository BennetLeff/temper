"""
Factory for creating PhysicsHypergraph instances from Netlists.

This module handles the complexity of parsing netlists, filtering global nets,
and extracting physical attributes to populate the clean PhysicsHypergraph
data structure.
"""

from __future__ import annotations

import jax.numpy as jnp
from jax.experimental import sparse

from temper_placer.core.hypergraph import HypergraphIncidence, PhysicsHypergraph
from temper_placer.core.netlist import Netlist


class HypergraphFactory:
    """
    Builder for PhysicsHypergraph.
    """

    def __init__(
        self, 
        netlist: Netlist,
        ignore_global_nets: bool = False,
        global_net_threshold: int = 50
    ):
        self.netlist = netlist
        self.ignore_global_nets = ignore_global_nets
        self.global_net_threshold = global_net_threshold

    def build(self) -> PhysicsHypergraph:
        """
        Build and return the PhysicsHypergraph.
        """
        n_nodes = self.netlist.n_components
        node_ref_to_idx = {c.ref: i for i, c in enumerate(self.netlist.components)}
        
        # 1. Collect valid edges (Nets)
        valid_nets = []
        for net in self.netlist.nets:
            if self.ignore_global_nets and len(net.pins) > self.global_net_threshold:
                continue
            # Only include nets with >= 2 pins (single-pin nets don't constrain placement)
            if len(net.pins) >= 2:
                valid_nets.append(net)
        
        n_edges = len(valid_nets)
        
        # 2. Build COO Data
        rows = []
        cols = []
        data = []
        
        edge_voltages = []
        edge_currents = [] 
        edge_widths = []   
        
        for net_idx, net in enumerate(valid_nets):
            # Physics extraction (Defaults for now - TODO: Extract from constraints)
            is_hv = 1.0 if net.net_class == "HighVoltage" else 0.0
            edge_voltages.append(is_hv)
            edge_currents.append(1.0) 
            edge_widths.append(0.2)   
            
            # Connections
            connected_indices = set()
            for comp_ref, _ in net.pins:
                if comp_ref in node_ref_to_idx:
                    connected_indices.add(node_ref_to_idx[comp_ref])
            
            for node_idx in connected_indices:
                rows.append(node_idx)
                cols.append(net_idx)
                data.append(net.weight)
                
        # 3. Create JAX Arrays
        if n_edges > 0:
            indices = jnp.array([rows, cols]).T # (N_entries, 2)
            values = jnp.array(data, dtype=jnp.float32)
        else:
            indices = jnp.empty((0, 2), dtype=jnp.int32)
            values = jnp.empty((0,), dtype=jnp.float32)
        
        shape = (n_nodes, n_edges)
        bcoo_matrix = sparse.BCOO((values, indices), shape=shape)
        
        # 4. Node Weights (Area based)
        node_weights = jnp.array(
            [c.width * c.height for c in self.netlist.components],
            dtype=jnp.float32
        )
        
        # 5. Hyperedge Weights (Base importance)
        hyperedge_weights = jnp.array(
            [n.weight for n in valid_nets],
            dtype=jnp.float32
        )
        
        return PhysicsHypergraph(
            incidence=HypergraphIncidence(
                matrix=bcoo_matrix,
                node_weights=node_weights,
                hyperedge_weights=hyperedge_weights
            ),
            node_refs=[c.ref for c in self.netlist.components],
            hyperedge_names=[n.name for n in valid_nets],
            edge_voltages=jnp.array(edge_voltages, dtype=jnp.float32),
            edge_currents=jnp.array(edge_currents, dtype=jnp.float32),
            edge_widths=jnp.array(edge_widths, dtype=jnp.float32)
        )


def netlist_to_hypergraph(
    netlist: Netlist,
    ignore_global_nets: bool = False,
    global_net_threshold: int = 50
) -> PhysicsHypergraph:
    """Convenience wrapper for HypergraphFactory."""
    return HypergraphFactory(
        netlist, 
        ignore_global_nets=ignore_global_nets, 
        global_net_threshold=global_net_threshold
    ).build()
