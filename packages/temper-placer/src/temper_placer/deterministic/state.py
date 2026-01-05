from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.loop import LoopCollection
    from temper_placer.core.netlist import Netlist
    from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation

    from .stages.clearance_grid import ClearanceGrid
    from .stages.connectivity_validation import ConnectivityViolation

@dataclass(frozen=True)
class BoardState:
    '''Immutable snapshot of board at any pipeline stage.'''
    board: Optional['Board'] = None
    netlist: Optional['Netlist'] = None
    loops: Optional['LoopCollection'] = None
    grid: Optional['ClearanceGrid'] = None
    drc_oracle: Optional['DRCOracle'] = None
    drc_violations: tuple['Violation', ...] | None = None
    connectivity_violations: tuple['ConnectivityViolation', ...] | None = None
    placements: frozenset = frozenset()
    routes: frozenset = frozenset()
    vias: frozenset = frozenset()
    violations: frozenset = frozenset()
    net_order: tuple[str, ...] = field(default_factory=tuple)
    zones: frozenset = frozenset()  # Set of Zone objects
    component_zone_map: frozenset = frozenset()  # Set of (component_ref, zone_name) tuples
    zone_slots: frozenset = frozenset()  # Set of (zone_name, tuple_of_slots) - each zone maps to tuple of (x,y) positions
    layer_assignments: frozenset = frozenset()  # Set of LayerAssignment objects (net_name, layer)




