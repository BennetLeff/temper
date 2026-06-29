"""
Determinism verification utilities.

Ensure that functions produce identical output for identical input.
Critical for reproducibility and debugging.
"""

from __future__ import annotations

import hashlib
import pickle
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import numpy as np

T = TypeVar("T")

try:
    import jax
    import jax.numpy as jnp
    HAS_JAX = True
except ImportError:
    HAS_JAX = False


@dataclass
class DeterminismResult:
    """Result of determinism verification."""
    passed: bool
    num_runs: int
    all_identical: bool
    first_divergence_run: int | None
    divergence_details: str | None


def verify(
    fn: Callable[..., T],
    args: tuple = (),
    kwargs: dict | None = None,
    runs: int = 10,
    compare: Callable[[T, T], bool] | None = None,
) -> DeterminismResult:
    """
    Verify function produces identical output across multiple runs.

    Args:
        fn: Function to test.
        args: Positional arguments.
        kwargs: Keyword arguments.
        runs: Number of times to run.
        compare: Custom comparison function (default: deep equality).

    Returns:
        DeterminismResult with details.

    Example:
        >>> def my_func(x):
        ...     return x * 2
        >>> result = verify(my_func, args=(5,), runs=10)
        >>> assert result.passed
    """
    kwargs = kwargs or {}

    if compare is None:
        compare = _default_compare

    results = []
    for _i in range(runs):
        result = fn(*args, **kwargs)
        results.append(result)

    # Compare all results to first
    first = results[0]
    for i, result in enumerate(results[1:], start=1):
        if not compare(first, result):
            return DeterminismResult(
                passed=False,
                num_runs=runs,
                all_identical=False,
                first_divergence_run=i,
                divergence_details=_describe_divergence(first, result),
            )

    return DeterminismResult(
        passed=True,
        num_runs=runs,
        all_identical=True,
        first_divergence_run=None,
        divergence_details=None,
    )


def verify_with_seed(
    fn: Callable[..., T],
    seed: int,
    args: tuple = (),
    kwargs: dict | None = None,
    runs: int = 5,
    compare: Callable[[T, T], bool] | None = None,
) -> DeterminismResult:
    """
    Verify function is deterministic when given same random seed.

    For JAX functions, creates new PRNGKey for each run.

    Args:
        fn: Function to test. First arg should accept PRNGKey or seed.
        seed: Random seed to use.
        args: Additional positional arguments (after key/seed).
        kwargs: Keyword arguments.
        runs: Number of runs.
        compare: Custom comparison function.

    Returns:
        DeterminismResult with details.

    Example:
        >>> def random_init(key, shape):
        ...     return jax.random.normal(key, shape)
        >>> result = verify_with_seed(random_init, seed=42, args=((10,),))
        >>> assert result.passed
    """
    kwargs = kwargs or {}

    if compare is None:
        compare = _default_compare

    results = []
    for _i in range(runs):
        if HAS_JAX:
            key = jax.random.PRNGKey(seed)
            result = fn(key, *args, **kwargs)
        else:
            np.random.seed(seed)
            result = fn(seed, *args, **kwargs)
        results.append(result)

    # Compare all results
    first = results[0]
    for i, result in enumerate(results[1:], start=1):
        if not compare(first, result):
            return DeterminismResult(
                passed=False,
                num_runs=runs,
                all_identical=False,
                first_divergence_run=i,
                divergence_details=_describe_divergence(first, result),
            )

    return DeterminismResult(
        passed=True,
        num_runs=runs,
        all_identical=True,
        first_divergence_run=None,
        divergence_details=None,
    )


def hash_output(value: Any) -> str:
    """
    Compute deterministic hash of a value.

    Useful for quick comparison of complex outputs.
    """
    if HAS_JAX and hasattr(value, "device"):
        # JAX array - convert to numpy
        value = np.array(value)

    if isinstance(value, np.ndarray):
        # Numpy array - hash bytes
        return hashlib.sha256(value.tobytes()).hexdigest()[:16]

    # Generic - pickle and hash
    try:
        pickled = pickle.dumps(value)
        return hashlib.sha256(pickled).hexdigest()[:16]
    except Exception:
        return f"unhashable:{type(value).__name__}"


def _default_compare(a: Any, b: Any) -> bool:
    """Default comparison for determinism checking."""
    if HAS_JAX and hasattr(a, "device") and hasattr(b, "device"):
        return bool(jnp.allclose(a, b, rtol=0, atol=0))

    if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        return np.array_equal(a, b)

    if isinstance(a, float) and isinstance(b, float):
        return a == b  # Exact equality for determinism

    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_default_compare(a[k], b[k]) for k in a.keys())

    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_default_compare(ai, bi) for ai, bi in zip(a, b, strict=False))

    return a == b


def _describe_divergence(a: Any, b: Any) -> str:
    """Describe how two values differ."""
    if HAS_JAX and hasattr(a, "device") and hasattr(b, "device"):
        diff = jnp.abs(a - b)
        return (
            f"JAX array divergence:\n"
            f"  Max diff: {float(jnp.max(diff))}\n"
            f"  Num diffs: {int(jnp.sum(diff > 0))}\n"
            f"  Shape: {a.shape}"
        )

    if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        diff = np.abs(a - b)
        return (
            f"NumPy array divergence:\n"
            f"  Max diff: {np.max(diff)}\n"
            f"  Num diffs: {np.sum(diff > 0)}\n"
            f"  Shape: {a.shape}"
        )

    return f"Value divergence:\n  First: {a}\n  Second: {b}"


# Pytest plugin helpers

def assert_deterministic(
    fn: Callable[..., T],
    args: tuple = (),
    kwargs: dict | None = None,
    runs: int = 5,
    message: str = "",
) -> None:
    """
    Pytest-friendly assertion for determinism.

    Example:
        >>> def my_init(key):
        ...     return jax.random.normal(key, (10,))
        >>> assert_deterministic(my_init, args=(jax.random.PRNGKey(42),))
    """
    result = verify(fn, args, kwargs, runs)
    if not result.passed:
        raise AssertionError(
            f"Function is non-deterministic{': ' + message if message else ''}\n"
            f"First divergence at run {result.first_divergence_run}\n"
            f"{result.divergence_details}"
        )


def deterministic_test(runs: int = 5):
    """
    Decorator to verify test function is deterministic.

    Example:
        >>> @deterministic_test(runs=3)
        ... def test_something():
        ...     return compute_result()  # Must return same value each run
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs):
            result = verify(fn, args, kwargs, runs)
            if not result.passed:
                raise AssertionError(
                    f"Test {fn.__name__} is non-deterministic\n"
                    f"{result.divergence_details}"
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator
