from ..state import BoardState
from .base import Stage

class SlotGenerationStage(Stage):
    @property
    def name(self) -> str:
        return "slot_generation"
    
    def run(self, state: BoardState) -> BoardState:
        return state
