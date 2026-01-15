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
from temper_placer.placement.spectral import SpectralPlacer
from temper_placer.placement.analytical import AnalyticalLegalizer
from temper_placer.router_v7.negotiated_router import NegotiatedRouter
from temper_placer.router_v7.diff_pair_router import DiffPairRouter
from temper_placer.router_v6.routing_demand import RoutingDemand, estimate_routing_demand
from temper_placer.router_v6.routing_results import RoutingResults, compile_routing_results
from temper_placer.router_v6.routing_space import RoutingSpace, compute_routing_space
from temper_placer.router_v6.sat_model import SATModel, build_sat_model
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.topology_extraction import TopologyGraph, extract_topology_solution
from temper_placer.router_v6.topology_solver import TopologicalSolution, solve_topology
from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment, assign_trace_widths
from temper_placer.router_v6.via_placement import ViaPlacement, place_vias
from temper_placer.router_v6.analysis.max_flow import MaxFlowAnalyzer, MaxFlowResult


@dataclass
class Stage2Output:
    """Output from Stage 2: Channel Analysis."""

    obstacle_maps: dict[str, any]  # layer -> obstacles
    routing_spaces: dict[str, RoutingSpace]  # layer -> routing space
    skeletons: dict[str, ChannelSkeleton]  # layer -> skeleton
    channel_widths: dict[str, ChannelWidths]  # layer -> widths
    occupancy_grids: dict[str, OccupancyGrid]  # layer -> grid
    hv_occupancy_grids: dict[str, OccupancyGrid]  # dedicated HV grids
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
    power_planes: list[dict] | None = None  # List of zone definitions


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
        enable_negotiated_congestion: bool = False,  # Phase 8 PathFinder
        enable_routability_analysis: bool = False,  # Max-Flow feasibility analysis
        enable_topological_ordering: bool = False,  # Phase 2: Ordering Optimization
        placement_mode: str = "physics",  # "physics" or "analytical"
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
            enable_negotiated_congestion: Use PathFinder algorithm (Phase 8)
            enable_routability_analysis: Run Max-Flow feasibility analysis (Phase 10)
            enable_topological_ordering: Optimize routing sequence (Phase 11)
            placement_mode: Strategy for placement ("physics", "analytical")
            max_nets: Limit number of nets to route (for profiling)
            target_nets: List of specific net names to route
        """
        self.verbose = verbose
        self.enable_theta_star = enable_theta_star
        self.enable_lazy_theta_star = enable_lazy_theta_star
        self.enable_smoothing = enable_smoothing
        self.enable_legalization = enable_legalization
        self.enable_negotiated_congestion = enable_negotiated_congestion
        self.enable_routability_analysis = enable_routability_analysis
        self.enable_topological_ordering = enable_topological_ordering
        self.placement_mode = placement_mode
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

        # MANUAL OVERRIDE: Fix Placement of Gate Driver Cluster to avoid AC Mains violations
        # Loaded from placement_constraints.json to separate data from logic.
        try:
            import json
            from pathlib import Path
            
            config_path = Path(__file__).parent / "placement_constraints.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = json.load(f)
                    overrides = config.get("overrides", {})
                    
                if self.verbose and overrides:
                    print(f"Applying {len(overrides)} placement constraints from {config_path.name}...")

                for comp in pcb.components:
                    if comp.ref in overrides:
                        data = overrides[comp.ref]
                        new_pos = tuple(data["position"])
                        is_fixed = data.get("fixed", False)
                        
                        comp.initial_position = new_pos
                        comp.fixed = is_fixed
                        
                        if self.verbose:
                            status = "LOCKED" if is_fixed else "PLACED"
                            print(f"  {status} {comp.ref} at {new_pos}")
            else:
                if self.verbose:
                    print(f"Warning: Constraint file not found at {config_path}")
        except Exception as e:
            print(f"Error loading placement constraints: {e}")

        # Stage 0.5: Legalization
        if self.enable_legalization:
            if self.verbose:
                print(f"Stage 0.5: Placement Optimization (Mode: {self.placement_mode})...")

            if self.placement_mode == "analytical":
                # Experiment P3: Spectral + LP
                if self.verbose:
                    print("  Running Spectral Placement...")
                spectral = SpectralPlacer(pcb)
                coords = spectral.compute_placement()

                # Determine bounds (use existing board area or component extent)
                # For now, use existing component extent as bounds to avoid expansion
                init_x = [c.initial_position[0] for c in pcb.components if c.initial_position]
                init_y = [c.initial_position[1] for c in pcb.components if c.initial_position]
                if init_x:
                    bounds = (min(init_x), min(init_y), max(init_x), max(init_y))
                else:
                    bounds = (0, 0, 100, 100)

                # Scale spectral coords to bounds
                spec_x = [p[0] for p in coords.values()]
                spec_y = [p[1] for p in coords.values()]
                s_min_x, s_max_x = min(spec_x), max(spec_x)
                s_min_y, s_max_y = min(spec_y), max(spec_y)

                # Avoid div by zero
                sx = (bounds[2] - bounds[0]) / (s_max_x - s_min_x) if s_max_x != s_min_x else 1
                sy = (bounds[3] - bounds[1]) / (s_max_y - s_min_y) if s_max_y != s_min_y else 1
                scale = min(sx, sy)  # Uniform scaling

                # Center
                cx = (bounds[0] + bounds[2]) / 2
                cy = (bounds[1] + bounds[3]) / 2

                scaled_coords = {}
                for ref, (x, y) in coords.items():
                    scaled_coords[ref] = (x * scale + cx, y * scale + cy)

                if self.verbose:
                    print("  Running Analytical Legalization (LP)...")
                legalizer = AnalyticalLegalizer(pcb)
                if legalizer.legalize(scaled_coords, bounds):
                    if self.verbose:
                        print("  Analytical Legalization successful")
                else:
                    if self.verbose:
                        print("  Warning: LP Infeasible, falling back to Physics")
                    # Fallback to physics
                    phys_legalizer = Legalizer(pcb)
                    phys_legalizer.legalize()

            else:
                # Default: Physics-based Legalization (Experiment P2)
                legalizer = Legalizer(pcb)
                # Check collisions before
                if self.verbose:
                    collisions = legalizer.auditor.check_collisions()
                    print(f"  Found {len(collisions)} initial collisions")

                if legalizer.legalize():
                    if self.verbose:
                        print("  Physics Legalization successful (0 overlaps)")
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

        # Calculate base inflation using MAX clearance from routing-relevant net classes
        # Excludes ACMains/HighVoltageIsolated which have special safety requirements
        # and would inflate C-Space too aggressively for normal routing
        max_clearance = pcb.design_rules.default_clearance_mm
        max_trace_width = pcb.design_rules.default_trace_width_mm
        for nc_name, nc_rules in pcb.design_rules.net_classes.items():
            if nc_name in ("ACMains", "HighVoltageIsolated"):
                continue  # Skip special safety classes
            if nc_rules.clearance_mm > max_clearance:
                max_clearance = nc_rules.clearance_mm
            if nc_rules.trace_width_mm > max_trace_width:
                max_trace_width = nc_rules.trace_width_mm

        # Increase C-space inflation for better clearance
        # Original: (trace_width/2 + clearance) = 0.125 + 0.2 = 0.325mm
        # New: Add extra margin for routing safety
        base_inflation = (max_trace_width / 2.0) + max_clearance + 0.1  # Extra 0.1mm margin

        if self.verbose:
            print(f"    Using max clearance: {max_clearance}mm for C-Space inflation")

        occupancy_grids = {}
        hv_occupancy_grids = {}  # dedicated grids for AC Mains (6.0mm clearance)

        # HV Inflation: Conservative estimate for AC Mains
        # We assume AC Mains might use wide traces, so we take the max trace width from all classes (or default safe value)
        # + 6.0mm safety clearance.
        hv_inflation = (max_trace_width / 2.0) + 6.0
        
        if self.verbose:
             print(f"    Building specialized HV grids with inflation: {hv_inflation}mm")

        for layer_name, routing_space in routing_spaces.items():
            # 1. Standard Grid (Low Voltage)
            grid = build_occupancy_grid(routing_space, cell_size=0.2, inflation_mm=base_inflation)

            # Apply Stackup Strategy: Prefer Top Layer (F.Cu)
            if layer_name == "F.Cu":
                grid.base_cost = 1.0
            elif layer_name == "B.Cu":
                grid.base_cost = 10.0  # 10x cost -> Prefer Top unless blocked
            else:
                grid.base_cost = 5.0  # Inner layers
            
            occupancy_grids[layer_name] = grid
            
            # 2. HV Grid (High Voltage / AC Mains)
            hv_grid = build_occupancy_grid(routing_space, cell_size=0.2, inflation_mm=hv_inflation)
            hv_grid.base_cost = grid.base_cost # inherit cost strategy
            hv_occupancy_grids[layer_name] = hv_grid

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

        # 2.9: Max-Flow Routability Analysis (Phase 10)
        if self.enable_routability_analysis:
            if self.verbose:
                print("  2.9: Running Max-Flow Routability Analysis...")
            
            analyzer = MaxFlowAnalyzer(skeletons, channel_widths, pcb.design_rules)
            
            demands = {}
            from temper_placer.router_v6.astar_pathfinding import _extract_pad_centers_per_net
            pad_centers = _extract_pad_centers_per_net(pcb)
            
            for net_name, pads in pad_centers.items():
                if len(pads) >= 2:
                    demands[net_name] = {
                        "source": (pads[0][0], pads[0][1]),
                        "sink": (pads[-1][0], pads[-1][1]),
                        "allowed_layers": list(skeletons.keys())
                    }
            
            if demands:
                result = analyzer.compute_feasibility(demands)
                if self.verbose:
                    print(f"    Max-Flow Capacity: {result.max_flow} traces")
                    print(f"    Net Demand: {result.total_demand} nets")
                    if not result.is_feasible:
                        print(f"    WARNING: Board is MATHEMATICALLY UNROUTABLE! Bottleneck: {len(result.min_cut_edges)} edges.")
            elif self.verbose:
                print("    Skipping Max-Flow: No multi-pin nets found")

        return Stage2Output(
            obstacle_maps=obstacle_maps,
            routing_spaces=routing_spaces,
            skeletons=skeletons,
            channel_widths=channel_widths,
            occupancy_grids=occupancy_grids,
            hv_occupancy_grids=hv_occupancy_grids,
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
        solution = solve_topology(sat_model, timeout_ms=5000.0)

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

        # Load layer assignments from YAML config
        from pathlib import Path
        import yaml
        
        # Config is at packages/temper-placer/configs/, not src/temper_placer/configs/
        layer_config_path = Path(__file__).parent.parent.parent.parent / "configs" / "temper_layer_assignments.yaml"
        if layer_config_path.exists():
            with open(layer_config_path) as f:
                layer_config = yaml.safe_load(f)
                
                # Merge net-specific layer assignments
                if "net_layers" in layer_config:
                    pcb.design_rules.net_layer_assignments.update(layer_config["net_layers"])
                    if self.verbose:
                        print(f"  Loaded {len(layer_config['net_layers'])} layer assignments from YAML")
                
                # Merge net class layer constraints
                if "net_class_layers" in layer_config and layer_config["net_class_layers"]:
                    for class_name, layer in layer_config["net_class_layers"].items():
                        if class_name in pcb.design_rules.net_classes:
                            pcb.design_rules.net_classes[class_name].layer_constraint = layer
                
                # Load net categories (power/control/analog/differential)
                if "net_categories" in layer_config:
                    for category, nets in layer_config["net_categories"].items():
                        if nets:
                            for net in nets:
                                pcb.design_rules.net_categories[net] = category
                    if self.verbose:
                        print(f"  Loaded {len(pcb.design_rules.net_categories)} net categories")
                
                # Load crossing rules
                if "crossing_rules" in layer_config:
                    rules = layer_config["crossing_rules"]
                    if "accept_crossings" in rules and rules["accept_crossings"]:
                        pcb.design_rules.accept_crossings = [tuple(p) for p in rules["accept_crossings"]]
                    if "via_at_crossing" in rules and rules["via_at_crossing"]:
                        pcb.design_rules.via_at_crossing = [tuple(p) for p in rules["via_at_crossing"]]
                    if self.verbose:
                        print(f"  Loaded {len(pcb.design_rules.accept_crossings)} accepted crossing pairs")
                        print(f"  Loaded {len(pcb.design_rules.via_at_crossing)} via-at-crossing pairs")
        
        # Map all nets with layer assignment
        channel_mapping = map_topology_to_channels(
            stage3.topology_graph,
            fcu_skeleton,  # Use F.Cu skeleton for mapping (waypoints are generic)
            nets=pcb.nets,
            components=pcb.components,
            design_rules=pcb.design_rules,
        )

        if self.verbose:
            print("  4.2: Running Routing (Sequential A*)...")

        # Get primary and alternate grids
        fcu_grid = stage2.occupancy_grids.get("F.Cu")
        bcu_grid = stage2.occupancy_grids.get("B.Cu")

        if not fcu_grid:
            fcu_grid = list(stage2.occupancy_grids.values())[0]
        if not bcu_grid and len(stage2.occupancy_grids) > 1:
            bcu_grid = [g for g in stage2.occupancy_grids.values() if g != fcu_grid][0]
        
        # Pass HV grids for ACMains handling
        hv_grids = stage2.hv_occupancy_grids

        # 1. Route Differential Pairs (Priority)
        routed_paths_dp = {}

        # Identify Diff Pairs
        diff_pairs = []  # List of (p_net, n_net)
        processed_nets = set()

        # Use F.Cu skeleton for initial mapping (layer assignment happens inside)
        # We need a list of nets to scan.
        sorted_nets = sorted(channel_mapping.channel_paths.keys())
        for n1 in sorted_nets:
            if n1 in processed_nets:
                continue

            # Check for pair: USB_D+, USB_D- or similar
            if n1.endswith("+"):
                base = n1[:-1]
                n2 = base + "-"
                if n2 in channel_mapping.channel_paths:
                    diff_pairs.append((n1, n2))
                    processed_nets.add(n1)
                    processed_nets.add(n2)
            elif n1.endswith("_P"):
                base = n1[:-2]
                n2 = base + "_N"
                if n2 in channel_mapping.channel_paths:
                    diff_pairs.append((n1, n2))
                    processed_nets.add(n1)
                    processed_nets.add(n2)

        if diff_pairs:
            if self.verbose:
                print(f"  Found {len(diff_pairs)} differential pairs")

            # Extract pads for start/end
            from temper_placer.router_v6.astar_pathfinding import _extract_pad_centers_per_net

            pad_centers = _extract_pad_centers_per_net(pcb)

            # Prepare routers for all available layers
            # We prioritize F.Cu (Top) then B.Cu (Bottom)
            available_dp_routers = []
            if fcu_grid:
                available_dp_routers.append((fcu_grid, "F.Cu"))
            if bcu_grid:
                available_dp_routers.append((bcu_grid, "B.Cu"))

            for p_net, n_net in diff_pairs:
                # Get start/end from pads
                p_pads = pad_centers.get(p_net, [])
                n_pads = pad_centers.get(n_net, [])

                if len(p_pads) != 2 or len(n_pads) != 2:
                    if self.verbose:
                        print(f"    Skipping {p_net}/{n_net} (Not 2-pin nets)")
                    processed_nets.remove(p_net)
                    processed_nets.remove(n_net)
                    continue

                # Calculate Pair Center Start/End
                p1, p2 = p_pads[0], p_pads[1]
                n1, n2 = n_pads[0], n_pads[1]

                # Dist p1-n1
                d11 = (p1[0] - n1[0]) ** 2 + (p1[1] - n1[1]) ** 2
                d12 = (p1[0] - n2[0]) ** 2 + (p1[1] - n2[1]) ** 2

                if d11 < d12:
                    start_p, start_n = p1, n1
                    end_p, end_n = p2, n2
                else:
                    start_p, start_n = p1, n2
                    end_p, end_n = p2, n1

                width = pcb.design_rules.default_trace_width_mm
                gap = pcb.design_rules.default_clearance_mm

                # Get Differential class-specific values for correct diff pair routing
                diff_class = pcb.design_rules.net_classes.get("Differential")
                if diff_class:
                    width = diff_class.trace_width_mm
                    gap = diff_class.diff_pair_gap_mm if diff_class.diff_pair_gap_mm else gap

                if self.verbose:
                    print(f"    Routing Pair {p_net}/{n_net}...")

                # Try layers sequentially
                result_pair = None
                used_grid = None

                for grid, layer_name in available_dp_routers:
                    dp_router = DiffPairRouter(grid)
                    result_pair = dp_router.route_pair_with_fanout(
                        (start_p[0], start_p[1]),
                        (start_n[0], start_n[1]),
                        (end_p[0], end_p[1]),
                        (end_n[0], end_n[1]),
                        width,
                        gap,
                    )
                    if result_pair:
                        used_grid = grid
                        if self.verbose:
                            print(f"      ✓ Routed on {layer_name}")
                        break

                if result_pair:
                    path_p, path_n = result_pair
                    path_p.net_name = p_net
                    path_n.net_name = n_net
                    # Ensure layer name is correct in path
                    path_p.layer_name = used_grid.layer_name
                    path_n.layer_name = used_grid.layer_name

                    routed_paths_dp[p_net] = path_p
                    routed_paths_dp[n_net] = path_n

                    # Mark blocked on Used Grid
                    used_grid.mark_path_blocked(path_p.coordinates, width, gap, net_id=998)
                    used_grid.mark_path_blocked(path_n.coordinates, width, gap, net_id=999)
                else:
                    if self.verbose:
                        print(f"    Failed to route pair {p_net}/{n_net} on any layer")
                    processed_nets.remove(p_net)
                    processed_nets.remove(n_net)

        # Remove routed Diff Pairs from channel mapping for standard router
        # We need to filter channel_mapping.channel_paths
        # But channel_mapping object is used inside run_astar.
        # We can modify it in place?
        # Or pass a filtered list of 'target_nets' to run_astar?
        # run_astar takes 'target_nets'.

        # Calculate remaining nets
        all_nets = list(channel_mapping.channel_paths.keys())
        remaining_nets = [n for n in all_nets if n not in routed_paths_dp]

        if self.enable_negotiated_congestion:
            # Phase 8: Negotiated Router
            grids = stage2.occupancy_grids
            negotiated_router = NegotiatedRouter(
                grids=grids,
                design_rules=pcb.design_rules,
                max_iterations=30,  # Limit for prototype
            )

            # Need list of nets. Use remaining_nets.
            nets_to_route = remaining_nets

            # ... (Existing logic for pads) ...

            # Extract pads
            pad_centers_per_net = {}  # Should extract from pcb
            # Use helper from astar_pathfinding if available or inline
            from temper_placer.router_v6.astar_pathfinding import (
                _extract_pad_centers_per_net,
                _build_tht_pad_locations,
            )

            pad_centers_per_net = _extract_pad_centers_per_net(pcb)
            tht_locations = _build_tht_pad_locations(pcb)

            routed_paths_dict = negotiated_router.route(
                nets=nets_to_route,
                channel_mapping=channel_mapping,
                pad_centers=pad_centers_per_net,
                tht_locations=tht_locations,
            )

            # Merge Diff Pairs
            routed_paths_dict.update(routed_paths_dp)

            # Wrap in PathfindingResult
            pathfinding_result = PathfindingResult(
                routed_paths=routed_paths_dict,
                failed_nets=[],  # Assume all routed or failed silently
                failure_reports={},
                net_ids={},  # TODO: Generate IDs
            )

        else:
            # Unified call: pass all nets and both grids
            # Use 'target_nets' to exclude Diff Pairs

            # Merge target_nets (if CLI arg) with remaining_nets
            final_target_nets = remaining_nets
            if self.target_nets:
                final_target_nets = [n for n in remaining_nets if n in self.target_nets]

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
                target_nets=final_target_nets,  # Pass filtered list
                hv_grids=hv_grids,
                enable_topological_ordering=self.enable_topological_ordering,
            )

            print(f"  Checking for competing nets...", flush=True)
            
            # HYBRID ROUTING: Report competing nets but skip NegotiatedRouter
            # NegotiatedRouter hangs due to blocked grids - needs grid clearing fix
            if pathfinding_result.competing_nets and len(pathfinding_result.competing_nets) > 0:
                print(f"\n  ℹ️  Detected {len(pathfinding_result.competing_nets)} competing nets (oscillation detected)")
                print(f"     {', '.join(sorted(pathfinding_result.competing_nets))}")
                print(f"     (NegotiatedRouter disabled - using graceful degradation)")
            
            # Skip NegotiatedRouter for now
            if False and pathfinding_result.competing_nets and len(pathfinding_result.competing_nets) > 0:
                print(f"\n  🔄 Hybrid Routing: Handing off {len(pathfinding_result.competing_nets)} competing nets to NegotiatedRouter...", flush=True)
                print(f"     Competing nets: {', '.join(sorted(pathfinding_result.competing_nets))}", flush=True)
                
                # Extract pad centers and THT locations
                print(f"     Extracting pad centers and THT locations...", flush=True)
                from temper_placer.router_v6.astar_pathfinding import (
                    _extract_pad_centers_per_net,
                    _build_tht_pad_locations,
                )
                pad_centers_per_net = _extract_pad_centers_per_net(pcb)
                tht_locations = _build_tht_pad_locations(pcb)
                
                # Create NegotiatedRouter
                print(f"     Creating NegotiatedRouter...", flush=True)
                negotiated_router = NegotiatedRouter(
                    grids=stage2.occupancy_grids,
                    design_rules=pcb.design_rules,
                    max_iterations=5,  # Reduced for testing
                )
                
                # Route only the competing nets
                competing_nets_list = list(pathfinding_result.competing_nets)
                print(f"     Starting NegotiatedRouter.route() for {len(competing_nets_list)} nets...", flush=True)
                negotiated_paths = negotiated_router.route(
                    nets=competing_nets_list,
                    channel_mapping=channel_mapping,
                    pad_centers=pad_centers_per_net,
                    tht_locations=tht_locations,
                )
                print(f"     NegotiatedRouter.route() returned.", flush=True)
                
                # Merge negotiated results
                if negotiated_paths:
                    if self.verbose:
                        print(f"     ✓ NegotiatedRouter routed {len(negotiated_paths)}/{len(competing_nets_list)} competing nets")
                    
                    # Remove competing nets from failed list
                    for net_name in negotiated_paths.keys():
                        if net_name in pathfinding_result.failed_nets:
                            pathfinding_result.failed_nets.remove(net_name)
                        if net_name in pathfinding_result.failure_reports:
                            del pathfinding_result.failure_reports[net_name]
                    
                    # Add negotiated paths to result
                    pathfinding_result.routed_paths.update(negotiated_paths)

            # Merge Diff Pairs into result
            pathfinding_result.routed_paths.update(routed_paths_dp)

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

            # 2. Geometric Refinement (Hybrid)
            # Step A: Simplify (Decimate redundant nodes)
            if self.verbose:
                print("    Step A: Path Simplifier (H1)...")
            simplifier = PathSimplifier(
                sdf_grids=sdf_grids,
                step_size_mm=0.1,
                min_clearance_margin=0.0,
                occupancy_grids=stage2.occupancy_grids,
            )

            # Pre-calculate widths
            temp_widths = {}
            for net_name in pathfinding_result.routed_paths:
                rule = pcb.design_rules.get_rules_for_net(net_name)
                if hasattr(rule, "trace_width"):
                    temp_widths[net_name] = rule.trace_width
                elif hasattr(rule, "trace_width_mm"):
                    temp_widths[net_name] = rule.trace_width_mm
                else:
                    temp_widths[net_name] = pcb.design_rules.default_trace_width_mm

            simplified_paths = {}
            for net_name, path in pathfinding_result.routed_paths.items():
                net_width = temp_widths.get(net_name, pcb.design_rules.default_trace_width_mm)
                # Safety buffer for simplifier
                required_margin = (net_width / 2.0) + clearance_mm + 0.1
                net_id = pathfinding_result.net_ids.get(net_name, -1)

                opt_path = simplifier.simplify_path(
                    path, required_clearance_override=required_margin, net_id=net_id
                )
                simplified_paths[net_name] = opt_path

            # Step B: Snake Optimization (Nudge to fix aliasing/clearance)
            if self.verbose:
                print("    Step B: Variational Smoothing (Snakes)...")

            optimizer = SnakeOptimizer(
                sdf_grids=sdf_grids,
                alpha=0.2,
                beta=0.1,
                gamma=2.0,
                step_size=0.1,
                node_spacing_mm=0.5,  # Resample coarser for smoothness
                max_iterations=50,
            )

            final_paths = {}
            for net_name, path in simplified_paths.items():
                # Optimize
                opt_path = optimizer.optimize_path(path)
                final_paths[net_name] = opt_path

            pathfinding_result.routed_paths = final_paths

            if self.verbose:
                print(f"    Refined {len(final_paths)} paths")

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

        # 4.10: Generate Power Planes
        power_planes = []
        if self.verbose:
            print("  4.10: Generating Power Planes...")

        # Find GND net
        gnd_net_name = next((n.name for n in pcb.nets if "GND" in n.name.upper()), None)

        if gnd_net_name:
            if self.verbose:
                print(f"    Generating GND Plane for {gnd_net_name} on B.Cu...")

            # Determine bounds from components
            all_x = [c.initial_position[0] for c in pcb.components if c.initial_position]
            all_y = [c.initial_position[1] for c in pcb.components if c.initial_position]

            if all_x:
                # Add margin
                min_x, max_x = min(all_x) - 5, max(all_x) + 5
                min_y, max_y = min(all_y) - 5, max(all_y) + 5

                # Create zone dict
                power_planes.append(
                    {
                        "net_name": gnd_net_name,
                        "layer": "B.Cu",
                        "polygon_pts": [
                            (min_x, min_y),
                            (max_x, min_y),
                            (max_x, max_y),
                            (min_x, max_y),
                        ],
                    }
                )

        return Stage4Output(
            pathfinding_result=pathfinding_result,
            via_placement=via_placement,
            width_assignment=width_assignment,
            routing_results=routing_results,
            power_planes=power_planes,
        )
