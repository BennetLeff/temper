"""
Iterative DRC Router - Production Quality Routing

Strategy:
1. Route all nets with exact geometry
2. Run DRC to identify violations
3. Rip up nets involved in violations
4. Reroute with increased clearance
5. Repeat until DRC-clean or max iterations

This achieves production-ready routing by iteratively fixing violations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
import numpy as np
import uuid
import tempfile
import os

from temper_placer.router_v6.exact_geometry_router import (
    ExactGeometryRouter,
    ExactRoutePath,
    ExactSegment,
)
from temper_placer.router_v6.stage0_data import ParsedPCB, DesignRules
from temper_placer.io.kicad_drc import run_drc, DRCResult

try:
    from kiutils.board import Board
    from kiutils.items.brditems import Segment
    from kiutils.items.common import Position
    KIUTILS_AVAILABLE = True
except ImportError:
    KIUTILS_AVAILABLE = False


@dataclass
class IterationResult:
    """Result of one routing iteration."""
    iteration: int
    routed_nets: list[str]
    failed_nets: list[str]
    drc_errors: int
    routing_errors: int  # clearance + shorting + crossing
    violating_nets: set[str]
    

@dataclass  
class IterativeDRCRouterConfig:
    """Configuration for iterative DRC router."""
    max_iterations: int = 5
    clearance_increment: float = 0.05  # mm to add each iteration
    max_clearance: float = 0.5  # mm max clearance
    rrt_iterations: int = 15000
    step_size: float = 3.0
    verbose: bool = True


class IterativeDRCRouter:
    """
    Production-quality router using iterative DRC feedback.
    
    Workflow:
    1. Initial route with exact geometry
    2. Export to KiCad and run DRC
    3. Parse DRC to find violating nets
    4. Rip up violating nets
    5. Reroute with increased clearance
    6. Repeat until clean
    """
    
    ROUTING_ERROR_TYPES = {'clearance', 'shorting_items', 'tracks_crossing'}
    SKIP_NETS = {'GND', 'PGND', 'CGND', '+3V3', '+5V', '+15V', 'DC_BUS+'}
    
    def __init__(
        self,
        pcb: ParsedPCB,
        design_rules: DesignRules,
        source_pcb_path: str | Path,
        config: IterativeDRCRouterConfig | None = None,
    ):
        self.pcb = pcb
        self.design_rules = design_rules
        self.source_pcb_path = Path(source_pcb_path)
        self.config = config or IterativeDRCRouterConfig()
        
        self.iteration_history: list[IterationResult] = []
        self.final_routes: dict[str, ExactRoutePath] = {}
        
    def _get_signal_nets(self, router: ExactGeometryRouter) -> list[str]:
        """Get signal nets in optimal routing order (shortest first)."""
        signal_nets = [
            n for n in router._net_pads.keys()
            if n not in self.SKIP_NETS and len(router._net_pads[n]) >= 2
        ]
        
        def net_length(net_name: str) -> float:
            pads = router._net_pads.get(net_name, [])
            if len(pads) < 2:
                return float('inf')
            return sum(
                np.sqrt((pads[i][0] - pads[i+1][0])**2 + 
                       (pads[i][1] - pads[i+1][1])**2)
                for i in range(len(pads) - 1)
            )
        
        return sorted(signal_nets, key=net_length)
    
    def _export_to_kicad(
        self,
        routes: dict[str, ExactRoutePath],
        output_path: Path,
    ) -> None:
        """Export routes to KiCad PCB file."""
        if not KIUTILS_AVAILABLE:
            raise ImportError("kiutils required for DRC checking")
        
        board = Board.from_file(str(self.source_pcb_path))
        net_codes = {net.name: net.number for net in board.nets}
        
        for net_name, route in routes.items():
            for seg in route.segments:
                segment = Segment(
                    start=Position(X=seg.start[0], Y=seg.start[1]),
                    end=Position(X=seg.end[0], Y=seg.end[1]),
                    width=seg.width,
                    layer=seg.layer,
                    net=net_codes.get(net_name, 0),
                    tstamp=str(uuid.uuid4()),
                )
                board.traceItems.append(segment)
        
        board.to_file(str(output_path))
    
    def _parse_drc_violations(
        self,
        drc_result: DRCResult,
    ) -> tuple[int, set[str]]:
        """Parse DRC result to find TRUE routing errors (not footprint pad clearance)."""
        routing_errors = 0
        violating_nets = set()
        
        for v in drc_result.violations:
            if not v.is_error:
                continue
            if v.type not in self.ROUTING_ERROR_TYPES:
                continue
            
            # Check if this error involves a TRACK (routing issue)
            # vs just pads (footprint design issue)
            involves_track = False
            net_names = []
            
            if hasattr(v, 'items') and v.items:
                for item in v.items:
                    if isinstance(item, dict):
                        desc = item.get('description', '')
                        
                        # Check for track involvement
                        if 'Track' in desc:
                            involves_track = True
                        
                        # Extract net name
                        if '[' in desc and ']' in desc:
                            net = desc.split('[')[1].split(']')[0]
                            net_names.append(net)
            
            # Only count as routing error if it involves a track
            # Pad-to-pad clearance is footprint design, not routing
            if involves_track:
                routing_errors += 1
                for net in net_names:
                    if net not in self.SKIP_NETS:
                        violating_nets.add(net)
        
        return routing_errors, violating_nets
    
    def _route_iteration(
        self,
        iteration: int,
        nets_to_route: list[str],
        extra_clearance: float,
        existing_routes: dict[str, ExactRoutePath],
    ) -> dict[str, ExactRoutePath]:
        """Run one routing iteration."""
        # Create router with custom clearance
        router = ExactGeometryRouter(
            pcb=self.pcb,
            design_rules=self.design_rules,
            verbose=self.config.verbose,
        )
        
        # Add existing (non-ripped) routes as obstacles
        for net_name, route in existing_routes.items():
            for seg in route.segments:
                if seg.layer not in router.routed_segments:
                    router.routed_segments[seg.layer] = []
                router.routed_segments[seg.layer].append(seg)
        
        # Override RRT parameters for this iteration
        original_rrt = router._rrt_path
        def custom_rrt(start, goal, obstacles, max_iterations=None, step_size=None):
            return original_rrt.__func__(
                router, start, goal, obstacles,
                max_iterations=self.config.rrt_iterations,
                step_size=self.config.step_size,
            )
        router._rrt_path = custom_rrt
        
        # Override clearance for problem nets
        original_get_obstacles = router._get_obstacles_for_net
        def custom_get_obstacles(layer, net_name, clearance, trace_width, target_pads=None):
            # Add extra clearance for this iteration
            return original_get_obstacles.__func__(
                router, layer, net_name,
                clearance + extra_clearance,
                trace_width, target_pads
            )
        router._get_obstacles_for_net = custom_get_obstacles
        
        # Route the specified nets
        new_routes = {}
        for net_name in nets_to_route:
            layer = self.design_rules.get_layer_constraint(net_name) or 'F.Cu'
            pads = router._net_pads.get(net_name, [])
            
            if len(pads) < 2:
                continue
            
            route = router.route_net(net_name, layer, pads)
            if route:
                new_routes[net_name] = route
        
        return new_routes
    
    def route(self) -> dict[str, ExactRoutePath]:
        """
        Main entry point - iterative DRC-based routing.
        
        Returns:
            Dictionary of net_name -> ExactRoutePath for all routed nets
        """
        if self.config.verbose:
            print("=" * 70)
            print("ITERATIVE DRC ROUTER - Production Quality Routing")
            print("=" * 70)
        
        # Initial router to get net list
        init_router = ExactGeometryRouter(
            pcb=self.pcb,
            design_rules=self.design_rules,
            verbose=False,
        )
        all_signal_nets = self._get_signal_nets(init_router)
        
        if self.config.verbose:
            print(f"\nSignal nets to route: {len(all_signal_nets)}")
        
        # Track routes across iterations
        all_routes: dict[str, ExactRoutePath] = {}
        nets_to_route = all_signal_nets.copy()
        extra_clearance = 0.0
        
        for iteration in range(self.config.max_iterations):
            if self.config.verbose:
                print(f"\n{'='*60}")
                print(f"ITERATION {iteration + 1}")
                print(f"{'='*60}")
                print(f"  Nets to route: {len(nets_to_route)}")
                print(f"  Extra clearance: {extra_clearance:.2f}mm")
            
            # Route nets
            new_routes = self._route_iteration(
                iteration,
                nets_to_route,
                extra_clearance,
                all_routes,
            )
            
            # Merge new routes
            all_routes.update(new_routes)
            
            routed_this_iter = list(new_routes.keys())
            failed_this_iter = [n for n in nets_to_route if n not in new_routes]
            
            if self.config.verbose:
                print(f"\n  Routed this iteration: {len(routed_this_iter)}")
                print(f"  Failed this iteration: {len(failed_this_iter)}")
                if failed_this_iter:
                    print(f"    {failed_this_iter}")
            
            # Export and run DRC
            with tempfile.NamedTemporaryFile(suffix='.kicad_pcb', delete=False) as f:
                temp_path = Path(f.name)
            
            try:
                self._export_to_kicad(all_routes, temp_path)
                drc_result = run_drc(str(temp_path))
                
                routing_errors, violating_nets = self._parse_drc_violations(drc_result)
                
                if self.config.verbose:
                    print(f"\n  DRC Results:")
                    print(f"    Total errors: {drc_result.error_count}")
                    print(f"    Routing errors: {routing_errors}")
                    print(f"    Violating nets: {violating_nets}")
                
                # Record iteration
                result = IterationResult(
                    iteration=iteration + 1,
                    routed_nets=routed_this_iter,
                    failed_nets=failed_this_iter,
                    drc_errors=drc_result.error_count,
                    routing_errors=routing_errors,
                    violating_nets=violating_nets,
                )
                self.iteration_history.append(result)
                
                # Check if we're done
                if routing_errors == 0:
                    if self.config.verbose:
                        print(f"\n  ✓ DRC CLEAN - No routing errors!")
                    break
                
                # Prepare next iteration
                # Rip up violating nets
                for net in violating_nets:
                    if net in all_routes:
                        del all_routes[net]
                
                # Route violating nets + previously failed nets
                nets_to_route = list(violating_nets) + failed_this_iter
                
                # Increase clearance
                extra_clearance += self.config.clearance_increment
                if extra_clearance > self.config.max_clearance:
                    extra_clearance = self.config.max_clearance
                    if self.config.verbose:
                        print(f"  ⚠ Max clearance reached ({self.config.max_clearance}mm)")
                
            finally:
                if temp_path.exists():
                    os.unlink(temp_path)
        
        self.final_routes = all_routes
        
        if self.config.verbose:
            print("\n" + "=" * 70)
            print("FINAL RESULTS")
            print("=" * 70)
            print(f"  Total signal nets: {len(all_signal_nets)}")
            print(f"  Successfully routed: {len(all_routes)}")
            print(f"  Failed: {len(all_signal_nets) - len(all_routes)}")
            if self.iteration_history:
                last = self.iteration_history[-1]
                print(f"  Final routing errors: {last.routing_errors}")
        
        return all_routes
    
    def export_final(self, output_path: str | Path) -> Path:
        """Export final routes to KiCad PCB file."""
        output_path = Path(output_path)
        self._export_to_kicad(self.final_routes, output_path)
        return output_path


def run_iterative_drc_routing(
    pcb: ParsedPCB,
    design_rules: DesignRules,
    source_pcb_path: str | Path,
    output_path: str | Path | None = None,
    config: IterativeDRCRouterConfig | None = None,
) -> tuple[dict[str, ExactRoutePath], Path]:
    """
    Convenience function for iterative DRC routing.
    
    Returns:
        Tuple of (routes dict, output PCB path)
    """
    router = IterativeDRCRouter(pcb, design_rules, source_pcb_path, config)
    routes = router.route()
    
    if output_path is None:
        output_path = Path('/tmp/iterative_drc_routed.kicad_pcb')
    
    final_path = router.export_final(output_path)
    return routes, final_path
