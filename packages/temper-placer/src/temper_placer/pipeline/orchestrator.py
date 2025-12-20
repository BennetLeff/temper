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
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.pcl.parser import parse_pcl_file, ConstraintCollection
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
    
    # Status
    success: bool = False
    failure_reason: Optional[str] = None


class PipelineOrchestrator:
    """Orchestrates the full placement pipeline."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = PipelineState(config=config)
        
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
    
    def run(self) -> PipelineState:
        """Execute full pipeline."""
        phase_order = [
            PipelinePhase.INPUT,
            PipelinePhase.SEMANTIC,
            PipelinePhase.TOPOLOGICAL,
            PipelinePhase.PREFLIGHT,
        ]
        
        if not self.config.dry_run:
            phase_order.extend([
                PipelinePhase.GEOMETRIC,
                PipelinePhase.ROUTING,
                PipelinePhase.REFINEMENT,
                PipelinePhase.OUTPUT,
            ])
        
        for phase in phase_order:
            self.state.current_phase = phase
            
            if self.on_phase_start:
                self.on_phase_start(phase, self.state)
            
            try:
                handler = self.phases[phase]
                self.state = handler(self.state)
                
                # Check for critical failures
                if self.state.failure_reason and phase == PipelinePhase.PREFLIGHT:
                    if self.state.preflight_report and not self.state.preflight_report.passed:
                        self.state.success = False
                        return self.state

            except Exception as e:
                self.state.success = False
                self.state.failure_reason = f"Error in phase {phase.value}: {str(e)}"
                import traceback
                traceback.print_exc()
                return self.state
            
            if self.on_phase_complete:
                self.on_phase_complete(phase, self.state)
        
        self.state.success = True
        return self.state
    
    def _run_input(self, state: PipelineState) -> PipelineState:
        """Load input files."""
        parse_result = parse_kicad_pcb(self.config.input_pcb)
        state.board = parse_result.board
        state.netlist = parse_result.netlist
        
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
        from temper_placer.optimizer import train, OptimizerConfig
        from temper_placer.losses import CompositeLoss, WeightedLoss, OverlapLoss, BoundaryLoss, WirelengthLoss, SpreadLoss
        from temper_placer.losses.base import LossContext
        
        # Setup loss functions based on constraints
        losses = [
            WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weight=100.0),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            WeightedLoss(WirelengthLoss(), weight=10.0),
            WeightedLoss(SpreadLoss(), weight=5.0),
        ]
        
        composite_loss = CompositeLoss(losses)
        context = LossContext.from_netlist_and_board(state.netlist, state.board, constraints=None) # Simplified
        
        cfg = OptimizerConfig(
            epochs=self.config.epochs,
            seed=self.config.seed,
        )
        
        result = train(
            netlist=state.netlist,
            board=state.board,
            composite_loss=composite_loss,
            context=context,
            config=cfg,
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
        # For now, just a placeholder for the iteration logic
        return state
    
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
