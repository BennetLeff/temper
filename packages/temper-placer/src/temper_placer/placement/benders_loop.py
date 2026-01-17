"""
Benders Loop Orchestration.

Coordinates the Master Problem (ILP), Subproblem (Max-Flow), and cut generation
to find a provably routable PCB placement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.placement.benders_cut_generator import RoutabilityCut


class BendersStatus(Enum):
    """Status of Benders optimization."""

    OPTIMAL = "optimal"  # Found provably routable placement
    FEASIBLE = "feasible"  # Found feasible placement (routability not verified)
    INFEASIBLE = "infeasible"  # No feasible placement exists
    MAX_ITERATIONS = "max_iterations"  # Reached iteration limit
    ERROR = "error"  # Error during optimization


@dataclass
class BendersResult:
    """
    Result from Benders optimization.

    Attributes:
        status: Optimization status
        iterations: Number of Benders iterations
        final_positions: Final component positions {ref: (x, y)}
        total_movement: Total component movement in mm
        cuts_added: List of routability cuts added
        solve_time_sec: Total optimization time
        master_problem_time: Time spent in ILP solver
        routability_check_time: Time spent in Max-Flow analysis
        router_result: Router result (if use_router_feedback=True)
        drc_result: DRC result (if require_drc_clean=True)
    """

    status: BendersStatus
    iterations: int
    final_positions: dict[str, tuple[float, float]]
    total_movement: float
    cuts_added: list[RoutabilityCut]
    solve_time_sec: float
    master_problem_time: float = 0.0
    routability_check_time: float = 0.0
    router_result: Any = None  # PathfindingResult
    drc_result: Any = None  # DRCResult


class BendersOptimizer:
    """
    Benders decomposition optimizer for PCB placement.

    Iteratively solves:
    1. Master Problem (ILP): Find valid placement
    2. Subproblem (Max-Flow): Check if placement is routable
    3. Cut Generation: Add constraints to open routing channels
    """

    def __init__(
        self,
        component_data_json: str | Path,
        max_iterations: int = 20,
        time_limit_per_ilp_sec: float = 60.0,
        check_routability: bool = True,
        pcb_file: str | Path | None = None,
        verbose: bool = True,
        use_ultrafast_check: bool = True,  # Use ultra-fast heuristic check
        use_router_feedback: bool = False,  # NEW: Use actual router for feedback
        require_drc_clean: bool = False,  # NEW: Require DRC clean output
    ):
        """
        Initialize the Benders optimizer.

        Args:
            component_data_json: Path to benders_input.json
            max_iterations: Maximum Benders iterations
            time_limit_per_ilp_sec: Time limit for each ILP solve
            check_routability: Whether to check routability (set False for testing)
            pcb_file: Optional path to KiCad PCB file for routability checking
            verbose: Print progress information
            use_ultrafast_check: If True, use ultra-fast heuristic check (<1s).
                                 If False, use full Max-Flow analysis (~60s).
            use_router_feedback: If True, run actual router and use failures for cuts.
            require_drc_clean: If True, iterate until DRC is clean (actionable errors only).
        """
        self.component_data_json = Path(component_data_json)
        self.max_iterations = max_iterations
        self.time_limit_per_ilp_sec = time_limit_per_ilp_sec
        self.check_routability = check_routability
        self._pcb_file = Path(pcb_file) if pcb_file else None
        self.verbose = verbose
        self.use_ultrafast_check = use_ultrafast_check
        self.use_router_feedback = use_router_feedback
        self.require_drc_clean = require_drc_clean

        # State
        self.current_iteration = 0
        self.cuts_history: list[RoutabilityCut] = []

        # Components (lazy-loaded)
        self._master_problem = None
        self._mapper = None
        self._cut_generator = None
        self.design_rules = None  # Loaded from pipeline

        # Timing
        self._master_time_total = 0.0
        self._routability_time_total = 0.0
        self._router_time_total = 0.0
        self._drc_time_total = 0.0

    def optimize(self) -> BendersResult:
        """
        Run Benders optimization loop.

        Returns:
            BendersResult with final placement and statistics
        """
        start_time = time.time()

        try:
            # Initialize components
            self._initialize()

            # Benders loop
            for iteration in range(self.max_iterations):
                self.current_iteration = iteration

                if self.verbose:
                    print(f"\n=== Benders Iteration {iteration + 1}/{self.max_iterations} ===")

                # Step 1: Solve Master Problem
                master_result = self._solve_master_problem()

                if master_result.status == "INFEASIBLE":
                    if self.verbose:
                        print("Master Problem is infeasible!")
                    return self._build_result(
                        BendersStatus.INFEASIBLE,
                        {},
                        0.0,
                        time.time() - start_time,
                    )

                if self.verbose:
                    print(
                        f"Master: {master_result.status}, "
                        f"movement={master_result.objective_value:.2f}mm, "
                        f"time={master_result.solve_time_sec:.2f}s"
                    )

                self._master_time_total += master_result.solve_time_sec

                # If not checking routability, return after first iteration
                if not self.check_routability:
                    return self._build_result(
                        BendersStatus.FEASIBLE if master_result.status == "OPTIMAL" else BendersStatus.ERROR,
                        master_result.positions,
                        master_result.objective_value,
                        time.time() - start_time,
                    )

                # Step 2: Check routability
                cuts = []
                
                if self.use_router_feedback:
                    # Use actual router for feedback
                    if self.verbose:
                        print("  Running actual router...")
                    
                    # Update PCB with new placement
                    self._update_pcb_with_placement(master_result.positions)
                    
                    # Run router
                    router_result = self._run_actual_router(master_result.positions)
                    
                    if router_result and router_result.failure_count == 0:
                        # All nets routed successfully
                        if self.require_drc_clean:
                            # Gate 2: Check DRC
                            if self.verbose:
                                print("  ✓ All nets routed. Checking DRC...")
                            
                            drc_result = self._run_drc_check(self._pcb_file)
                            
                            if drc_result and drc_result.actionable_error_count == 0:
                                if self.verbose:
                                    print("  ✓ DRC clean!")
                                return self._build_result(
                                    BendersStatus.OPTIMAL,
                                    master_result.positions,
                                    master_result.objective_value,
                                    time.time() - start_time,
                                    router_result=router_result,
                                    drc_result=drc_result,
                                )
                            else:
                                # Generate cuts from DRC violations
                                if self.verbose:
                                    print(f"  ✗ DRC has {drc_result.actionable_error_count} actionable errors")
                                
                                from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
                                pcb = parse_kicad_pcb_v6(self._pcb_file)
                                
                                drc_cuts = self._generate_cuts_from_drc_violations(
                                    drc_result, pcb, master_result.positions
                                )
                                cuts.extend(drc_cuts)
                        else:
                            # Success - all nets routed
                            if self.verbose:
                                print("  ✓ All nets routed!")
                            return self._build_result(
                                BendersStatus.OPTIMAL,
                                master_result.positions,
                                master_result.objective_value,
                                time.time() - start_time,
                                router_result=router_result,
                            )
                    else:
                        # Router failures - generate cuts
                        if self.verbose:
                            failed = router_result.failure_count if router_result else "unknown"
                            print(f"  ✗ Router failed: {failed} nets")
                        
                        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
                        pcb = parse_kicad_pcb_v6(self._pcb_file)
                        
                        router_cuts = self._generate_cuts_from_router_failures(
                            router_result, pcb, master_result.positions
                        )
                        cuts.extend(router_cuts)
                else:
                    # Use Max-Flow or ultra-fast heuristic
                    is_routable, min_cut_edges = self._check_routability(master_result.positions)

                    if is_routable:
                        if self.verbose:
                            print("✓ Placement is routable!")
                        return self._build_result(
                            BendersStatus.OPTIMAL,
                            master_result.positions,
                            master_result.objective_value,
                            time.time() - start_time,
                        )

                    # Generate cuts from min-cut
                    if self.verbose:
                        print(f"✗ Placement not routable. Min-cut has {len(min_cut_edges)} edges")

                    mincut_cuts = self._generate_cuts_from_mincut(min_cut_edges)
                    cuts.extend(mincut_cuts)

                # Step 3: Add cuts to Master Problem
                if not cuts:
                    if self.verbose:
                        print("Warning: No cuts generated")
                    continue

                if self.verbose:
                    print(f"Generated {len(cuts)} routability cuts")

                for cut in cuts:
                    self._add_cut(cut)

            # Reached max iterations
            if self.verbose:
                print(f"\nReached maximum iterations ({self.max_iterations})")

            # Return best placement found so far
            final_master = self._solve_master_problem()
            
            # Run final router/DRC if requested
            final_router_result = None
            final_drc_result = None
            
            if self.use_router_feedback:
                self._update_pcb_with_placement(final_master.positions)
                final_router_result = self._run_actual_router(final_master.positions)
                
                if self.require_drc_clean and final_router_result:
                    final_drc_result = self._run_drc_check(self._pcb_file)
            
            return self._build_result(
                BendersStatus.MAX_ITERATIONS,
                final_master.positions,
                final_master.objective_value,
                time.time() - start_time,
                router_result=final_router_result,
                drc_result=final_drc_result,
            )

        except Exception as e:
            if self.verbose:
                print(f"Error during optimization: {e}")
                import traceback

                traceback.print_exc()

            return self._build_result(
                BendersStatus.ERROR,
                {},
                float("inf"),
                time.time() - start_time,
            )

    def _initialize(self) -> None:
        """Initialize Master Problem, mapper, and cut generator."""
        from temper_placer.placement.benders_master import BendersMasterProblem
        from temper_placer.placement.benders_mincut_mapper import MinCutMapper
        from temper_placer.placement.benders_cut_generator import BendersCutGenerator
        import json

        # Load component data
        with open(self.component_data_json) as f:
            data = json.load(f)

        # Create Master Problem
        self._master_problem = BendersMasterProblem.from_json(self.component_data_json)
        self._master_problem.build()

        # Create mapper
        from temper_placer.placement.benders_master import ComponentData

        components = []
        for c in data["components"]:
            components.append(
                ComponentData(
                    ref=c["ref"],
                    width_mm=c["width_mm"],
                    height_mm=c["height_mm"],
                    x_mm=c.get("center_x_mm", c.get("x_mm", 0)),
                    y_mm=c.get("center_y_mm", c.get("y_mm", 0)),
                    classification=c.get("classification", "FREE"),
                    hv_nets=c.get("hv_nets", []),
                )
            )

        self._mapper = MinCutMapper(components, tolerance_mm=2.0)

        # Create cut generator
        self._cut_generator = BendersCutGenerator()

        if self.verbose:
            print(f"Initialized with {len(components)} components")

    def _solve_master_problem(self):
        """Solve the ILP Master Problem."""
        return self._master_problem.solve(
            time_limit_sec=self.time_limit_per_ilp_sec,
            iteration=self.current_iteration,
        )

    def _check_routability(self, positions: dict[str, tuple[float, float]]) -> tuple[bool, list]:
        """
        Check if placement is routable.

        Uses either ultra-fast heuristic (<1s) or full Max-Flow analysis (~60s)
        depending on the use_ultrafast_check setting.

        Args:
            positions: Component positions from Master Problem

        Returns:
            Tuple of (is_routable, min_cut_edges)
        """
        import time
        start_time = time.time()
        
        # Try ultra-fast check first (if enabled)
        if self.use_ultrafast_check:
            try:
                result = self._check_routability_ultrafast(positions)
                self._routability_time_total += time.time() - start_time
                
                if self.verbose and not result[0]:
                    print(f"  Ultra-fast check: Not routable")
                
                return result
                
            except Exception as e:
                if self.verbose:
                    print(f"  Ultra-fast check failed: {e}, falling back to Max-Flow")
                # Fall through to Max-Flow
        
        # Full Max-Flow analysis
        try:
            # 1. Update PCB with new positions (if PCB file available)
            if hasattr(self, "_pcb_file") and self._pcb_file:
                self._update_pcb_with_placement(positions)
            
            # 2. Run router pipeline to get channel skeletons
            skeletons, widths, design_rules = self._run_router_pipeline()
            
            # 3. Extract nets from PCB
            nets = self._extract_nets_from_placement(positions)
            
            # 4. Run Max-Flow analysis
            from temper_placer.router_v6.analysis.max_flow import MaxFlowAnalyzer
            
            analyzer = MaxFlowAnalyzer(skeletons, widths, design_rules)
            result = analyzer.compute_feasibility(nets)
            
            self._routability_time_total += time.time() - start_time
            
            return result.is_feasible, result.min_cut_edges
            
        except ImportError as e:
            if self.verbose:
                print(f"Warning: Max-Flow analyzer not available: {e}")
            # Fall back to mock
            return True, []
        except Exception as e:
            if self.verbose:
                print(f"Warning: Routability check failed: {e}")
            # Fall back to assuming routable
            return True, []
    
    def _check_routability_ultrafast(self, positions: dict[str, tuple[float, float]]) -> tuple[bool, list]:
        """
        Ultra-fast routability check using heuristics.
        
        Args:
            positions: Component positions
            
        Returns:
            Tuple of (is_routable, []) - no min-cut edges for heuristic check
        """
        from temper_placer.router_v6.benders_routability_ultrafast import (
            check_routability_ultrafast
        )
        
        # Get component sizes from master problem
        import json
        with open(self.component_data_json) as f:
            data = json.load(f)
        
        sizes = {
            c["ref"]: (c["width_mm"], c["height_mm"])
            for c in data["components"]
        }
        
        # Extract net connections (simplified - connect components sharing nets)
        net_connections = []
        # For now, use empty net connections (quick check for overlaps/congestion only)
        
        # Get board bounds
        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        margin = 10.0
        bounds = (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
        
        result = check_routability_ultrafast(
            component_positions=positions,
            component_sizes=sizes,
            net_connections=net_connections,
            board_bounds=bounds,
            min_clearance_mm=0.5,
            verbose=self.verbose,
        )
        
        if self.verbose:
            print(f"  Ultra-fast: congestion={result.congestion_score:.1%}, overlaps={result.overlap_count}")
        
        # No min-cut edges for heuristic check
        return result.is_feasible, []

    def _generate_cuts_from_mincut(self, min_cut_edges: list) -> list[RoutabilityCut]:
        """
        Generate routability cuts from min-cut edges.

        Args:
            min_cut_edges: Min-cut edges from Max-Flow analysis

        Returns:
            List of RoutabilityCut objects
        """
        # Map min-cut to blocking components
        blocking = self._mapper.map_mincut_to_components(min_cut_edges)

        # Generate cuts
        cuts = self._cut_generator.generate_cuts(blocking, iteration=self.current_iteration)

        return cuts

    def _add_cut(self, cut: RoutabilityCut) -> None:
        """
        Add a routability cut to the Master Problem.

        Args:
            cut: RoutabilityCut to add
        """
        # Convert cut to Master Problem format
        cut_type, components, gap = cut.to_master_problem_args()

        # Add to Master Problem
        self._master_problem.add_routability_cut(cut_type, components, gap)

        # Track in history
        self.cuts_history.append(cut)

    def _update_pcb_with_placement(self, positions: dict[str, tuple[float, float]]) -> None:
        """
        Update PCB file with new component positions.

        Args:
            positions: New component positions {ref: (x, y)}
        """
        try:
            from kiutils.board import Board as KiBoard
            
            # Load PCB
            board = KiBoard.from_file(str(self._pcb_file))
            
            # Update component positions
            updated = 0
            for footprint in board.footprints:
                ref = footprint.properties.get('Reference', None)
                if ref and ref in positions:
                    new_x, new_y = positions[ref]
                    footprint.position.X = new_x
                    footprint.position.Y = new_y
                    updated += 1
            
            # Save PCB
            board.to_file(str(self._pcb_file))
            
            if self.verbose:
                print(f"  Updated {updated} component positions in PCB")
                
        except Exception as e:
            if self.verbose:
                print(f"  Warning: PCB update failed: {e}")
            # Continue anyway - Max-Flow can work with original positions

    def _run_router_pipeline(self):
        """
        Run router pipeline to get channel skeletons and widths.

        Returns:
            Tuple of (skeletons, widths, design_rules)
        """
        try:
            from temper_placer.router_v6.pipeline import RouterV6Pipeline
            
            pipeline = RouterV6Pipeline(
                verbose=False,
                enable_routability_analysis=False,  # Don't run Max-Flow recursively!
            )
            
            # Run full pipeline (loads PCB, runs Stage 0-4)
            result = pipeline.run(self._pcb_file)
            
            if self.verbose:
                print(f"  Router pipeline complete: {len(result.stage2.skeletons)} layers")
            
            return (
                result.stage2.skeletons,
                result.stage2.channel_widths,
                result.pcb.design_rules
            )
            
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Router pipeline failed: {e}")
            # Return empty structures - Max-Flow will gracefully fail
            return {}, {}, None

    def _extract_nets_from_placement(self, positions: dict[str, tuple[float, float]]) -> dict:
        """
        Extract net information for Max-Flow analysis.

        Args:
            positions: Component positions {ref: (x, y)}

        Returns:
            Dict of net_name -> {source, sink, allowed_layers}
        """
        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb
            
            # Parse PCB to get netlist with pad positions
            parse_result = parse_kicad_pcb(Path(self._pcb_file), normalize=False)
            
            nets_dict = {}
            
            # Extract terminal positions for each net
            for net in parse_result.netlist.nets:
                # Skip power/ground nets (heuristic: name contains GND, VCC, VDD, VBUS, etc.)
                is_power = any(
                    keyword in net.name.upper()
                    for keyword in ["GND", "VCC", "VDD", "VBUS", "+", "POWER"]
                )
                
                # Skip power nets and single-pin nets
                if is_power or len(net.pins) < 2:
                    continue
                
                # Get first two pads as source/sink (simplified)
                # In a full implementation, would use better heuristics
                pads_for_net = [
                    pad for pad in parse_result.pads 
                    if pad.net == net.name
                ]
                
                if len(pads_for_net) >= 2:
                    nets_dict[net.name] = {
                        "source": pads_for_net[0].position,
                        "sink": pads_for_net[1].position,
                        "allowed_layers": ["F.Cu", "B.Cu"],  # Simplified
                    }
            
            if self.verbose:
                print(f"  Extracted {len(nets_dict)} nets for Max-Flow analysis")
            
            return nets_dict
            
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Net extraction failed: {e}")
            # Return empty dict
            return {}

    def _run_actual_router(self, positions: dict[str, tuple[float, float]]):
        """
        Run the actual Router V6 pipeline and return routing results.
        
        Also writes routes to PCB file for DRC checking.
        
        Returns:
            PathfindingResult with success/failure information
        """
        router_start = time.time()
        
        try:
            # PCB should already be updated by caller
            # Just run the router
            from temper_placer.router_v6.pipeline import RouterV6Pipeline
            from temper_placer.io.kicad_writer import write_routes_direct
            
            pipeline = RouterV6Pipeline(verbose=self.verbose)
            result = pipeline.run(self._pcb_file)
            
            router_time = time.time() - router_start
            self._router_time_total += router_time
            
            # Extract PathfindingResult from Stage4Output
            pathfinding_result = result.stage4.pathfinding_result
            width_assignment = result.stage4.width_assignment
            
            if self.verbose:
                success = pathfinding_result.success_count if hasattr(pathfinding_result, 'success_count') else len(pathfinding_result.routed_paths)
                failed = pathfinding_result.failure_count if hasattr(pathfinding_result, 'failure_count') else len(pathfinding_result.failed_nets)
                total = success + failed
                print(f"  Router: {success}/{total} nets routed ({router_time:.1f}s)")
            
            # Write routes to PCB file for DRC checking
            routes, vias = self._extract_routes_for_export(
                pathfinding_result, 
                width_assignment,
                result.pcb.design_rules
            )
            
            if routes:
                write_routes_direct(
                    template_pcb=self._pcb_file,
                    output_pcb=self._pcb_file,  # Overwrite input file
                    routes=routes,
                    vias=vias if vias else None,
                    clear_existing=True,  # Remove old routes before adding new
                )
                if self.verbose:
                    print(f"  Wrote {len(routes)} traces, {len(vias) if vias else 0} vias to PCB")
            
            return pathfinding_result  # PathfindingResult
            
        except Exception as e:
            if self.verbose:
                print(f"  Router failed: {e}")
                import traceback
                traceback.print_exc()
            return None
    
    def _extract_routes_for_export(self, pathfinding_result, width_assignment, design_rules):
        """
        Extract routes from PathfindingResult in format for write_routes_direct.
        
        Returns:
            (routes, vias) where:
            - routes: list of {start, end, width, layer, net}
            - vias: list of {position, width, drill, layers, net}
        """
        routes = []
        vias = []
        
        for net_name, path in pathfinding_result.routed_paths.items():
            # Get trace width for this net
            width = None
            if width_assignment:
                width = width_assignment.get_width(net_name)
            if width is None:
                rules = design_rules.get_rules_for_net(net_name) if design_rules else None
                width = rules.trace_width_mm if rules else 0.25
            
            # Handle RoutePath3D (multi-layer with explicit segments)
            if hasattr(path, 'segments') and path.segments:
                # RoutePath3D: segments are (x, y, layer)
                for i in range(len(path.segments) - 1):
                    x1, y1, layer1 = path.segments[i]
                    x2, y2, layer2 = path.segments[i + 1]
                    
                    # If layers differ, we need a via (handled by via_positions)
                    if layer1 == layer2:
                        routes.append({
                            'start': (x1, y1),
                            'end': (x2, y2),
                            'width': width,
                            'layer': layer1,
                            'net': net_name,
                        })
                
                # Add vias at layer transitions
                if hasattr(path, 'via_positions') and path.via_positions:
                    for vx, vy in path.via_positions:
                        vias.append({
                            'position': (vx, vy),
                            'width': 0.8,  # Standard via size
                            'drill': 0.4,  # Standard drill size
                            'layers': ('F.Cu', 'B.Cu'),
                            'net': net_name,
                        })
            
            # Handle RoutePath (single layer with coordinates)
            elif hasattr(path, 'coordinates') and path.coordinates:
                layer = path.layer_name if hasattr(path, 'layer_name') else 'F.Cu'
                for i in range(len(path.coordinates) - 1):
                    x1, y1 = path.coordinates[i]
                    x2, y2 = path.coordinates[i + 1]
                    routes.append({
                        'start': (x1, y1),
                        'end': (x2, y2),
                        'width': width,
                        'layer': layer,
                        'net': net_name,
                    })
        
        return routes, vias
    
    def _run_drc_check(self, pcb_file: Path):
        """
        Run KiCad DRC and return actionable violations.
        
        Returns:
            DRCResult
        """
        drc_start = time.time()
        
        try:
            from temper_placer.io.kicad_drc import run_drc
            
            result = run_drc(pcb_file)
            
            drc_time = time.time() - drc_start
            self._drc_time_total += drc_time
            
            if self.verbose:
                actionable = len(result.actionable_violations) if hasattr(result, 'actionable_violations') else 0
                cosmetic = len(result.cosmetic_violations) if hasattr(result, 'cosmetic_violations') else 0
                print(f"  DRC: {actionable} actionable, {cosmetic} cosmetic ({drc_time:.1f}s)")
            
            return result
            
        except Exception as e:
            if self.verbose:
                print(f"  DRC check failed: {e}")
            return None
    
    def _generate_cuts_from_router_failures(self, router_result, pcb, positions):
        """
        Generate ILP cuts from router failures.
        
        Returns:
            List of RoutabilityCut objects
        """
        try:
            from temper_placer.placement.benders_failure_mapper import map_failures_to_components
            
            # Extract failure reports
            if not router_result.failure_reports:
                return []
            
            failures = list(router_result.failure_reports.values())
            
            # Map to blocking pairs
            blocking_pairs = map_failures_to_components(
                failures=failures,
                pcb=pcb,
                component_positions=positions,
                verbose=self.verbose,
            )
            
            # Generate cuts
            cuts = self._cut_generator.generate_cuts_from_router_failures(
                blocking_pairs=blocking_pairs,
                iteration=self.current_iteration,
            )
            
            return cuts
            
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Failed to generate cuts from router failures: {e}")
            return []
    
    def _generate_cuts_from_drc_violations(self, drc_result, pcb, positions):
        """
        Generate ILP cuts from DRC violations.
        
        Returns:
            List of RoutabilityCut objects
        """
        try:
            from temper_placer.placement.benders_drc_mapper import map_drc_violations_to_components
            
            # Get actionable violations only
            violations = drc_result.actionable_violations
            
            if not violations:
                return []
            
            # Map to blocking pairs
            blocking_pairs = map_drc_violations_to_components(
                violations=violations,
                pcb=pcb,
                component_positions=positions,
                verbose=self.verbose,
            )
            
            # Generate cuts
            cuts = self._cut_generator.generate_cuts_from_router_failures(
                blocking_pairs=blocking_pairs,
                iteration=self.current_iteration,
            )
            
            return cuts
            
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Failed to generate cuts from DRC violations: {e}")
            return []

    def _build_result(
        self,
        status: BendersStatus,
        positions: dict[str, tuple[float, float]],
        total_movement: float,
        total_time: float,
        router_result=None,
        drc_result=None,
    ) -> BendersResult:
        """Build a BendersResult object."""
        return BendersResult(
            status=status,
            iterations=self.current_iteration + 1,
            final_positions=positions,
            total_movement=total_movement,
            cuts_added=self.cuts_history,
            solve_time_sec=total_time,
            master_problem_time=self._master_time_total,
            routability_check_time=self._routability_time_total,
            router_result=router_result,
            drc_result=drc_result,
        )


def run_benders_optimization(
    component_data_json: str | Path,
    max_iterations: int = 20,
    pcb_file: str | Path | None = None,
    check_routability: bool = True,
    verbose: bool = True,
    use_ultrafast_check: bool = True,
) -> BendersResult:
    """
    Convenience function to run Benders optimization.

    Args:
        component_data_json: Path to benders_input.json
        max_iterations: Maximum Benders iterations
        pcb_file: Optional path to KiCad PCB file for routability checking
        check_routability: Whether to check routability
        verbose: Print progress
        use_ultrafast_check: If True, use ultra-fast heuristic check (<1s).
                             If False, use full Max-Flow analysis (~60s).

    Returns:
        BendersResult
    """
    optimizer = BendersOptimizer(
        component_data_json=component_data_json,
        max_iterations=max_iterations,
        check_routability=check_routability,
        pcb_file=pcb_file,
        verbose=verbose,
        use_ultrafast_check=use_ultrafast_check,
    )

    return optimizer.optimize()
