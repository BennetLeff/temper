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
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.routing.c_space_builder import (
    CSpaceBuilder,
    CSpaceConfig,
    CSpaceGrid,
    CSpaceCache,
    SoftCSpaceBuilder,
)
from temper_placer.routing.dithered_router import DitheredRouter, DitherConfig
from temper_placer.routing.maze_router import MazeRouter, RoutePath, GridCell
from temper_placer.routing.post_processing.funnel_smoother import FunnelSmoother
from temper_placer.routing.post_processing.trace_ballooner import TraceBallooner

if TYPE_CHECKING:
    from temper_placer.routing.layer_assignment import LayerAssignment
    from temper_placer.core.design_rules import DesignRules

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the C-Space routing pipeline."""

    resolution_mm: float = 0.1
    enable_dithering: bool = False
    enable_smoothing: bool = False
    enable_ballooning: bool = False
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


class CSpaceRoutingPipeline:
    """
    Unified routing pipeline integrating C-Space based routing components.
    """

    def __init__(
        self,
        board: Board,
        netlist: Netlist,
        config: PipelineConfig | None = None,
        design_rules: DesignRules | None = None,
    ):
        self.board = board
        self.netlist = netlist
        self.config = config or PipelineConfig()
        self.cell_size = self.config.resolution_mm
        
        if design_rules is None:
            from temper_placer.core.design_rules import create_temper_design_rules
            self.design_rules = create_temper_design_rules()
        else:
            self.design_rules = design_rules

        self.c_space_config = CSpaceConfig(resolution_mm=self.config.resolution_mm)
        self.c_space_builder = SoftCSpaceBuilder(
            width_mm=board.width,
            height_mm=board.height,
            origin=board.origin,
            config=self.c_space_config,
        )
        self.c_space_cache = CSpaceCache(self.c_space_builder)

        # Extraction needs to be done explicitly or from board
        # self.c_space_builder.extract_obstacles_from_board(ki_board)

        self.router: DitheredRouter | MazeRouter | None = None
        self.smoother = FunnelSmoother(resolution_mm=self.config.resolution_mm)
        
        # Ballooner will be initialized if DRC oracle is available
        self.ballooner: TraceBallooner | None = None

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
        """Route all specified nets through the pipeline."""
        if self.router is None:
            self.initialize_router()

        start_time = time.perf_counter()
        net_results = {}

        for net_name in net_order:
            pin_positions = self._get_pin_positions(net_name)

            if len(pin_positions) < 2:
                net_results[net_name] = RoutePath(
                    net=net_name,
                    cells=[],
                    length=0.0,
                    via_count=0,
                    success=True,
                )
                continue

            # 1. Update Cost Field for Safety
            net_class = self.design_rules.get_class_for_net(net_name)
            cost_grid = self.c_space_builder.build_cost_grid(
                net_class=net_class,
                exclude_nets={net_name}
            )
            
            # Get base router
            base = self.router.base_router if isinstance(self.router, DitheredRouter) else self.router
            base.soft_c_space = cost_grid

            # 2. Route
            route_result = self.router.route_net(
                net_name=net_name,
                pin_positions=pin_positions,
            )

            if route_result.success and self.config.enable_smoothing:
                # 3. Smooth
                c_space = self._get_c_space_grid(net_name, {net_name})
                route_result.smooth_points = self.smoother.smooth(route_result.cells, c_space)

            net_results[net_name] = route_result

        # 4. Ballooning (post-all-routing)
        if self.config.enable_ballooning and base.drc_oracle:
            from temper_placer.routing.constraints.spatial_index import Track
            self.ballooner = TraceBallooner(
                geometry=base.drc_oracle.geometry,
                power_nets=set(self.config.power_nets)
            )
            base.drc_oracle.geometry.tracks = self.ballooner.balloon_traces(
                base.drc_oracle.geometry.tracks
            )
            base.drc_oracle.geometry.rebuild_index()

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        successful = sum(1 for r in net_results.values() if r.success)
        completion = (successful / len(net_results) * 100) if net_results else 100.0

        return RoutingResult(
            net_results=net_results,
            total_time_ms=elapsed_ms,
            successful_count=successful,
            failed_count=len(net_results) - successful,
            completion_rate=completion,
        )

    def _get_c_space_grid(self, net_name: str, exclude_nets: set[str]) -> CSpaceGrid:
        """Get appropriate C-Space grid for routing a net."""
        rules = self.design_rules.get_rules_for_net(net_name)
        return self.c_space_cache.get_grid(
            trace_width=rules.trace_width,
            clearance=rules.clearance,
            exclude_nets=exclude_nets,
        )

    def _get_pin_positions(self, net_name: str) -> list[tuple[float, float]]:
        """Get world coordinates of all pins for a net."""
        # Find net in netlist
        net = next((n for n in self.netlist.nets if n.name == net_name), None)
        if not net:
            return []
            
        positions = []
        comp_map = {c.ref: c for c in self.netlist.components}
        
        for comp_ref, pin_name in net.pins:
            if comp_ref in comp_map:
                comp = comp_map[comp_ref]
                pin = next((p for p in comp.pins if p.name == pin_name or p.number == pin_name), None)
                if pin:
                    pos = pin.absolute_position(
                        comp.initial_position,
                        comp.initial_rotation * (np.pi / 2) if hasattr(comp, 'initial_rotation') else 0.0
                    )
                    positions.append(pos)
        return positions