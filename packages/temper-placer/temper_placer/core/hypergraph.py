"""
Physics-Aware Hypergraph representation for PCB placement.

This module defines the core data structures for the hypergraph.
Standardized on NumPy for the JAX-free Benders-V6 pipeline.
"""

from __future__ import annotations

from typing import Sequence
from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class HypergraphIncidence:
    """
    Representation of the Hypergraph Incidence Matrix H.
    
    Dimensions: (N_nodes, N_hyperedges)
    - Rows: Components (Nodes)
    - Cols: Nets (Hyperedges)
    
    Values:
    - 1.0 (or weight) if connected
    - 0.0 otherwise
    """
    matrix: np.ndarray  # (N_nodes, N_hyperedges) - could be sparse in future
    node_weights: np.ndarray      # (N_nodes,) - e.g., component area
    hyperedge_weights: np.ndarray # (N_edges,) - e.g., net priority/current


@dataclass(frozen=True)
class PhysicsHypergraph:
    """
    Hypergraph with embedded physical attributes.
    """
    incidence: HypergraphIncidence
    
    # Metadata for reconstruction/mapping
    node_refs: Sequence[str]
    hyperedge_names: Sequence[str]
    
    # Physics Attributes (Parallel arrays to hyperedges)
    edge_voltages: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32)) # (N_edges,) 0=LV, 1=HV
    edge_currents: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32)) # (N_edges,) Amps
    edge_widths: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))   # (N_edges,) mm

    @property
    def n_nodes(self) -> int:
        return len(self.node_refs)

    @property
    def n_edges(self) -> int:
        return len(self.hyperedge_names)

    def compute_node_degrees(self) -> np.ndarray:
        """Compute degree of each node (sum of incident hyperedge weights)."""
        ones = np.ones(self.n_edges)
        return self.incidence.matrix @ ones

    def compute_edge_degrees(self) -> np.ndarray:
        """Compute degree of each hyperedge (number of connected nodes)."""
        ones = np.ones(self.n_nodes)
        return self.incidence.matrix.T @ ones