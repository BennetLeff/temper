"""PCL parsing utilities: unit conversion, enum parsing, and PCLParseError.

The parsing *compute* is implemented in Rust in the ``temper-design-bundle``
crate (``temper_design_bundle_python``, module ``pcl_parse.rs``) -- the
Wave 4 Phase 2 "contracts-as-pyo3" pivot. This module keeps the
pre-migration public API unchanged and delegates.

``PCLParseError`` deliberately stays a Python class defined *here*: it is the
identity every ``except PCLParseError`` in the tree binds against, and the
Rust side raises this very class object rather than a look-alike.

The enums returned (``Axis``, ``BoardSide``, ``ConstraintTier``,
``DistanceMetric``, ``EdgeType``) also stay Python ``enum.Enum`` classes --
``for m in SomeEnum`` and ``SomeEnum(value)`` are part of the public API and
a pyo3 ``#[pyclass]`` enum cannot provide class-level iteration. Rust hands
back the same singletons, so callers cannot tell the difference.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/pcl/test_parse_utils_rust_differential.py`` (oracle:
``tests/pcl/_parse_utils_py_oracle.py``); the structural argument lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from typing import Any

import temper_design_bundle_python as _tdb

# Imported for re-export compatibility: callers have always been able to reach
# the enums through this module's namespace via the functions' return values,
# and `from temper_placer.pcl._parse_utils import ...` of these names is used
# by the pinned oracle. Keep the import so the module graph is unchanged.
from temper_placer.pcl.constraints import (  # noqa: F401
    Axis,
    BoardSide,
    ConstraintTier,
    DistanceMetric,
    EdgeType,
)


class PCLParseError(Exception):
    """Error parsing a PCL constraint definition."""

    pass


def _parse_distance_with_unit(value: Any) -> float:
    """Parse distance value with optional unit suffix.

    Supports:
    - Plain float (assumed mm)
    - String with unit: "10mm", "5mil", "0.1in"

    Args:
        value: Distance value (float or string)

    Returns:
        Distance in millimeters

    Raises:
        PCLParseError: If unit is invalid or value cannot be parsed
        ValueError: If a *unit-less* string is not a valid float. This is the
            shipped behaviour -- the bare-number path returns `float(value)`
            directly, so `""`, `"."`, `"-"` and `"..."` raise ValueError, not
            PCLParseError. Preserved deliberately; see the differential's
            `test_unitless_malformed_raises_bare_valueerror`.
    """
    return _tdb.pcl_parse_distance_with_unit(value)


def _parse_tier(tier_value: Any) -> ConstraintTier:
    """Parse tier from integer or string."""
    return _tdb.pcl_parse_tier(tier_value)


def _parse_metric(metric_value: str | None) -> DistanceMetric:
    """Parse distance metric from string."""
    return _tdb.pcl_parse_metric(metric_value)


def _parse_axis(axis_value: str) -> Axis:
    """Parse axis from string."""
    return _tdb.pcl_parse_axis(axis_value)


def _parse_board_side(side_value: str) -> BoardSide:
    """Parse board side from string."""
    return _tdb.pcl_parse_board_side(side_value)


def _parse_edge_type(edge_value: str) -> EdgeType:
    """Parse edge type from string."""
    return _tdb.pcl_parse_edge_type(edge_value)
