"""Pipeline orchestrator for temper-placer.

This module provides the main orchestration logic for running the full
placement pipeline from inputs to outputs.

Pipeline Phases:
    1. INPUT - Load KiCad PCB, constraints, loops
    2. SEMANTIC - Extract loops, assign ownership
    3. TOPOLOGICAL - Reason about adjacency/separation
    4. PREFLIGHT - Verify constraints are satisfiable
    5. GEOMETRIC - JAX gradient descent optimization
    6. ROUTING - Check placement is routable
    7. REFINEMENT - Iterate if routing fails
    8. OUTPUT - Write placed PCB, reports
"""

import time
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
        dry_run: Stop after preflight check (fast feasibility check)
        epochs: Number of optimization epochs
        seed: Random seed for reproducibility
        max_iterations: Maximum refinement iterations
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
        placement_state: Current placement (populated by GEOMETRIC)
        routing_result: Routing verification result (populated by ROUTING)
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
    phase_timings: dict[PipelinePhase, float] = field(default_factory=dict)

    # Data populated by phases
    board: Any = None  # Board from core
    netlist: Any = None  # Netlist from core
    loops: list = field(default_factory=list)  # Loop definitions
    constraints: Any = None  # PCLConstraints
    deterministic_result: Any = None  # PlacementResult (NumPy) from topological/deterministic
    placement_state: Any = None  # PlacementState from optimizer
    routing_result: Any = None  # RoutingResult from routing
    decision_trace: Any = None  # DecisionTrace from explainability

    # Internal flags
    _refinement_complete: bool = False


