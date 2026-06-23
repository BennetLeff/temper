from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..state import BoardState

if TYPE_CHECKING:
    from temper_drc.core.fence import InvariantSpec

class Stage(ABC):
    '''Abstract base class for pipeline stages.'''
    
    alternative: Stage | None = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    def invariants(self) -> tuple[InvariantSpec, ...]:
        return ()
    
    @property
    def last_modified_regions(self) -> list[tuple[float, float, float, float]] | None:
        return None
    
    @abstractmethod
    def run(self, state: BoardState) -> BoardState:
        '''Execute stage and return new state.'''
        pass
