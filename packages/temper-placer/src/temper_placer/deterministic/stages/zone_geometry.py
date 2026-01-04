from ..state import BoardState
from .base import Stage

class ZoneGeometryStage(Stage):
    @property
    def name(self) -> str:
        return "zone_geometry"
    
    def run(self, state: BoardState) -> BoardState:
        return state
