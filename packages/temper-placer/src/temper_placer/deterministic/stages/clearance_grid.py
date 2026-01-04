from ..state import BoardState
from .base import Stage

class ClearanceGridStage(Stage):
    @property
    def name(self) -> str:
        return "clearance_grid"
    
    def run(self, state: BoardState) -> BoardState:
        return state
