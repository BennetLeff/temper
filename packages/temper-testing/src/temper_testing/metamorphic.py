"""
Metamorphic testing framework.

Test relationships between inputs and outputs rather than exact values.
Useful when oracles are unavailable but relationships are known.

Example relationships:
- Larger margin → more blocked cells
- Finer grid → more precise blocking
- Rotation by 360° → same result
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import numpy as np

T = TypeVar("T")  # Input type
U = TypeVar("U")  # Output type


@dataclass
class MetamorphicResult:
    """Result of metamorphic property verification."""
    passed: bool
    num_cases: int
    num_failed: int
    first_failure: dict[str, Any] | None
    message: str


class Property(ABC, Generic[T, U]):
    """
    Base class for metamorphic properties.

    A metamorphic property defines:
    1. How to transform an input to a related input
    2. What relationship should hold between outputs
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the property."""
        pass

    @abstractmethod
    def transform_input(self, input1: T) -> T:
        """Transform input1 to produce related input2."""
        pass

    @abstractmethod
    def check_relation(self, output1: U, output2: U, input1: T, input2: T) -> bool:
        """Check if outputs satisfy the expected relationship."""
        pass

    def describe_failure(self, output1: U, output2: U, _input1: T, _input2: T) -> str:
        """Describe why the relation check failed."""
        return f"Relation failed: output1={output1}, output2={output2}"


def verify_property(
    prop: Property[T, U],
    fn: Callable[[T], U],
    inputs: list[T],
) -> MetamorphicResult:
    """
    Verify a metamorphic property holds for a function.

    Args:
        prop: The metamorphic property to verify.
        fn: The function under test.
        inputs: List of inputs to test.

    Returns:
        MetamorphicResult with verification details.
    """
    num_failed = 0
    first_failure = None

    for input1 in inputs:
        input2 = prop.transform_input(input1)

        output1 = fn(input1)
        output2 = fn(input2)

        if not prop.check_relation(output1, output2, input1, input2):
            num_failed += 1
            if first_failure is None:
                first_failure = {
                    "input1": input1,
                    "input2": input2,
                    "output1": output1,
                    "output2": output2,
                    "description": prop.describe_failure(output1, output2, input1, input2),
                }

    passed = num_failed == 0
    message = (
        f"Property '{prop.name}' {'PASSED' if passed else 'FAILED'}: "
        f"{len(inputs) - num_failed}/{len(inputs)} cases passed"
    )

    return MetamorphicResult(
        passed=passed,
        num_cases=len(inputs),
        num_failed=num_failed,
        first_failure=first_failure,
        message=message,
    )


# =============================================================================
# Common Metamorphic Properties
# =============================================================================

class Monotonic(Property[float, float]):
    """Output increases/decreases monotonically with input."""

    def __init__(self, delta: float = 1.0, increasing: bool = True):
        self.delta = delta
        self.increasing = increasing

    @property
    def name(self) -> str:
        direction = "increasing" if self.increasing else "decreasing"
        return f"Monotonic ({direction})"

    def transform_input(self, input1: float) -> float:
        return input1 + self.delta

    def check_relation(self, output1: float, output2: float, _input1: float, _input2: float) -> bool:
        if self.increasing:
            return output2 >= output1
        else:
            return output2 <= output1

    def describe_failure(self, output1: float, output2: float, input1: float, input2: float) -> str:
        direction = "increase" if self.increasing else "decrease"
        return (
            f"Expected output to {direction} when input increases from {input1} to {input2}, "
            f"but output went from {output1} to {output2}"
        )


class Symmetric(Property[tuple[Any, Any], Any]):
    """f(a, b) == f(b, a)"""

    @property
    def name(self) -> str:
        return "Symmetric"

    def transform_input(self, input1: tuple[Any, Any]) -> tuple[Any, Any]:
        a, b = input1
        return (b, a)

    def check_relation(self, output1: Any, output2: Any, _input1: Any, _input2: Any) -> bool:
        if isinstance(output1, np.ndarray):
            return np.allclose(output1, output2)
        elif isinstance(output1, float):
            return abs(output1 - output2) < 1e-10
        else:
            return output1 == output2


class Idempotent(Property[T, T]):
    """f(f(x)) == f(x)"""

    def __init__(self, fn: Callable[[T], T]):
        self._fn = fn

    @property
    def name(self) -> str:
        return "Idempotent"

    def transform_input(self, input1: T) -> T:
        # Apply function once to get input for second application
        return self._fn(input1)

    def check_relation(self, output1: T, output2: T, _input1: T, _input2: T) -> bool:
        # output1 = f(input1), output2 = f(f(input1))
        # Should have output1 == output2
        if isinstance(output1, np.ndarray):
            return np.allclose(output1, output2)
        return output1 == output2


class Subset(Property[Any, set]):
    """Transformed input produces subset of original output."""

    def __init__(self, transform: Callable[[Any], Any]):
        self._transform = transform

    @property
    def name(self) -> str:
        return "Subset"

    def transform_input(self, input1: Any) -> Any:
        return self._transform(input1)

    def check_relation(self, output1: set, output2: set, _input1: Any, _input2: Any) -> bool:
        return output1.issubset(output2) or output2.issubset(output1)


class Superset(Property[Any, set]):
    """Transformed input produces superset of original output."""

    def __init__(self, transform: Callable[[Any], Any]):
        self._transform = transform

    @property
    def name(self) -> str:
        return "Superset"

    def transform_input(self, input1: Any) -> Any:
        return self._transform(input1)

    def check_relation(self, output1: set, output2: set, _input1: Any, _input2: Any) -> bool:
        return output2.issuperset(output1)


class Invariant(Property[T, U]):
    """Output unchanged under transformation."""

    def __init__(self, transform: Callable[[T], T]):
        self._transform = transform

    @property
    def name(self) -> str:
        return "Invariant"

    def transform_input(self, input1: T) -> T:
        return self._transform(input1)

    def check_relation(self, output1: U, output2: U, _input1: T, _input2: T) -> bool:
        if isinstance(output1, np.ndarray):
            return np.allclose(output1, output2)
        elif isinstance(output1, float):
            return abs(output1 - output2) < 1e-10
        return output1 == output2


# =============================================================================
# Domain-Specific Properties for PCB Placement
# =============================================================================

class LargerMarginBlocksMore(Property[float, set]):
    """Larger blocking margin → more cells blocked."""

    @property
    def name(self) -> str:
        return "LargerMarginBlocksMore"

    def transform_input(self, margin1: float) -> float:
        return margin1 + 0.5  # Increase margin

    def check_relation(self, blocked1: set, blocked2: set, _margin1: float, _margin2: float) -> bool:
        return blocked1.issubset(blocked2)

    def describe_failure(self, blocked1: set, blocked2: set, margin1: float, margin2: float) -> str:
        extra_in_1 = blocked1 - blocked2
        return (
            f"With margin {margin1}, blocked {len(blocked1)} cells. "
            f"With margin {margin2}, blocked {len(blocked2)} cells. "
            f"But {len(extra_in_1)} cells were blocked with smaller margin only: {list(extra_in_1)[:5]}"
        )


class FinerGridMorePrecise(Property[float, int]):
    """Finer grid cell size → blocking count ≥ coarse grid."""

    @property
    def name(self) -> str:
        return "FinerGridMorePrecise"

    def transform_input(self, cell_size1: float) -> float:
        return cell_size1 / 2  # Halve cell size (finer)

    def check_relation(self, count1: int, count2: int, cell_size1: float, cell_size2: float) -> bool:
        # Finer grid should have same or more blocked cells
        # (scaled by area ratio)
        ratio = (cell_size1 / cell_size2) ** 2
        return count2 >= count1 * ratio * 0.9  # Allow 10% tolerance


class RotationInvariantArea(Property[list, float]):
    """Polygon area invariant to rotation."""

    def __init__(self, angle_degrees: float = 90.0):
        self.angle = angle_degrees

    @property
    def name(self) -> str:
        return f"RotationInvariantArea({self.angle}°)"

    def transform_input(self, vertices: list) -> list:
        """Rotate all vertices around centroid."""
        import math
        cx = sum(v[0] for v in vertices) / len(vertices)
        cy = sum(v[1] for v in vertices) / len(vertices)
        angle_rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)

        rotated = []
        for x, y in vertices:
            dx, dy = x - cx, y - cy
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            rotated.append((rx, ry))

        return rotated

    def check_relation(self, area1: float, area2: float, _v1: list, _v2: list) -> bool:
        return abs(area1 - area2) < 1e-6


class TranslationInvariantArea(Property[list, float]):
    """Polygon area invariant to translation."""

    def __init__(self, dx: float = 10.0, dy: float = 10.0):
        self.dx = dx
        self.dy = dy

    @property
    def name(self) -> str:
        return f"TranslationInvariantArea(dx={self.dx}, dy={self.dy})"

    def transform_input(self, vertices: list) -> list:
        return [(x + self.dx, y + self.dy) for x, y in vertices]

    def check_relation(self, area1: float, area2: float, _v1: list, _v2: list) -> bool:
        return abs(area1 - area2) < 1e-10
