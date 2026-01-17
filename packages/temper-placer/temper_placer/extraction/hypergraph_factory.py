"""
Factory for creating PhysicsHypergraph instances from Netlists.

This module handles the complexity of parsing netlists, filtering global nets,
and extracting physical attributes to populate the clean PhysicsHypergraph
data structure. Standardized on NumPy for the JAX-free Benders-V6 pipeline.
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sparse

from temper_placer.core.hypergraph import HypergraphIncidence, PhysicsHypergraph
from temper_placer.core.netlist import Netlist


class HypergraphFactory:
    """
    Builder for PhysicsHypergraph using NumPy and SciPy.
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
            if len(net.pins) >= 2:
                valid_nets.append(net)
        
        n_edges = len(valid_nets)
        
        # 2. Build COO Data for sparse matrix
        rows = []
        cols = []
        data = []
        
        edge_voltages = []
        edge_currents = [] 
        edge_widths = []   
        
        for net_idx, net in enumerate(valid_nets):
            is_hv = 1.0 if net.voltage_class == "HV" or net.net_class == "HighVoltage" else 0.0
            edge_voltages.append(is_hv)
            edge_currents.append(net.max_current)
            
            if net.net_class == "HighVoltage":
                width = 1.0
            elif net.max_current > 1.0:
                width = 0.5
            else:
                width = 0.2
            edge_widths.append(width)   
            
            connected_indices = set()
            for comp_ref, _ in net.pins:
                if comp_ref in node_ref_to_idx:
                    connected_indices.add(node_ref_to_idx[comp_ref])
            
            for node_idx in connected_indices:
                rows.append(node_idx)
                cols.append(net_idx)
                data.append(net.weight)
                
        # 3. Create Incidence Matrix
        if n_edges > 0 and rows:
            # We use dense for now if expected by downstream, but CSR is better
            # For Benders-V6 and spectral, we often dense it anyway
            coo = sparse.coo_matrix((data, (rows, cols)), shape=(n_nodes, n_edges))
            matrix = coo.toarray()
        else:
            matrix = np.zeros((n_nodes, n_edges), dtype=np.float32)
        
        # 4. Node Weights (Area based)
        node_weights = np.array(
            [c.width * c.height for c in self.netlist.components],
            dtype=np.float32
        )
        
        # 5. Hyperedge Weights (Base importance)
        hyperedge_weights = np.array(
            [n.weight for n in valid_nets],
            dtype=np.float32
        )
        
        return PhysicsHypergraph(
            incidence=HypergraphIncidence(
                matrix=matrix,
                node_weights=node_weights,
                hyperedge_weights=hyperedge_weights
            ),
            node_refs=[c.ref for c in self.netlist.components],
            hyperedge_names=[n.name for n in valid_nets],
            edge_voltages=np.array(edge_voltages, dtype=np.float32),
            edge_currents=np.array(edge_currents, dtype=np.float32),
            edge_widths=np.array(edge_widths, dtype=np.float32)
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
