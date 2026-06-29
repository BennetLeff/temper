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

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any, Optional

import jax.numpy as jnp

from temper_placer.explainability.trace import Trace

# Global context for active tracing.
# This allows @traced decorators to automatically find the current context.
_active_traced_ctx: ContextVar[Optional["TracedLossContext"]] = ContextVar(
    "active_traced_ctx", default=None
)


def traced(
    _func: Callable | None = None,
    *,
    subject: str | None = None,
    because: str | None = None,
    threshold: float = 1e-6,
):
    """Decorator to automatically trace function execution.

    If running within a TracedLossContext, it automatically adds the result
    to the context and returns the original result.
    If NOT in a context, it returns a (result, trace) tuple.

    Args:
        subject: Subject for the trace (defaults to function name)
        because: Reason for the trace
        threshold: Minimum value to record a trace entry (default 1e-6)

    Example:
        >>> @traced(subject="Q1", because="Overlap penalty")
        ... def compute_overlap(pos):
        ...     return jnp.sum(pos)
        ...
        >>> # Standalone usage
        >>> val, trace = compute_overlap(pos)
        >>>
        >>> # Context usage
        >>> with TracedLossContext() as ctx:
        ...     val = compute_overlap(pos) # Result is added to ctx automatically
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Execute original function
            result = func(*args, **kwargs)

            # Prepare trace
            final_subject = subject or func.__name__
            final_because = because or f"Result of {func.__name__}"

            # Create trace entry if value is significant
            trace = Trace.empty()
            try:
                val_float = float(result)
                if val_float > threshold:
                    trace = trace.add(final_subject, val_float, final_because)
            except (TypeError, ValueError):
                # If result is not a float (e.g. specialized object), record it anyway
                trace = trace.add(final_subject, result, final_because)

            # Handle context
            ctx = _active_traced_ctx.get()
            if ctx is not None:
                ctx.add(result, trace)
                return result # Return original result within context

            return result, trace # Return tuple standalone

        return wrapper

    if _func is None:
        return decorator
    return decorator(_func)


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
    """
    @wraps(loss_fn)
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


class TracedLossContext:
    """Context manager for collecting traced losses during optimization.

    Example:
        >>> with TracedLossContext() as ctx:
        ...     for constraint in constraints:
        ...         loss, trace = compute_constraint_loss(constraint, positions)
        ...         ctx.add(loss, trace)
        ...
        >>> total_loss, combined_trace = ctx.result()
    """
    def __init__(self):
        self.losses = []
        self.traces = []
        self._token = None

    def __enter__(self):
        self._token = _active_traced_ctx.set(self)
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        if self._token:
            _active_traced_ctx.reset(self._token)

    def add(self, loss: Any, trace: Trace):
        """Add a traced loss result."""
        self.losses.append(loss)
        self.traces.append(trace)

    def result(self) -> tuple[Any, Trace]:
        """Get combined result."""
        if not self.losses:
            return 0.0, Trace.empty()

        # Ensure we handle JAX arrays correctly during sum
        total_loss = jnp.zeros(())
        for loss in self.losses:
            total_loss = total_loss + loss

        combined_trace = Trace.empty()
        for trace in self.traces:
            combined_trace = combined_trace + trace

        return total_loss, combined_trace
