
import time
import jax
import jax.numpy as jnp
from jax.experimental import sparse
import numpy as np

def benchmark_wirelength_implementations():
    """
    Benchmark comparing Iterative vs Sparse Matrix Wirelength calculation.
    
    Scenario:
    - 500 Nets
    - 1000 Components
    - Avg Net Degree: 3 (some massive nets included)
    """
    
    N_COMPS = 1000
    N_NETS = 500
    
    # Random Positions
    key = jax.random.PRNGKey(0)
    positions = jax.random.uniform(key, (N_COMPS, 2)) * 100.0
    
    # Build Netlist Data (Naive list of lists)
    nets_naive = []
    
    # Build Sparse Data
    rows = []
    cols = []
    data = []
    
    np.random.seed(42)
    for net_idx in range(N_NETS):
        # Random degree: 2 to 10, with one massive net (GND)
        if net_idx == 0:
            degree = 200
        else:
            degree = np.random.randint(2, 6)
            
        pins = np.random.choice(N_COMPS, degree, replace=False)
        nets_naive.append(jnp.array(pins))
        
        for p in pins:
            rows.append(p)
            cols.append(net_idx)
            data.append(1.0)
            
    # Create BCOO
    indices = jnp.array([rows, cols]).T
    values = jnp.array(data, dtype=jnp.float32)
    H = sparse.BCOO((values, indices), shape=(N_COMPS, N_NETS))
    
    # --- Approach 1: Naive Loop (The "Old" Way) ---
    # Mimics looping over net objects
    @jax.jit
    def loss_naive(pos):
        loss = 0.0
        for pins in nets_naive:
            # Star Model: Variance from mean
            net_pos = pos[pins]
            center = jnp.mean(net_pos, axis=0)
            dist = jnp.sum((net_pos - center)**2)
            loss += dist
        return loss

    # --- Approach 2: Sparse Matrix (The "New" Way) ---
    # L = sum || p_i - center_e ||^2
    # Can be rewritten algebraically, but let's do the H^T @ P projection
    @jax.jit
    def loss_sparse(pos):
        # 1. Compute Centroids
        # Degrees of nets
        ones = jnp.ones(N_COMPS)
        net_degrees = H.T @ ones
        
        # Sum of positions per net
        sum_pos = H.T @ pos # (N_nets, 2)
        
        # Centroids
        centroids = sum_pos / net_degrees[:, None]
        
        # 2. Compute Variance (vectorized)
        # This part is tricky with just H. 
        # L = sum(x^2) - N * mean^2  (Standard variance formula)
        # sum( ||p_i - mu_e||^2 ) = sum( ||p_i||^2 ) - |e| * ||mu_e||^2
        
        # Term 1: Sum of squared positions for every pin connection
        # We need to know which pins are in which nets.
        # Actually, simpler: sum_{e} [ sum_{v in e} ||v||^2 ] - sum_{e} [ |e| ||mu_e||^2 ]
        
        # Term 1 can be computed as: (H.T @ (pos**2)) . sum()
        term1 = jnp.sum(H.T @ (pos**2))
        
        # Term 2
        term2 = jnp.sum(net_degrees[:, None] * (centroids**2))
        
        return term1 - term2

    # --- Run Benchmarks ---
    print(f"Benchmarking with {N_COMPS} components, {N_NETS} nets...")
    
    # Warmup
    print("Compiling Naive...")
    start = time.time()
    _ = loss_naive(positions).block_until_ready()
    print(f"Naive Compile: {time.time() - start:.4f}s")
    
    print("Compiling Sparse...")
    start = time.time()
    _ = loss_sparse(positions).block_until_ready()
    print(f"Sparse Compile: {time.time() - start:.4f}s")
    
    # Execution Speed
    N_ITERS = 100
    
    start = time.time()
    for _ in range(N_ITERS):
        _ = loss_naive(positions).block_until_ready()
    naive_time = (time.time() - start) / N_ITERS
    
    start = time.time()
    for _ in range(N_ITERS):
        _ = loss_sparse(positions).block_until_ready()
    sparse_time = (time.time() - start) / N_ITERS
    
    print(f"\nAvg Execution Time (100 runs):")
    print(f"Naive:  {naive_time*1000:.4f} ms")
    print(f"Sparse: {sparse_time*1000:.4f} ms")
    print(f"Speedup: {naive_time / sparse_time:.2f}x")

if __name__ == "__main__":
    benchmark_wirelength_implementations()
