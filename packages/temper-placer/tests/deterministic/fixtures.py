from dataclasses import dataclass, field
from typing import List, Tuple, Optional

@dataclass(frozen=True)
class RouteSegment:
    start: Tuple[float, float]
    end: Tuple[float, float]
    layer: int
    width: float

@dataclass(frozen=True)
class Route:
    net_name: str
    segments: Tuple[RouteSegment, ...]

@dataclass(frozen=True)
class RouteResult:
    success: bool
    route: Optional[Route]
    error: Optional[str]

@dataclass
class RoutingTestBoard:
    width_mm: float
    height_mm: float
    components: dict = field(default_factory=dict)
    nets: dict = field(default_factory=dict)
    
    def add_component(self, ref: str, footprint: str, position: Tuple[float, float]):
        self.components[ref] = {
            'footprint': footprint,
            'position': position,
            'pads': self._get_pads_for_footprint(footprint),
        }
    
    def add_net(self, name: str, pins: List[Tuple[str, str]]):
        self.nets[name] = pins
    
    def _get_pads_for_footprint(self, footprint: str) -> List[dict]:
        # Simplified: 0805 has two pads 1.5mm apart
        if footprint == '0805':
            return [
                {'id': '1', 'offset': (-0.75, 0), 'radius': 0.5},
                {'id': '2', 'offset': (0.75, 0), 'radius': 0.5},
            ]
        return []
