# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the pre-migration source of
#   packages/temper-placer/src/temper_placer/deterministic/stages/zone_geometry.py
# at the D2 dispatch base (origin/main, bd85d76e). Relative imports are
# adapted to absolute paths so the oracle imports from the test tree; every
# other line is the verbatim pre-migration source.
#
# This is the R1a behavioural oracle for the D2 Rust Stage-engine port in
# packages/temper-orchestration (plan 2026-08-09-001, Phase D batch D2). It
# must keep the ORIGINAL pure-Python semantics forever, including any warts.
# If a differential test fails, the Rust side is wrong until proven
# otherwise -- never edit this file to make a test pass.
#
# test_deterministic_d2_rust_differential.py recomputes the sha256 of
# everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
from dataclasses import dataclass, replace
from typing import Any

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage


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
