"""
Runtime invariant checking.

Enable/disable runtime checks via environment variable.
Useful for catching bugs in development while avoiding overhead in production.

Usage:
    TEMPER_CHECK_INVARIANTS=1 python train.py  # Enable checks
    python train.py  # Disabled by default
"""

from __future__ import annotations

import os
import functools
from typing import Callable, Any, TypeVar
import numpy as np

T = TypeVar("T")

# Global flag - set by environment variable
INVARIANTS_ENABLED = os.environ.get("TEMPER_CHECK_INVARIANTS", "0") == "1"


def enabled() -> bool:
    """Check if invariant checking is enabled."""
    return INVARIANTS_ENABLED


def enable():
    """Enable invariant checking (for testing)."""
    global INVARIANTS_ENABLED
    INVARIANTS_ENABLED = True


def disable():
    """Disable invariant checking."""
    global INVARIANTS_ENABLED
    INVARIANTS_ENABLED = False


class InvariantViolation(Exception):
    """Raised when an invariant is violated."""
    pass


def assert_invariant(
    condition: bool,
    message: str = "Invariant violated",
    data: dict[str, Any] | None = None,
) -> None:
    """
    Assert an invariant holds (when checking enabled).

    Args:
        condition: The invariant condition.
        message: Error message if violated.
        data: Additional context data.

    Raises:
        InvariantViolation: If condition is False and checking enabled.
    """
    if not INVARIANTS_ENABLED:
        return

    if not condition:
        full_message = message
        if data:
            full_message += f"\nContext: {data}"
        raise InvariantViolation(full_message)


def check(cls: type[T]) -> type[T]:
    """
    Class decorator to enable invariant checking on methods.

    Methods can use assert_invariant() and checks will only run
    when TEMPER_CHECK_INVARIANTS=1.

    Example:
        @check
        class MazeRouter:
            def route(self, net):
                result = self._route_impl(net)
                assert_invariant(result.path_connected(), "Path must be connected")
                return result
    """
    # Just return the class unchanged - invariants are checked via assert_invariant
    return cls


