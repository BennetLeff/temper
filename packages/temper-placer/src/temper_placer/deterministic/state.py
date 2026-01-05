from dataclasses import dataclass, field
from typing import FrozenSet, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.loop import LoopCollection
    from .stages.clearance_grid import ClearanceGrid
    from temper_placer.routing.constraints.drc_oracle import DRCOracle

@dataclass(frozen=True)
class BoardState:
    '''Immutable snapshot of board at any pipeline stage.'''
    board: Optional['Board'] = None
    netlist: Optional['Netlist'] = None
    loops: Optional['LoopCollection'] = None
    grid: Optional['ClearanceGrid'] = None
    drc_oracle: Optional['DRCOracle'] = None
    placements: FrozenSet = frozenset()
    routes: FrozenSet = frozenset()
    vias: FrozenSet = frozenset()
    violations: FrozenSet = frozenset()
    net_order: Tuple[str, ...] = field(default_factory=tuple)
    zones: FrozenSet = frozenset()  # Set of Zone objects
    component_zone_map: FrozenSet = frozenset()  # Set of (component_ref, zone_name) tuples
    zone_slots: FrozenSet = frozenset()  # Set of (zone_name, tuple_of_slots) - each zone maps to tuple of (x,y) positions
    layer_assignments: FrozenSet = frozenset()  # Set of LayerAssignment objects (net_name, layer)




