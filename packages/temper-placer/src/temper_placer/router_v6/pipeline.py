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
from typing import TYPE_CHECKING

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.astar_pathfinding import PathfindingResult, run_astar_pathfinding
from temper_placer.router_v6.bottleneck_analysis import BottleneckAnalysis
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_mapping import map_topology_to_channels
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import ConstraintModel, ModelBuilder
from temper_placer.router_v6.dense_package_detection import identify_dense_packages
from temper_placer.router_v6.escape_via_generator import EscapeVia, generate_escape_vias
from temper_placer.router_v6.layer_capacity import LayerCapacity
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.routing.geometry_fields.sdf_builder import SDFGrid
from temper_placer.routing.variational_router.snake_optimizer import SnakeOptimizer
from temper_placer.routing.exact_geometry.path_simplifier import PathSimplifier
from temper_placer.placement.legalization import Legalizer
from temper_placer.router_v6.routing_demand import RoutingDemand
from temper_placer.router_v6.routing_results import RoutingResults, compile_routing_results
from temper_placer.router_v6.routing_space import PLANE_NETS, RoutingSpace
from temper_placer.router_v6.sat_model import SATModel, build_sat_model
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.topology_extraction import TopologyGraph, extract_topology_solution
from temper_placer.router_v6.topology_solver import TopologicalSolution, solve_topology
from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment, assign_trace_widths
from temper_placer.router_v6.via_placement import ViaPlacement, place_vias

if TYPE_CHECKING:
    from temper_drc.core.fence import DRCFence


@dataclass
class Stage2Output:
    """Output from Stage 2: Channel Analysis."""

    obstacle_maps: dict[str, any]
    routing_spaces: dict[str, RoutingSpace]
    skeletons: dict[str, ChannelSkeleton]
    channel_widths: dict[str, ChannelWidths]
    occupancy_grids: dict[str, OccupancyGrid]
    layer_capacities: dict[str, LayerCapacity]
    routing_demand: RoutingDemand
    bottleneck_analysis: BottleneckAnalysis

    def to_snapshot_dict(self) -> dict[str, any]:
        return {
            "obstacle_maps": self.obstacle_maps,
            "routing_spaces": self.routing_spaces,
            "skeletons": self.skeletons,
            "channel_widths": self.channel_widths,
            "occupancy_grids": self.occupancy_grids,
            "layer_capacities": self.layer_capacities,
            "routing_demand": self.routing_demand,
            "bottleneck_analysis": self.bottleneck_analysis,
        }


@dataclass
class Stage3Output:
    """Output from Stage 3: Topological Routing."""

    constraint_model: ConstraintModel
    sat_model: SATModel
    solution: TopologicalSolution
    topology_graph: TopologyGraph

    def to_snapshot_dict(self) -> dict[str, any]:
        return {
            "constraint_model": self.constraint_model,
            "sat_model": self.sat_model,
            "solution": self.solution,
            "topology_graph": self.topology_graph,
        }


@dataclass
class Stage4Output:
    """Output from Stage 4: Geometric Realization."""

    pathfinding_result: PathfindingResult
    via_placement: ViaPlacement
    width_assignment: TraceWidthAssignment
    routing_results: RoutingResults

    def to_snapshot_dict(self) -> dict[str, any]:
        return {
            "via_placement": self.via_placement,
            "width_assignment": self.width_assignment,
            "pathfinding_result": self.pathfinding_result,
            "routing_results": self.routing_results,
        }


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


def _parsed_pcb_to_drc_input(
    pcb: ParsedPCB,
) -> tuple:
    """Convert ParsedPCB to temper_drc Placement and ConstraintSet.

    Bridges the RouterV6 pipeline's ParsedPCB representation to the
    DRC check input format. Extracts component positions, net assignments,
    and board dimensions.

    Initial implementation handles component overlap and clearance checks;
    expanded as additional checks require more data fields.
    """
    from temper_drc.input.placement import Placement as DRCPlacement, ComponentPlacement as DRCCompPlacement
    from temper_drc.input.constraints import ConstraintSet, ClearanceRule

    board_width = pcb.board.width
    board_height = pcb.board.height

    components = {}
    for comp in pcb.components:
        if hasattr(comp, 'initial_position') and comp.initial_position:
            x, y = comp.initial_position
        else:
            x, y = 0.0, 0.0

        side = getattr(comp, 'initial_side', 0)
        layer = "F.Cu" if side == 0 else "B.Cu"

        components[comp.ref] = DRCCompPlacement(
            ref=comp.ref,
            footprint=comp.footprint,
            x=float(x),
            y=float(y),
            rotation=float(getattr(comp, 'initial_rotation', 0) or 0),
            layer=layer,
            width=comp.width,
            height=comp.height,
            net_class=comp.net_class,
        )

    nets = {}
    for net in pcb.nets:
        if hasattr(net, 'pins'):
            nets[net.name] = [pin[0] for pin in net.pins]

    zones = {}
    for zone in pcb.zones:
        if hasattr(zone, 'name') and hasattr(zone, 'bounds'):
            zones[zone.name] = zone.bounds

    placement = DRCPlacement(
        components=components,
        nets=nets,
        zones=zones,
        board_width=board_width,
        board_height=board_height,
    )

    default_clearance = getattr(pcb.design_rules, 'default_clearance_mm', 0.3)
    constraints = ConstraintSet(
        clearances=[ClearanceRule(from_class="*", to_class="*", min_mm=default_clearance)],
        board_width=board_width,
        board_height=board_height,
    )

    return placement, constraints


