import math
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Tuple, Optional
from kiutils.board import Board
from kiutils.items.common import Position
from kiutils.items.brditems import Via, Segment
from temper_placer.core.netlist import Netlist

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import MazeRouter

logger = logging.getLogger(__name__)


@dataclass
class EscapePreRoute:
    """Represents a pre-routed escape trace from a pin to a fanout via.

    These are treated as fixed routes that the main router must respect.
    The router will:
    1. Mark these traces as occupied in the grid
    2. Not rip them up during RRR iterations
    3. Use the via position as the effective routing endpoint
    """

    net_name: str
    pin_position: Tuple[float, float]
    via_position: Tuple[float, float]
    layer: int = 0
    trace_width: float = 0.2
    via_size: float = 0.6
    via_drill: float = 0.3
    component_ref: str = ""
    pin_name: str = ""

    def to_grid_cells(self, router: "MazeRouter") -> List[Tuple[int, int, int]]:
        """Convert this pre-route to grid cells for the router's occupancy grid.

        Args:
            router: The MazeRouter instance to use for coordinate conversion

        Returns:
            List of (x, y, layer) tuples representing the trace cells
        """
        cells = []
        gx, gy = router._world_to_grid(*self.pin_position)
        vgx, vgy = router._world_to_grid(*self.via_position)

        step_x = 1 if vgx > gx else -1 if vgx < gx else 0
        step_y = 1 if vgy > gy else -1 if vgy < gy else 0

        cx, cy = gx, gy
        while (cx, cy) != (vgx, vgy):
            cells.append((cx, cy, self.layer))
            if cx != vgx:
                cx += step_x
            if cy != vgy:
                cy += step_y
        cells.append((vgx, vgy, self.layer))

        return cells


@dataclass
class FanoutConfig:
    """Configuration for Fanout Generation."""

    pitch: float = 2.54  # Grid pitch in mm
    via_drill: float = 0.3
    via_size: float = 0.6
    trace_width: float = 0.2

    # "Grid" strategy: offset by half pitch
    # "Void" strategy: search for nearest empty space
    strategy: str = "grid"

    # Offset factors for Grid strategy (relative to pitch)
    # (0.5, 0.5) puts via in the center of 4 pins
    offset_x: float = 0.5
    offset_y: float = 0.5


class FanoutGenerator:
    """
    Generates 'dog-bone' fanouts for pins to allow routing from clear areas.
    """

    def __init__(self, board: Board, netlist: Netlist, config: FanoutConfig = None):
        self.board = board
        self.netlist = netlist
        self.config = config or FanoutConfig()
        self.last_escape_routes: List[EscapePreRoute] = []

    def generate_fanouts(
        self,
        target_nets: Optional[List[str]] = None,
        return_escape_routes: bool = False,
    ) -> Dict[str, List[Tuple[float, float]]]:
        """
        Generate fanouts for specified nets (or all if None).
        Returns a map of net_name -> list of NEW start/end positions (the vias).
        Updates self.board with new Vias and Tracks.

        Args:
            target_nets: List of net names to generate fanouts for, or None for all
            return_escape_routes: If True, also returns detailed EscapePreRoute info

        Returns:
            Dict mapping net_name to list of via positions
            If return_escape_routes=True, also populates self.last_escape_routes
        """
        new_positions = {}
        self.last_escape_routes: List[EscapePreRoute] = []

        for net in self.netlist.nets:
            if not net.name:
                continue
            if target_nets and net.name not in target_nets:
                continue

            fanout_points = []

            if net.pins is None:
                continue

            # Find all pins for this net
            for comp_ref, pin_name in net.pins:
                # Find the component
                comp = next((c for c in self.netlist.components if c.ref == comp_ref), None)
                if not comp:
                    continue

                # Find the pin relative position
                pin_def = next(
                    (p for p in comp.pins if p.name == pin_name or p.number == pin_name), None
                )
                if not pin_def:
                    continue

                # Calculate absolute position
                if comp.initial_position is None:
                    continue
                cx, cy = comp.initial_position
                px = cx + pin_def.position[0]
                py = cy + pin_def.position[1]

                # Calculate Fanout Position (Escape Point)
                # Strategy: Grid (Offset)
                fx = px + (self.config.pitch * self.config.offset_x)
                fy = py + (self.config.pitch * self.config.offset_y)

                # Create Via
                via = Via(
                    position=Position(X=fx, Y=fy),
                    size=self.config.via_size,
                    drill=self.config.via_drill,
                    layers=["F.Cu", "B.Cu"],  # Through via
                    net=None,
                )

                # Find Net ID from Board (handle both kiutils and temper_placer Board)
                ki_net = None
                if hasattr(self.board, "nets") and self.board.nets is not None:
                    ki_net = next((n for n in self.board.nets if n.name == net.name), None)
                if ki_net:
                    via.net = ki_net

                # Only add to board if it supports traceItems (kiutils Board)
                if hasattr(self.board, "traceItems"):
                    self.board.traceItems.append(via)

                # Create Trace (Pin -> Via)
                track = Segment(
                    start=Position(X=px, Y=py),
                    end=Position(X=fx, Y=fy),
                    width=self.config.trace_width,
                    layer="F.Cu",  # Assume pins are accessible on Top (SMD or TH)
                    net=ki_net,
                )

                # Only add to board if it supports traceItems (kiutils Board)
                if hasattr(self.board, "traceItems"):
                    self.board.traceItems.append(track)

                # Record the Via position as the new "Routing Point"
                fanout_points.append((fx, fy))

                # Track escape route info if requested
                if return_escape_routes:
                    escape_route = EscapePreRoute(
                        net_name=net.name if net.name else "",
                        pin_position=(px, py),
                        via_position=(fx, fy),
                        layer=0,
                        trace_width=self.config.trace_width,
                        via_size=self.config.via_size,
                        via_drill=self.config.via_drill,
                        component_ref=comp_ref,
                        pin_name=pin_name,
                    )
                    self.last_escape_routes.append(escape_route)

            if fanout_points:
                new_positions[net.name] = fanout_points

        return new_positions
