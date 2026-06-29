"""Composable traced pipeline - combines optimizer and router traces.

This module demonstrates the full power of the functional explainability system
by composing traces from different pipeline phases using monoid operations.

Example:
    >>> from temper_placer.explainability.pipeline import run_traced_pipeline
    >>>
    >>> result, trace = run_traced_pipeline(pcb, pcl)
    >>>
    >>> # Query placement decisions
    >>> print(trace.why("Q1"))
    >>> # Query routing decisions
    >>> print(trace.why("VCC"))
"""

from typing import Any

from temper_placer.explainability.trace import Trace


def compose_traces(*traces: Trace) -> Trace:
    """Compose multiple traces using monoid operation.

    This is a convenience function that makes trace composition more explicit.

    Args:
        *traces: Variable number of Trace objects

    Returns:
        Combined trace with all entries

    Example:
        >>> trace1 = Trace.empty().add("Q1", (10, 20), "R1")
        >>> trace2 = Trace.empty().add("Q2", (30, 40), "R2")
        >>> trace3 = Trace.empty().add("VCC", path, "R3")
        >>> combined = compose_traces(trace1, trace2, trace3)
        >>> len(combined)
        3
    """
    result = Trace.empty()
    for trace in traces:
        result = result + trace
    return result


def traced_pipeline_example(
    placement_fn,
    routing_fn,
    *args,
    **kwargs
) -> tuple[Any, Trace]:
    """Example of composable traced pipeline.

    This demonstrates how to structure a pipeline where each phase
    returns (result, trace) tuples that compose naturally.

    Args:
        placement_fn: Function returning (positions, trace)
        routing_fn: Function returning (routes, trace)
        *args, **kwargs: Arguments for pipeline functions

    Returns:
        (final_result, combined_trace) tuple

    Example:
        >>> def place(components):
        ...     positions = optimize(components)
        ...     trace = Trace.empty().add("Q1", positions[0], "Optimized")
        ...     return positions, trace
        >>>
        >>> def route(nets, positions):
        ...     routes = route_nets(nets, positions)
        ...     trace = Trace.empty().add("VCC", routes["VCC"], "Routed")
        ...     return routes, trace
        >>>
        >>> result, trace = traced_pipeline_example(place, route, components, nets)
        >>> print(trace.why("Q1"))  # Placement decision
        >>> print(trace.why("VCC"))  # Routing decision
    """
    # Phase 1: Placement
    placement_result, placement_trace = placement_fn(*args, **kwargs)

    # Phase 2: Routing (uses placement result)
    routing_result, routing_trace = routing_fn(placement_result, *args, **kwargs)

    # Compose traces (monoid!)
    combined_trace = placement_trace + routing_trace

    # Return final result and combined trace
    return (placement_result, routing_result), combined_trace


class TracedPipeline:
    """Pipeline builder for composing traced operations.

    This class provides a fluent interface for building pipelines
    where each stage returns (result, trace) tuples.

    Example:
        >>> pipeline = TracedPipeline()
        >>> pipeline.add_stage("placement", optimize_with_trace)
        >>> pipeline.add_stage("routing", route_with_trace)
        >>> result, trace = pipeline.run(initial_data)
        >>> print(trace.why("Q1"))
    """

    def __init__(self):
        self.stages = []
        self.stage_names = []

    def add_stage(self, name: str, fn):
        """Add a stage to the pipeline.

        Args:
            name: Name of the stage (for debugging)
            fn: Function returning (result, trace) tuple

        Returns:
            self for chaining
        """
        self.stages.append(fn)
        self.stage_names.append(name)
        return self

    def run(self, initial_data: Any) -> tuple[Any, Trace]:
        """Run the pipeline and return combined result and trace.

        Args:
            initial_data: Input to first stage

        Returns:
            (final_result, combined_trace) tuple
        """
        result = initial_data
        combined_trace = Trace.empty()

        for _stage_name, stage_fn in zip(self.stage_names, self.stages):
            result, trace = stage_fn(result)
            combined_trace = combined_trace + trace

        return result, combined_trace


# Example usage demonstration
def example_placement_optimizer(components) -> tuple[Any, Trace]:
    """Example traced placement function.

    In reality, this would call the actual optimizer with traced losses.
    """
    trace = Trace.empty()

    # Simulate placement decisions
    for comp in components:
        trace = trace.add(
            comp,
            (10.0, 20.0),  # Mock position
            f"Placed {comp} to minimize wirelength"
        )

    return {"positions": "mock"}, trace


def example_router(_placement_result) -> tuple[Any, Trace]:
    """Example traced routing function.

    In reality, this would call route_all_with_trace.
    """
    trace = Trace.empty()

    # Simulate routing decisions
    trace = trace.add(
        "VCC",
        ["L1", "L4"],
        "Power net can route on signal layers L1, L4"
    )

    return {"routes": "mock"}, trace


def demo_pipeline():
    """Demonstrate the composable pipeline.

    Example:
        >>> result, trace = demo_pipeline()
        >>> print(trace.why("Q1"))
        >>> print(trace.why("VCC"))
    """
    components = ["Q1", "Q2", "U1"]

    # Build pipeline
    pipeline = TracedPipeline()
    pipeline.add_stage("placement", example_placement_optimizer)
    pipeline.add_stage("routing", example_router)

    # Run pipeline
    result, trace = pipeline.run(components)

    return result, trace