class RouterV6Pipeline:
    """Router V6 end-to-end pipeline."""

    def __init__(
        self,
        verbose: bool = False,
        enable_theta_star: bool = False,
        enable_lazy_theta_star: bool = False,
        enable_smoothing: bool = False,
        enable_legalization: bool = True,
        max_nets: int | None = None,
        target_nets: list[str] | None = None,
        fence: DRCFence | None = None,
        profiler: object | None = None,
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
            fence: Optional DRCFence for per-stage DRC verification
            profiler: Optional PipelineProfiler for stage timing instrumentation
        """
        self.verbose = verbose
        self.enable_theta_star = enable_theta_star
        self.enable_lazy_theta_star = enable_lazy_theta_star
        self.enable_smoothing = enable_smoothing
        self.enable_legalization = enable_legalization
        self.max_nets = max_nets
        self.target_nets = target_nets
        self.fence = fence
        self.profiler = profiler

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

        # Stage 0.5 Fence: Check component overlap after legalization
        if self.fence:
            self._run_fence(
                stage_name="router_v6.legalization",
                invariants=_stage_0_5_invariants(),
                pcb=pcb,
            )

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

        # NOTE: No Stage 1 fence. The temper_drc Placement model only
        # carries component-level data (no via positions or trace geometry).
        # The drc_clearance and drc_component_overlap checks operate on
        # component pairs only; a fence check at this stage would be a no-op.
        # Revisit when the DRC input model supports via/trace primitives.

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

        # NOTE: No Stage 4 fence. Same reason as Stage 1 -- the DRC input
        # model cannot represent routed traces or vias, so clearance and
        # overlap checks on geometric realization output would be no-ops.
        # Revisit when the DRC input model supports trace/via primitives.

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
        """Run Stage 2: Channel Analysis (delegated to Stage2Orchestrator)."""
        from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator

        if self.verbose:
            print("Stage 2 (Orchestrated): Channel analysis...")

        _p = self.profiler
        if _p:
            with _p.stage("stage2"):
                orchestrator = Stage2Orchestrator(verbose=self.verbose)
                state = orchestrator.run(pcb, escape_vias)
                stage2 = Stage2Orchestrator.assemble_stage2_output(state)
        else:
            orchestrator = Stage2Orchestrator(verbose=self.verbose)
            state = orchestrator.run(pcb, escape_vias)
            stage2 = Stage2Orchestrator.assemble_stage2_output(state)

        if self.verbose and stage2.bottleneck_analysis.has_critical_bottlenecks:
            print(f"    Warning: {len(stage2.bottleneck_analysis.bottlenecks)} bottlenecks identified")

        return stage2

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

        # Map all nets with layer assignment
        channel_mapping = map_topology_to_channels(
            stage3.topology_graph,
            fcu_skeleton,  # Use F.Cu skeleton for mapping (waypoints are generic)
            nets=pcb.nets,
            components=pcb.components,
        )

        # Fallback: nets without SAT channel assignment get direct A* attempt
        from temper_placer.router_v6.channel_mapping import ChannelPath
        routed_nets = {cp.net_name for cp in channel_mapping.channel_paths.values()}
        for net in pcb.nets:
            if net.name not in routed_nets and len(net.pads) >= 2:
                start = net.pads[0].position
                end = net.pads[-1].position
                fallback_cp = ChannelPath(
                    net_name=net.name,
                    channel_sequence=[],
                    waypoints=[start, end],
                    total_length=0.0,
                    preferred_layer="F.Cu",
                )
                channel_mapping.channel_paths[net.name] = fallback_cp

        # 4.2: Run A* pathfinding (orchestrated via Stage 4 micro-stages)
        if self.verbose:
            print("  4.2: Running A* pathfinding (orchestrated)...")

        from temper_placer.router_v6.stage4_orchestrator import Stage4Orchestrator

        orchestrated = Stage4Orchestrator(verbose=self.verbose)
        state = BoardState(
            _parsed_pcb=pcb,
            channel_mapping=channel_mapping,
            escape_vias_map=escape_vias_map,
            enable_theta_star=self.enable_theta_star,
            enable_lazy_theta_star=self.enable_lazy_theta_star,
        )
        state = orchestrated.run(initial_state=state)
        pathfinding_result = orchestrated.assemble_pathfinding_result(state)

        if pathfinding_result is None:
            from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding

            fcu_grid = stage2.occupancy_grids.get("F.Cu")
            bcu_grid = stage2.occupancy_grids.get("B.Cu")
            if not fcu_grid:
                fcu_grid = list(stage2.occupancy_grids.values())[0]
            if not bcu_grid and len(stage2.occupancy_grids) > 1:
                bcu_grid = [g for g in stage2.occupancy_grids.values() if g != fcu_grid][0]

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

        pathfinding_result = self._run_stage5(pcb, stage2, pathfinding_result)

        return pathfinding_result

    def _run_stage5(
        self,
        pcb: ParsedPCB,
        stage2: Stage2Output,
        pathfinding_result: PathfindingResult,
    ) -> Stage4Output:
        """Run Stage 5: Post-processing (smoothing, via placement, width, results)."""
        if self.verbose:
            print("Stage 5: Post-processing...")

        # 4.2.5: Smoothing
        pathfinding_result = self._apply_smoothing(pcb, stage2, pathfinding_result)

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

        # 4.9: Compile results
        if self.verbose:
            print("  4.9: Compiling routing results...")
        plane_net_names = [
            net.name for net in pcb.nets
            if net.name.upper() in {n.upper() for n in PLANE_NETS}
        ]
        routing_results = compile_routing_results(
            pathfinding_result,
            width_assignment,
            via_placement,
            length_matching=None,
            plane_net_names=plane_net_names,
        )

        return Stage4Output(
            pathfinding_result=pathfinding_result,
            via_placement=via_placement,
            width_assignment=width_assignment,
            routing_results=routing_results,
        )

    def _apply_smoothing(
        self,
        pcb: ParsedPCB,
        stage2: Stage2Output,
        pathfinding_result: PathfindingResult,
    ) -> PathfindingResult:
        """Apply optional force-directed smoothing to routed paths."""
        if not self.enable_smoothing:
            return pathfinding_result

        if self.verbose:
            print("  4.2.5: Applying Variational Smoothing (Snakes)...")

        sdf_grids = {}
        clearance_mm = pcb.design_rules.default_clearance_mm

        if hasattr(pcb, "board") and pcb.board:
            bounds_array = pcb.board.get_bounds_array()
            bounds = tuple(bounds_array)
        else:
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

        bounds = (bounds[0] - 1, bounds[1] - 1, bounds[2] + 1, bounds[3] + 1)

        for layer_name, routing_space in stage2.routing_spaces.items():
            if self.verbose:
                print(f"    Building Exact SDF for {layer_name}...")

            obstacles = routing_space.obstacles
            if not obstacles:
                polygon_list = []
            elif hasattr(obstacles, "geoms"):
                polygon_list = list(obstacles.geoms)
            else:
                polygon_list = [obstacles]

            sdf_grids[layer_name] = SDFGrid.from_polygons(
                polygons=polygon_list, bounds=bounds, resolution_mm=0.05
            )

        simplifier = PathSimplifier(
            sdf_grids=sdf_grids,
            step_size_mm=0.1,
            min_clearance_margin=0.0,
            occupancy_grids=stage2.occupancy_grids,
        )

        temp_widths = {}
        for net_name in pathfinding_result.routed_paths:
            rule = pcb.design_rules.get_rules_for_net(net_name)
            if hasattr(rule, "trace_width"):
                temp_widths[net_name] = rule.trace_width
            elif hasattr(rule, "trace_width_mm"):
                temp_widths[net_name] = rule.trace_width_mm
            else:
                temp_widths[net_name] = pcb.design_rules.default_trace_width_mm

        smoothed_paths = {}
        for net_name, path in pathfinding_result.routed_paths.items():
            net_width = temp_widths.get(net_name, pcb.design_rules.default_trace_width_mm)
            required_margin = (net_width / 2.0) + clearance_mm + 0.05
            net_id = pathfinding_result.net_ids.get(net_name, -1)
            opt_path = simplifier.simplify_path(
                path, required_clearance_override=required_margin, net_id=net_id
            )
            smoothed_paths[net_name] = opt_path

        pathfinding_result.routed_paths = smoothed_paths

        if self.verbose:
            print(f"    Smoothed {len(smoothed_paths)} paths")

        return pathfinding_result

    def _run_fence(
        self,
        *,
        stage_name: str,
        invariants: tuple,
        pcb: ParsedPCB,
    ):
        """Run fence checks for a Router V6 stage.

        Creates DRC inputs from the PCB data and invokes the fence.

        NOTE: Currently only Stage 0.5 (legalization) is fenced.
        The temper_drc Placement model only carries component-level data
        (positions, nets, zones).  Stage 1 (escape vias) and Stage 4
        (routed traces) produce geometry that the DRC input model cannot
        represent yet, so those stages are not fenced.
        """
        placement, constraints = _parsed_pcb_to_drc_input(pcb)
        self.fence.check(
            stage_name=stage_name,
            invariants=invariants,
            placement=placement,
            constraints=constraints,
        )


def _stage_0_5_invariants() -> tuple:
    """Invariants for Stage 0.5 legalization."""
    from temper_drc.core.fence import InvariantSpec
    return (
        InvariantSpec("drc_component_overlap", "No component overlaps after legalization"),
    )

