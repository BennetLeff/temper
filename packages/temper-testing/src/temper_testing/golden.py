"""
Golden/snapshot testing utilities.

Compare function output against saved "golden" files.
First run saves the output; subsequent runs compare against it.

Update golden files with: TEMPER_UPDATE_GOLDEN=1 pytest
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

T = TypeVar("T")

# Configuration
GOLDEN_DIR = Path(os.environ.get("TEMPER_GOLDEN_DIR", ".golden"))
UPDATE_GOLDEN = os.environ.get("TEMPER_UPDATE_GOLDEN", "0") == "1"


@dataclass
class GoldenComparison:
    """Result of golden file comparison."""
    passed: bool
    golden_path: Path
    is_new: bool
    differences: list[str] | None


def test(fn: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator for golden/snapshot testing.

    First run: saves result to .golden/{test_name}.json
    Later runs: compares result against saved file

    Example:
        @golden.test
        def test_optimize_simple():
            return optimizer.run(simple_netlist)
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)

        # Determine golden file path
        test_name = fn.__name__
        golden_path = GOLDEN_DIR / f"{test_name}.json"

        if UPDATE_GOLDEN or not golden_path.exists():
            # Save new golden file
            _save_golden(result, golden_path)
            if not golden_path.exists():
                print(f"Created golden file: {golden_path}")
        else:
            # Compare against golden
            comparison = _compare_golden(result, golden_path)
            if not comparison.passed:
                raise AssertionError(
                    f"Golden file mismatch for {test_name}:\n"
                    f"  Golden: {golden_path}\n"
                    f"  Differences: {comparison.differences}\n"
                    f"  Run with TEMPER_UPDATE_GOLDEN=1 to update"
                )

        return result

    return wrapper


def compare(
    result: Any,
    golden_name: str,
    tolerance: float = 1e-10,
) -> GoldenComparison:
    """
    Compare result against golden file.

    Args:
        result: The result to compare.
        golden_name: Name of the golden file (without extension).
        tolerance: Tolerance for floating-point comparison.

    Returns:
        GoldenComparison with details.
    """
    golden_path = GOLDEN_DIR / f"{golden_name}.json"

    if UPDATE_GOLDEN or not golden_path.exists():
        _save_golden(result, golden_path)
        return GoldenComparison(
            passed=True,
            golden_path=golden_path,
            is_new=True,
            differences=None,
        )

    return _compare_golden(result, golden_path, tolerance)


def _save_golden(result: Any, path: Path) -> None:
    """Save result to golden file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    serialized = _serialize(result)

    with open(path, "w") as f:
        json.dump(serialized, f, indent=2, default=_json_default)


def _compare_golden(
    result: Any,
    path: Path,
    tolerance: float = 1e-10,
) -> GoldenComparison:
    """Compare result against golden file."""
    with open(path) as f:
        golden = json.load(f)

    serialized = _serialize(result)
    differences = _find_differences(serialized, golden, tolerance)

    return GoldenComparison(
        passed=len(differences) == 0,
        golden_path=path,
        is_new=False,
        differences=differences if differences else None,
    )


def _serialize(obj: Any) -> Any:
    """Convert object to JSON-serializable form."""
    if isinstance(obj, np.ndarray):
        return {
            "__type__": "ndarray",
            "dtype": str(obj.dtype),
            "shape": list(obj.shape),
            "data": obj.tolist(),
        }
    elif hasattr(obj, "__dict__"):
        return {
            "__type__": type(obj).__name__,
            **{k: _serialize(v) for k, v in obj.__dict__.items()},
        }
    elif isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        return str(obj)


def _json_default(obj: Any) -> Any:
    """JSON encoder for special types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    raise TypeError(f"Cannot serialize {type(obj)}")


def _find_differences(
    actual: Any,
    expected: Any,
    tolerance: float,
    path: str = "",
) -> list[str]:
    """Find differences between actual and expected."""
    differences = []

    if type(actual) != type(expected):  # noqa: E721
        differences.append(f"{path}: type mismatch ({type(actual)} vs {type(expected)})")
        return differences

    if isinstance(actual, dict):
        # Check for ndarray type
        if actual.get("__type__") == "ndarray" and expected.get("__type__") == "ndarray":
            actual_arr = np.array(actual["data"])
            expected_arr = np.array(expected["data"])
            if not np.allclose(actual_arr, expected_arr, rtol=tolerance, atol=tolerance):
                diff = np.abs(actual_arr - expected_arr)
                differences.append(
                    f"{path}: ndarray mismatch (max_diff={np.max(diff):.2e})"
                )
            return differences

        # Regular dict comparison
        all_keys = set(actual.keys()) | set(expected.keys())
        for key in all_keys:
            if key not in actual:
                differences.append(f"{path}.{key}: missing in actual")
            elif key not in expected:
                differences.append(f"{path}.{key}: missing in expected")
            else:
                differences.extend(
                    _find_differences(actual[key], expected[key], tolerance, f"{path}.{key}")
                )

    elif isinstance(actual, list):
        if len(actual) != len(expected):
            differences.append(f"{path}: list length mismatch ({len(actual)} vs {len(expected)})")
        else:
            for i, (a, e) in enumerate(zip(actual, expected, strict=False)):
                differences.extend(
                    _find_differences(a, e, tolerance, f"{path}[{i}]")
                )

    elif isinstance(actual, float):
        if abs(actual - expected) > tolerance:
            differences.append(f"{path}: {actual} != {expected} (diff={abs(actual-expected):.2e})")

    elif actual != expected:
        differences.append(f"{path}: {actual} != {expected}")

    return differences


# =============================================================================
# Pytest Integration
# =============================================================================

def pytest_configure(config):
    """Register golden file markers."""
    config.addinivalue_line(
        "markers", "golden: mark test for golden file comparison"
    )


def assert_golden(
    result: Any,
    name: str,
    tolerance: float = 1e-10,
) -> None:
    """
    Pytest-friendly golden file assertion.

    Example:
        def test_something():
            result = compute()
            assert_golden(result, "test_something")
    """
    comparison = compare(result, name, tolerance)

    if not comparison.passed:
        raise AssertionError(
            f"Golden file mismatch:\n"
            f"  File: {comparison.golden_path}\n"
            f"  Differences:\n" +
            "\n".join(f"    - {d}" for d in comparison.differences[:10])
        )


# =============================================================================
# Utilities
# =============================================================================

def list_golden_files() -> list[Path]:
    """List all golden files."""
    if not GOLDEN_DIR.exists():
        return []
    return list(GOLDEN_DIR.glob("*.json"))


def clean_golden_files() -> int:
    """Remove all golden files. Returns count removed."""
    files = list_golden_files()
    for f in files:
        f.unlink()
    return len(files)


def golden_file_hash(name: str) -> str | None:
    """Get hash of golden file contents."""
    path = GOLDEN_DIR / f"{name}.json"
    if not path.exists():
        return None

    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]
