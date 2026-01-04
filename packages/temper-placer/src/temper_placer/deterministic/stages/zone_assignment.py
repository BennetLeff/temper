from ..state import BoardState
from .base import Stage

class ZoneAssignmentStage(Stage):
    @property
    def name(self) -> str:
        return "zone_assignment"
    
    def run(self, state: BoardState) -> BoardState:
        return state
