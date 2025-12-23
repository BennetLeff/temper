"""Traced loss computation - wraps losses to propagate 'because' field.

This module provides utilities to make loss functions return (loss, reason) tuples,
enabling automatic trace generation from constraint evaluation.

The key insight: PCL constraints already have 'because' fields. We just need to
propagate them through the loss computation pipeline.

Example:
    >>> from temper_placer.explainability import Trace
    >>> from temper_placer.explainability.traced_loss import compute_traced_loss
    >>>
    >>> # Constraint with 'because'
    >>> constraint = AdjacentConstraint(
    ...     a="Q1", b="Q2",
    ...     max_distance_mm=15,
    ...     tier=ConstraintTier.HARD,
    ...     because="Minimize commutation loop for half-bridge"
    ... )
    >>>
    >>> # Compute traced loss
    >>> loss_value, trace = compute_traced_loss(constraint, positions)
    >>> print(trace.why("Q1"))
    Q1 moved because:
      - Minimize commutation loop for half-bridge
"""

from typing import Any, Callable
from temper_placer.explainability.trace import Trace
import jax.numpy as jnp


def traced_loss(
    loss_fn: Callable,
    subject: str,
    because: str,
) -> Callable:
    """Wrap a loss function to return (loss, trace) tuple.
    
    Args:
        loss_fn: Original loss function returning scalar loss
        subject: Component/net being constrained
        because: Reason for the constraint (from PCL)
        
    Returns:
        Wrapped function returning (loss, trace) tuple
        
    Example:
        >>> def adjacency_loss(positions):
        ...     return jnp.sum((positions[0] - positions[1]) ** 2)
        >>>
        >>> traced_fn = traced_loss(
        ...     adjacency_loss,
        ...     subject="Q1",
        ...     because="Minimize commutation loop"
        ... )
        >>>
        >>> loss, trace = traced_fn(positions)
        >>> print(trace.why("Q1"))
        Q1 moved because:
          - Minimize commutation loop
    """
    def wrapper(*args, **kwargs):
        loss_value = loss_fn(*args, **kwargs)
        
        # Create trace entry if loss is significant
        trace = Trace.empty()
        if float(loss_value) > 1e-6:  # Only trace if constraint is active
            trace = trace.add(subject, float(loss_value), because)
        
        return loss_value, trace
    
    return wrapper


def combine_traced_losses(
    traced_results: list[tuple[Any, Trace]]
) -> tuple[Any, Trace]:
    """Combine multiple (loss, trace) tuples into single result.
    
    Args:
        traced_results: List of (loss, trace) tuples
        
    Returns:
        (total_loss, combined_trace) tuple
        
    Example:
        >>> results = [
        ...     (loss1, trace1),
        ...     (loss2, trace2),
        ...     (loss3, trace3),
        ... ]
        >>> total_loss, combined_trace = combine_traced_losses(results)
        >>> # combined_trace has all entries from trace1, trace2, trace3
    """
    if not traced_results:
        return 0.0, Trace.empty()
    
    # Sum losses
    total_loss = sum(loss for loss, _ in traced_results)
    
    # Combine traces (monoid!)
    combined_trace = Trace.empty()
    for _, trace in traced_results:
        combined_trace = combined_trace + trace
    
    return total_loss, combined_trace


def constraint_to_traced_loss(
    constraint: Any,
    loss_fn: Callable,
) -> Callable:
    """Convert a PCL constraint to a traced loss function.
    
    Args:
        constraint: PCL constraint with 'because' field
        loss_fn: Function computing loss from constraint
        
    Returns:
        Traced loss function returning (loss, trace)
        
    Example:
        >>> constraint = AdjacentConstraint(
        ...     a="Q1", b="Q2",
        ...     max_distance_mm=15,
        ...     tier=ConstraintTier.HARD,
        ...     because="Minimize commutation loop"
        ... )
        >>>
        >>> def compute_adjacency_loss(c, positions):
        ...     dist = jnp.linalg.norm(positions[c.a] - positions[c.b])
        ...     return jnp.maximum(0, dist - c.max_distance_mm) ** 2
        >>>
        >>> traced_fn = constraint_to_traced_loss(constraint, compute_adjacency_loss)
        >>> loss, trace = traced_fn(positions)
    """
    # Get subject from constraint
    if hasattr(constraint, 'a'):
        subject = constraint.a
    elif hasattr(constraint, 'component'):
        subject = constraint.component
    elif hasattr(constraint, 'components'):
        subject = constraint.components[0] if constraint.components else "unknown"
    else:
        subject = "unknown"
    
    # Get because from constraint
    because = constraint.because if hasattr(constraint, 'because') else "constraint"
    
    # Wrap loss function
    return traced_loss(
        lambda *args, **kwargs: loss_fn(constraint, *args, **kwargs),
        subject=subject,
        because=because,
    )


# Example: Traced loss context for optimizer
class TracedLossContext:
    """Context manager for collecting traced losses during optimization.
    
    Example:
        >>> with TracedLossContext() as ctx:
        ...     for constraint in constraints:
        ...         loss, trace = compute_constraint_loss(constraint, positions)
        ...         ctx.add(loss, trace)
        ...
        >>> total_loss, combined_trace = ctx.result()
        >>> print(combined_trace.why("Q1"))
    """
    def __init__(self):
        self.losses = []
        self.traces = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def add(self, loss: Any, trace: Trace):
        """Add a traced loss result."""
        self.losses.append(loss)
        self.traces.append(trace)
    
    def result(self) -> tuple[Any, Trace]:
        """Get combined result."""
        if not self.losses:
            return 0.0, Trace.empty()
        
        total_loss = sum(self.losses)
        combined_trace = Trace.empty()
        for trace in self.traces:
            combined_trace = combined_trace + trace
        
        return total_loss, combined_trace
