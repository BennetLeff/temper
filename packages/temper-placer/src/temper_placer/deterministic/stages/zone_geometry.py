"""Zone geometry for the deterministic placement pipeline.

The stage orchestration is implemented in Rust (``temper-orchestration``'s
``ZoneGeometryStage``, Phase D batch D2 of the Rust Orchestration Engine
plan 2026-08-09-001): it reads ``board`` from the state, dispatches on the
config (the config-vs-default branches), and delegates the layout math to
the already-Rust leaf kernels (``temper_design_bundle_python
.deterministic_stages.define_zone_layout`` / ``scale_zone_bounds`` — the
Wave-4 Phase-5 first-slice migration). This module keeps the public API
(``Zone``, the ``ZoneGeometryStage`` Stage subclass, its constructor and
``name``) and delegates ``run`` across the FFI once per stage call. The
differential oracle for the pre-migration implementation is pinned VERBATIM
in ``tests/deterministic/_zone_geometry_py_oracle.py``.
"""

from dataclasses import dataclass
from typing import Any

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


@dataclass(frozen=True)
class Zone:
    """Represents a placement zone on the board."""

    name: str
    bounds: tuple[tuple[float, float], tuple[float, float]]  # ((x_min, y_min), (x_max, y_max))


class ZoneGeometryStage(Stage):
    def __init__(self, zone_config: list[dict[str, Any]] | None = None):
        self.zone_config = zone_config

    @property
    def name(self) -> str:
        return "zone_geometry"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_zone_geometry(state, self.zone_config)
