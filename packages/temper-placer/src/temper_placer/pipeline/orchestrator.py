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
    dry_run: bool = False

    # Optimization config
    epochs: int = 8000
    seed: int = 42

    # Iteration config
    max_iterations: int = 5
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

        for phase in phase_order:
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

            # Call complete callback
            if self.on_phase_complete:
                self.on_phase_complete(phase, self.state)

        self.state.success = True
        self.state.elapsed_time_s = time.time() - start_time
        return self.state

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
            raise PipelineError(f"Failed to parse PCB: {e}", phase=PipelinePhase.INPUT)

        state.board = result.board
        state.netlist = result.netlist

        if result.has_warnings:
            print(f"Warnings during parsing: {result.warnings}")

        # TODO: Load real constraints
        # For now, create a mock constraint object that satisfies PreflightChecker
        class MockConstraints:
            constraints = []

        state.constraints = MockConstraints()

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
        """Run topological placement phase.

        This is a stub implementation that will be expanded in later tasks.
        """
        # TODO: Implement topological placement
        # - Build adjacency graph
        # - Check constraint satisfiability
        # - Identify clusters
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
        """Run geometric optimization (JAX gradient descent)."""
        from temper_placer.core.state import PlacementState
        import jax.numpy as jnp
        import numpy as np

        print("Initializing geometric optimization...")

        # Initialize placement state
        if state.placement_state is None:
            if state.deterministic_result is not None:
                print("Initializing from deterministic placement result...")
                # Convert NumPy arrays to JAX arrays
                positions = jnp.array(state.deterministic_result.positions)
                # We could also use rotations if PlacementState supports initial rotations
                # For now just positions
                state.placement_state = PlacementState.from_positions(positions)
            else:
                print("Initializing random placement...")
                # Fallback to random initialization
                # This requires board dimensions and a key
                import jax
                key = jax.random.PRNGKey(state.config.seed)
                state.placement_state = PlacementState.random_init(
                    n_components=state.netlist.n_components,
                    board_width=state.board.width,
                    board_height=state.board.height,
                    key=key,
                    origin=state.board.origin,
                )

        # TODO: Run optimizer with curriculum learning
        # - Track decision trace
        return state

    def _run_routing(self, state: PipelineState) -> PipelineState:
        """Run routing verification.

        This is a stub implementation that will be expanded in later tasks.
        """
        # TODO: Implement routing verification using routing module
        # - Create RoutingVerifier
        # - Run verification at configured level
        # - Store result in state
        return state

    def _run_refinement(self, state: PipelineState) -> PipelineState:
        """Run placement-routing refinement loop.

        This is a stub implementation that will be expanded in later tasks.
        """
        # TODO: Implement refinement loop
        # - Check routing result
        # - Generate placement adjustments
        # - Re-run geometric if needed
        # - Call on_iteration callback
        return state

    def _run_output(self, state: PipelineState) -> PipelineState:
        """Generate output files (placed PCB, reports).

        This is a stub implementation that will be expanded in later tasks.
        """
        # TODO: Implement output generation
        # - Write placed PCB if output_pcb specified
        # - Write HTML report if output_report specified
        # - Write decision trace if output_trace specified
        return state
