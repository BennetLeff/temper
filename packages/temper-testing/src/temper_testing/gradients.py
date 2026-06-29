"""
Gradient verification utilities.

Compare autodiff gradients against numerical approximation to find:
- Implementation bugs
- Numerical instability
- Discontinuities in loss landscape
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import jax
    import jax.numpy as jnp
    HAS_JAX = True
except ImportError:
    HAS_JAX = False


@dataclass
class GradientCheckResult:
    """Result of gradient verification."""
    passed: bool
    max_abs_diff: float
    max_rel_diff: float
    worst_param_idx: tuple[int, ...]
    numerical_grad: np.ndarray
    autodiff_grad: np.ndarray
    message: str


def check_gradient(
    fn: Callable,
    params: np.ndarray | Any,
    epsilon: float = 1e-5,
    rtol: float = 1e-3,
    atol: float = 1e-6,
    _seed: int | None = None,
) -> GradientCheckResult:
    """
    Compare autodiff gradient against numerical approximation.

    Uses central difference: (f(x+h) - f(x-h)) / 2h

    Args:
        fn: Function to differentiate. Must return scalar.
        params: Parameters to differentiate with respect to.
        epsilon: Step size for numerical differentiation.
        rtol: Relative tolerance for comparison.
        atol: Absolute tolerance for comparison.
        seed: Random seed for JAX (if needed).

    Returns:
        GradientCheckResult with comparison details.

    Example:
        >>> def loss(x):
        ...     return jnp.sum(x ** 2)
        >>> result = check_gradient(loss, jnp.array([1.0, 2.0, 3.0]))
        >>> assert result.passed
    """
    if HAS_JAX:
        return _check_gradient_jax(fn, params, epsilon, rtol, atol)
    else:
        return _check_gradient_numpy(fn, params, epsilon, rtol, atol)


def _check_gradient_jax(
    fn: Callable,
    params: Any,
    epsilon: float,
    rtol: float,
    atol: float,
) -> GradientCheckResult:
    """JAX implementation of gradient checking."""
    # Get autodiff gradient
    grad_fn = jax.grad(fn)
    autodiff_grad = grad_fn(params)

    # Flatten for numerical computation
    flat_params, unflatten = jax.flatten_util.ravel_pytree(params)
    flat_autodiff = jax.flatten_util.ravel_pytree(autodiff_grad)[0]

    # Compute numerical gradient
    numerical_grad = np.zeros_like(flat_params)
    for i in range(len(flat_params)):
        params_plus = flat_params.at[i].add(epsilon)
        params_minus = flat_params.at[i].add(-epsilon)

        f_plus = fn(unflatten(params_plus))
        f_minus = fn(unflatten(params_minus))

        numerical_grad[i] = (f_plus - f_minus) / (2 * epsilon)

    # Compare
    abs_diff = np.abs(numerical_grad - flat_autodiff)
    rel_diff = abs_diff / (np.abs(numerical_grad) + 1e-10)

    max_abs_diff = float(np.max(abs_diff))
    max_rel_diff = float(np.max(rel_diff))
    worst_idx = int(np.argmax(abs_diff))

    passed = np.allclose(numerical_grad, flat_autodiff, rtol=rtol, atol=atol)

    if passed:
        message = f"Gradient check PASSED (max_abs_diff={max_abs_diff:.2e})"
    else:
        message = (
            f"Gradient check FAILED at index {worst_idx}:\n"
            f"  numerical: {numerical_grad[worst_idx]:.6e}\n"
            f"  autodiff:  {flat_autodiff[worst_idx]:.6e}\n"
            f"  abs_diff:  {abs_diff[worst_idx]:.6e}"
        )

    return GradientCheckResult(
        passed=passed,
        max_abs_diff=max_abs_diff,
        max_rel_diff=max_rel_diff,
        worst_param_idx=(worst_idx,),
        numerical_grad=np.array(numerical_grad),
        autodiff_grad=np.array(flat_autodiff),
        message=message,
    )


def _check_gradient_numpy(
    fn: Callable,
    params: np.ndarray,
    epsilon: float,
    rtol: float,
    atol: float,
) -> GradientCheckResult:
    """NumPy fallback for gradient checking (requires manual grad function)."""
    raise NotImplementedError(
        "NumPy gradient checking requires JAX. "
        "Install with: pip install jax jaxlib"
    )


@dataclass
class Discontinuity:
    """A detected discontinuity in the loss landscape."""
    location: np.ndarray
    direction: np.ndarray
    left_value: float
    right_value: float
    jump_size: float


def find_discontinuities(
    fn: Callable,
    params: np.ndarray | Any,
    num_samples: int = 1000,
    epsilon: float = 1e-6,
    threshold: float = 0.1,
    seed: int = 42,
) -> list[Discontinuity]:
    """
    Search for discontinuities in loss landscape.

    Samples random directions and checks for sudden jumps.

    Args:
        fn: Loss function.
        params: Current parameters.
        num_samples: Number of random directions to test.
        epsilon: Step size.
        threshold: Jump size to consider discontinuous.
        seed: Random seed.

    Returns:
        List of detected discontinuities.

    Example:
        >>> def loss_with_jump(x):
        ...     return jnp.where(x[0] > 0, 1.0, 0.0)
        >>> disconts = find_discontinuities(loss_with_jump, jnp.array([0.0, 0.0]))
        >>> len(disconts) > 0  # Should find the jump at x=0
        True
    """
    if HAS_JAX:
        key = jax.random.PRNGKey(seed)
        flat_params, unflatten = jax.flatten_util.ravel_pytree(params)
    else:
        np.random.seed(seed)
        flat_params = params.flatten()
        def unflatten(x):
            return x.reshape(params.shape)

    discontinuities = []

    for _i in range(num_samples):
        # Random direction
        if HAS_JAX:
            key, subkey = jax.random.split(key)
            direction = jax.random.normal(subkey, flat_params.shape)
            direction = direction / jnp.linalg.norm(direction)
        else:
            direction = np.random.randn(*flat_params.shape)
            direction = direction / np.linalg.norm(direction)

        # Sample along direction
        steps = np.linspace(-epsilon * 10, epsilon * 10, 21)
        values = []

        for step in steps:
            if HAS_JAX:
                test_params = flat_params + step * direction
                values.append(float(fn(unflatten(test_params))))
            else:
                test_params = flat_params + step * direction
                values.append(float(fn(unflatten(test_params))))

        # Check for jumps
        values = np.array(values)
        diffs = np.abs(np.diff(values))

        for j, diff in enumerate(diffs):
            if diff > threshold:
                discontinuities.append(Discontinuity(
                    location=np.array(flat_params + steps[j] * direction),
                    direction=np.array(direction),
                    left_value=values[j],
                    right_value=values[j + 1],
                    jump_size=diff,
                ))

    return discontinuities


def gradient_flow_analysis(
    fn: Callable,
    params: Any,
    _param_names: list[str] | None = None,
) -> dict[str, float]:
    """
    Analyze gradient magnitudes for each parameter group.

    Useful for detecting vanishing/exploding gradients.

    Args:
        fn: Loss function.
        params: Parameters (can be pytree).
        _param_names: Optional names for parameter groups.

    Returns:
        Dict mapping param name to gradient L2 norm.
    """
    if not HAS_JAX:
        raise NotImplementedError("Requires JAX")

    grad_fn = jax.grad(fn)
    grads = grad_fn(params)

    if isinstance(grads, dict):
        result = {}
        for key, grad in grads.items():
            flat = jax.flatten_util.ravel_pytree(grad)[0]
            result[key] = float(jnp.linalg.norm(flat))
        return result
    else:
        flat = jax.flatten_util.ravel_pytree(grads)[0]
        return {"params": float(jnp.linalg.norm(flat))}


def check_gradient_at_boundary(
    fn: Callable,
    params: Any,
    boundary_params: Any,
    _epsilon: float = 1e-5,
) -> dict[str, Any]:
    """
    Check gradient behavior at boundary conditions.

    Useful for verifying smooth transitions at constraints.

    Args:
        fn: Loss function.
        params: Interior parameters.
        boundary_params: Parameters at boundary.
        epsilon: Step size.

    Returns:
        Analysis of gradient behavior near boundary.
    """
    if not HAS_JAX:
        raise NotImplementedError("Requires JAX")

    grad_fn = jax.grad(fn)

    interior_grad = grad_fn(params)
    boundary_grad = grad_fn(boundary_params)

    flat_interior = jax.flatten_util.ravel_pytree(interior_grad)[0]
    flat_boundary = jax.flatten_util.ravel_pytree(boundary_grad)[0]

    return {
        "interior_norm": float(jnp.linalg.norm(flat_interior)),
        "boundary_norm": float(jnp.linalg.norm(flat_boundary)),
        "ratio": float(jnp.linalg.norm(flat_boundary) / (jnp.linalg.norm(flat_interior) + 1e-10)),
        "boundary_has_nan": bool(jnp.any(jnp.isnan(flat_boundary))),
        "boundary_has_inf": bool(jnp.any(jnp.isinf(flat_boundary))),
    }
