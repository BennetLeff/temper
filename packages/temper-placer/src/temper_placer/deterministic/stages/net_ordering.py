from ..state import BoardState
from .base import Stage

class NetOrderingStage(Stage):
    @property
    def name(self) -> str:
        return "net_ordering"
    
    def run(self, state: BoardState) -> BoardState:
        return state
