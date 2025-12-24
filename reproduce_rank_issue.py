import time
import jax.numpy as jnp
import numpy as np

def benchmark_rank_assignment(pop_size):
    # Simulate fronts
    # Assume 10 fronts, roughly equal size
    n_fronts = 10
    front_size = pop_size // n_fronts
    fronts = []
    current_idx = 0
    for i in range(n_fronts):
        end_idx = min(current_idx + front_size, pop_size)
        fronts.append(list(range(current_idx, end_idx)))
        current_idx = end_idx
    
    # Add any remainders to last front
    if current_idx < pop_size:
        fronts[-1].extend(range(current_idx, pop_size))

    start_time = time.time()
    
    # The slow implementation
    ranks = jnp.array([next(i for i, f in enumerate(fronts) if idx in f) for idx in range(pop_size)])
    
    end_time = time.time()
    return end_time - start_time

def benchmark_optimized_rank_assignment(pop_size):
    # Simulate fronts
    n_fronts = 10
    front_size = pop_size // n_fronts
    fronts = []
    current_idx = 0
    for i in range(n_fronts):
        end_idx = min(current_idx + front_size, pop_size)
        fronts.append(list(range(current_idx, end_idx)))
        current_idx = end_idx
    
    if current_idx < pop_size:
        fronts[-1].extend(range(current_idx, pop_size))

    start_time = time.time()
    
    # Optimized implementation
    # Using numpy for the assignment because front indices are python lists/ints
    ranks_np = np.zeros(pop_size, dtype=int)
    for rank_val, front in enumerate(fronts):
        for idx in front:
            ranks_np[idx] = rank_val
            
    ranks = jnp.array(ranks_np)
    
    end_time = time.time()
    return end_time - start_time

if __name__ == "__main__":
    for size in [50, 200, 500, 1000, 5000]:
        print(f"--- Population Size: {size} ---")
        time_orig = benchmark_rank_assignment(size)
        print(f"Original: {time_orig:.6f}s")
        
        time_opt = benchmark_optimized_rank_assignment(size)
        print(f"Optimized: {time_opt:.6f}s")
        
        speedup = time_orig / time_opt if time_opt > 0 else 0
        print(f"Speedup: {speedup:.2f}x\n")
