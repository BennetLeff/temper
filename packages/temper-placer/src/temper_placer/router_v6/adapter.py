"""Adapter for Router V6 pipeline integration with the closure test.

Provides ``route_pcb(parsed, placements, seed)`` which applies placement
data to a KiCad PCB file, invokes RouterV6Pipeline, and returns results.

Also provides ``V6RouterAdapter`` — a MazeRouter-compatible in-memory adapter
for consumers that currently depend on ``routing/maze_router``.

Public API re-exports from internal modules:
  _adapter_types   → DrcViolation, CongestionRegion, RoutingResult,
                      ParsedPcbLike
  _adapter_core    → V6RouterAdapter, _extract_conflicts
  _adapter_convert → route_pcb, _apply_placements_to_pcb,
                      _build_routing_result, _emit_zone_pours,
                      _stitch_isolated_pads, _write_routes_to_content,
                      _zone_layers_for_net, _zone_params_for_net
"""

from temper_placer.router_v6._adapter_convert import (
    _apply_placements_to_pcb,
    _build_routing_result,
    _emit_zone_pours,
    _stitch_isolated_pads,
    _write_routes_to_content,
    _zone_layers_for_net,
    _zone_params_for_net,
    route_pcb,
)
from temper_placer.router_v6._adapter_core import (
    V6RouterAdapter,
    _extract_conflicts,
)
from temper_placer.router_v6._adapter_types import (
    CongestionRegion,
    DrcViolation,
    ParsedPcbLike,
    RoutingResult,
    _AdapterRoutePath,
)

MazeRouter = V6RouterAdapter

__all__ = [
    "CongestionRegion",
    "DrcViolation",
    "MazeRouter",
    "ParsedPcbLike",
    "RoutingResult",
    "V6RouterAdapter",
    "_AdapterRoutePath",
    "_apply_placements_to_pcb",
    "_build_routing_result",
    "_emit_zone_pours",
    "_extract_conflicts",
    "_stitch_isolated_pads",
    "_write_routes_to_content",
    "_zone_layers_for_net",
    "_zone_params_for_net",
    "route_pcb",
]
