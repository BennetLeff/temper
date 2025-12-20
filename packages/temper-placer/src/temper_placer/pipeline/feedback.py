from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Callable, TYPE_CHECKING
import jax.numpy as jnp

from temper_placer.routing.analysis import RoutabilityReport, RoutingDiagnostic, FailureType
from temper_placer.pcl import (
    ConstraintCollection, 
    AdjacentConstraint, 
    SeparatedConstraint,
    ConstraintTier
)

if TYPE_CHECKING:
    from temper_placer.core.state import PlacementState
    from temper_placer.pipeline.orchestrator import PipelineState

@dataclass
class PlacementAdjustment:
    """Hint from routing to placement."""
    component: str
    adjustment_type: str  # 'move', 'rotate', 'spread'
    direction: tuple[float, float] | None  # For move
    magnitude: float | None  # How much to move
    reason: str
    priority: float  # 0.0 to 1.0

class FeedbackGenerator:
    """Converts routing failures to placement adjustments."""
    
    def generate(
        self,
        routing_report: RoutabilityReport,
        placement_state: PlacementState
    ) -> list[PlacementAdjustment]:
        """Generate placement adjustments from routing failures."""
        adjustments = []
        
        for diagnostic in routing_report.diagnostics:
            adj = self._diagnostic_to_adjustment(diagnostic, placement_state)
            if adj:
                adjustments.append(adj)
        
        # Sort by priority
        adjustments.sort(key=lambda a: -a.priority)
        return adjustments
    
    def _diagnostic_to_adjustment(
        self,
        diagnostic: RoutingDiagnostic,
        state: PlacementState
    ) -> Optional[PlacementAdjustment]:
        """Convert single diagnostic to adjustment."""
        
        if diagnostic.failure_type == FailureType.NO_PATH:
            if not diagnostic.blocking_elements or not diagnostic.net:
                return None
                
            # Move blocking component out of the way
            blocker = diagnostic.blocking_elements[0]
            direction = self._compute_clear_direction(
                diagnostic.net, blocker, state
            )
            return PlacementAdjustment(
                component=blocker,
                adjustment_type='move',
                direction=direction,
                magnitude=2.0,  # mm
                reason=f'Clear path for {diagnostic.net}',
                priority=1.0
            )
        
        elif diagnostic.failure_type == FailureType.CONGESTION:
            if not diagnostic.blocking_elements:
                return None
                
            # Spread components in congested area
            components = diagnostic.blocking_elements
            return PlacementAdjustment(
                component=components[0],  # Start with first
                adjustment_type='spread',
                direction=None,
                magnitude=5.0,  # mm spread radius
                reason=f'Reduce congestion at {diagnostic.location}',
                priority=0.8
            )
        
        return None
    
    def _compute_clear_direction(
        self,
        net: str,
        blocker: str,
        state: PlacementState
    ) -> tuple[float, float]:
        """Compute which direction to move blocker."""
        # Get net endpoints
        try:
            net_obj = state.netlist.get_net(net)
            # Need actual positions
            positions = []
            for ref, pin_name in net_obj.pins:
                idx = state.netlist.get_component_index(ref)
                pos = state.positions[idx]
                positions.append(pos)
            
            if len(positions) >= 2:
                dx = float(positions[1][0] - positions[0][0])
                dy = float(positions[1][1] - positions[0][1])
                # Perpendicular direction
                length = (dx**2 + dy**2)**0.5
                if length > 1e-6:
                    return (-dy/length, dx/length)
        except Exception:
            pass
            
        return (1.0, 0.0)  # Default: move right

class AdjustmentApplier:
    """Applies placement adjustments as soft constraints."""
    
    def apply(
        self,
        adjustments: list[PlacementAdjustment],
        constraints: ConstraintCollection
    ) -> ConstraintCollection:
        """Add soft constraints based on adjustments."""
        # Note: ConstraintCollection.constraints is a list we can append to
        # But we should ideally not modify in place if we want to follow 'copy' pattern
        new_constraints_list = list(constraints.constraints)
        
        for adj in adjustments:
            if adj.adjustment_type == 'move':
                # PCL doesn't have 'attraction' or 'direction' constraints yet.
                # As a workaround, we could use AdjacentConstraint with a virtual anchor point,
                # but PCL only supports component-to-component adjacency.
                
                # For now, let's use a placeholder or skip if not supported by current PCL.
                # Actually, we can't easily implement 'move in direction' with current PCL.
                pass
            
            elif adj.adjustment_type == 'spread':
                # Add repulsion constraint - using SeparatedConstraint
                # We need another component to separate from. 
                # If we want to 'spread', we usually mean separate from neighbors.
                pass
        
        return ConstraintCollection(
            constraints=new_constraints_list,
            version=constraints.version,
            metadata=constraints.metadata
        )

def run_feedback_loop(
    state: PipelineState,
    max_iterations: int = 5,
    on_iteration: Optional[Callable] = None
) -> PipelineState:
    """Run placement-routing feedback loop."""
    
    feedback_gen = FeedbackGenerator()
    # applier = AdjustmentApplier() # Placeholder until PCL supports needed types
    
    for iteration in range(max_iterations):
        # Check if routing succeeded
        if state.routing_report and state.routing_report.feasible:
            break
        
        if on_iteration:
            on_iteration(iteration, state)
        
        # Generate adjustments
        adjustments = feedback_gen.generate(
            state.routing_report,
            state.placement_state
        )
        
        if not adjustments:
            # No actionable feedback
            break
            
        # Refinement logic would go here:
        # 1. Convert adjustments to soft constraints/forces
        # 2. Re-run optimizer
        # 3. Update state.routing_report
        
        # For now, this is a skeleton as requested by the task.
        break
    
    return state
