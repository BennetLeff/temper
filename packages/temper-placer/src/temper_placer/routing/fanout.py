import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from kiutils.board import Board
from kiutils.items.common import Position
from kiutils.items.brditems import Via, Segment
from temper_placer.core.netlist import Netlist
from temper_placer.routing.escape_analyzer import (
    RingClassifier,
    PinInfo,
    EscapeDirection,
    EscapeAssignment,
)

logger = logging.getLogger(__name__)


@dataclass
class FanoutConfig:
    """Configuration for Fanout Generation."""

    pitch: float = 2.54
    via_drill: float = 0.3
    via_size: float = 0.6
    trace_width: float = 0.2
    strategy: str = "staggered"
    via_clearance: float = 0.2

    offset_multipliers: Tuple[float, float] = (0.5, 0.5)

    ring_offset_multipliers: Optional[Dict[int, Tuple[float, float]]] = None

    def __post_init__(self):
        if self.ring_offset_multipliers is None:
            self.ring_offset_multipliers = {
                0: (0.5, 0.5),
                1: (0.25, 0.75),
                2: (0.75, 0.25),
                3: (0.0, 0.5),
                4: (0.5, 0.0),
            }
        if not isinstance(self.ring_offset_multipliers, dict):
            self.ring_offset_multipliers = {}


class FanoutGenerator:
    """
    Generates 'dog-bone' fanouts for pins to allow routing from clear areas.
    """

    def __init__(self, board: Board, netlist: Netlist, config: FanoutConfig = None):
        self.board = board
        self.netlist = netlist
        self.config = config or FanoutConfig()
        self.escape_assignments: Dict[str, EscapeAssignment] = {}
        self._analyzed = False

    def _analyze_components(self):
        """Analyze all components to determine escape directions."""
        if self._analyzed:
            return

        for comp in self.netlist.components:
            if not comp.pins:
                continue

            pins_info = []
            cx, cy = comp.initial_position

            # Collect all pins for this component
            valid_pins = []
            for pin_def in comp.pins:
                # Calculate absolute position
                # Note: This assumes no rotation. If rotated, we need to transform.
                # Ideally we should use a utility for absolute position.
                # For now, sticking to the existing logic assumption.
                px = cx + pin_def.position[0]
                py = cy + pin_def.position[1]

                # Use a unique ID for the pin: "Ref-PinName"
                pin_id = f"{comp.ref}-{pin_def.name}"
                pins_info.append(PinInfo(id=pin_id, x=px, y=py))
                valid_pins.append(pin_id)

            if not pins_info:
                continue

            # Run classifier
            classifier = RingClassifier(pins_info)
            results = classifier.analyze()

            # Store results
            for pin_id, assignment in results.items():
                self.escape_assignments[pin_id] = assignment

        self._analyzed = True

    def _get_direction_offset(
        self, direction: EscapeDirection, ring_index: int = 0
    ) -> Tuple[float, float]:
        """Convert direction to (dx, dy) offset multipliers with ring-based staggering.

        Uses IPC-7095 spacing guidelines for via grid pattern. Inner rings use
        different offset multipliers to avoid via-to-via clearance violations.
        """
        base_offsets = {
            EscapeDirection.NORTH: (0, -1),
            EscapeDirection.SOUTH: (0, 1),
            EscapeDirection.EAST: (1, 0),
            EscapeDirection.WEST: (-1, 0),
            EscapeDirection.NORTH_EAST: (1, -1),
            EscapeDirection.NORTH_WEST: (-1, -1),
            EscapeDirection.SOUTH_EAST: (1, 1),
            EscapeDirection.SOUTH_WEST: (-1, 1),
        }

        base_dx, base_dy = base_offsets.get(direction, (1, 1))

        ring_mults = self.config.ring_offset_multipliers.get(
            ring_index, self.config.ring_offset_multipliers.get(0, (0.5, 0.5))
        )

        dx = base_dx * ring_mults[0] * self.config.pitch
        dy = base_dy * ring_mults[1] * self.config.pitch

        return (dx, dy)

    def generate_fanouts(
        self, target_nets: List[str] = None
    ) -> Dict[str, List[Tuple[float, float]]]:
        """
        Generate fanouts for specified nets (or all if None).
        Returns a map of net_name -> list of NEW start/end positions (the vias).
        Updates self.board with new Vias and Tracks.
        """
        self._analyze_components()
        new_positions = {}

        for net in self.netlist.nets:
            if not net.name:
                continue
            if target_nets and net.name not in target_nets:
                continue

            fanout_points = []

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
                cx, cy = comp.initial_position
                px = cx + pin_def.position[0]
                py = cy + pin_def.position[1]

                pin_id = f"{comp_ref}-{pin_def.name}"  # Note: pin_def.name vs pin_name from netlist
                # Netlist pin_name usually matches pin_def.name or number.
                # Let's try both or ensure consistency.

                assignment = self.escape_assignments.get(pin_id)
                if not assignment:
                    # Try with number if name failed
                    pin_id_num = f"{comp_ref}-{pin_def.number}"
                    assignment = self.escape_assignments.get(pin_id_num)

                # Determine offset based on assignment or default
                if assignment:
                    dx, dy = self._get_direction_offset(assignment.direction, assignment.ring_index)
                else:
                    dx, dy = 0.5 * self.config.pitch, 0.5 * self.config.pitch

                # Calculate Fanout Position (Escape Point)
                fx = px + dx
                fy = py + dy

                # Create Via
                via = Via(
                    position=Position(X=fx, Y=fy),
                    size=self.config.via_size,
                    drill=self.config.via_drill,
                    layers=["F.Cu", "B.Cu"],
                    net=None,
                )

                # Find Net ID from Board
                ki_net = next((n for n in self.board.nets if n.name == net.name), None)
                if ki_net:
                    via.net = ki_net

                self.board.traceItems.append(via)

                # Create Trace (Pin -> Via)
                track = Segment(
                    start=Position(X=px, Y=py),
                    end=Position(X=fx, Y=fy),
                    width=self.config.trace_width,
                    layer="F.Cu",
                    net=ki_net,
                )
                self.board.traceItems.append(track)

                # Record the Via position as the new "Routing Point"
                fanout_points.append((fx, fy))

            if fanout_points:
                new_positions[net.name] = fanout_points

        return new_positions
