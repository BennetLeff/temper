from typing import List, TYPE_CHECKING
from .state import BoardState
from .stages.base import Stage
from .stages.clearance_grid import ClearanceGrid
from .stages.astar import DeterministicAStar

if TYPE_CHECKING:
    from tests.deterministic.fixtures import TestBoard, RouteResult

class DeterministicPipeline:
    def __init__(self, stages: List[Stage] = None):
        self.stages = stages or []
        
    def run(self, initial_state: BoardState = None) -> BoardState:
        state = initial_state or BoardState()
        for stage in self.stages:
            state = stage.run(state)
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