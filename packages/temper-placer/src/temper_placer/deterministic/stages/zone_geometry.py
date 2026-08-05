"""Zone geometry for the deterministic placement pipeline.

The pure compute is implemented in Rust in the ``temper-design-bundle`` crate
(Wave 4 **Phase 5, first slice** — deterministic leaf stages). This module
keeps the pre-migration public API unchanged and delegates the layout math to
``temper_design_bundle_python.deterministic_stages`` (``define_zone_layout``
for the 4-zone MVP-3 layout, ``scale_zone_bounds`` for the config ``bounds_ratio``
branch); the ``run`` orchestration (the ``state.board`` guard and the
``frozenset`` wrap) stays Python, as does the core/board.py ``Zone``-object
adaptation in ``_define_zones_from_config`` (a type conversion, not compute).

Bit-exactness: the Rust kernels reproduce the oracle's exact expression
order — every MAX boundary is an INDEPENDENT fresh multiply
(``board_width * 0.3 / * 0.6 / * 0.9``; a reuse chain would break
bit-parity, e.g. ``(w*0.3)*3 = 0.09`` vs ``w*0.9 = 0.09000000000000001``
for ``w = 0.1``), only the MIN boundaries reuse the previous product, and
the config branch scales ``ratio[i] * board_dim`` — and keep ``HV.x_min``
/ every ``y_min`` as Python ``int`` ``0``, passing the board dims through
with their original type (``int`` on an integer board), so the
type-carrying differential canon (int-vs-float) stays green. Verified by
``tests/deterministic/stages/test_zone_geometry_rust_differential.py``
(oracle: ``tests/deterministic/stages/_zone_geometry_py_oracle.py``) and the
PBT suite ``test_zone_geometry_pbt.py``; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from dataclasses import dataclass, replace
from typing import Any

import temper_design_bundle_python as _tdb

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
        if not state.board:
            return state

        if self.zone_config:
            zones = self._define_zones_from_config(state.board.width, state.board.height)
        else:
            zones = self._define_zone_layout(state.board.width, state.board.height)

        return replace(state, zones=frozenset(zones))

    def _define_zones_from_config(self, board_width: float, board_height: float) -> list[Zone]:
        """Define zones using bounds_ratio from config.

        Handles both Zone objects (from config_loader) and dicts (raw YAML).
        The core/board.py Zone uses bounds: (x_min, y_min, x_max, y_max)
        but our local Zone uses bounds: ((x_min, y_min), (x_max, y_max))
        """
        zones = []
        for z in self.zone_config:  # type: ignore[union-attr]
            # Check if z is already a Zone object (from core/board.py)
            if hasattr(z, "name") and hasattr(z, "bounds"):
                # Convert from (x_min, y_min, x_max, y_max) to ((x_min, y_min), (x_max, y_max))
                b = z.bounds
                # core/board.py format: (x_min, y_min, x_max, y_max) vs nested tuple
                bounds = ((b[0], b[1]), (b[2], b[3])) if len(b) == 4 else b
                zones.append(Zone(name=z.name, bounds=bounds))
            elif isinstance(z, dict):
                # Dict format - use bounds_ratio
                name = z["name"]
                ratio = z.get("bounds_ratio", [0, 0, 1, 1])
                x_min, y_min, x_max, y_max = _tdb.deterministic_stages.scale_zone_bounds(
                    name, ratio[0], ratio[1], ratio[2], ratio[3], board_width, board_height
                )
                zones.append(Zone(name=name, bounds=((x_min, y_min), (x_max, y_max))))
            else:
                print(f"WARNING: Unknown zone format: {type(z)}")
        return zones

    def _define_zone_layout(self, board_width: float, board_height: float) -> list[Zone]:
        """
        Define 4-zone layout for MVP-3.

        Zones (left to right):
        - HV: 30% (high-voltage: AC input, IGBTs, gate drivers)
        - Power: 30% (power conversion: DC-DC, bulk caps)
        - Signal: 30% (control: sensing, temperature)
        - MCU: 10% (ESP32-S3 and peripherals)
        """
        rows = _tdb.deterministic_stages.define_zone_layout(board_width, board_height)
        return [
            Zone(name=name, bounds=((x_min, y_min), (x_max, y_max)))
            for name, x_min, y_min, x_max, y_max in rows
        ]
