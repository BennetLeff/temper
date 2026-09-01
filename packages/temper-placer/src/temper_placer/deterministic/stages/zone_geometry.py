"""``Zone`` dataclass -- the placement-zone data type.

Shim-debt cleanup (2026-08-20): the ``ZoneGeometryStage`` class (its
constructor state and its ``run``) moved to ``stages/__init__.py`` as a
:class:`~stages.base.RustFunctionStage` parameterized adapter over
``temper_orchestration.run_zone_geometry`` (Phase D batch D2 of the Rust
Orchestration Engine plan 2026-08-09-001).

This module survives as the home of the :class:`Zone` dataclass -- a real
data type, not a shim: the Rust ``ZoneGeometryStage``
(``temper-orchestration/src/zone_geometry_stage.rs``) and the
``netlist_owned`` marshalling resolve it at runtime by importing
``temper_placer.deterministic.stages.zone_geometry`` and reading ``Zone``,
and the pinned VERBATIM oracle
(``tests/deterministic/_zone_geometry_py_oracle.py``) compares the stage's
output structurally against its own Zone snapshot. The stage class no
longer lives here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    """Represents a placement zone on the board."""

    name: str
    bounds: tuple[tuple[float, float], tuple[float, float]]  # ((x_min, y_min), (x_max, y_max))


__all__ = ["Zone"]
