"""
Oracle testing framework.

Test against known-correct answers rather than just properties.
An "oracle" is a reference implementation or known result.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Callable, Any, TypeVar
import numpy as np

T = TypeVar("T")


@dataclass
class OracleResult:
    """Result of oracle comparison."""
    passed: bool
    expected: Any
    actual: Any
    tolerance: float | None
    message: str


def exact(
    expected: T,
    tolerance: float = 1e-10,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for oracle tests with exact expected value.

    Args:
        expected: The known-correct result.
        tolerance: Tolerance for floating-point comparison.

    Example:
        >>> @exact(expected=12.0)
        ... def test_rectangle_area():
        ...     return 4.0 * 3.0  # Should be 12.0
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            actual = fn(*args, **kwargs)
            _compare_oracle(expected, actual, tolerance, fn.__name__)
            return actual
        return wrapper
    return decorator


def bounded(
    min_val: float | None = None,
    max_val: float | None = None,
) -> Callable[[Callable[..., float]], Callable[..., float]]:
    """
    Decorator for oracle tests with bounded expected value.

    Args:
        min_val: Minimum acceptable value.
        max_val: Maximum acceptable value.

    Example:
        >>> @bounded(min_val=0.0, max_val=100.0)
        ... def test_loss():
        ...     return compute_loss()  # Must be in [0, 100]
    """
    def decorator(fn: Callable[..., float]) -> Callable[..., float]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> float:
            actual = fn(*args, **kwargs)

            if min_val is not None and actual < min_val:
                raise AssertionError(
                    f"Oracle bound violation in {fn.__name__}: "
                    f"{actual} < {min_val} (min)"
                )
            if max_val is not None and actual > max_val:
                raise AssertionError(
                    f"Oracle bound violation in {fn.__name__}: "
                    f"{actual} > {max_val} (max)"
                )

            return actual
        return wrapper
    return decorator


def oracle_test(
    oracle_fn: Callable[..., T],
    tolerance: float = 1e-10,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator comparing function output against oracle function.

    Args:
        oracle_fn: Reference implementation to compare against.
        tolerance: Tolerance for comparison.

    Example:
        >>> def numpy_matmul(a, b):
        ...     return np.matmul(a, b)
        >>>
        >>> @oracle_test(oracle_fn=numpy_matmul)
        ... def test_custom_matmul(a, b):
        ...     return custom_matmul(a, b)
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            expected = oracle_fn(*args, **kwargs)
            actual = fn(*args, **kwargs)
            _compare_oracle(expected, actual, tolerance, fn.__name__)
            return actual
        return wrapper
    return decorator


def _compare_oracle(
    expected: Any,
    actual: Any,
    tolerance: float,
    name: str,
) -> None:
    """Compare actual vs expected with appropriate method."""
    if isinstance(expected, np.ndarray) or isinstance(actual, np.ndarray):
        if not np.allclose(expected, actual, rtol=tolerance, atol=tolerance):
            diff = np.abs(np.asarray(expected) - np.asarray(actual))
            raise AssertionError(
                f"Oracle mismatch in {name}:\n"
                f"  Max difference: {np.max(diff)}\n"
                f"  At index: {np.unravel_index(np.argmax(diff), diff.shape)}\n"
                f"  Expected shape: {np.asarray(expected).shape}\n"
                f"  Actual shape: {np.asarray(actual).shape}"
            )
    elif isinstance(expected, float) or isinstance(actual, float):
        if abs(expected - actual) > tolerance:
            raise AssertionError(
                f"Oracle mismatch in {name}:\n"
                f"  Expected: {expected}\n"
                f"  Actual: {actual}\n"
                f"  Difference: {abs(expected - actual)}"
            )
    else:
        if expected != actual:
            raise AssertionError(
                f"Oracle mismatch in {name}:\n"
                f"  Expected: {expected}\n"
                f"  Actual: {actual}"
            )


# Common oracles for geometry

def shoelace_area_oracle(vertices: list[tuple[float, float]]) -> float:
    """
    Reference implementation of shoelace formula for polygon area.

    This is the oracle - a known-correct implementation.
    """
    n = len(vertices)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]

    return abs(area) / 2.0


def manhattan_distance_oracle(p1: tuple[int, int], p2: tuple[int, int]) -> int:
    """Oracle for Manhattan distance."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def euclidean_distance_oracle(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Oracle for Euclidean distance."""
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def box_overlap_oracle(
    box1: tuple[float, float, float, float],  # x, y, w, h
    box2: tuple[float, float, float, float],
) -> bool:
    """Oracle for axis-aligned box overlap detection."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    # Check if boxes are separated
    if x1 + w1 / 2 < x2 - w2 / 2:  # box1 left of box2
        return False
    if x1 - w1 / 2 > x2 + w2 / 2:  # box1 right of box2
        return False
    if y1 + h1 / 2 < y2 - h2 / 2:  # box1 below box2
        return False
    if y1 - h1 / 2 > y2 + h2 / 2:  # box1 above box2
        return False

    return True


# Oracle test case generators

@dataclass
class OracleCase:
    """A test case with known input and output."""
    name: str
    input: Any
    expected: Any
    tolerance: float = 1e-10


def generate_rectangle_area_cases() -> list[OracleCase]:
    """Generate oracle test cases for rectangle area."""
    return [
        OracleCase(
            name="unit_square",
            input=[(0, 0), (1, 0), (1, 1), (0, 1)],
            expected=1.0,
        ),
        OracleCase(
            name="3x4_rectangle",
            input=[(0, 0), (3, 0), (3, 4), (0, 4)],
            expected=12.0,
        ),
        OracleCase(
            name="degenerate_line",
            input=[(0, 0), (5, 0), (10, 0)],
            expected=0.0,
        ),
        OracleCase(
            name="triangle",
            input=[(0, 0), (4, 0), (2, 3)],
            expected=6.0,  # allow-safety-constant: triangle area oracle
        ),
        OracleCase(
            name="negative_coords",
            input=[(-1, -1), (1, -1), (1, 1), (-1, 1)],
            expected=4.0,
        ),
    ]


def generate_path_length_cases() -> list[OracleCase]:
    """Generate oracle test cases for path length."""
    return [
        OracleCase(
            name="straight_horizontal",
            input=[(0, 0), (1, 0), (2, 0), (3, 0)],
            expected=3,
        ),
        OracleCase(
            name="straight_vertical",
            input=[(0, 0), (0, 1), (0, 2)],
            expected=2,
        ),
        OracleCase(
            name="L_shape",
            input=[(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)],
            expected=4,
        ),
        OracleCase(
            name="single_cell",
            input=[(5, 5)],
            expected=0,
        ),
    ]
