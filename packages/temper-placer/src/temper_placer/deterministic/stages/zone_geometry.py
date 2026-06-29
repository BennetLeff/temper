from dataclasses import dataclass, replace
from typing import Any

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
        for z in self.zone_config:
            # Check if z is already a Zone object (from core/board.py)
            if hasattr(z, 'name') and hasattr(z, 'bounds'):
                # Convert from (x_min, y_min, x_max, y_max) to ((x_min, y_min), (x_max, y_max))
                b = z.bounds
                # core/board.py format: (x_min, y_min, x_max, y_max) vs nested tuple
                bounds = ((b[0], b[1]), (b[2], b[3])) if len(b) == 4 else b
                zones.append(Zone(name=z.name, bounds=bounds))
            elif isinstance(z, dict):
                # Dict format - use bounds_ratio
                name = z['name']
                ratio = z.get('bounds_ratio', [0, 0, 1, 1])
                zones.append(Zone(
                    name=name,
                    bounds=(
                        (ratio[0] * board_width, ratio[1] * board_height),
                        (ratio[2] * board_width, ratio[3] * board_height)
                    )
                ))
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
        zones = []

        # HV Zone: 0 to 30%
        hv_x_max = board_width * 0.3
        zones.append(Zone(
            name="HV",
            bounds=((0, 0), (hv_x_max, board_height))
        ))

        # Power Zone: 30% to 60%
        power_x_min = hv_x_max
        power_x_max = board_width * 0.6
        zones.append(Zone(
            name="Power",
            bounds=((power_x_min, 0), (power_x_max, board_height))
        ))

        # Signal Zone: 60% to 90%
        signal_x_min = power_x_max
        signal_x_max = board_width * 0.9
        zones.append(Zone(
            name="Signal",
            bounds=((signal_x_min, 0), (signal_x_max, board_height))
        ))

        # MCU Zone: 90% to 100%
        mcu_x_min = signal_x_max
        zones.append(Zone(
            name="MCU",
            bounds=((mcu_x_min, 0), (board_width, board_height))
        ))

        return zones
