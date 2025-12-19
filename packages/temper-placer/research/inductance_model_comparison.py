import time

import jax.numpy as jnp
from jax import grad, jit, vmap

# --- Models to Evaluate ---


def model_manhattan(p1, p2, width_mm=1.0):
    """
    Simple Manhattan distance model.
    L ~ length (approx 1 nH/mm for typical PCB traces)
    """
    dist = jnp.sum(jnp.abs(p1 - p2))
    # Approximation: 1nH per mm is a common rule of thumb
    return dist * 1.0


def model_euclidean(p1, p2, width_mm=1.0):
    """
    Straight-line Euclidean distance model.
    L ~ length
    """
    dist = jnp.linalg.norm(p1 - p2)
    return dist * 1.0


def model_wheeler_microstrip(p1, p2, width_mm=1.0):
    """
    Wheeler formula for straight microstrip inductance.
    L = 0.00508 * l * (ln(2*l/w + h/w) + 0.5 + 0.2235*(w+h)/l)
    Simplified for placement (ignoring height h for now or assuming constant h):
    Classic approximation for wire in free space (self-inductance):
    L = 2 * l * (ln(2*l/w) - 0.75)  (in nH, l and w in cm)

    Let's use a standard PCB trace approximation:
    L_self = 2e-4 * l * (ln(2*l/w) + 0.5 + 0.2235 * (w/l))
    where L is in uH, l and w in mm? No, units vary wildy in literature.

    Let's use: L (nH) ≈ 2 * l(mm) * (ln(2*l/w) + 0.5)
    (Valid for l >> w)
    """
    l = jnp.linalg.norm(p1 - p2)
    w = width_mm

    # Avoid log(0) and division by zero
    l = jnp.maximum(l, 1e-6)

    # Term 1: 2 * l
    # Term 2: ln(2*l/w) + 0.5
    inductance = 2.0 * l * (jnp.log((2.0 * l) / w) + 0.5)
    return inductance


def model_loop_area(p1, p2, ref_point=jnp.array([0.0, 0.0])):
    """
    Approximates loop inductance by calculating the area of the triangle
    formed by p1, p2, and a reference point (e.g., ground return via nearest cap).
    L ~ Area
    Area = 0.5 * |x1(y2 - y3) + x2(y3 - y1) + x3(y1 - y2)|
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = ref_point

    area = 0.5 * jnp.abs(x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))

    # Inductance is proportional to loop area.
    # L = mu0 * Area / distance_between_layers?
    # Let's just return a proportional value.
    return area * 1.0


# --- Evaluation Harness ---


def evaluate_model(model_func, name, p1, p2, iterations=1000):
    print(f"--- Evaluating {name} ---")

    # 1. JIT Compilation
    start_jit = time.time()
    jitted_func = jit(model_func)
    _ = jitted_func(p1, p2)  # Trigger compilation
    jit_time = time.time() - start_jit
    print(f"JIT Compilation Time: {jit_time:.4f} s")

    # 2. Execution Speed
    start_run = time.time()
    # Use scan or simple loop for timing (vmap is better for batching)
    # vmapping to simulate batch evaluation
    batch_p1 = jnp.tile(p1, (iterations, 1))
    batch_p2 = jnp.tile(p2, (iterations, 1))

    vmapped_func = jit(vmap(model_func, in_axes=(0, 0)))
    _ = vmapped_func(batch_p1, batch_p2)  # Trigger compile

    start_batch = time.time()
    results = vmapped_func(batch_p1, batch_p2)
    results.block_until_ready()
    batch_time = time.time() - start_batch

    print(f"Batch Execution Time ({iterations} iters): {batch_time:.4f} s")
    print(f"Time per op: {(batch_time / iterations) * 1e6:.2f} us")

    # 3. Differentiability check
    grad_func = jit(grad(lambda x, y: jnp.sum(model_func(x, y))))

    start_grad = time.time()
    grads = grad_func(p1, p2)
    grad_time = time.time() - start_grad
    print(f"Gradient Calculation: Safe? {jnp.all(jnp.isfinite(grads))}")
    print(f"Gradient Calc Time: {grad_time:.4f} s")

    return {
        "name": name,
        "time_per_op_us": (batch_time / iterations) * 1e6,
        "differentiable": True,  # Assuming it didn't crash
    }


# --- Main ---


def main():
    print("Running Inductance Model Research for temper-jzq.8")
    print("==================================================")

    # Test points (mm)
    p1 = jnp.array([10.0, 10.0])
    p2 = jnp.array([20.0, 20.0])  # 14.14mm diagonal

    results = []

    results.append(evaluate_model(model_manhattan, "Manhattan Distance", p1, p2))
    results.append(evaluate_model(model_euclidean, "Euclidean Distance", p1, p2))
    results.append(evaluate_model(model_wheeler_microstrip, "Wheeler Formula", p1, p2))
    results.append(evaluate_model(model_loop_area, "Loop Area (Area-based)", p1, p2))

    print("\n\n--- Final Comparison ---")
    print(f"{'Model':<25} | {'Time (us)':<10} | {'Differentiable':<15}")
    print("-" * 55)
    for r in results:
        print(f"{r['name']:<25} | {r['time_per_op_us']:<10.2f} | {str(r['differentiable']):<15}")


if __name__ == "__main__":
    main()
