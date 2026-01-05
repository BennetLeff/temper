from dataclasses import dataclass, field
from typing import FrozenSet, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.loop import LoopCollection
    from .stages.clearance_grid import ClearanceGrid

@dataclass(frozen=True)
class BoardState:
    '''Immutable snapshot of board at any pipeline stage.'''
    board: Optional['Board'] = None
    netlist: Optional['Netlist'] = None
    loops: Optional['LoopCollection'] = None
    grid: Optional['ClearanceGrid'] = None
    placements: FrozenSet = frozenset()
    routes: FrozenSet = frozenset()
    violations: FrozenSet = frozenset()
    net_order: Tuple[str, ...] = field(default_factory=tuple)
