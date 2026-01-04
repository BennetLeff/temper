from ..state import BoardState
from .base import Stage

class DRCValidationStage(Stage):
    @property
    def name(self) -> str:
        return "drc_validation"
    
    def run(self, state: BoardState) -> BoardState:
        return state
