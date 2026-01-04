from abc import ABC, abstractmethod
from ..state import BoardState

class Stage(ABC):
    '''Abstract base class for pipeline stages.'''
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @abstractmethod
    def run(self, state: BoardState) -> BoardState:
        '''Execute stage and return new state.'''
        pass
