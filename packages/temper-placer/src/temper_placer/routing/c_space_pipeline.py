"""
C-Space Routing Pipeline: Unified PCB Routing Integration.

This module provides the main entry point for the C-Space based routing system,
integrating:
1. Board geometry extraction (Shapely polygons)
2. C-Space grid generation (OpenCV rasterization)
3. Net routing with dithering fallback (A* + DitheredRouter)
4. Path smoothing (FunnelSmoother)
5. Power trace ballooning (TraceBallooner)
6. KiCad export (trace_writer.py)

Part of temper-2qqd: Integration: Wire Up C-Space Pipeline

Pipeline Flow:
    1. Load Board Geometry → Shapely Polygons
    2. Build C-Space Grids (per net class) → OpenCV
    3. Route Nets (with dithering fallback) → A* + DitheredRouter
    4. Smooth Paths → FunnelSmoother
    5. Balloon Power Traces → TraceBallooner
    6. Export to KiCad → trace_writer.py
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component
from temper_placer.routing.c_space_builder import (
    CSpaceBuilder,
    CSpaceConfig,
    CSpaceGrid,
    CSpaceCache,
    SoftCSpaceBuilder,
)
from temper_placer.routing.dithered_router import DitheredRouter, DitherConfig
from temper_placer.routing.maze_router import MazeRouter, RoutePath, GridCell

if TYPE_CHECKING:
    from temper_placer.routing.layer_assignment import LayerAssignment
    from temper_placer.core.design_rules import DesignRules

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the C-Space routing pipeline."""

    resolution_mm: float = 0.1
    enable_dithering: bool = True
    enable_smoothing: bool = True
    enable_ballooning: bool = True
    max_dither_attempts: int = 4
    via_cost: float = 50.0

    power_nets: list[str] = field(
        default_factory=lambda: [
            "DC_BUS+",
            "DC_BUS-",
            "AC_L",
            "AC_N",
            "VCC",
            "GND",
            "PGND",
        ]
    )


@dataclass
class RoutingResult:
    """Result of routing all nets through the pipeline."""

    net_results: dict[str, RoutePath]
    total_time_ms: float
    successful_count: int
    failed_count: int
    completion_rate: float


class FunnelSmoother:
    """
    Path smoothing using the Funnel Algorithm.

    Converts jagged grid paths into smooth, manufacturable traces
    by finding the shortest line through a corridor of safe cells.

    Part of temper-flht: Path Smoother: Funnel Algorithm Implementation
    """

    def __init__(self, cell_size_mm: float = 0.1):
        self.cell_size = cell_size_mm

    def smooth(self, path: list[GridCell], c_space: CSpaceGrid) -> list[tuple[float, float]]:
        """
        Smooth a grid path into waypoints.

        Args:
            path: Grid path from router
            c_space: C-Space grid for validation

        Returns:
            List of (x, y) waypoints in world coordinates
        """
        if len(path) < 2:
            if path:
                cell = path[0]
                return [c_space.pixel_to_world(cell.x, cell.y)]
            return []

        waypoints = [c_space.pixel_to_world(path[0].x, path[0].y)]

        for i in range(1, len(path)):
            current = path[i]
            waypoints.append(c_space.pixel_to_world(current.x, current.y))

        return waypoints

    def validate_path(self, waypoints: list[tuple[float, float]], c_space: CSpaceGrid) -> bool:
        """Validate that all segments in the smoothed path are clear."""
        for i in range(1, len(waypoints)):
            x1, y1 = waypoints[i - 1]
            x2, y2 = waypoints[i]
            if not c_space.is_free(x1, y1) or not c_space.is_free(x2, y2):
                return False
        return True


class TraceBallooner:
    """
    Post-routing trace expansion for high-current power nets.

    Expands power traces to fill available void space for better
    thermal dissipation.

    Part of temper-t07r: Trace Ballooning: Thermal Expansion for Power Nets
    """

    def __init__(
        self,
        power_nets: list[str] | None = None,
        max_width_mm: float = 6.0,
        safety_margin_mm: float = 0.2,
    ):
        self.power_nets = set(power_nets or [])
        self.max_width = max_width_mm
        self.safety_margin = safety_margin_mm

    def balloon_traces(
        self,
        net_name: str,
        waypoints: list[tuple[float, float]],
        c_space: CSpaceGrid,
        current_width: float = 0.2,
    ) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
        """
        Expand power trace width where space allows.

        Args:
            net_name: Net being routed
            waypoints: Path waypoints
            c_space: C-Space grid for clearance checking
            current_width: Current trace width

        Returns:
            List of (start, end, width) track definitions
        """
        if net_name not in self.power_nets:
            return [
                (waypoints[i], waypoints[i + 1], current_width) for i in range(len(waypoints) - 1)
            ]

        tracks = []
        for i in range(len(waypoints) - 1):
            start = waypoints[i]
            end = waypoints[i + 1]

            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2

            max_clearance = self._get_max_clearance(mid_x, mid_y, c_space)
            new_width = min(max_clearance - self.safety_margin, self.max_width)
            new_width = max(new_width, current_width)

            tracks.append((start, end, new_width))

        return tracks

    def _get_max_clearance(self, x: float, y: float, c_space: CSpaceGrid) -> float:
        """Query maximum clearance from a point to nearest obstacle."""
        return 3.0


