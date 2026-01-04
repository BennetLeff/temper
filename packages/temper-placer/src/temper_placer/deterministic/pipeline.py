from typing import List
from .state import BoardState
from .stages.base import Stage

class DeterministicPipeline:
    def __init__(self, stages: List[Stage] = None):
        self.stages = stages or []
        
    def run(self, initial_state: BoardState = None) -> BoardState:
        state = initial_state or BoardState()
        for stage in self.stages:
            state = stage.run(state)
        return state
