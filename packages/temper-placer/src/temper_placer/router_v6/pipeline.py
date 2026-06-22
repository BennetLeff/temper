"""
Router V6 Pipeline: End-to-End Integration

Wires together Stages 0-4 of Router V6 topological architecture:
- Stage 0: Load PCB data
- Stage 1: Generate escape vias
- Stage 2: Channel extraction and analysis
- Stage 3: Topological routing (SAT-based)
- Stage 4: Geometric realization (A*)

Part of Phase 1.5: Integration & Validation
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.astar_pathfinding import PathfindingResult, run_astar_pathfinding
from temper_placer.router_v6.bottleneck_analysis import BottleneckAnalysis, identify_bottlenecks
from temper_placer.router_v6.channel_mapping import map_topology_to_channels
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton, extract_channel_skeleton
from temper_placer.router_v6.channel_widths import ChannelWidths, compute_channel_widths
from temper_placer.router_v6.constraint_model import ConstraintModel, ModelBuilder
from temper_placer.router_v6.dense_package_detection import identify_dense_packages
from temper_placer.router_v6.escape_via_generator import EscapeVia, generate_escape_vias
from temper_placer.router_v6.layer_capacity import LayerCapacity, calculate_layer_capacity
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.occupancy_grid import OccupancyGrid, build_occupancy_grid
from temper_placer.routing.geometry_fields.sdf_builder import SDFGrid
from temper_placer.routing.variational_router.snake_optimizer import SnakeOptimizer
from temper_placer.routing.exact_geometry.path_simplifier import PathSimplifier
from temper_placer.placement.legalization import Legalizer
from temper_placer.router_v6.routing_demand import RoutingDemand, estimate_routing_demand
from temper_placer.router_v6.routing_results import RoutingResults, compile_routing_results
from temper_placer.router_v6.routing_space import RoutingSpace, compute_routing_space
from temper_placer.router_v6.sat_model import SATModel, build_sat_model
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.topology_extraction import TopologyGraph, extract_topology_solution
from temper_placer.router_v6.topology_solver import TopologicalSolution, solve_topology
from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment, assign_trace_widths
from temper_placer.router_v6.via_placement import ViaPlacement, place_vias


@dataclass
class Stage2Output:
    """Output from Stage 2: Channel Analysis."""

    obstacle_maps: dict[str, any]  # layer -> obstacles
    routing_spaces: dict[str, RoutingSpace]  # layer -> routing space
    skeletons: dict[str, ChannelSkeleton]  # layer -> skeleton
    channel_widths: dict[str, ChannelWidths]  # layer -> widths
    occupancy_grids: dict[str, OccupancyGrid]  # layer -> grid
    layer_capacities: dict[str, LayerCapacity]  # layer -> capacity
    routing_demand: RoutingDemand
    bottleneck_analysis: BottleneckAnalysis


@dataclass
class Stage3Output:
    """Output from Stage 3: Topological Routing."""

    constraint_model: ConstraintModel
    sat_model: SATModel
    solution: TopologicalSolution
    topology_graph: TopologyGraph


@dataclass
class Stage4Output:
    """Output from Stage 4: Geometric Realization."""

    pathfinding_result: PathfindingResult
    via_placement: ViaPlacement
    width_assignment: TraceWidthAssignment
    routing_results: RoutingResults


@dataclass
class RouterV6Result:
    """Complete Router V6 pipeline result."""

    pcb: ParsedPCB
    escape_vias: list[EscapeVia]
    stage2: Stage2Output
    stage3: Stage3Output
    stage4: Stage4Output

    runtime_seconds: float

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets."""
        return self.stage4.routing_results.success_count

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return self.stage4.routing_results.failure_count

    @property
    def completion_rate(self) -> float:
        """Fraction of nets successfully routed."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class RouterV6Pipeline:
    """Router V6 end-to-end pipeline."""

    def __init__(
        self,
        verbose: bool = False,
        enable_theta_star: bool = False,
        enable_lazy_theta_star: bool = False,
        enable_smoothing: bool = False,
        enable_legalization: bool = True,  # Default ON for robustness
        max_nets: int | None = None,
        target_nets: list[str] | None = None,
    ):
        """
        Initialize Router V6 pipeline.

        Args:
            verbose: Enable verbose logging
            enable_theta_star: Use Theta* any-angle routing (Experiment F)
            enable_lazy_theta_star: Use Lazy Theta* (Experiment O4)
            enable_smoothing: Apply force-directed smoothing (Experiment G)
            enable_legalization: Auto-fix component overlaps (Phase 6)
            max_nets: Limit number of nets to route (for profiling)
            target_nets: List of specific net names to route
        """
        self.verbose = verbose
        self.enable_theta_star = enable_theta_star
        self.enable_lazy_theta_star = enable_lazy_theta_star
        self.enable_smoothing = enable_smoothing
        self.enable_legalization = enable_legalization
        self.max_nets = max_nets
        self.target_nets = target_nets

    def run(self, pcb_path: Path) -> RouterV6Result:
        """
        Run complete Router V6 pipeline on a PCB file.

        Args:
            pcb_path: Path to .kicad_pcb file

        Returns:
            RouterV6Result with complete routing solution
        """
        start_time = time.time()

        # Stage 0: Load PCB
        if self.verbose:
            print("Stage 0: Loading PCB...")
        pcb = parse_kicad_pcb_v6(pcb_path)

        # Stage 0.5: Legalization
        if self.enable_legalization:
            if self.verbose:
                print("Stage 0.5: Checking and Legalizing Placement...")

            legalizer = Legalizer(pcb)
            # Check collisions before
            if self.verbose:
                collisions = legalizer.auditor.check_collisions()
                print(f"  Found {len(collisions)} initial collisions")

            if legalizer.legalize():
                if self.verbose:
                    print("  Legalization successful (0 overlaps)")
            else:
                if self.verbose:
                    print("  Warning: Legalization did not fully converge (residual overlap)")

        # Validate placement (Post-Legalization)
        # Note: pcb.validate_placement checks for missing footprints etc, not necessarily geometric overlap.
        # But we assume Legalizer updated pcb.components in-place.
        errors = pcb.validate_placement()
        if errors:
            raise ValueError(f"PCB validation failed: {errors}")

        # Stage 1: Generate escape vias
        if self.verbose:
            print(f"Stage 1: Detecting dense packages in {len(pcb.components)} components...")
        dense_packages = identify_dense_packages(pcb.components)
        if self.verbose:
            print(f"  Found {len(dense_packages)} dense packages")

        escape_vias = []
        for dense_pkg in dense_packages:
            # Try dog-bone first
            vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="dog-bone")

            # If that fails (tight pitch), try via-in-pad
            if not vias:
                if self.verbose:
                    print(f"    Falling back to via-in-pad for {dense_pkg.component.ref}")
                vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="via-in-pad")

            escape_vias.extend(vias)
        if self.verbose:
            print(f"  Generated {len(escape_vias)} escape vias")

        # Stage 2: Channel analysis
        if self.verbose:
            print("Stage 2: Channel analysis...")
        stage2 = self._run_stage2(pcb, escape_vias)

        # Stage 3: Topological routing
        if self.verbose:
            print("Stage 3: Topological routing...")
        stage3 = self._run_stage3(pcb, stage2)

        # Stage 4: Geometric realization
        if self.verbose:
            print("Stage 4: Geometric realization...")
        stage4 = self._run_stage4(pcb, stage2, stage3, escape_vias)

        runtime = time.time() - start_time

        if self.verbose:
            print(f"\nRouter V6 complete in {runtime:.1f}s")
            print(f"  Routed: {stage4.routing_results.success_count} nets")
            print(f"  Failed: {stage4.routing_results.failure_count} nets")
            print(
                f"  Completion: {100 * stage4.routing_results.success_count / max(1, stage4.routing_results.success_count + stage4.routing_results.failure_count):.1f}%"
            )

        return RouterV6Result(
            pcb=pcb,
            escape_vias=escape_vias,
            stage2=stage2,
            stage3=stage3,
            stage4=stage4,
            runtime_seconds=runtime,
        )

    def _run_stage2(self, pcb: ParsedPCB, escape_vias: list[EscapeVia]) -> Stage2Output:
        """Run Stage 2: Channel Analysis."""

        # 2.1-2.2: Compute routing space (includes obstacle map building)
        if self.verbose:
            print("  2.1-2.2: Computing routing space...")
        routing_spaces = compute_routing_space(pcb, escape_vias)
        if self.verbose:
            print(f"    Computed routing spaces for {len(routing_spaces)} layers")

        # Build obstacle maps separately for later use
        obstacle_maps = build_obstacle_map(pcb, escape_vias)

        # 2.3: Extract channel skeleton
        if self.verbose:
            print("  2.3: Extracting channel skeleton...")
        skeletons = {}
        for layer_name, routing_space in routing_spaces.items():
            skeleton = extract_channel_skeleton(routing_space, pcb=pcb)
            skeletons[layer_name] = skeleton
            if self.verbose:
                print(f"    {layer_name}: {skeleton.node_count} nodes, {skeleton.edge_count} edges")

        # 2.4: Compute channel widths
        if self.verbose:
            print("  2.4: Computing channel widths...")
        channel_widths = {}
        for layer_name, skeleton in skeletons.items():
            widths = compute_channel_widths(
                routing_spaces[layer_name],
                skeleton,
            )
            channel_widths[layer_name] = widths

        # 2.5: Build occupancy grid
        if self.verbose:
            print("  2.5: Building occupancy grid...")

        # Calculate base inflation for C-Space (trace radius + clearance)
        base_inflation = (
            pcb.design_rules.default_trace_width_mm / 2.0
        ) + pcb.design_rules.default_clearance_mm

        occupancy_grids = {}
        for layer_name, routing_space in routing_spaces.items():
            grid = build_occupancy_grid(routing_space, inflation_mm=base_inflation)
            occupancy_grids[layer_name] = grid

        # 2.6: Calculate per-layer capacity
        if self.verbose:
            print("  2.6: Calculating layer capacity...")
        layer_capacities = {}
        for layer_name in occupancy_grids.keys():
            capacity = calculate_layer_capacity(
                occupancy_grids[layer_name],
                channel_widths[layer_name],
                pcb.design_rules.default_trace_width_mm * 1.5,  # 50% safety margin
                pcb.design_rules.default_clearance_mm,
            )
            layer_capacities[layer_name] = capacity

        # 2.7: Estimate demand
        if self.verbose:
            print("  2.7: Estimating routing demand...")
        routing_demand = estimate_routing_demand(pcb)

        # 2.8: Identify bottlenecks
        if self.verbose:
            print("  2.8: Identifying bottlenecks...")
        bottleneck_analysis = identify_bottlenecks(
            layer_capacities,
            routing_demand,
        )
        if self.verbose and bottleneck_analysis.has_critical_bottlenecks:
            print(f"    Warning: {len(bottleneck_analysis.bottlenecks)} bottlenecks identified")

        return Stage2Output(
            obstacle_maps=obstacle_maps,
            routing_spaces=routing_spaces,
            skeletons=skeletons,
            channel_widths=channel_widths,
            occupancy_grids=occupancy_grids,
            layer_capacities=layer_capacities,
            routing_demand=routing_demand,
            bottleneck_analysis=bottleneck_analysis,
        )

    def _run_stage3(self, pcb: ParsedPCB, stage2: Stage2Output) -> Stage3Output:
        """Run Stage 3: Topological Routing."""

        # 3.1-3.6: Build constraint model
        if self.verbose:
            print("  3.1-3.6: Building constraint model...")
        model_builder = ModelBuilder(
            skeletons=stage2.skeletons,
            nets=pcb.nets,
            channel_widths=stage2.channel_widths,
            design_rules=pcb.design_rules,
            diff_pairs=[],  # TODO: Add diff pair inference
            pcb=pcb,
        )
        constraint_model = model_builder.build()

        # 3.7: Build SAT model
        if self.verbose:
            print("  3.7: Building SAT model...")
        sat_model = build_sat_model()  # Creates empty model

        # Populate SAT model from constraint model
        from temper_placer.router_v6.sat_model import populate_sat_from_constraints

        net_names = [net.name for net in pcb.nets]
        populate_sat_from_constraints(sat_model, constraint_model, net_names)

        if self.verbose:
            print(
                f"    SAT model: {sat_model.variable_count} vars, {sat_model.clause_count} clauses"
            )

        # 3.8: Solve topology
        if self.verbose:
            print("  3.8: Solving topology...")
        solution = solve_topology(sat_model, timeout_ms=30000.0)

        if self.verbose:
            if solution.is_satisfiable:
                print("    Solution found (SAT)")
            else:
                print("    No solution found (UNSAT)")

        # 3.9: Extract topology
        if self.verbose:
            print("  3.9: Extracting topology graph...")
        net_names = [net.name for net in pcb.nets]
        topology_graph = extract_topology_solution(solution, net_names)

        return Stage3Output(
            constraint_model=constraint_model,
            sat_model=sat_model,
            solution=solution,
            topology_graph=topology_graph,
        )

    def _run_stage4(
        self,
        pcb: ParsedPCB,
        stage2: Stage2Output,
        stage3: Stage3Output,
        escape_vias: list[EscapeVia] | None = None,
    ) -> Stage4Output:
        """Run Stage 4: Geometric Realization with multi-layer support."""
        from temper_placer.router_v6.channel_mapping import ChannelMapping

        # Convert escape_vias list to map for A*
        escape_vias_map: dict[str, list[tuple[float, float, float]]] = {}
        if escape_vias:
            for v in escape_vias:
                if v.net_name not in escape_vias_map:
                    escape_vias_map[v.net_name] = []
                escape_vias_map[v.net_name].append((v.position[0], v.position[1], v.diameter))

        # 4.1: Setup channel mapping (from topology solution)
        if self.verbose:
            print("  4.1: Setting up channel mapping...")

        # Use F.Cu skeleton for initial mapping (layer assignment happens inside)
        fcu_skeleton = stage2.skeletons.get("F.Cu")
        bcu_skeleton = stage2.skeletons.get("B.Cu")

        # Fall back to first available if named layers don't exist
        if not fcu_skeleton:
            fcu_skeleton = list(stage2.skeletons.values())[0]
        if not bcu_skeleton:
            bcu_skeleton = list(stage2.skeletons.values())[-1]

        # Map all nets with layer assignment
        channel_mapping = map_topology_to_channels(
            stage3.topology_graph,
            fcu_skeleton,  # Use F.Cu skeleton for mapping (waypoints are generic)
            nets=pcb.nets,
            components=pcb.components,
        )

        # 4.2: Run A* pathfinding (Unified)
        if self.verbose:
            print("  4.2: Running A* pathfinding (unified multi-layer)...")

        # Get primary and alternate grids
        fcu_grid = stage2.occupancy_grids.get("F.Cu")
        bcu_grid = stage2.occupancy_grids.get("B.Cu")

        if not fcu_grid:
            fcu_grid = list(stage2.occupancy_grids.values())[0]
        if not bcu_grid and len(stage2.occupancy_grids) > 1:
            bcu_grid = [g for g in stage2.occupancy_grids.values() if g != fcu_grid][0]

        # Unified call: pass all nets and both grids
        pathfinding_result = run_astar_pathfinding(
            channel_mapping,
            fcu_grid,
            pcb.design_rules,
            alternate_grid=bcu_grid,
            pcb=pcb,
            escape_vias_map=escape_vias_map,
            use_theta_star=self.enable_theta_star,
            use_lazy_theta_star=self.enable_lazy_theta_star,
            max_nets=self.max_nets,
            target_nets=self.target_nets,
        )

        # 4.2.5: Force-directed smoothing (optional post-processing)
        if self.enable_smoothing:
            if self.verbose:
                print("  4.2.5: Applying Variational Smoothing (Snakes)...")

            # 1. Build SDFs for all layers
            sdf_grids = {}
            clearance_mm = pcb.design_rules.default_clearance_mm

            # Use exact geometry from Stage 2.1 RoutingSpace
            # This avoids grid quantization artifacts in the SDF

            # Calculate bounds safely
            if hasattr(pcb, "board") and pcb.board:
                bounds_array = pcb.board.get_bounds_array()  # [xmin, ymin, xmax, ymax]
                bounds = tuple(bounds_array)
            else:
                # Fallback: compute from components
                all_x = []
                all_y = []
                for comp in pcb.components:
                    x, y = comp.initial_position
                    all_x.append(x)
                    all_y.append(y)
                if all_x:
                    bounds = (min(all_x) - 5, min(all_y) - 5, max(all_x) + 5, max(all_y) + 5)
                else:
                    bounds = (0, 0, 100, 100)

            # Add small padding to bounds
            bounds = (bounds[0] - 1, bounds[1] - 1, bounds[2] + 1, bounds[3] + 1)

            for layer_name, routing_space in stage2.routing_spaces.items():
                if self.verbose:
                    print(f"    Building Exact SDF for {layer_name}...")

                # Get raw obstacles (Shapely polygons)
                # Ensure it's a list
                obstacles = routing_space.obstacles
                if not obstacles:
                    polygon_list = []
                elif hasattr(obstacles, "geoms"):
                    polygon_list = list(obstacles.geoms)
                else:
                    polygon_list = [obstacles]

                # Build high-resolution SDF (0.05mm)
                sdf_grids[layer_name] = SDFGrid.from_polygons(
                    polygons=polygon_list, bounds=bounds, resolution_mm=0.05
                )

            # 2. Run Path Simplifier (H1)
            if True:
                if self.verbose:
                    print("    Using SDF-Verified Path Simplifier (H1)...")
                simplifier = PathSimplifier(
                    sdf_grids=sdf_grids,
                    step_size_mm=0.1,
                    min_clearance_margin=0.0,  # Default value, will override per net
                    occupancy_grids=stage2.occupancy_grids,  # Dynamic obstacles
                )

                # Pre-calculate widths (Stage 4.4 runs later, but we need widths now)
                # This duplicates logic but avoids reordering the pipeline stages
                temp_widths = {}
                for net_name in pathfinding_result.routed_paths:
                    # Use helper method to resolve net class rules
                    rule = pcb.design_rules.get_rules_for_net(net_name)
                    # print(f"DEBUG: rule keys: {rule.__dict__.keys()}")
                    # Handle attribute naming variations if any
                    if hasattr(rule, "trace_width"):
                        temp_widths[net_name] = rule.trace_width
                    elif hasattr(rule, "trace_width_mm"):
                        temp_widths[net_name] = rule.trace_width_mm
                    else:
                        temp_widths[net_name] = pcb.design_rules.default_trace_width_mm

                smoothed_paths = {}
                for net_name, path in pathfinding_result.routed_paths.items():
                    # Calculate required margin = width/2 + clearance + safety buffer
                    # Safety buffer absorbs SDF/Grid aliasing errors (0.05mm grid -> +/-0.025mm error)
                    net_width = temp_widths.get(net_name, pcb.design_rules.default_trace_width_mm)
                    safety_buffer = 0.05
                    required_margin = (net_width / 2.0) + clearance_mm + safety_buffer

                    # Get Net ID for dynamic check
                    net_id = pathfinding_result.net_ids.get(net_name, -1)

                    # Simplify
                    opt_path = simplifier.simplify_path(
                        path, required_clearance_override=required_margin, net_id=net_id
                    )
                    smoothed_paths[net_name] = opt_path
            else:
                # 2. Run Snake Optimizer
                optimizer = SnakeOptimizer(
                    sdf_grids=sdf_grids,
                    alpha=0.2,  # Lower elasticity to allow sticking to path
                    beta=0.1,  # Low stiffness to allow sharp turns near pads
                    gamma=2.0,  # Strong repulsion from obstacles
                    step_size=0.1,
                    node_spacing_mm=0.2,
                    max_iterations=100,
                )

                smoothed_paths = {}
                for net_name, path in pathfinding_result.routed_paths.items():
                    # Optimize
                    opt_path = optimizer.optimize_path(path)
                    smoothed_paths[net_name] = opt_path

            pathfinding_result.routed_paths = smoothed_paths

            if self.verbose:
                print(f"    Smoothed {len(smoothed_paths)} paths")

        # 4.3: Place vias
        if self.verbose:
            print("  4.3: Placing vias...")
        via_placement = place_vias(
            pathfinding_result,
            pcb.design_rules.default_via_diameter_mm,
            pcb.design_rules.default_via_drill_mm,
        )

        # 4.4: Assign trace widths
        if self.verbose:
            print("  4.4: Assigning trace widths...")
        width_assignment = assign_trace_widths(
            pathfinding_result,
            default_width=pcb.design_rules.default_trace_width_mm,
        )

        # 4.5-4.8: Skip length matching for now

        # 4.9: Compile results
        if self.verbose:
            print("  4.9: Compiling routing results...")
        routing_results = compile_routing_results(
            pathfinding_result,
            width_assignment,
            via_placement,
            length_matching=None,
        )

        return Stage4Output(
            pathfinding_result=pathfinding_result,
            via_placement=via_placement,
            width_assignment=width_assignment,
            routing_results=routing_results,
        )
