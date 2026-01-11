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

    def __init__(self, verbose: bool = False):
        """
        Initialize Router V6 pipeline.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

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

        # Validate placement
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
            vias = generate_escape_vias(dense_pkg, pcb.design_rules)
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
        stage4 = self._run_stage4(pcb, stage2, stage3)

        runtime = time.time() - start_time

        if self.verbose:
            print(f"\nRouter V6 complete in {runtime:.1f}s")
            print(f"  Routed: {stage4.routing_results.success_count} nets")
            print(f"  Failed: {stage4.routing_results.failure_count} nets")
            print(f"  Completion: {100 * stage4.routing_results.success_count / max(1, stage4.routing_results.success_count + stage4.routing_results.failure_count):.1f}%")

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
            skeleton = extract_channel_skeleton(routing_space)
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
        occupancy_grids = {}
        for layer_name, routing_space in routing_spaces.items():
            grid = build_occupancy_grid(routing_space)
            occupancy_grids[layer_name] = grid

        # 2.6: Calculate per-layer capacity
        if self.verbose:
            print("  2.6: Calculating layer capacity...")
        layer_capacities = {}
        for layer_name in occupancy_grids.keys():
            capacity = calculate_layer_capacity(
                occupancy_grids[layer_name],
                channel_widths[layer_name],
                pcb.design_rules.default_trace_width_mm,
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
            print(f"    SAT model: {sat_model.variable_count} vars, {sat_model.clause_count} clauses")

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
    ) -> Stage4Output:
        """Run Stage 4: Geometric Realization."""

        # 4.1: Setup channel mapping (from topology solution)
        if self.verbose:
            print("  4.1: Setting up channel mapping...")
        # Map topology graph to concrete channels
        # Use first layer skeleton for mapping (simplified)
        first_skeleton = list(stage2.skeletons.values())[0]
        channel_mapping = map_topology_to_channels(
            stage3.topology_graph,
            first_skeleton,
        )

        # 4.2: Run A* pathfinding
        if self.verbose:
            print("  4.2: Running A* pathfinding...")
        # Use first layer's grid for pathfinding
        first_layer = list(stage2.occupancy_grids.values())[0]
        pathfinding_result = run_astar_pathfinding(channel_mapping, first_layer)

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
            pcb.design_rules,
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
