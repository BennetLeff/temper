from ..state import BoardState
from .base import Stage

class SequentialRoutingStage(Stage):
    @property
    def name(self) -> str:
        return "sequential_routing"
    
    def run(self, state: BoardState) -> BoardState:
        return state
