"""
Pipeline orchestrator for PCB placement optimization.

Tie all phases into a cohesive, iterative pipeline:
semantic -> topological -> preflight -> geometric -> routing -> refinement -> output.
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from temper_placer.core.board import Board
from temper_placer.core.community import detect_communities
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.pcl.parser import parse_pcl_file, ConstraintCollection
from temper_placer.losses.base import LossContext
from temper_placer.pipeline.convergence import ConvergenceChecker, TerminationReason
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import export_placements
from temper_placer.pipeline.preflight import PreflightChecker, PreflightReport, PreflightResult


class PipelinePhase(Enum):
    """Phases of the placement pipeline."""
    INPUT = 'input'
    SEMANTIC = 'semantic'
    TOPOLOGICAL = 'topological'
    PREFLIGHT = 'preflight'
    GEOMETRIC = 'geometric'
    ROUTING = 'routing'
    REFINEMENT = 'refinement'
    OUTPUT = 'output'


class PipelineError(Exception):
    """Base class for pipeline-related errors."""
    pass


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""
    # Input files
    input_pcb: Path
    constraints_yaml: Optional[Path] = None
    loops_yaml: Optional[Path] = None
    
    # Output files
    output_pcb: Optional[Path] = None
    output_report: Optional[Path] = None
    output_trace: Optional[Path] = None
    
    # Phase configuration
    skip_topological: bool = False
    skip_routing: bool = False
    
    # Optimization config
    epochs: int = 8000
    seed: int = 42
    
    # Iteration config
    max_iterations: int = 5
    convergence_threshold: float = 0.01
    
    # Manufacturing
    fab_preset: str = 'jlcpcb_standard'
    
    # Dry run
    dry_run: bool = False


@dataclass
class PipelineState:
    """State passed between pipeline phases."""
    config: PipelineConfig
    current_phase: PipelinePhase = PipelinePhase.INPUT
    iteration: int = 0
    
    # Data populated by phases
    board: Optional[Board] = None
    netlist: Optional[Netlist] = None
    loops: list = field(default_factory=list)
    constraints: Optional[ConstraintCollection] = None
    placement_state: Optional[PlacementState] = None
    preflight_report: Optional[PreflightReport] = None
    routing_report: Optional[Any] = None # Will be RoutabilityReport
    context: Optional[LossContext] = None
    
    # Status
    success: bool = False
    failure_reason: Optional[str] = None


class PipelineOrchestrator:
    """Orchestrates the full placement pipeline."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = PipelineState(config=config)
        self.convergence_checker = ConvergenceChecker()
        
        # Phase handlers
        self.phases = {
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
        self.on_phase_start: Optional[Callable[[PipelinePhase, PipelineState], None]] = None
        self.on_phase_complete: Optional[Callable[[PipelinePhase, PipelineState], None]] = None
        self.on_iteration: Optional[Callable[[int, PipelineState], None]] = None
        self.on_epoch: Optional[Callable[[Any], None]] = None
    
    def run(self) -> PipelineState:
        """Execute full pipeline."""
        # Phase 0: Setup and preflight
        setup_phases = [
            PipelinePhase.INPUT,
            PipelinePhase.SEMANTIC,
            PipelinePhase.TOPOLOGICAL,
            PipelinePhase.PREFLIGHT,
        ]
        
        for phase in setup_phases:
            if not self._execute_phase(phase):
                return self.state
                
        # Early infeasibility check
        is_infeasible, reason = self.convergence_checker.check_infeasibility(
            self.state.board, self.state.netlist, self.state.constraints
        )
        if is_infeasible:
            self.state.success = False
            self.state.failure_reason = f"Infeasible: {reason}"
            return self.state

        if self.config.dry_run:
            self.state.success = True
            return self.state

        # Phase 1: Initial placement
        if not self._execute_phase(PipelinePhase.GEOMETRIC):
            return self.state

        # Refinement loop
        for iteration in range(self.config.max_iterations):
            self.state.iteration = iteration
            if self.on_iteration:
                self.on_iteration(iteration, self.state)
                
            # 1. Check for termination (timeout, etc.)
            terminated, reason = self.convergence_checker.check_early_termination(iteration)
            if terminated:
                self.state.success = False
                self.state.failure_reason = f"Terminated: {reason.value}"
                break

            # 2. Routing verification
            if not self._execute_phase(PipelinePhase.ROUTING):
                break
                
            # 3. Check for success
            success, reason = self.convergence_checker.check_success(self.state)
            if success:
                self.state.success = True
                break
            
            # 4. Refinement (Feedback)
            if not self._execute_phase(PipelinePhase.REFINEMENT):
                break
                
            # 5. Re-optimize
            if not self._execute_phase(PipelinePhase.GEOMETRIC):
                break
        
        # Phase 2: Final output
        self._execute_phase(PipelinePhase.OUTPUT)
        
        return self.state

    def _execute_phase(self, phase: PipelinePhase) -> bool:
        """Execute a single phase and handle lifecycle."""
        self.state.current_phase = phase
        
        if self.on_phase_start:
            self.on_phase_start(phase, self.state)
        
        try:
            handler = self.phases[phase]
            self.state = handler(self.state)
            
            # Check for failures recorded in state
            if self.state.failure_reason and phase == PipelinePhase.PREFLIGHT:
                if self.state.preflight_report and not self.state.preflight_report.passed:
                    self.state.success = False
                    return False

        except Exception as e:
            self.state.success = False
            self.state.failure_reason = f"Error in phase {phase.value}: {str(e)}"
            import traceback
            traceback.print_exc()
            return False
        
        if self.on_phase_complete:
            self.on_phase_complete(phase, self.state)
            
        return True
    
    def _run_input(self, state: PipelineState) -> PipelineState:
        """Load input files."""
        parse_result = parse_kicad_pcb(self.config.input_pcb)
        state.board = parse_result.board
        state.netlist = parse_result.netlist
        
        # Initialize LossContext
        state.context = LossContext.from_netlist_and_board(state.netlist, state.board)
        
        if self.config.constraints_yaml:
            state.constraints = parse_pcl_file(self.config.constraints_yaml)
        else:
            state.constraints = ConstraintCollection([])
        
        # loops loading would go here if implemented
        
        return state
    
    def _run_semantic(self, state: PipelineState) -> PipelineState:
        """Extract semantic information (loops, roles)."""
        # Placeholder for loop extraction logic
        return state
    
    def _run_topological(self, state: PipelineState) -> PipelineState:
        """Topological reasoning/placement phase."""
        if self.config.skip_topological:
            return state
        # Placeholder for topological placement
        return state
    
    def _run_preflight(self, state: PipelineState) -> PipelineState:
        """Run feasibility checks."""
        checker = PreflightChecker()
        # Use default fab preset for now
        report = checker.run(state.board, state.netlist, state.constraints)
        state.preflight_report = report
        
        if not report.passed:
            state.failure_reason = "Preflight feasibility check failed"
            
        return state
    
    def _run_geometric(self, state: PipelineState) -> PipelineState:
        """Geometric optimization (JAX)."""
        import jax.numpy as jnp
        from temper_placer.optimizer import train_multiphase, OptimizerConfig
        from temper_placer.losses import (
            CompositeLoss, 
            WeightedLoss, 
            OverlapLoss, 
            BoundaryLoss, 
            WirelengthLoss, 
            SpreadLoss,
            GroupConfig,
            GroupClusterLoss
        )
        from temper_placer.optimizer.curriculum import create_default_phases
        
        # 1. Detect functional groups for better clustering
        detected_communities = detect_communities(state.netlist)
        
        # 2. Build composite loss with curriculum-aware weights
        def make_loss(weights: dict) -> CompositeLoss:
            """Factory function for curriculum learning."""
            losses = []

            # Core feasibility losses
            if "overlap" in weights:
                losses.append(
                    WeightedLoss(
                        OverlapLoss(margin=1.0, rotation_invariant=True), weight=weights["overlap"]
                    )
                )
            if "boundary" in weights:
                losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))

            # Performance losses
            if "wirelength" in weights:
                losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
            if "spread" in weights:
                losses.append(WeightedLoss(SpreadLoss(), weight=weights["spread"]))

            # Auto-grouping clusters
            if detected_communities or state.constraints.component_groups:
                group_configs = []

                if detected_communities:
                    for comm in detected_communities:
                        indices = [state.netlist.get_component_index(ref) for ref in comm.component_refs]
                        group_configs.append(
                            GroupConfig(
                                name=f"auto_{comm.name}",
                                component_indices=jnp.array(indices, dtype=jnp.int32),
                                max_diameter_mm=30.0,
                                weight=1.0,
                            )
                        )

                if group_configs:
                    losses.append(WeightedLoss(GroupClusterLoss(group_configs), weight=10.0))

            return CompositeLoss(losses)

        # 3. Configure optimizer
        phases = create_default_phases(self.config.epochs)
        cfg = OptimizerConfig(
            epochs=self.config.epochs,
            seed=self.config.seed,
            curriculum_phases=phases,
        )
        
        # 4. Run optimization
        result = train_multiphase(
            netlist=state.netlist,
            board=state.board,
            loss_factory=make_loss,
            context=state.context,
            config=cfg,
            initial_state=state.placement_state,
            callback=self.on_epoch
        )
        
        state.placement_state = result.best_state
        return state
    
    def _run_routing(self, state: PipelineState) -> PipelineState:
        """Analyze routability of the current placement."""
        if self.config.skip_routing:
            return state
            
        from temper_placer.routing.analysis import analyze_routability
        from temper_placer.losses.base import LossContext
        
        context = LossContext.from_netlist_and_board(state.netlist, state.board)
        state.routing_report = analyze_routability(state.placement_state.positions, context)
        
        return state
    
    def _run_refinement(self, state: PipelineState) -> PipelineState:
        """Iterative refinement loop."""
        from temper_placer.pipeline.feedback import run_feedback_loop
        
        return run_feedback_loop(
            state, 
            max_iterations=self.config.max_iterations,
            on_iteration=self.on_iteration
        )
    
    def _run_output(self, state: PipelineState) -> PipelineState:
        """Generate final outputs."""
        if self.config.output_pcb and state.placement_state:
            export_placements(
                template_pcb=self.config.input_pcb,
                output_pcb=self.config.output_pcb,
                state=state.placement_state,
                component_refs=[c.ref for c in state.netlist.components],
                origin=state.board.origin
            )
            
        if self.config.output_report:
            # Report generation logic
            pass
            
        return state
