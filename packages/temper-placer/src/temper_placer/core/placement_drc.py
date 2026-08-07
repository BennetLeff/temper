"""Pre-routing placement DRC: pad shorts and electrical clearance.

Wave-4 Phase 2: ``PinInfo`` and ``PlacementViolation`` are now the Rust
``#[pyclass]`` types of the same names in ``temper-io-types``, and the
O(n^2) pair scan runs there.

Two contract details worth knowing when reading the Rust:

* ``violation.item_a`` is the caller's *own* pin object, by identity, not
  a copy -- the Rust boundary re-attaches ``pins[i]`` after the scan.
* the CLEARANCE message embeds ``f"{dist:.3f}"``, which CPython renders
  ``nan``/``inf`` where Rust's ``{:.3}`` renders ``NaN``/``inf``; the
  Rust port formats through its own CPython-compatible helper.
"""

from __future__ import annotations

from typing import TypeAlias

import temper_io_types as _rs

# `temper_io_types` has no `.pyi` stub, so `_rs.PinInfo`/`_rs.PlacementViolation`
# type as `Any`; without an explicit `TypeAlias` annotation mypy cannot tell
# this rebinding is meant to be used as a type (`Variable ... is not valid as
# a type`) rather than a runtime value -- same idiom used for the numpy Array
# aliases elsewhere in core/ (e.g. core/board.py, core/netlist.py).
PinInfo: TypeAlias = _rs.PinInfo
PlacementViolation: TypeAlias = _rs.PlacementViolation


def validate_placement_drc(
    pins: list[PinInfo], min_clearance_mm: float, _trace_width_mm: float = 0.25
) -> list[PlacementViolation]:
    """
    Validate placement for DRC violations before routing.

    Checks for:
    1. Shorts: Different nets overlapping (Distance < r1 + r2)
    2. Clearance: Different nets too close (Distance < r1 + r2 + clearance)
    3. Routability (Heuristic): Heuristic warning if pins are barely separated

    Args:
        pins: List of PinInfo objects
        min_clearance_mm: Minimum electrical clearance required
        _trace_width_mm: Nominal trace width. Accepted for signature
            compatibility; the reference never read it either (the
            "routability" check its docstring names is not implemented).

    Returns:
        List of PlacementViolation objects
    """
    return _rs.validate_placement_drc(pins, min_clearance_mm, _trace_width_mm)
