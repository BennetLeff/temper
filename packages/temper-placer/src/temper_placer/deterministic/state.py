from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, FrozenSet

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.loop import LoopCollection
    from temper_placer.core.netlist import Netlist
    from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation

    from .stages.clearance_grid import ClearanceGrid
    from .stages.connectivity_validation import ConnectivityViolation
    from .stages.placement_validation import PlacementViolation


@dataclass(frozen=True)
class BoardState:
    """Immutable snapshot of board at any pipeline stage."""

    board: Optional["Board"] = None
    netlist: Optional["Netlist"] = None
    loops: Optional["LoopCollection"] = None
    grid: Optional["ClearanceGrid"] = None
    drc_oracle: Optional["DRCOracle"] = None
    drc_violations: tuple["Violation", ...] | None = None
    connectivity_violations: tuple["ConnectivityViolation", ...] | None = None
    placement_violations: tuple["PlacementViolation", ...] | None = None
    placements: frozenset = frozenset()
    routes: frozenset = frozenset()
    vias: frozenset = frozenset()
    violations: frozenset = frozenset()
    net_order: tuple[str, ...] = field(default_factory=tuple)
    zones: frozenset = frozenset()  # Set of Zone objects
    component_zone_map: frozenset = frozenset()  # Set of (component_ref, zone_name) tuples
    zone_slots: frozenset = (
        frozenset()
    )  # Set of (zone_name, tuple_of_slots) - each zone maps to tuple of (x,y) positions
    layer_assignments: frozenset = frozenset()  # Set of LayerAssignment objects (net_name, layer)
    # EXP-5: Route locking - nets that have been successfully routed and should be preserved
    locked_routes: FrozenSet[str] = field(default_factory=frozenset)

    def with_locked_route(self, net_name: str) -> "BoardState":
        """Return new state with the given net marked as locked.

        Locked routes are preserved across feedback iterations and not re-routed.
        This is used by EXP-5 to prevent zone expansion from breaking working routes.

        Args:
            net_name: Name of the net to lock

        Returns:
            New BoardState with the net added to locked_routes
        """
        from dataclasses import replace

        new_locked = frozenset(self.locked_routes | {net_name})
        return replace(self, locked_routes=new_locked)

    def with_locked_routes(self, net_names: set) -> "BoardState":
        """Return new state with multiple nets marked as locked.

        Args:
            net_names: Set of net names to lock

        Returns:
            New BoardState with the nets added to locked_routes
        """
        from dataclasses import replace

        new_locked = frozenset(self.locked_routes | net_names)
        return replace(self, locked_routes=new_locked)

    def is_route_locked(self, net_name: str) -> bool:
        """Check if a route is locked and should not be re-routed.

        Args:
            net_name: Name of the net to check

        Returns:
            True if the route is locked
        """
        return net_name in self.locked_routes