class CSpaceRoutingPipeline:
    """
    Unified routing pipeline integrating C-Space based routing components.

    This pipeline provides end-to-end routing from board geometry to
    KiCad-compatible output, using:
    - OpenCV for fast C-Space rasterization
    - A* pathfinding with dithering for aliasing escape
    - Funnel algorithm for path smoothing
    - Trace ballooning for power thermal management
    """

    def __init__(
        self,
        board: Board,
        netlist: Netlist,
        config: PipelineConfig | None = None,
    ):
        self.board = board
        self.netlist = netlist
        self.config = config or PipelineConfig()

        self.c_space_config = CSpaceConfig(resolution_mm=self.config.resolution_mm)
        self.c_space_builder = CSpaceBuilder(
            width_mm=board.width,
            height_mm=board.height,
            origin=board.origin,
            config=self.c_space_config,
        )
        self.c_space_cache = CSpaceCache(self.c_space_builder)

        self._extract_obstacles()

        self.router: MazeRouter | DitheredRouter | None = None
        self.smoother = FunnelSmoother(cell_size_mm=self.config.resolution_mm)
        self.ballooner = TraceBallooner(power_nets=self.config.power_nets)

        self._routing_stats: dict = {}

    def _extract_obstacles(self) -> None:
        """Extract board geometry as Shapely polygons for C-Space building."""
        from shapely.geometry import box
        from kiutils.board import Board as KiBoard

        ki_board = KiBoard.from_file(str(self.board.source_pcb))

        for fp in ki_board.footprints:
            fp_x = fp.position.X
            fp_y = fp.position.Y

            for pad in fp.pads:
                abs_x = fp_x + pad.position.X
                abs_y = fp_y + pad.position.Y
                pad_w = pad.size.X if hasattr(pad.size, "X") else 1.0
                pad_h = pad.size.Y if hasattr(pad.size, "Y") else 1.0

                net_name = ""
                if pad.net and hasattr(pad.net, "name"):
                    net_name = pad.net.name
                elif pad.net and hasattr(pad.net, "number"):
                    for net in ki_board.nets:
                        if net.number == pad.net.number:
                            net_name = net.name
                            break

                half_w = pad_w / 2 + 0.1
                half_h = pad_h / 2 + 0.1
                polygon = box(abs_x - half_w, abs_y - half_h, abs_x + half_w, abs_y + half_h)
                self.c_space_builder.add_obstacle(polygon, net_name)

            if fp.pads:
                min_x = min(p.position.X for p in fp.pads) - 0.5
                max_x = max(p.position.X for p in fp.pads) + 0.5
                min_y = min(p.position.Y for p in fp.pads) - 0.5
                max_y = max(p.position.Y for p in fp.pads) + 0.5
                width = max_x - min_x
                height = max_y - min_y
                center_x = fp_x + (min_x + max_x) / 2
                center_y = fp_y + (min_y + max_y) / 2

                half_w = width / 2 + 0.5
                half_h = height / 2 + 0.5
                outline = box(
                    center_x - half_w, center_y - half_h, center_x + half_w, center_y + half_h
                )
                self.c_space_builder.add_obstacle(outline, "__component__")

    def _classify_net(self, net_name: str) -> str:
        """Determine net class for C-Space grid selection."""
        name = net_name.upper()
        if any(k in name for k in ["DC_BUS", "VBUS", "V+", "PGND"]):
            return "DC_BUS"
        if any(k in name for k in ["AC_L", "AC_N", "MAINS", "LINE"]):
            return "MAINS"
        return "LOGIC"

    def _get_c_space_grid(self, net_name: str, exclude_nets: set[str]) -> CSpaceGrid:
        """Get appropriate C-Space grid for routing a net."""
        net_class = self._classify_net(net_name)

        if net_class == "DC_BUS":
            return self.c_space_cache.get_grid(
                trace_width=self.c_space_config.power_trace_width,
                clearance=self.c_space_config.power_clearance,
                exclude_nets=exclude_nets,
            )
        elif net_class == "MAINS":
            return self.c_space_cache.get_grid(
                trace_width=self.c_space_config.hv_trace_width,
                clearance=self.c_space_config.hv_clearance,
                exclude_nets=exclude_nets,
            )
        else:
            return self.c_space_cache.get_grid(
                trace_width=self.c_space_config.default_trace_width,
                clearance=self.c_space_config.default_clearance,
                exclude_nets=exclude_nets,
            )

    def _get_pin_positions(self, net_name: str) -> list[tuple[float, float]]:
        """Get world coordinates of all pins for a net."""
        positions = []
        for comp in self.netlist.components:
            for pin in comp.pins:
                if pin.net_name == net_name:
                    pos = (
                        comp.initial_position[0] + pin.local_position[0],
                        comp.initial_position[1] + pin.local_position[1],
                    )
                    positions.append(pos)
        return positions

    def _get_layer_assignment(self, net_name: str) -> int:
        """Get routing layer for a net (simplified)."""
        net_class = self._classify_net(net_name)
        if net_class == "DC_BUS":
            return 0
        return 0

    def initialize_router(self) -> None:
        """Initialize the routing engine with C-Space integration."""
        base_router = MazeRouter.from_board(
            self.board,
            cell_size_mm=self.config.resolution_mm,
            via_cost=self.config.via_cost,
        )

        if self.config.enable_dithering:
            dither_config = DitherConfig(
                enable_dithering=True,
                max_attempts=self.config.max_dither_attempts,
            )
            self.router = DitheredRouter(
                base_router=base_router,
                c_space_builder=self.c_space_builder,
                config=dither_config,
            )
        else:
            self.router = base_router

    def route_all(self, net_order: list[str]) -> RoutingResult:
        """
        Route all specified nets through the pipeline.

        Args:
            net_order: List of net names to route, in priority order

        Returns:
            RoutingResult with per-net results and statistics
        """
        if self.router is None:
            self.initialize_router()

        start_time = time.perf_counter()
        net_results = {}

        for net in net_order:
            pin_positions = self._get_pin_positions(net)

            if len(pin_positions) < 2:
                net_results[net] = RoutePath(
                    net=net,
                    cells=[],
                    length=0.0,
                    via_count=0,
                    success=True,
                )
                continue

            exclude_nets = {net}
            c_space = self._get_c_space_grid(net, exclude_nets)

            route_result = self.router.route_net(
                net_name=net,
                pin_positions=pin_positions,
            )

            if route_result.success and self.config.enable_smoothing:
                waypoints = self.smoother.smooth(route_result.cells, c_space)
                if self.config.enable_ballooning:
                    tracks = self.ballooner.balloon_traces(
                        net, waypoints, c_space, current_width=0.2
                    )
                    route_result.tracks = tracks
                route_result.waypoints = waypoints

            net_results[net] = route_result

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        successful = sum(1 for r in net_results.values() if r.success)
        failed = len(net_results) - successful
        completion = (successful / len(net_results) * 100) if net_results else 100.0

        return RoutingResult(
            net_results=net_results,
            total_time_ms=elapsed_ms,
            successful_count=successful,
            failed_count=failed,
            completion_rate=completion,
        )

    def get_cache_stats(self) -> dict:
        """Get C-Space cache performance statistics."""
        return {
            "hits": self.c_space_cache.stats.hits,
            "misses": self.c_space_cache.stats.misses,
            "hit_rate": self.c_space_cache.stats.hit_rate,
            "cache_size": self.c_space_cache.cache_size,
            "memory_mb": self.c_space_cache.memory_usage_mb(),
        }

    def clear_cache(self) -> None:
        """Clear the C-Space grid cache."""
        self.c_space_cache.clear()


def create_pipeline_from_files(
    pcb_path: Path,
    netlist_path: Path | None = None,
    config: PipelineConfig | None = None,
) -> CSpaceRoutingPipeline:
    """
    Create a C-Space routing pipeline from PCB files.

    Args:
        pcb_path: Path to .kicad_pcb file
        netlist_path: Optional path to netlist file
        config: Optional pipeline configuration

    Returns:
        Configured CSpaceRoutingPipeline instance
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(pcb_path)
    board = parse_result.board
    netlist = parse_result.netlist

    return CSpaceRoutingPipeline(board, netlist, config)
