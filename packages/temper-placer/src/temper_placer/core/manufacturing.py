"""Fab-process capabilities and worst-case tolerance arithmetic.

Wave-4 Phase 2: ``FabPreset`` is now the Rust ``#[pyclass]`` of the same
name in ``temper-io-types``, and the two tolerance functions delegate to
it. The Python-visible contract is unchanged -- same constructor
signature and defaults, same ``__repr__``, same ``__eq__``, and the same
``TypeError: unhashable type: 'FabPreset'`` a non-frozen dataclass
raises on ``hash()``.

``inflated_clearance`` is ``max(0.0, nominal - tolerance)`` with CPython's
*builtin* ``max`` semantics, which are not ``f64::max``: the builtin keeps
its left operand unless the right compares strictly greater, so it
propagates a NaN from the left only. See ``placer_core/manufacturing.rs``.
"""

from __future__ import annotations

from typing import TypeAlias

import temper_io_types as _rs

# `temper_io_types` has no `.pyi` stub, so `_rs.FabPreset` types as `Any`;
# without an explicit `TypeAlias` annotation mypy cannot tell this rebinding
# is meant to be used as a type (`Variable "FabPreset" is not valid as a
# type`) rather than a runtime value -- same idiom used for the numpy Array
# aliases elsewhere in core/ (e.g. core/board.py, core/netlist.py).
FabPreset: TypeAlias = _rs.FabPreset


def get_fab_presets() -> dict[str, FabPreset]:
    """Get all pre-configured fab house presets."""
    return _rs.get_fab_presets()


def inflated_clearance(nominal: float, tolerance: float = 0.1) -> float:
    """Calculate worst-case (smaller) clearance."""
    return _rs.inflated_clearance(nominal, tolerance)


def inflated_width(nominal: float, tolerance: float = 0.1) -> float:
    """Calculate worst-case (larger) trace width."""
    return _rs.inflated_width(nominal, tolerance)
