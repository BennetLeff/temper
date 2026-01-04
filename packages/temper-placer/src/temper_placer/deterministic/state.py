from dataclasses import dataclass
from typing import FrozenSet

@dataclass(frozen=True)
class BoardState:
    '''Immutable snapshot of board at any pipeline stage.'''
    placements: FrozenSet = frozenset()
    routes: FrozenSet = frozenset()
    violations: FrozenSet = frozenset()
