from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, TYPE_CHECKING

import jax.numpy as jnp

from temper_placer.losses import OverlapLoss, BoundaryLoss
from temper_placer.routing.analysis import RoutabilityReport

if TYPE_CHECKING:
    from temper_placer.core.state import PlacementState
    from temper_placer.pipeline.orchestrator import PipelineState
    from temper_placer.core.board import Board
    from temper_placer.pcl.parser import ConstraintCollection

class TerminationReason(Enum):
    """Reasons why the pipeline might terminate."""
    SUCCESS = 'success'
    MAX_ITERATIONS = 'max_iterations'
    TIMEOUT = 'timeout'
    INFEASIBLE = 'infeasible'
    NO_PROGRESS = 'no_progress'
    USER_ABORT = 'user_abort'

class EscalationPolicy(Enum):
    """Policies for escalating constraint tiers."""
    NONE = 'none'
    ON_STAGNATION = 'on_stagnation'
    ON_ITERATION = 'on_iteration'

@dataclass
class ConvergenceCriteria:
    """Define when the pipeline should stop iterating."""
    # Iteration limits
    max_iterations: int = 5
    max_refinement_iterations: int = 3
    
    # Escalation
    escalation_policy: EscalationPolicy = EscalationPolicy.ON_ITERATION
    escalation_start_iteration: int = 2
    
    # Time limits (seconds)
    timeout_seconds: float = 600.0  # 10 minutes total
    phase_timeout_seconds: float = 120.0  # 2 minutes per phase
    
    # Success thresholds
    max_overlap_mm2: float = 0.01
    max_boundary_violation_mm: float = 0.01
    min_routing_completion: float = 1.0  # 100%
    min_manufacturing_margin_mm: float = 0.05
    
    # Progress detection
    min_loss_improvement: float = 0.001  # 0.1% improvement
    stagnation_epochs: int = 500  # Epochs without improvement

@dataclass
class ConvergenceState:
    """Track convergence state during pipeline execution."""
    start_time: datetime = field(default_factory=datetime.now)
    iteration: int = 0
    
    # Loss history
    loss_history: list[float] = field(default_factory=list)
    best_loss: float = float('inf')
    epochs_since_improvement: int = 0
    
    # Status
    terminated: bool = False
    termination_reason: Optional[TerminationReason] = None

class ConvergenceChecker:
    """Check if the placement pipeline has converged or should terminate."""
    
    def __init__(self, criteria: Optional[ConvergenceCriteria] = None):
        self.criteria = criteria or ConvergenceCriteria()
        self.state = ConvergenceState()
    
    def check_early_termination(
        self,
        iteration: int
    ) -> tuple[bool, Optional[TerminationReason]]:
        """Check if pipeline should terminate early based on limits."""
        
        # Check timeout
        elapsed = (datetime.now() - self.state.start_time).total_seconds()
        if elapsed > self.criteria.timeout_seconds:
            return True, TerminationReason.TIMEOUT
        
        # Check max iterations
        if iteration >= self.criteria.max_iterations:
            return True, TerminationReason.MAX_ITERATIONS
        
        return False, None
    
    def check_success(
        self,
        pipeline_state: PipelineState
    ) -> tuple[bool, str]:
        """
        Check if pipeline has reached success criteria.
        
        Returns (True, reason) if successful, (False, reason) if not yet.
        """
        if pipeline_state.placement_state is None:
            return False, "No placement state yet"
            
        # 1. Check overlap
        overlap_loss = OverlapLoss(margin=0.0)
        overlap_res = overlap_loss(
            pipeline_state.placement_state.positions,
            jnp.zeros((pipeline_state.placement_state.positions.shape[0], 4)), # Placeholder
            pipeline_state.context
        )
        overlap_val = float(overlap_res.value)
        if overlap_val > self.criteria.max_overlap_mm2:
            return False, f"Overlap {overlap_val:.4f}mm2 > {self.criteria.max_overlap_mm2}mm2"
            
        # 2. Check boundary
        boundary_loss = BoundaryLoss(edge_margin=0.0)
        boundary_res = boundary_loss(
            pipeline_state.placement_state.positions,
            jnp.zeros((pipeline_state.placement_state.positions.shape[0], 4)), # Placeholder
            pipeline_state.context
        )
        boundary_val = float(boundary_res.value)
        if boundary_val > self.criteria.max_boundary_violation_mm:
            return False, f"Boundary violation {boundary_val:.4f}mm > {self.criteria.max_boundary_violation_mm}mm"
            
        # 3. Check routing
        if pipeline_state.routing_report:
            report: RoutabilityReport = pipeline_state.routing_report
            # If we don't have completion_rate yet, we assume success if feasible flag is set
            if hasattr(report, 'completion_rate'):
                if report.completion_rate < self.criteria.min_routing_completion:
                    return False, f"Routing {report.completion_rate:.1%} < {self.criteria.min_routing_completion:.1%}"
            elif not report.feasible:
                return False, "Routing not yet feasible"
        else:
            return False, "No routing report available"
            
        return True, "All criteria satisfied"
    
    def check_progress(self, current_loss: float) -> bool:
        """Check if optimization is making sufficient progress."""
        self.state.loss_history.append(current_loss)
        
        if current_loss < self.state.best_loss * (1 - self.criteria.min_loss_improvement):
            self.state.best_loss = current_loss
            self.state.epochs_since_improvement = 0
            return True
        else:
            self.state.epochs_since_improvement += 1
            return self.state.epochs_since_improvement < self.criteria.stagnation_epochs
            
    def check_infeasibility(
        self,
        board: Board,
        netlist: Netlist,
        constraints: ConstraintCollection
    ) -> tuple[bool, Optional[str]]:
        """Detect fundamentally infeasible configurations early."""
        
        # Check 1: Total component area vs board area
        total_comp_area = sum(c.bounds[0] * c.bounds[1] for c in netlist.components)
        board_area = board.width * board.height
        
        if board_area > 0 and total_comp_area > board_area * 0.85:
            return True, f"Components ({total_comp_area:.1f}mm2) exceed 85% of board area ({board_area:.1f}mm2)"
            
        # Check 2: Contradictory constraints via linter
        lint_result = constraints.lint(netlist, board)
        if not lint_result.passed:
            return True, f"Constraint contradictions: {lint_result.errors[0].message}"
        
        return False, None

    def escalate_constraints(
        self,
        constraints: ConstraintCollection,
        iteration: int
    ) -> bool:
        """Escalate constraint tiers based on policy.
        
        Returns True if any constraints were escalated.
        """
        if self.criteria.escalation_policy == EscalationPolicy.NONE:
            return False
            
        if self.criteria.escalation_policy == EscalationPolicy.ON_ITERATION:
            if iteration >= self.criteria.escalation_start_iteration:
                any_escalated = False
                for c in constraints.constraints:
                    old_tier = c.tier
                    c.escalate()
                    if c.tier != old_tier:
                        any_escalated = True
                return any_escalated
                
        return False
