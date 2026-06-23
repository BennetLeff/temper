from __future__ import annotations

import time
from typing import List, Optional, TYPE_CHECKING

from .state import BoardState
from .stages.base import Stage
from .stages.clearance_grid import ClearanceGrid
from .stages.astar import DeterministicAStar

if TYPE_CHECKING:
    from temper_drc.core.fence import DRCFence
    from tests.deterministic.fixtures import TestBoard, RouteResult


def _board_state_to_drc_input(
    state: BoardState,
) -> tuple:
    """Convert BoardState to temper_drc Placement and ConstraintSet.

    Bridges the deterministic pipeline's BoardState representation to the
    DRC check input format. Extracts component positions, net assignments,
    and board dimensions from the immutable state.

    Initial implementation handles component overlap and clearance checks;
    expanded as additional checks require more data fields.
    """
    from temper_drc.input.placement import Placement as DRCPlacement, ComponentPlacement as DRCCompPlacement
    from temper_drc.input.constraints import ConstraintSet, ClearanceRule

    board_width = state.board.width if state.board else 100.0
    board_height = state.board.height if state.board else 100.0

    # Build component ref -> Component lookup from netlist
    comp_map = {}
    netlist = state.netlist
    if netlist and hasattr(netlist, 'components'):
        for comp in netlist.components:
            comp_map[comp.ref] = comp

    # Extract placed positions from placements frozenset
    components = {}
    for item in state.placements:
        if isinstance(item, tuple) and len(item) == 2:
            ref, placement = item
            comp = comp_map.get(ref)
            if comp:
                width, height = comp.bounds
                footprint = comp.footprint
                net_class = comp.net_class
            else:
                width, height = 1.0, 1.0
                footprint = ""
                net_class = "Signal"

            pos = getattr(placement, 'position', (0.0, 0.0))
            if not isinstance(pos, (tuple, list)):
                pos = (0.0, 0.0)
            rot = getattr(placement, 'rotation', 0)
            if not isinstance(rot, (int, float)):
                rot = 0

            side = getattr(comp, 'initial_side', 0) if comp else 0
            layer = "F.Cu" if side == 0 else "B.Cu"

            components[ref] = DRCCompPlacement(
                ref=ref,
                footprint=footprint,
                x=float(pos[0]),
                y=float(pos[1]),
                rotation=float(rot),
                layer=layer,
                width=width,
                height=height,
                net_class=net_class,
            )

    # Build nets from netlist
    nets = {}
    if netlist and hasattr(netlist, 'nets'):
        for net in netlist.nets:
            if hasattr(net, 'pins'):
                nets[net.name] = [pin[0] for pin in net.pins]

    # Build zones from board
    zones = {}
    if state.board:
        for zone in state.board.zones:
            zones[zone.name] = zone.bounds

    placement = DRCPlacement(
        components=components,
        nets=nets,
        zones=zones,
        board_width=board_width,
        board_height=board_height,
    )

    constraints = ConstraintSet(
        clearances=[ClearanceRule(from_class="*", to_class="*", min_mm=0.3)],
        board_width=board_width,
        board_height=board_height,
    )

    return placement, constraints


class DeterministicPipeline:
    def __init__(self, stages: List[Stage] = None, fence: Optional[DRCFence] = None):
        self.stages = stages or []
        self.fence = fence

    def run(self, initial_state: BoardState = None) -> BoardState:
        from temper_drc.core.fence import _issue_fingerprint

        state = initial_state or BoardState()
        previous_violations: frozenset[str] | None = None
        for stage in self.stages:
            t0 = time.time()
            state = stage.run(state)
            stage_time = (time.time() - t0) * 1000

            if self.fence and stage.invariants:
                invariants = stage.invariants
                modified_regions = stage.last_modified_regions
                placement, constraints = _board_state_to_drc_input(state)

                result = self.fence.check(
                    stage_name=stage.name,
                    invariants=invariants,
                    placement=placement,
                    constraints=constraints,
                    modified_regions=modified_regions,
                    previous_violations=previous_violations,
                    stage_wall_time_ms=stage_time,
                )
                previous_violations = frozenset(
                    _issue_fingerprint(v.issue) for v in result.violations
                )
        return state

    def route_single_net(self, board: 'TestBoard', net_name: str) -> 'RouteResult':
        '''Route a single net (MVP-0 scope).'''
        from tests.deterministic.fixtures import RouteResult, Route, RouteSegment
        
        # Stage 5: Build clearance grid
        grid = ClearanceGrid(
            width_mm=board.width_mm,
            height_mm=board.height_mm,
            cell_size_mm=0.5,
        )
        
        # Block all pads
        for ref, comp in board.components.items():
            cx, cy = comp['position']
            for pad in comp['pads']:
                px = cx + pad['offset'][0]
                py = cy + pad['offset'][1]
                grid.block_circle(
                    center=(px, py),
                    radius_mm=pad['radius'],
                    clearance_mm=0.3,  # Default clearance
                )
        
        # Unblock the pins we're routing to
        net_pins = board.nets[net_name]
        pin_positions = []
        for ref, pad_id in net_pins:
            comp = board.components[ref]
            cx, cy = comp['position']
            pad = next(p for p in comp['pads'] if p['id'] == pad_id)
            px = cx + pad['offset'][0]
            py = cy + pad['offset'][1]
            pin_positions.append((px, py))
            # Unblock this pin (we need to route to it)
            grid.unblock_circle(center=(px, py), radius_mm=pad['radius'])
        
        # Stage 7: Route with A*
        pathfinder = DeterministicAStar(grid)
        path = pathfinder.find_path(start=pin_positions[0], end=pin_positions[1])
        
        if path is None:
            return RouteResult(success=False, route=None, error='No path found')
        
        # Convert path to route segments
        segments = []
        for i in range(len(path) - 1):
            segments.append(RouteSegment(
                start=path[i],
                end=path[i + 1],
                layer=0,
                width=0.25,  # Default trace width
            ))
        
        return RouteResult(
            success=True,
            route=Route(net_name=net_name, segments=tuple(segments)),
            error=None,
        )