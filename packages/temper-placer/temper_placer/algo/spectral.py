"""
Spectral placement algorithms for Hypergraphs.

Implements the Zhou et al. hypergraph Laplacian expansion and eigendecomposition
for global placement initialization.
"""

from __future__ import annotations

import logging
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh

from temper_placer.core.hypergraph import PhysicsHypergraph
from temper_placer.algo.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph

logger = logging.getLogger(__name__)


def compute_laplacian(hg: PhysicsHypergraph) -> sparse.csr_matrix:
    """
    Compute the normalized hypergraph Laplacian.
    
    L = I - D_v^(-1/2) H W D_e^(-1) H^T D_v^(-1/2)
    """
    H = hg.incidence.matrix
    
    # hg.incidence.matrix is likely a jax.experimental.sparse.BCOO or similar
    # Convert to scipy CSR for standard sparse ops
    if hasattr(H, "todense"):
        H_np = np.array(H.todense())
        H = sparse.csr_matrix(H_np)
    else:
        H = sparse.csr_matrix(np.array(H))

    W = np.array(hg.incidence.hyperedge_weights)
    
    ones_v = np.ones(hg.n_nodes)
    D_e_vec = np.array(H.T @ ones_v).flatten()
    
    D_v_vec = np.array(H @ W).flatten()
    
    eps = 1e-10
    D_e_inv = 1.0 / (D_e_vec + eps)
    
    scale_factor = W * D_e_inv
    H_scaled = H.multiply(scale_factor)
    
    A = H_scaled @ H.T
    
    row_sums = np.array(A.sum(axis=1)).flatten()
    D_mat = sparse.diags(row_sums)
    
    L = D_mat - A
    return L


def spectral_layout(
    hg: PhysicsHypergraph, 
    dim: int = 2
) -> np.ndarray:
    """
    Compute spectral layout positions using the smallest non-zero eigenvectors.
    """
    if hg.n_nodes <= dim:
        return np.random.uniform(-1, 1, (hg.n_nodes, dim))

    L = compute_laplacian(hg)
    
    try:
        # Which='SM' finds smallest magnitude eigenvalues
        # We need dim + 1 because the first eigenvector is constant (eigenvalue 0)
        eigenvalues, eigenvectors = eigsh(L, k=dim + 1, which='SM')
        
        # Skip the constant eigenvector (index 0)
        coords = eigenvectors[:, 1:1+dim]
        return coords
    except Exception as e:
        logger.warning(f"Sparse eigendecomposition failed, falling back to dense: {e}")
        L_dense = L.toarray()
        eigenvalues, eigenvectors = np.linalg.eigh(L_dense)
        return eigenvectors[:, 1:1+dim]


class SpectralPlacementHeuristic(Heuristic):
    """
    Globally place components using Spectral Graph Layout.

    This heuristic constructs a hypergraph from the netlist and uses the
    eigenvectors of the hypergraph Laplacian to find coordinates that minimize
    the total squared wirelength.
    """

    def __init__(self, confidence: float = 0.1):
        self._confidence = confidence

    @property
    def name(self) -> str:
        return "spectral_initialization"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.INITIALIZATION

    @property
    def description(self) -> str:
        return "Global spectral layout minimizing squared wirelength"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply spectral layout initialized from the hypergraph."""
        # Build the hypergraph
        # Filter global nets like GND/VCC which would wash out the spectral signal
        hg = netlist_to_hypergraph(
            context.netlist, 
            ignore_global_nets=True,
            global_net_threshold=50
        )

        if hg.n_nodes == 0:
            return HeuristicResult(success=True, message="Empty graph")

        # Compute spectral layout
        coords = spectral_layout(hg, dim=2)

        # Scale and transform coordinates to board space
        board = context.board
        margin = context.constraints.board_margin_mm
        
        w_eff = board.width - 2 * margin
        h_eff = board.height - 2 * margin
        
        # Normalize coords to [0, 1] then scale to board
        c_min = coords.min(axis=0)
        c_max = coords.max(axis=0)
        c_rng = np.maximum(c_max - c_min, 1e-6)
        
        norm_coords = (coords - c_min) / c_rng
        
        # Board coordinates
        board_coords = norm_coords * np.array([w_eff, h_eff]) + margin
        
        placements: dict[str, ComponentPlacement] = {}
        for i, ref in enumerate(hg.node_refs):
            if ref in context.current_placements:
                continue
                
            comp = context.netlist.get_component(ref)
            if comp.fixed:
                continue

            x, y = board_coords[i]
            # Extra safety bounds check
            x = max(margin + comp.width / 2, min(x, board.width - margin - comp.width / 2))
            y = max(margin + comp.height / 2, min(y, board.height - margin - comp.height / 2))
            
            placements[ref] = ComponentPlacement(
                ref=ref,
                position=(float(x), float(y)),
                rotation=0,
                confidence=self._confidence,
                placed_by=self.name,
            )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Spectrally placed {len(placements)} components using Hypergraph Laplacian",
        )
