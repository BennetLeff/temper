from dataclasses import dataclass, replace
from typing import Tuple
from ..state import BoardState
from .base import Stage

@dataclass(frozen=True)
class Zone:
    """Represents a placement zone on the board."""
    name: str
    bounds: Tuple[Tuple[float, float], Tuple[float, float]]  # ((x_min, y_min), (x_max, y_max))

class ZoneGeometryStage(Stage):
    @property
    def name(self) -> str:
        return "zone_geometry"
    
    def run(self, state: BoardState) -> BoardState:
        if not state.board:
            return state
        
        zones = self._define_zone_layout(state.board.width, state.board.height)
        return replace(state, zones=frozenset(zones))
    
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
