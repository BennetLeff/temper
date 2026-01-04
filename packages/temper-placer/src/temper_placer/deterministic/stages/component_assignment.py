from ..state import BoardState
from .base import Stage

class ComponentAssignmentStage(Stage):
    @property
    def name(self) -> str:
        return "component_assignment"
    
    def run(self, state: BoardState) -> BoardState:
        return state