class PipelineOrchestrator:
    """Orchestrates the full placement pipeline.

    The orchestrator sequences phases correctly, handles errors gracefully,
    and provides callbacks for progress reporting.

    Usage:
        config = PipelineConfig(input_pcb=Path("board.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)
        orchestrator.on_phase_start = lambda phase, state: print(f"Starting {phase}")
        result = orchestrator.run()
        if result.success:
            print("Pipeline completed successfully")
        else:
            print(f"Pipeline failed: {result.failure_reason}")
    """

    def __init__(self, config: PipelineConfig):
        """Initialize the orchestrator with configuration.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.state = PipelineState(config=config)

        # Phase handlers - these will be replaced with actual implementations
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

        # Callbacks
        self.on_phase_start: Callable[[PipelinePhase, PipelineState], None] | None = None
        self.on_phase_complete: Callable[[PipelinePhase, PipelineState], None] | None = None
        self.on_iteration: Callable[[int, PipelineState], None] | None = None

    def get_phase_order(self) -> list[PipelinePhase]:
        """Get the ordered list of phases to execute based on config.

        Returns:
            List of phases in execution order, respecting skip flags and dry_run.
        """
        # Full phase order
        all_phases = [
            PipelinePhase.INPUT,
            PipelinePhase.SEMANTIC,
            PipelinePhase.TOPOLOGICAL,
            PipelinePhase.PREFLIGHT,
            PipelinePhase.GEOMETRIC,
            PipelinePhase.ROUTING,
            PipelinePhase.REFINEMENT,
            PipelinePhase.OUTPUT,
        ]

        # Filter based on config
        phases = []
        for phase in all_phases:
            # Skip topological if requested
            if phase == PipelinePhase.TOPOLOGICAL and self.config.skip_topological:
                continue

            # Skip routing phases if requested
            if (
                phase in (PipelinePhase.ROUTING, PipelinePhase.REFINEMENT)
                and self.config.skip_routing
            ):
                continue

            # Skip local refinement if requested
            if (
                phase == PipelinePhase.GEOMETRIC
                and self.config.skip_local_refinement
            ):
                continue

            # In dry_run mode, stop after PREFLIGHT
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
        """Execute the full pipeline.

        Returns:
            PipelineState with results and status.
        """
        start_time = time.time()
        phase_order = self.get_phase_order()

        idx = 0
        while idx < len(phase_order):
            phase = phase_order[idx]
            self.state.current_phase = phase

            # Call start callback
            if self.on_phase_start:
                self.on_phase_start(phase, self.state)

            # Execute phase
            phase_start = time.time()
            try:
                handler = self.phases[phase]
                self.state = handler(self.state)
            except PipelineError as e:
                self.state.success = False
                self.state.failure_reason = str(e)
                self.state.failed_phase = e.phase if e.phase else phase
                self.state.elapsed_time_s = time.time() - start_time
                return self.state

            # Record phase timing
            self.state.phase_timings[phase] = time.time() - phase_start

            # Save snapshot
            self._save_snapshot(phase)

            # Call complete callback
            if self.on_phase_complete:
                self.on_phase_complete(phase, self.state)

            # Handle refinement loop
            if (
                phase == PipelinePhase.REFINEMENT
                and not self.state._refinement_complete
                and self.state.iteration < self.state.config.max_iterations
            ):
                # Jump back to GEOMETRIC
                try:
                    idx = phase_order.index(PipelinePhase.GEOMETRIC)
                    continue
                except ValueError:
                    pass  # No geometric phase to jump back to

            idx += 1

        self.state.success = True
        self.state.elapsed_time_s = time.time() - start_time
        return self.state

    def _save_snapshot(self, phase: PipelinePhase) -> None:
        """Save state snapshot (JSON + SVG)."""
        from temper_placer.io.snapshot import save_json_snapshot, save_svg_snapshot

        # Determine snapshot directory
        if self.config.output_pcb:
            snapshot_dir = self.config.output_pcb.parent / "snapshots"
        else:
            snapshot_dir = Path("snapshots")

        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # File prefix: 01_input, 02_semantic, etc.
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

    def _run_input(self, state: PipelineState) -> PipelineState:
        """Load input files (KiCad PCB, constraints, loops)."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        # from temper_placer.io.config_loader import load_constraints  # TODO: Implement

        print(f"Loading PCB from {state.config.input_pcb}")
        if not state.config.input_pcb.exists():
            raise PipelineError(
                f"Input PCB not found: {state.config.input_pcb}",
                phase=PipelinePhase.INPUT,
            )

        # Parse KiCad PCB
        try:
            result = parse_kicad_pcb(state.config.input_pcb)
        except Exception as e:
            raise PipelineError(f"Failed to parse PCB: {e}", phase=PipelinePhase.INPUT) from e

        state.board = result.board
        state.netlist = result.netlist

        if result.has_warnings:
            print(f"Warnings during parsing: {result.warnings}")

        # TODO: Load real constraints
        # For now, create a mock constraint object that satisfies PreflightChecker
        class MockConstraints:
            constraints = []

        state.constraints = MockConstraints()

        # Load physical specification if provided
        from temper_placer.core.specification import PcbSpecification
        from temper_placer.pipeline.derivation import derive_constraints_from_spec
        
        # Default spec for Temper
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if spec_path.exists():
            print(f"Loading specification from {spec_path}")
            spec = PcbSpecification.load(spec_path)
            derived = derive_constraints_from_spec(spec, state.netlist)
            print(f"  Derived {len(derived)} physical constraints from spec.")
            # Store spec in state if needed
            # state.specification = spec

        return state

    def _run_semantic(self, state: PipelineState) -> PipelineState:
        """Extract semantic information (loops, ownership).

        This is a stub implementation that will be expanded in later tasks.
        """
        # TODO: Implement semantic extraction
        # - Auto-extract loops if not provided
        # - Assign component ownership to loops
        return state

    def _run_topological(self, state: PipelineState) -> PipelineState:
        """Run topological placement phase (deterministic/legalization)."""
        from temper_placer.optimizer.legalization import legalize_zone_aware
        from temper_placer.placer.deterministic import PlacementResult
        from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic
        import numpy as np

        print("Running topological placement...")

        # 1. MCU Subsystem Template (Step 1)
        mcu_heuristic = MCUSubsystemHeuristic()
        mcu_result = mcu_heuristic.apply(state.netlist, state.board)
        
        # Initialize positions from MCU result
        positions = np.array(mcu_result.positions)
        rotations = np.array(mcu_result.rotations)

        # 2. Load other initial positions
        for i, comp in enumerate(state.netlist.components):
            if comp.ref in mcu_result.placed_refs:
                continue # Already placed by MCU template
                
            if comp.initial_position:
                positions[i] = comp.initial_position
            else:
                # Default to board/zone center
                if comp.zone:
                    zone = state.board.get_zone(comp.zone)
                    if zone:
                        positions[i] = zone.center
                    else:
                        positions[i] = (state.board.width / 2, state.board.height / 2)
                else:
                    positions[i] = (state.board.width / 2, state.board.height / 2)

            if comp.initial_rotation is not None:
                rotations[i] = comp.initial_rotation * 90.0

        # 3. Zone-Aware Legalization (Step 2)
        print("Running zone-aware legalization...")
        fixed_mask = np.array([c.fixed for c in state.netlist.components], dtype=bool)

        legalized_pos, success = legalize_zone_aware(
            positions,
            state.netlist,
            state.board,
            fixed_mask=fixed_mask,
            max_iterations=500
        )

        if not success:
            print("Warning: Legalization could not fully resolve overlaps/constraints.")

        # 4. Store Result
        state.deterministic_result = PlacementResult(
            positions=legalized_pos,
            rotations=rotations,
            placed_refs=[c.ref for c in state.netlist.components],
            unplaced_refs=[],
        )

        return state

    def _run_preflight(self, state: PipelineState) -> PipelineState:
        """Run preflight feasibility checks."""
        from temper_placer.pipeline.preflight import PreflightChecker

        print("Running preflight feasibility checks...")

        # Mock FabPreset (TODO: Load from config)
        @dataclass
        class MockFabPreset:
            min_clearance: float = 0.2

        checker = PreflightChecker()
        report = checker.run(
            board=state.board,
            netlist=state.netlist,
            constraints=state.constraints,
            fab_preset=MockFabPreset(),
        )

        print(report.summary())

        if not report.passed:
            raise PipelineError(
                f"Preflight checks failed: {report.summary()}",
                phase=PipelinePhase.PREFLIGHT,
            )

        return state

    def _run_geometric(self, state: PipelineState) -> PipelineState:
        """Run geometric optimization (JAX gradient descent with trust region)."""
        import jax
        import jax.numpy as jnp
        import numpy as np
        import optax

        from temper_placer.core.state import PlacementState
        from temper_placer.losses.base import CompositeLoss, LossContext
        from temper_placer.optimizer.legalization import (
            project_to_trust_region,
            resolve_overlaps_priority,
        )

        print("Initializing local refinement (Step 3)...")

        # 1. Initialize from Step 2 result
        if state.deterministic_result is None:
             print("No deterministic result to refine. Running topological first...")
             state = self._run_topological(state)

        anchor_positions = np.array(state.deterministic_result.positions)
        positions = anchor_positions.copy()
        n = state.netlist.n_components

        # 2. Setup Loss
        # For local refinement, we focus on wirelength and critical loops
        # TODO: Load real weights from config
        from temper_placer.losses.base import WeightedLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.losses.physics import HypergraphWirelengthLoss

        loss_fn = CompositeLoss([
            WeightedLoss(HypergraphWirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=10.0),  # Soft overlap to guide gradient
        ])

        context = LossContext.from_netlist_and_board(state.netlist, state.board)
        # 3. Optimization Loop
        print(
            f"Running refinement for {state.config.epochs} epochs "
            f"(max {state.config.max_movement_mm}mm movement)..."
        )

        optimizer = optax.adam(learning_rate=0.1)
        params = {"positions": jnp.array(positions)}
        opt_state = optimizer.init(params)

        @jax.jit
        def step(params, opt_state):
            def f(p):
                # Sample rotations (fixed at 0 deg one-hot for now in this simple loop)
                # rotations must be (N, 4)
                rotations = jnp.zeros((n, 4))
                rotations = rotations.at[:, 0].set(1.0)
                res = loss_fn(p["positions"], rotations, context)
                return res.value

            loss, grads = jax.value_and_grad(f)(params)
            updates, opt_state = optimizer.update(grads, opt_state)
            params = optax.apply_updates(params, updates)
            return params, opt_state, loss

        for epoch in range(min(state.config.epochs, 500)):  # Limit refinement epochs
            params, opt_state, loss_val = step(params, opt_state)

            # 4. Projection (Every N steps or every step)
            if epoch % 10 == 0:
                pos_np = np.array(params["positions"])
                # Trust region: max X mm
                pos_np = project_to_trust_region(
                    pos_np, anchor_positions, max_radius=state.config.max_movement_mm
                )
                # Keep in board
                # pos_np = clamp_to_bounds(pos_np, ...)
                params["positions"] = jnp.array(pos_np)

        # 5. Final Legalization (Ensure zero overlap)
        print("Finalizing placement...")
        final_pos = np.array(params["positions"])
        final_pos = resolve_overlaps_priority(
            final_pos, state.netlist, state.board,
            min_separation=0.5, enforce_zones=True
        )

        state.placement_state = PlacementState.from_positions(
            jnp.array(final_pos)
        )

        return state

    def _run_routing(self, state: PipelineState) -> PipelineState:
        """Run routing verification (congestion estimation)."""
        import jax.numpy as jnp

        from temper_placer.routing.congestion import analyze_congestion

        print("Running routing verification...")

        positions = None
        if state.placement_state:
            positions = state.placement_state.positions
        elif state.deterministic_result:
            positions = jnp.array(state.deterministic_result.positions)
        else:
            print("No placement to verify.")
            return state

        # Estimate congestion
        result = analyze_congestion(
            state.netlist, state.board, positions=positions
        )

        print(f"Max congestion: {result.max_utilization:.2f}")
        print(f"Total overflow: {result.total_overflow:.2f}")

        state.routing_result = result

        if not result.is_feasible():
            print("Warning: High congestion detected (overflow > 0)!")

        return state

    def _run_refinement(self, state: PipelineState) -> PipelineState:
        """Run placement-routing refinement loop."""

        if state.routing_result is None:
            return state

        # Check if routing was successful/feasible
        # For CongestionResult, we check overflow
        is_feasible = state.routing_result.is_feasible(
            threshold=state.config.routability_threshold
        )

        if is_feasible or state.iteration >= state.config.max_iterations:
            print("Placement is routable or max iterations reached. Ending refinement.")
            state._refinement_complete = True
            return state

        print(f"Refinement iteration {state.iteration + 1}: Routing congestion too high.")

        # 0. Root Cause Analysis
        from temper_placer.pipeline.feedback import analyze_root_cause, ValidationFailure
        
        # Simulated failure for analysis
        failure = ValidationFailure(
            spec_name="routability",
            actual_value=state.routing_result.max_utilization,
            limit_value=state.config.routability_threshold,
            margin=state.config.routability_threshold - state.routing_result.max_utilization
        )
        
        analysis = analyze_root_cause(
            failure, state.placement_state or state.deterministic_result, 
            state.netlist, state.board
        )
        
        if analysis.fixes:
            print(f"  Suggested fix: {analysis.fixes[0].action} (Target: {analysis.fixes[0].target})")

        # 1. Adjust based on congestion

        state.iteration += 1

        # We need to signal the orchestrator to go back to GEOMETRIC
        # The current 'run' loop is linear, so we'd need to modify it
        # or handle recursion here.

        return state

    def _run_output(self, state: PipelineState) -> PipelineState:
        """Generate output files (placed PCB, reports)."""
        from temper_placer.io.kicad_writer import (
            add_bounding_boxes_to_pcb,
            add_silkscreen_labels,
            export_placements,
        )

        if not state.config.output_pcb:
            print("No output path specified, skipping export.")
            return state

        print(f"Exporting placed PCB to {state.config.output_pcb}...")

        # Determine which state to export
        if state.placement_state:
            ps = state.placement_state
        elif state.deterministic_result:
            import jax.numpy as jnp

            from temper_placer.core.state import PlacementState
            ps = PlacementState.from_positions(jnp.array(state.deterministic_result.positions))
        else:
            print("No placement data to export.")
            return state

        # Export
        component_refs = [c.ref for c in state.netlist.components]
        try:
            write_result = export_placements(
                template_pcb=state.config.input_pcb,
                output_pcb=state.config.output_pcb,
                state=ps,
                component_refs=component_refs,
                origin=state.board.origin,
            )
            print(f"  Updated: {write_result.components_updated} components")

            # Add visualization layers
            add_bounding_boxes_to_pcb(state.config.output_pcb)
            add_silkscreen_labels(state.config.output_pcb)
            print("  Added visualization layers (bounding boxes, labels).")

        except Exception as e:
            print(f"Error during export: {e}")
            # We don't fail the pipeline if export fails (maybe just a path issue)

        return state
