"""Pipeline orchestrator for temper-placer.

This module provides the main orchestration logic for running the full
placement pipeline from inputs to outputs.

The orchestrator is now a thin adapter that delegates to the declarative
StageDAGEngine. The old phase handler methods remain with deprecation
warnings for backward compatibility.

Pipeline Stages (via DAG manifest):
    1. input - Load KiCad PCB, constraints, loops
    2. semantic - Extract loops, assign ownership
    3. topological - Reason about adjacency/separation
    4. preflight - Verify constraints are satisfiable
    5. geometric - JAX gradient descent optimization
    6. routing - Check placement is routable
    7. refinement - Iterate if routing fails
    8. output - Write placed PCB, reports
"""

import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PipelinePhase(Enum):
    """Enumeration of pipeline phases in execution order."""

    INPUT = "input"
    SEMANTIC = "semantic"
    TOPOLOGICAL = "topological"
    PREFLIGHT = "preflight"
    GEOMETRIC = "geometric"
    ROUTING = "routing"
    REFINEMENT = "refinement"
    OUTPUT = "output"
    # Deterministic sub-phases (BoundaryRegistry boundaries).
    ZONE_GEOMETRY = "zone_geometry"
    ZONE_ASSIGNMENT = "zone_assignment"
    SLOT_GENERATION = "slot_generation"
    COMPONENT_ASSIGNMENT = "component_assignment"
    APPLY_PLACEMENTS = "apply_placements"
    COURTYARD_CHECK = "courtyard_check"
    APPLY_PLACEMENTS_REAPPLY = "apply_placements_reapply"
    PLACEMENT_VALIDATION = "placement_validation"


