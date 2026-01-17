"""
Spectral placement algorithms for Hypergraphs.

Implements the Zhou et al. hypergraph Laplacian expansion and eigendecomposition
for global placement initialization.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh

from temper_placer.core.hypergraph import PhysicsHypergraph


def compute_laplacian(hg: PhysicsHypergraph) -> sparse.csr_matrix:
    """
    Compute the normalized hypergraph Laplacian.
    
    L = I - D_v^(-1/2) H W D_e^(-1) H^T D_v^(-1/2)
    """
    H = hg.incidence.matrix
    # hg.incidence.matrix is likely a jax.experimental.sparse.BCOO
    # Conver to scipy CSR for standard sparse ops
    if hasattr(H, "todense"):
        H_np = np.array(H.todense())
        H = sparse.csr_matrix(H_np)
    else:
        # Fallback if it's already some array type
        H = sparse.csr_matrix(np.array(H))

    W = np.array(hg.incidence.hyperedge_weights)
    
    ones_v = np.ones(hg.n_nodes)
    D_e_vec = np.array(H.T @ ones_v).flatten()
    
    D_v_vec = np.array(H @ W).flatten()
    
    eps = 1e-10
    D_e_inv = 1.0 / (D_e_vec + eps)
    
    # Simple clique expansion L = D_v - H W D_e^-1 H^T
    scale_factor = W * D_e_inv
    
    # H_scaled = H * scale_factor
    H_scaled = H.multiply(scale_factor)
    
    A = H_scaled @ H.T
    
    # Form Laplacian
    row_sums = np.array(A.sum(axis=1)).flatten()
    D_mat = sparse.diags(row_sums)
    
    L = D_mat - A
    return L


def spectral_layout(
    hg: PhysicsHypergraph, 
    dim: int = 2
) -> np.ndarray:
    """
    Compute spectral layout positions.
    """
    L = compute_laplacian(hg)
    
    # Smallest eigenvalues/vectors for Laplacian
    # 0 is always an eigenvalue, we want the next ones.
    # We use eigsh for sparse symmetric matrices.
    try:
        # Which='SM' finds smallest magnitude
        eigenvalues, eigenvectors = eigsh(L, k=dim + 1, which='SM')
        
        # Skip the constant eigenvector (index 0)
        coords = eigenvectors[:, 1:1+dim]
        return coords
    except:
        # Fallback to dense if sparse solver fails or matrix is too small/singular
        L_dense = L.toarray()
        eigenvalues, eigenvectors = np.linalg.eigh(L_dense)
        return eigenvectors[:, 1:1+dim]
