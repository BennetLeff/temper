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
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.routing.c_space_builder import (
    CSpaceCache,
    CSpaceConfig,
    CSpaceGrid,
    SoftCSpaceBuilder,
)
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import Pad as CPad
from temper_placer.routing.dithered_router import DitherConfig, DitheredRouter
from temper_placer.routing.maze_router import MazeRouter, RoutePath
from temper_placer.routing.post_processing.funnel_smoother import FunnelSmoother
from temper_placer.routing.post_processing.trace_ballooner import TraceBallooner
from temper_placer.routing.net_classification import (
    GROUND_NET_PATTERNS,
    HV_NET_PATTERNS,
    POWER_NET_PATTERNS,
)

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the C-Space routing pipeline."""

    resolution_mm: float = 0.2
    fine_resolution_mm: float = 0.05
    enable_dithering: bool = False
    enable_smoothing: bool = False
    enable_ballooning: bool = False
    max_dither_attempts: int = 4
    via_cost: float = 50.0
    
    # RRR Parameters
    max_rrr_iterations: int = 5
    p_scale_start: float = 1.0
    p_scale_step: float = 2.0
    history_increment: float = 1.0  # History penalty increment per iteration
    component_margin: float = 0.5   # Margin around component bounding boxes in mm

    power_nets: list[str] = field(
        default_factory=lambda: list(
            GROUND_NET_PATTERNS | POWER_NET_PATTERNS | HV_NET_PATTERNS
        )
    )


@dataclass
class RoutingResult:
    """Result of routing all nets through the pipeline."""

    net_results: dict[str, RoutePath]
    total_time_ms: float
    successful_count: int
    failed_count: int
    completion_rate: float
    optimized_geometry: PCBGeometry | None = None


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

        # Perform layer assignment once for the whole netlist
        from temper_placer.routing.layer_assignment import assign_layers
        self.layer_assignments = assign_layers(self.netlist)

        self.router: DitheredRouter | MazeRouter | None = None
        self.smoother = FunnelSmoother(resolution_mm=self.config.resolution_mm)

        # Ballooner will be initialized if DRC oracle is available
        self.ballooner: TraceBallooner | None = None

    def extract_geometry(self) -> None:
        """Extract obstacles from netlist (components/pins) and board (mounting holes)."""
        # 1. Clear existing
        self.c_space_builder.pads = []
        self.c_space_builder.pads_by_net = {}
        self.c_space_builder.tracks = []
        self.c_space_builder.vias = []

        # 2. Extract from Netlist Components
        for comp in self.netlist.components:
            if comp.initial_position is None:
                continue

            pos = comp.initial_position
            # Convert rotation index to radians
            rot_idx = comp.initial_rotation or 0
            angle_rad = rot_idx * (np.pi / 2)

            for pin in comp.pins:
                # Absolute position using Pin helper
                abs_pos = pin_world_position(pin, comp)

                # Create spatial index Pad
                p = CPad(
                    center=Point(abs_pos[0], abs_pos[1]),
                    size=(pin.width, pin.height),
                    shape=pin.shape,
                    rotation=float(np.rad2deg(angle_rad)),
                    net=pin.net or "",
                    layer=-1 # All layers (Through-hole or top-side assumed)
                )
                self.c_space_builder.pads.append(p)
                if p.net not in self.c_space_builder.pads_by_net:
                    self.c_space_builder.pads_by_net[p.net] = []
                self.c_space_builder.pads_by_net[p.net].append(p)

        # 3. Extract from Board (Mounting Holes)
        for hole in self.board.mounting_holes:
            p = CPad(
                center=Point(hole.position[0], hole.position[1]),
                size=(hole.diameter, hole.diameter),
                shape="circle",
                rotation=0.0,
                net="KEEP_OUT", # Routing keepout
                layer=-1
            )
            self.c_space_builder.pads.append(p)

        # 4. Extract from Board (Zones)
        for zone in self.board.zones:
            # Treat zones as rectangular obstacles
            # We use the zone name as the net name to allow class-based exclusions
            p = CPad(
                center=Point(zone.center[0], zone.center[1]),
                size=(zone.width, zone.height),
                shape="rect",
                rotation=0.0,
                net=f"ZONE_{zone.name}",
                layer=-1
            )
            self.c_space_builder.pads.append(p)

    def initialize_router(self) -> None:
        """Initialize the routing engine with C-Space integration."""
        # Sync C-Space builder resolution with pipeline config
        self.c_space_builder.update_resolution(self.config.resolution_mm)
        self.c_space_cache.clear()

        self.router = MazeRouter.from_board(
            self.board,
            cell_size_mm=self.config.resolution_mm,
            via_cost=self.config.via_cost,
            design_rules=self.design_rules, # Ensure design rules are passed
        )
        
        # Block pads and components to ensure occupancy grid is properly initialized
        # This is critical for preventing foreign tracks from crossing pads/components
        import numpy as np
        positions = np.array([c.initial_position for c in self.netlist.components])
        
        self.router.block_components(
            self.netlist.components,
            positions,
            margin=0.5,
            layer_specific=(self.router.num_layers > 2)
        )
        
        self.router.block_pads(
            self.netlist.components,
            positions,
            self.netlist,
            trace_width=0.2,
            clearance=0.2
        )
        
        # Block Zones (prevent bleeding)
        self.router.block_zones(
            self.board.zones,
            clearance=0.3
        )

        if self.config.enable_dithering:
            dither_config = DitherConfig(
                enable_dithering=True,
                max_attempts=self.config.max_dither_attempts,
            )
            self.router = DitheredRouter(
                base_router=self.router,
                c_space_builder=self.c_space_builder,
                config=dither_config,
            )

    def route_all(self, net_order: list[str]) -> RoutingResult:
        """Route all specified nets through the pipeline using multi-resolution passes."""
        start_time = time.perf_counter()
        net_results = {}

        # 1. Split nets into Fine and Standard batches
        fine_nets = [n for n in net_order if self._is_high_density_net(n)]
        standard_nets = [n for n in net_order if n not in fine_nets]

        logger.info(f"Multi-resolution routing: {len(fine_nets)} fine nets ({self.config.fine_resolution_mm}mm), "
                    f"{len(standard_nets)} standard nets ({self.config.resolution_mm}mm)")

        # 2. Phase 1: Fine Resolution Routing (MCU breakout etc.)
        if fine_nets:
            # Temporarily use fine resolution
            original_res = self.config.resolution_mm
            self.config.resolution_mm = self.config.fine_resolution_mm
            self.initialize_router()

            logger.info(f"Phase 1: Routing {len(fine_nets)} high-density nets at {self.config.fine_resolution_mm}mm")
            net_results.update(self._route_batch(fine_nets))

            # Restore resolution for Phase 2
            self.config.resolution_mm = original_res

        # 3. Phase 2: Standard Resolution Routing
        if standard_nets:
            if self.router is None:
                self.initialize_router()
            else:
                # Resize existing router to preserve fine-grid occupancy from Phase 1
                base = self.router.base_router if isinstance(self.router, DitheredRouter) else self.router
                if abs(base.cell_size - self.config.resolution_mm) > 1e-6:
                    base.resize_grid(self.config.resolution_mm)

                    # Update CSpace structures for new resolution
                    self.c_space_builder.update_resolution(self.config.resolution_mm)
                    self.c_space_cache.clear()

            logger.info(f"Phase 2: Routing {len(standard_nets)} standard nets at {self.config.resolution_mm}mm")
            net_results.update(self._route_batch(standard_nets))

        # 4. Ballooning (post-all-routing)
        base = self.router.base_router if isinstance(self.router, DitheredRouter) else self.router
        if self.config.enable_ballooning and base.drc_oracle:
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

        # 4. Final Capture: Retrieve optimized geometry from the base router
        base = self.router.base_router if hasattr(self.router, "base_router") else self.router
        optimized_geometry = getattr(base, "optimized_geometry", None)

        return RoutingResult(
            net_results=net_results,
            total_time_ms=elapsed_ms,
            successful_count=successful,
            failed_count=len(net_results) - successful,
            completion_rate=completion,
            optimized_geometry=optimized_geometry
        )

    def _route_batch(self, net_names: list[str]) -> dict[str, RoutePath]:
        """Route a batch of nets at the current resolution using iterative RRR."""
        # 1. Pre-calculate Soft C-Spaces for all nets in batch
        soft_c_spaces = {}
        batch_assignments = {}
        for net_name in net_names:
            pin_positions = self._get_pin_positions(net_name)
            if len(pin_positions) < 2:
                continue

            net_class = self.design_rules.get_class_for_net(net_name)
            
            # Determine exclude_nets for this specific net
            exclude_nets = {net_name}
            for zone in self.board.zones:
                if net_class in zone.net_classes:
                    exclude_nets.add(f"ZONE_{zone.name}")
            
            # AUTO-EXCLUSION: A net must not be blocked by a zone it starts/ends in.
            for x, y in pin_positions:
                pin_zone = self.board.get_zone_for_point(x, y)
                if pin_zone:
                    exclude_nets.add(f"ZONE_{pin_zone.name}")
            
            soft_c_spaces[net_name] = self.c_space_builder.build_cost_grid(
                net_class=net_class,
                exclude_nets=exclude_nets
            )
            
            if net_name in self.layer_assignments:
                batch_assignments[net_name] = self.layer_assignments[net_name]

            # 1. Update Cost Field for Safety
            net_class = self.design_rules.get_class_for_net(net_name)

            # Determine which zones to exclude from blocking based on net class
            exclude_nets = {net_name}
            for zone in self.board.zones:
                if net_class in zone.net_classes:
                    exclude_nets.add(f"ZONE_{zone.name}")

            cost_grid = self.c_space_builder.build_cost_grid(
                net_class=net_class,
                exclude_nets=exclude_nets
            )

        # 2. Call RRR on the base router
        # (DitheredRouter is a wrapper, so we unwrap it)
        base = self.router.base_router if hasattr(self.router, "base_router") else self.router
        
        # Determine current positions array for router internal compute
        import numpy as np
        # Maintain consistent indexing: positions must match netlist.components 1-to-1
        comp_positions_list = []
        for comp in self.netlist.components:
            if comp.initial_position is not None:
                comp_positions_list.append(comp.initial_position)
            else:
                comp_positions_list.append((0.0, 0.0))
        comp_positions = np.array(comp_positions_list)
        
        results = base.rrr_route_all_nets(
            netlist=self.netlist,
            positions=comp_positions,
            net_order=net_names,
            assignments=batch_assignments,
            soft_c_spaces=soft_c_spaces,
            max_iterations=self.config.max_rrr_iterations,
            p_scale_start=self.config.p_scale_start,
            p_scale_step=self.config.p_scale_step,
            history_increment=self.config.history_increment,
            component_margin=self.config.component_margin,
        )

        # 3. Post-process: Smoothing and Missing Nets
        for net_name in net_names:
            if net_name not in results:
                # Handle nets that were skipped (e.g. < 2 pins)
                pin_positions = self._get_pin_positions(net_name)
                results[net_name] = RoutePath(
                    net=net_name,
                    cells=[],
                    length=0.0,
                    via_count=0,
                    success=True if len(pin_positions) < 2 else False,
                    cell_size=self.router.cell_size if hasattr(self.router, "cell_size") else 0.2
                )

            # Legacy smoothing disabled - relying on modern Trace-Aware PostProcessingPipeline
            # if result.success and result.cells and self.config.enable_smoothing:
            #     mask_grid = self._get_c_space_grid(net_name, exclude_nets)
            #     result.smooth_points = self.smoother.smooth(result.cells, mask_grid)
            pass

        return results

    def _is_high_density_net(self, net_name: str) -> bool:
        """Check if a net requires high-resolution routing."""
        # 1. Check if ANY pin is in MCU_ZONE
        positions = self._get_pin_positions(net_name)
        for x, y in positions:
            zone = self.board.get_zone_for_point(x, y)
            if zone and zone.name == "MCU_ZONE":
                return True

        # 2. Check net class rules - anything with fine features
        rules = self.design_rules.get_rules_for_net(net_name)
        # 0.15mm or less is considered high density for our grid approach
        return bool(rules.trace_width <= 0.15 or rules.clearance <= 0.15)

    def _get_c_space_grid(self, net_name: str, exclude_nets: set[str]) -> CSpaceGrid:
        """Get appropriate C-Space grid for routing a net."""
        rules = self.design_rules.get_rules_for_net(net_name)
        class_name = self.design_rules.get_class_for_net(net_name)
        return self.c_space_cache.get_grid(
            class_name=class_name,
            clearance=rules.clearance,
            trace_width=rules.trace_width,
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
                    pos = pin_world_position(pin, comp)
                    positions.append(pos)
        return positions
