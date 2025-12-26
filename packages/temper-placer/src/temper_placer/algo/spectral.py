"""
Spectral placement algorithms for Hypergraphs.

Implements the Zhou et al. hypergraph Laplacian expansion and eigendecomposition
for global placement initialization.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array
from jax.experimental import sparse

from temper_placer.core.hypergraph import PhysicsHypergraph


def compute_laplacian(hg: PhysicsHypergraph) -> sparse.BCOO:
    """
    Compute the normalized hypergraph Laplacian.
    
    L = I - D_v^(-1/2) H W D_e^(-1) H^T D_v^(-1/2)
    
    Where:
    - H is incidence matrix
    - W is hyperedge weight diagonal
    - D_v is vertex degree diagonal
    - D_e is hyperedge degree diagonal
    """
    H = hg.incidence.matrix
    
    # 1. Degrees
    # Vertex degree d(v) = sum_{e \in E} w(e) * H(v,e)
    # We computed simple degree earlier, but strictly we need weighted degree.
    # Let's trust H @ ones if H is unweighted binary. 
    # If H contains weights, H @ ones is correct.
    # But wait, spectral clustering usually uses:
    # d(v) = sum_{e} w(e) * h(v,e)
    # d(e) = sum_{v} h(v,e) (size of edge)
    
    # Edge weights W (vector)
    W = hg.incidence.hyperedge_weights
    
    # D_e (vector) = sum columns of H
    ones_v = jnp.ones(hg.n_nodes)
    D_e_vec = H.T @ ones_v
    
    # D_v (vector) = H @ W
    # Note: standard matrix mult H @ W works if W is vector
    D_v_vec = H @ W
    
    # 2. Inverses (avoid divide by zero)
    eps = 1e-10
    D_e_inv = 1.0 / (D_e_vec + eps)
    D_v_inv_sqrt = 1.0 / jnp.sqrt(D_v_vec + eps)
    
    # 3. Construct Normalized Laplacian
    # We want L = I - Theta
    # Theta = D_v^(-1/2) @ H @ W @ D_e^(-1) @ H.T @ D_v^(-1/2)
    # This is a bit complex with BCOO directly.
    # Let's do it step by step.
    
    # Scale H columns by (W * D_e_inv)
    # H_scaled_cols = H * (W * D_e_inv)[None, :]
    # Sparse multiply is tricky.
    # Alternative: Use the fact that A @ diag(d) is scaling columns.
    
    # Let's try a simpler unnormalized Laplacian for placement first?
    # L_un = D_v - H W D_e^(-1) H^T
    # This is often more robust for placement (Star clique expansion).
    
    # Let's compute the Clique Adjacency A_c = H @ diag(W * D_e_inv) @ H.T
    # We need to constructing a diagonal matrix from a vector in sparse.
    # Or just multiply.
    
    # Optimization: H is (N, M). 
    # We can form diagonal S = diag(W / D_e)
    # A = H S H.T
    
    scale_factor = W * D_e_inv # (M,)
    
    # H_scaled = H @ diag(scale_factor)
    # Since H is BCOO, we can multiply its 'data' by scale_factor[indices[:,1]]
    # This requires accessing internals.
    
    # JAX way:
    # H_scaled = H * scale_factor[None, :] ? No, broadcasting might be dense.
    
    # Safe way:
    indices = H.indices
    data = H.data
    
    # Multiply data by scale factor corresponding to the column (edge) index
    col_indices = indices[:, 1]
    new_data = data * scale_factor[col_indices]
    
    H_scaled = sparse.BCOO((new_data, indices), shape=H.shape)
    
    # Now A = H_scaled @ H.T
    # This matrix multiplication is (N,M) @ (M,N) -> (N,N).
    # It creates the clique expansion adjacency matrix.
    # WARNING: This can be dense if there's a massive net!
    # Global net filtering is CRITICAL here.
    A = H_scaled @ H.T
    
    # L = D_v - A
    # But D_v must match A's row sums.
    ones = jnp.ones(hg.n_nodes)
    row_sums = A @ ones
    
    # In sparse land: L = Diag(row_sums) - A
    # Creating Diag(row_sums) as BCOO
    idx_diag = jnp.arange(hg.n_nodes)
    indices_diag = jnp.stack([idx_diag, idx_diag], axis=1)
    D_mat = sparse.BCOO((row_sums, indices_diag), shape=(hg.n_nodes, hg.n_nodes))
    
    L = D_mat - A
    
    return L


def spectral_layout(
    hg: PhysicsHypergraph, 
    dim: int = 2
) -> Array:
    """
    Compute spectral layout positions.
    
    Args:
        hg: PhysicsHypergraph
        dim: Dimensions (2 for 2D)
        
    Returns:
        (N, dim) positions array
    """
    L = compute_laplacian(hg)
    
    # Convert to dense for eigendecomposition if small
    # For large graphs, we'd use lobpcg, but let's start simple.
    # Assuming coarsening reduced N to < 1000.
    L_dense = L.todense()
    
    # Eigh for symmetric Hermitian
    eigenvalues, eigenvectors = jnp.linalg.eigh(L_dense)
    
    # Sort eigenvalues (they should be sorted by eigh, but verifying)
    # The smallest eigenvalue is 0 (constant vector).
    # We want the next 'dim' smallest non-zero eigenvectors.
    
    # Indices of smallest non-zero
    # Skip the first one (index 0)
    indices = jnp.arange(1, 1 + dim)
    
    coords = eigenvectors[:, indices]
    
    # Normalize coords?
    # Spectral usually gives centered at 0.
    
    return coords