class PipelineError(Exception):
    """Exception raised when a pipeline phase fails.

    Attributes:
        message: Human-readable error message
        phase: The phase where the error occurred (optional)
    """

    def __init__(self, message: str, phase: PipelinePhase | None = None):
        super().__init__(message)
        self.phase = phase


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution.

    Attributes:
        input_pcb: Path to input KiCad PCB file (required)
        constraints_yaml: Path to PCL constraints file (optional)
        loops_yaml: Path to loop definitions file (optional)
        output_pcb: Path for output placed PCB file (optional)
        output_report: Path for HTML report (optional)
        output_trace: Path for decision trace JSON (optional)
        skip_topological: Skip topological placement phase
        skip_routing: Skip routing verification phases
        skip_local_refinement: Skip gradient refinement phase
        dry_run: Stop after preflight check (fast feasibility check)
        epochs: Number of optimization epochs
        seed: Random seed for reproducibility
        max_movement_mm: Max movement radius for refinement
        max_iterations: Maximum refinement iterations
        routability_threshold: Threshold for triggering refinement
        convergence_threshold: Loss convergence threshold
        fab_preset: Manufacturing fab preset name
    """

    input_pcb: Path

    # Optional input files
    constraints_yaml: Path | None = None
    loops_yaml: Path | None = None

    # Optional output files
    output_pcb: Path | None = None
    output_report: Path | None = None
    output_trace: Path | None = None

    # Phase control
    skip_topological: bool = False
    skip_routing: bool = False
    skip_local_refinement: bool = False
    dry_run: bool = False

    # Optimization config
    epochs: int = 8000
    seed: int = 42
    max_movement_mm: float = 2.0

    # Iteration config
    max_iterations: int = 5
    routability_threshold: float = 0.85
    convergence_threshold: float = 0.01

    # Manufacturing
    fab_preset: str = "jlcpcb_standard"


@dataclass
class PipelineState:
    """State passed between pipeline phases.

    This object accumulates data as each phase processes it.
    It also tracks execution metadata like timing and success status.

    Attributes:
        config: Pipeline configuration
        current_phase: Currently executing phase
        iteration: Current refinement iteration (0 = first pass)
        success: Whether pipeline completed successfully
        failure_reason: Error message if failed
        failed_phase: Phase where failure occurred
        elapsed_time_s: Total elapsed time in seconds
        phase_timings: Time taken by each phase
        board: Board specification (populated by INPUT)
        netlist: Netlist data (populated by INPUT)
        loops: Loop definitions (populated by SEMANTIC)
        constraints: PCL constraints (populated by INPUT)
        deterministic_result: Results from Step 1-2
        placement_state: Current placement (populated by GEOMETRIC)
        routing_result: Routing verification result (populated by ROUTING)
        physics_report: Raw physical metrics
        decision_trace: Explainability trace (populated throughout)
    """

    config: PipelineConfig

    # Execution state
    current_phase: PipelinePhase = PipelinePhase.INPUT
    iteration: int = 0

    # Status
    success: bool = False
    failure_reason: str | None = None
    failed_phase: PipelinePhase | None = None

    # Timing
    elapsed_time_s: float = 0.0
    phase_timings: dict[PipelinePhase | str, float] = field(default_factory=dict)

    # Data populated by phases
    board: Any = None  # Board from core
    netlist: Any = None  # Netlist from core
    loops: list = field(default_factory=list)  # Loop definitions
    constraints: Any = None  # PCLConstraints
    deterministic_result: Any = None  # PlacementResult (NumPy)
    placement_state: Any = None  # PlacementState from optimizer
    routing_result: Any = None  # RoutingResult from routing
    physics_report: Any = None  # PhysicsReport
    preflight_report: Any = None  # PreflightReport
    decision_trace: Any = None  # DecisionTrace from explainability

    # Internal flags
    _refinement_complete: bool = False


class PipelineOrchestrator:
    """Orchestrates the full placement pipeline.

    Delegates to StageDAGEngine backed by a declarative YAML manifest.
    The old handler methods remain with DeprecationWarning for backward compat.
    """

    def __init__(self, config: PipelineConfig, manifest_path: Path | str | None = None):
        self.config = config
        self.state = PipelineState(config=config)

        if manifest_path is None:
            manifest_path = (
                Path(__file__).parent.parent.parent.parent
                / "configs"
                / "pipeline_default.yaml"
            )

        from temper_placer.pipeline.dag_engine import StageDAGEngine
        from temper_placer.pipeline.dag_observability import DAGToLegacyObserver

        self._engine = StageDAGEngine(manifest_path)
        self._dag_observer = DAGToLegacyObserver(self)
        self._engine.add_observer(self._dag_observer)

        self.phases: dict[PipelinePhase, Callable[[PipelineState], PipelineState]] = {
            PipelinePhase.INPUT: self._run_input,
            PipelinePhase.SEMANTIC: self._run_semantic,
            PipelinePhase.TOPOLOGICAL: self._run_topological,
            PipelinePhase.PREFLIGHT: self._run_preflight,
            PipelinePhase.GEOMETRIC: self._run_geometric,
            PipelinePhase.ROUTING: self._run_routing,
            PipelinePhase.REFINEMENT: self._run_refinement,
            PipelinePhase.OUTPUT: self._run_output,
        }

        self.on_phase_start: Callable[[PipelinePhase, PipelineState], None] | None = None
        self.on_phase_complete: Callable[[PipelinePhase, PipelineState], None] | None = None
        self.on_iteration: Callable[[int, PipelineState], None] | None = None

    def get_phase_order(self) -> list[PipelinePhase]:
        """Get the ordered list of phases to execute (from DAG manifest, config-filtered).

        NOTE: The hardcoded skip filter below duplicates the DAG engine's
        skip_if expression evaluation. These two code paths can produce
        different phase orders if a stage's skip_if in the manifest diverges
        from the boolean checks here. For the authoritative ordering, inspect
        StageDAGEngine.stage_order directly, which reflects the manifest's
        skip_if expressions evaluated at runtime.
        """
        phase_map = {p.value: p for p in PipelinePhase}
        all_phases = []
        for stage_name in self._engine.stage_order:
            if stage_name in phase_map:
                all_phases.append(phase_map[stage_name])

        phases = []
        for phase in all_phases:
            if phase == PipelinePhase.TOPOLOGICAL and self.config.skip_topological:
                continue
            if (
                phase in (PipelinePhase.ROUTING, PipelinePhase.REFINEMENT)
                and self.config.skip_routing
            ):
                continue
            if (
                phase == PipelinePhase.GEOMETRIC
                and self.config.skip_local_refinement
            ):
                continue
            if self.config.dry_run and phase in (
                PipelinePhase.GEOMETRIC,
                PipelinePhase.ROUTING,
                PipelinePhase.REFINEMENT,
                PipelinePhase.OUTPUT,
            ):
                continue
            phases.append(phase)
        return phases

    def run(self) -> PipelineState:
        """Execute the full pipeline via DAG engine."""
        return self._engine.run(self.state)

    def _save_snapshot(self, phase: PipelinePhase) -> None:
        """Save state snapshot (JSON + SVG)."""
        from temper_placer.io.snapshot import save_json_snapshot, save_svg_snapshot
        
        if self.config.output_pcb:
            snapshot_dir = self.config.output_pcb.parent / "snapshots"
        else:
            snapshot_dir = Path("snapshots")
            
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        phase_idx = self.get_phase_order().index(phase)
        prefix = f"{phase_idx:02d}_{phase.value}"
        if phase == PipelinePhase.REFINEMENT:
            prefix += f"_iter{self.state.iteration}"
            
        json_path = snapshot_dir / f"{prefix}.json"
        svg_path = snapshot_dir / f"{prefix}.svg"
        
        try:
            save_json_snapshot(self.state, json_path)
            save_svg_snapshot(self.state, svg_path)
        except Exception as e:
            print(f"Warning: Failed to save snapshot for {phase}: {e}")

    # ==========================================================================
    # Phase Handlers
    # ==========================================================================

    def _run_input(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Load input files (deprecated — use InputStage)."""
        warnings.warn("_run_input is deprecated. Use InputStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        
        print(f"Loading PCB from {state.config.input_pcb}")
        if not state.config.input_pcb.exists():
            raise PipelineError(f"Input PCB not found: {state.config.input_pcb}", phase=PipelinePhase.INPUT)

        try:
            result = parse_kicad_pcb(state.config.input_pcb)
        except Exception as e:
            raise PipelineError(f"Failed to parse PCB: {e}", phase=PipelinePhase.INPUT) from e

        state.board = result.board
        state.netlist = result.netlist

        # Load constraints
        from temper_placer.io.config_loader import (
            apply_fixed_components_to_netlist,
            apply_zones_to_netlist,
            create_board_from_constraints,
            load_constraints,
        )

        if state.config.constraints_yaml:
            print(f"Loading constraints from {state.config.constraints_yaml}")
            try:
                state.constraints = load_constraints(state.config.constraints_yaml)
                
                # Update board with zones from constraints
                # result.board might not have zones if it's a fresh KiCad file
                # create_board_from_constraints combines board geometry + constraints
                constrained_board = create_board_from_constraints(state.constraints)
                # Keep original width/height if result.board had them? 
                # Actually create_board_from_constraints uses values from YAML
                state.board = constrained_board
                
                # Apply assignments to netlist
                apply_fixed_components_to_netlist(state.netlist, state.constraints)
                apply_zones_to_netlist(state.netlist, state.constraints)
                
            except Exception as e:
                raise PipelineError(f"Failed to load constraints: {e}", phase=PipelinePhase.INPUT) from e
        else:
            class MockConstraints:
                constraints = []
            state.constraints = MockConstraints()

        # Load physical specification
        from temper_placer.core.specification import PcbSpecification
        from temper_placer.pipeline.derivation import derive_constraints_from_spec
        
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if spec_path.exists():
            print(f"Loading specification from {spec_path}")
            spec = PcbSpecification.load(spec_path)
            derived = derive_constraints_from_spec(spec, state.netlist)
            print(f"  Derived {len(derived)} physical constraints from spec.")

        return state

    def _run_semantic(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Extract semantic information (deprecated — use SemanticStage)."""
        warnings.warn("_run_semantic is deprecated. Use SemanticStage.", DeprecationWarning, stacklevel=2)
        return state

    def _run_topological(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Run topological placement phase (deprecated — use TopologicalStage)."""
        warnings.warn("_run_topological is deprecated. Use TopologicalStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.optimizer.legalization import legalize_zone_aware
        from temper_placer.placer.deterministic import PlacementResult
        from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic
        import numpy as np

        print("Running topological placement...")

        # 1. MCU Subsystem Template
        mcu_heuristic = MCUSubsystemHeuristic()
        # Try control_zone then MCU_ZONE
        try:
            mcu_result = mcu_heuristic.apply(state.netlist, state.board, zone_name="control_zone")
        except ValueError:
            try:
                mcu_result = mcu_heuristic.apply(state.netlist, state.board, zone_name="MCU_ZONE")
            except ValueError:
                # If neither found, just use default (likely fails or uses board center)
                mcu_result = mcu_heuristic.apply(state.netlist, state.board)
        
        positions = np.array(mcu_result.positions)
        rotations = np.array(mcu_result.rotations)

        # 2. Other positions
        for i, comp in enumerate(state.netlist.components):
            if comp.ref in mcu_result.placed_refs:
                continue
            if comp.initial_position:
                positions[i] = comp.initial_position
            else:
                if comp.zone:
                    zone = state.board.get_zone(comp.zone)
                    positions[i] = zone.center if zone else (state.board.width / 2, state.board.height / 2)
                else:
                    positions[i] = (state.board.width / 2, state.board.height / 2)
            if comp.initial_rotation is not None:
                rotations[i] = comp.initial_rotation * 90.0

        # 3. Zone-Aware Legalization
        print("Running zone-aware legalization...")
        fixed_mask = np.array([c.fixed for c in state.netlist.components], dtype=bool)
        legalized_pos, success = legalize_zone_aware(positions, state.netlist, state.board, fixed_mask=fixed_mask)
        
        if not success:
            print("Warning: Legalization could not fully resolve overlaps.")

        state.deterministic_result = PlacementResult(
            positions=legalized_pos, rotations=rotations,
            placed_refs=[c.ref for c in state.netlist.components], unplaced_refs=[],
        )
        return state

    def _run_preflight(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Run preflight feasibility checks (deprecated — use PreflightStage)."""
        warnings.warn("_run_preflight is deprecated. Use PreflightStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.pipeline.preflight import PreflightChecker
        print("Running preflight feasibility checks...")
        @dataclass
        class MockFabPreset:
            min_clearance: float = 0.2
        checker = PreflightChecker()
        report = checker.run(state.board, state.netlist, state.constraints, MockFabPreset())
        print(report.summary())
        if not report.passed:
            raise PipelineError(f"Preflight checks failed: {report.summary()}", phase=PipelinePhase.PREFLIGHT)
        return state

    def _run_geometric(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Run geometric optimization (deprecated — use GeometricStage)."""
        warnings.warn("_run_geometric is deprecated. Use GeometricStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.core.state import PlacementState
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.optimizer.legalization import project_to_trust_region, resolve_overlaps_priority
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.losses.channel_capacity import ChannelCapacityLoss
        import jax
        import jax.numpy as jnp
        import numpy as np
        import optax

        print("Initializing local refinement (Step 3)...")
        if state.deterministic_result is None:
             state = self._run_topological(state)
        
        anchor_positions = np.array(state.deterministic_result.positions)
        positions = anchor_positions.copy()
        n = state.netlist.n_components
        
        loss_fn = CompositeLoss([
            WeightedLoss(WirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=10.0),
            WeightedLoss(ChannelCapacityLoss(), weight=5.0),
        ])
        context = LossContext.from_netlist_and_board(state.netlist, state.board)
        
        print(f"Running refinement for {state.config.epochs} epochs (max {state.config.max_movement_mm}mm movement)...")
        optimizer = optax.adam(learning_rate=0.1)
        params = {"positions": jnp.array(positions)}
        opt_state = optimizer.init(params)
        
        @jax.jit
        def step(params, opt_state):
            def f(p):
                rotations = jnp.zeros((n, 4)).at[:, 0].set(1.0)
                return loss_fn(p["positions"], rotations, context).value
            loss, grads = jax.value_and_grad(f)(params)
            updates, opt_state = optimizer.update(grads, opt_state)
            params = optax.apply_updates(params, updates)
            return params, opt_state, loss

        for epoch in range(min(state.config.epochs, 500)):
            params, opt_state, _ = step(params, opt_state)
            if epoch % 10 == 0:
                pos_np = np.array(params["positions"])
                pos_np = project_to_trust_region(pos_np, anchor_positions, max_radius=state.config.max_movement_mm)
                from temper_placer.optimizer.legalization import clamp_to_bounds, clamp_to_zones
                pos_np = clamp_to_bounds(pos_np, np.array([c.bounds[0] for c in state.netlist.components]), 
                                         np.array([c.bounds[1] for c in state.netlist.components]), state.board)
                pos_np = clamp_to_zones(pos_np, state.netlist, state.board)
                params["positions"] = jnp.array(pos_np)

        final_pos = resolve_overlaps_priority(np.array(params["positions"]), state.netlist, state.board, min_separation=0.5, enforce_zones=True)
        state.placement_state = PlacementState.from_positions(jnp.array(final_pos))
        return state

    def _run_routing(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Run routing verification (deprecated — use RoutingStage)."""
        warnings.warn("_run_routing is deprecated. Use RoutingStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.routing.congestion import analyze_congestion
        import jax.numpy as jnp
        print("Running routing verification...")
        positions = state.placement_state.positions if state.placement_state else jnp.array(state.deterministic_result.positions)
        result = analyze_congestion(state.netlist, state.board, positions=positions)
        print(f"Max congestion: {result.max_utilization:.2f}, Total overflow: {result.total_overflow:.2f}")
        state.routing_result = result
        if not result.is_feasible():
            print("Warning: High congestion detected!")
        return state

    def _run_refinement(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Run placement-routing refinement loop (deprecated — use RefinementStage)."""
        warnings.warn("_run_refinement is deprecated. Use RefinementStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.pipeline.iterator import PlaceRouteIterator
        from temper_placer.router_v6.adapter import V6RouterAdapter
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        from temper_placer.optimizer.legalization import resolve_overlaps_priority
        from temper_placer.pipeline.iterative_placer import simple_congestion_repel
        import numpy as np
        import jax.numpy as jnp

        if state.routing_result is None:
            return state
            
        # Check if already feasible
        if state.routing_result.is_feasible(threshold=state.config.routability_threshold):
            state._refinement_complete = True
            return state

        print(f"Starting iterative refinement (max {state.config.max_iterations} iterations)...")

        # 1. Define Router wrapper for iterator
        class OrchestratorRouter:
            def __init__(self, state):
                self.state = state
            def route(self, pos):
                # Use MazeRouter for refinement routing
                # Use 0.5mm grid for reasonable performance during refinement
                router = MazeRouter.from_board(self.state.board, cell_size_mm=0.5, num_layers=2)
                router.block_board_features(self.state.board)
                router.block_components(self.state.netlist.components, pos, margin=-0.1, escape_length=5)
                
                # Simple routing for all nets
                success_count = 0
                for net in self.state.netlist.nets:
                    from temper_placer.routing.congestion import _get_pin_positions
                    pins = _get_pin_positions(self.state.netlist, net.name, pos)
                    if len(pins) < 2: continue
                    res = router.route_net_adaptive(net.name, pins, None) # Simplification
                    if res.success: success_count += 1
                
                completion = success_count / len(self.state.netlist.nets)
                
                class Result:
                    def __init__(self, c, r):
                        self.completion_rate = c
                        self.router = r
                        self.is_feasible = lambda: c >= 1.0
                return Result(completion, router)

        # 2. Define placement update function
        def update_fn(pos, routing_res):
            print("    Refining placement using JAX optimization with routing feedback loss...")
            from temper_placer.pipeline.feedback import RoutingFeedbackLoss
            from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
            from temper_placer.losses.wirelength import WirelengthLoss
            from temper_placer.losses.overlap import OverlapLoss
            from temper_placer.losses.channel_capacity import ChannelCapacityLoss
            import optax
            import jax
            
            heatmap = CongestionHeatmap.from_router(routing_res.router)
            
            # Combine original losses with the new routing feedback loss
            loss_fn = CompositeLoss([
                WeightedLoss(WirelengthLoss(), weight=1.0),
                WeightedLoss(OverlapLoss(), weight=50.0),
                WeightedLoss(ChannelCapacityLoss(), weight=20.0),
                WeightedLoss(RoutingFeedbackLoss(heatmap), weight=100.0), # Strong repulsion from congestion
            ])
            
            context = LossContext.from_netlist_and_board(state.netlist, state.board)
            n = state.netlist.n_components
            
            # Run a mini-optimization loop (Step 3 style)
            optimizer = optax.adam(learning_rate=0.05)
            params = {"positions": jnp.array(pos)}
            opt_state = optimizer.init(params)
            
            @jax.jit
            def step(params, opt_state):
                def f(p):
                    rotations = jnp.zeros((n, 4)).at[:, 0].set(1.0)
                    return loss_fn(p["positions"], rotations, context).value
                loss, grads = jax.value_and_grad(f)(params)
                updates, opt_state = optimizer.update(grads, opt_state)
                params = optax.apply_updates(params, updates)
                return params, opt_state, loss

            # Fewer epochs for iterative refinement
            for epoch in range(200):
                params, opt_state, _ = step(params, opt_state)
                if epoch % 50 == 0:
                    # Occasional boundary clamping
                    from temper_placer.optimizer.legalization import clamp_to_bounds
                    pos_np = np.array(params["positions"])
                    pos_np = clamp_to_bounds(pos_np, np.array([c.bounds[0] for c in state.netlist.components]), 
                                             np.array([c.bounds[1] for c in state.netlist.components]), state.board)
                    params["positions"] = jnp.array(pos_np)

            # Final legalization
            legalized = resolve_overlaps_priority(np.array(params["positions"]), state.netlist, state.board, min_separation=1.0)
            return jnp.array(legalized)

        # 3. Run iterator
        iterator = PlaceRouteIterator(
            netlist=state.netlist,
            board=state.board,
            router=OrchestratorRouter(state),
            placement_update_fn=update_fn,
            max_iterations=state.config.max_iterations,
            target_completion=state.config.routability_threshold,
            min_improvement=state.config.convergence_threshold
        )

        current_pos = state.placement_state.positions if state.placement_state else jnp.array(state.deterministic_result.positions)
        result = iterator.run(current_pos)
        
        # 4. Update state with best result
        from temper_placer.core.state import PlacementState
        state.placement_state = PlacementState.from_positions(result.final_positions)
        state.iteration = result.iterations
        state._refinement_complete = True
        
        print(f"Refinement complete. Best completion: {result.iteration_history[-1].completion_rate:.2%}")
        
        return state

    def _run_output(self, state: PipelineState) -> PipelineState:  # pragma: no cover
        """Generate output files (deprecated — use OutputStage)."""
        warnings.warn("_run_output is deprecated. Use OutputStage.", DeprecationWarning, stacklevel=2)
        from temper_placer.io.kicad_writer import export_placements, add_bounding_boxes_to_pcb, add_silkscreen_labels
        self._compute_physics_metrics()
        if not state.config.output_pcb:
            print("No output path specified.")
            return state
        print(f"Exporting placed PCB to {state.config.output_pcb}...")
        ps = state.placement_state or PlacementState.from_positions(jnp.array(state.deterministic_result.positions))
        try:
            write_result = export_placements(state.config.input_pcb, state.config.output_pcb, ps, 
                                             [c.ref for c in state.netlist.components], state.board.origin)
            print(f"  Updated: {write_result.components_updated} components")
            add_bounding_boxes_to_pcb(state.config.output_pcb)
            add_silkscreen_labels(state.config.output_pcb)
            metrics_path = state.config.output_pcb.with_suffix(".metrics.json")
            import json
            with open(metrics_path, "w") as f:
                json.dump(state.physics_report.to_dict(), f, indent=2)
            print(f"  Metrics saved to {metrics_path.name}")
        except Exception as e:
            print(f"Error during export: {e}")
        return state

    def _compute_physics_metrics(self) -> None:
        """Compute physical metrics."""
        from temper_placer.metrics.physics import measure_emi, measure_geometric, measure_routability, measure_thermal, PhysicsReport
        state = self.state
        if state.placement_state is None and state.deterministic_result is None:
            return
        ps = state.placement_state or PlacementState.from_positions(jnp.array(state.deterministic_result.positions))
        geo = measure_geometric(ps, state.netlist, state.board)
        loop_refs = [["Q1", "Q2", "C_BUS1"], ["U_MCU", "C_MCU_1"]]
        emi = measure_emi(ps, state.netlist, loop_refs=loop_refs)
        power = {"Q1": 15.0, "Q2": 15.0, "U_BUCK": 2.0}
        thermal = measure_thermal(ps, state.netlist, state.board, power_dissipation=power)
        routability = measure_routability(ps, state.netlist, state.board)
        state.physics_report = PhysicsReport(geometric=geo, emi=emi, thermal=thermal, routability=routability)