def checked(fn: Callable[..., T]) -> Callable[..., T]:
    """
    Function decorator to wrap with invariant checking.

    Example:
        @checked
        def compute_area(vertices):
            area = shoelace(vertices)
            assert_invariant(area >= 0, "Area must be non-negative")
            return area
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


# =============================================================================
# Common Invariants for PCB Placement
# =============================================================================

def assert_positions_in_bounds(
    positions: np.ndarray,
    bounds: tuple[float, float, float, float],  # x_min, y_min, x_max, y_max
    message: str = "Positions out of bounds",
) -> None:
    """Assert all positions are within bounds."""
    if not INVARIANTS_ENABLED:
        return

    x_min, y_min, x_max, y_max = bounds
    xs = positions[:, 0]
    ys = positions[:, 1]

    violations = []
    if np.any(xs < x_min):
        violations.append(f"x < x_min: {xs[xs < x_min]}")
    if np.any(xs > x_max):
        violations.append(f"x > x_max: {xs[xs > x_max]}")
    if np.any(ys < y_min):
        violations.append(f"y < y_min: {ys[ys < y_min]}")
    if np.any(ys > y_max):
        violations.append(f"y > y_max: {ys[ys > y_max]}")

    if violations:
        raise InvariantViolation(f"{message}: {'; '.join(violations)}")


def assert_no_nan(
    array: np.ndarray,
    name: str = "array",
) -> None:
    """Assert array contains no NaN values."""
    if not INVARIANTS_ENABLED:
        return

    if np.any(np.isnan(array)):
        nan_count = np.sum(np.isnan(array))
        nan_indices = np.argwhere(np.isnan(array))[:5]  # First 5
        raise InvariantViolation(
            f"NaN values in {name}: {nan_count} NaNs found at indices {nan_indices.tolist()}"
        )


def assert_no_inf(
    array: np.ndarray,
    name: str = "array",
) -> None:
    """Assert array contains no infinite values."""
    if not INVARIANTS_ENABLED:
        return

    if np.any(np.isinf(array)):
        inf_count = np.sum(np.isinf(array))
        raise InvariantViolation(
            f"Infinite values in {name}: {inf_count} found"
        )


def assert_finite(
    array: np.ndarray,
    name: str = "array",
) -> None:
    """Assert array contains only finite values (no NaN or Inf)."""
    assert_no_nan(array, name)
    assert_no_inf(array, name)


def assert_positive(
    array: np.ndarray,
    name: str = "array",
    strict: bool = False,
) -> None:
    """Assert array values are positive (or non-negative)."""
    if not INVARIANTS_ENABLED:
        return

    if strict:
        if np.any(array <= 0):
            violations = array[array <= 0]
            raise InvariantViolation(
                f"Non-positive values in {name}: {violations[:5]}"
            )
    else:
        if np.any(array < 0):
            violations = array[array < 0]
            raise InvariantViolation(
                f"Negative values in {name}: {violations[:5]}"
            )


def assert_normalized(
    array: np.ndarray,
    axis: int = -1,
    tolerance: float = 1e-6,
    name: str = "array",
) -> None:
    """Assert vectors in array are unit length."""
    if not INVARIANTS_ENABLED:
        return

    norms = np.linalg.norm(array, axis=axis)
    if not np.allclose(norms, 1.0, atol=tolerance):
        bad_norms = norms[~np.isclose(norms, 1.0, atol=tolerance)]
        raise InvariantViolation(
            f"Non-unit vectors in {name}: norms = {bad_norms[:5]}"
        )


def assert_probability_distribution(
    probs: np.ndarray,
    axis: int = -1,
    tolerance: float = 1e-6,
    name: str = "probabilities",
) -> None:
    """Assert array represents valid probability distribution."""
    if not INVARIANTS_ENABLED:
        return

    # Check non-negative
    if np.any(probs < -tolerance):
        raise InvariantViolation(
            f"Negative probabilities in {name}: {probs[probs < 0][:5]}"
        )

    # Check sums to 1
    sums = np.sum(probs, axis=axis)
    if not np.allclose(sums, 1.0, atol=tolerance):
        raise InvariantViolation(
            f"Probabilities don't sum to 1 in {name}: sums = {sums}"
        )


def assert_symmetric(
    matrix: np.ndarray,
    tolerance: float = 1e-10,
    name: str = "matrix",
) -> None:
    """Assert matrix is symmetric."""
    if not INVARIANTS_ENABLED:
        return

    if matrix.shape[0] != matrix.shape[1]:
        raise InvariantViolation(f"{name} is not square: {matrix.shape}")

    if not np.allclose(matrix, matrix.T, atol=tolerance):
        diff = np.abs(matrix - matrix.T)
        max_diff = np.max(diff)
        raise InvariantViolation(
            f"{name} is not symmetric: max asymmetry = {max_diff}"
        )


def assert_path_connected(
    path: list[tuple[int, int]] | list[tuple[int, int, int]],
    allow_diagonal: bool = False,
) -> None:
    """Assert path cells are connected (Manhattan adjacency)."""
    if not INVARIANTS_ENABLED:
        return

    if len(path) < 2:
        return  # Empty or single cell is trivially connected

    for i in range(len(path) - 1):
        p1, p2 = path[i], path[i + 1]

        # Handle 2D or 3D cells
        if len(p1) == 2:
            dx = abs(p1[0] - p2[0])
            dy = abs(p1[1] - p2[1])
            dist = dx + dy
        else:
            dx = abs(p1[0] - p2[0])
            dy = abs(p1[1] - p2[1])
            dz = abs(p1[2] - p2[2])
            dist = dx + dy + dz

        max_dist = 2 if allow_diagonal else 1
        if dist > max_dist:
            raise InvariantViolation(
                f"Path disconnected at index {i}: {p1} -> {p2} (distance={dist})"
            )


def assert_no_overlap(
    positions: np.ndarray,
    sizes: np.ndarray,
    min_gap: float = 0.0,
) -> None:
    """Assert no components overlap."""
    if not INVARIANTS_ENABLED:
        return

    n = len(positions)
    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(positions[i, 0] - positions[j, 0])
            dy = abs(positions[i, 1] - positions[j, 1])

            min_dx = (sizes[i, 0] + sizes[j, 0]) / 2 + min_gap
            min_dy = (sizes[i, 1] + sizes[j, 1]) / 2 + min_gap

            if dx < min_dx and dy < min_dy:
                raise InvariantViolation(
                    f"Overlap between components {i} and {j}: "
                    f"positions={positions[i]}, {positions[j]}, "
                    f"sizes={sizes[i]}, {sizes[j]}"
                )


# =============================================================================
# Gradient Invariants
# =============================================================================

def assert_gradient_finite(
    grad: np.ndarray,
    name: str = "gradient",
) -> None:
    """Assert gradient is finite (no NaN or Inf)."""
    assert_finite(grad, name)


def assert_gradient_bounded(
    grad: np.ndarray,
    max_norm: float = 1e6,
    name: str = "gradient",
) -> None:
    """Assert gradient magnitude is bounded."""
    if not INVARIANTS_ENABLED:
        return

    norm = np.linalg.norm(grad)
    if norm > max_norm:
        raise InvariantViolation(
            f"Gradient {name} too large: ||grad|| = {norm} > {max_norm}"
        )
