"""Traced routing functions - pure functions returning (routes, trace) tuples.

This module provides functional wrappers around the MazeRouter that return
traced results, enabling explainability for routing decisions.

Example:
    >>> from temper_placer.explainability import Trace
    >>> from temper_placer.routing.traced_routing import route_with_trace
    >>>
    >>> routes, trace = route_with_trace(router, nets, layer_stackup)
    >>> print(trace.why("VCC"))
    VCC routed on layers [0, 3] because:
      - Power net can route on signal layers L1, L4
      - Via at (23.4, 15.2) to avoid obstacle
"""

from temper_placer.explainability.trace import Trace
from temper_placer.routing.heuristics import GridCell
from temper_placer.routing.maze_router import MazeRouter


def explain_layer_assignment(net_class: str, allowed_layers: list[int]) -> str:
    """Generate explanation for layer assignment decision.
    
    Args:
        net_class: Net class (Signal, Power, HighVoltage)
        allowed_layers: List of allowed layer indices
        
    Returns:
        Natural language explanation
    """
    if net_class == "HighVoltage":
        return "HV net restricted to L1 (2oz copper for current capacity)"
    elif net_class == "Power":
        layer_names = ", ".join(f"L{i+1}" for i in allowed_layers)
        return f"Power net can route on signal layers {layer_names}"
    else:
        return f"Signal net can route on {len(allowed_layers)} routable layers"


def explain_via(
    from_layer: int,
    to_layer: int,
    reason: str = "obstacle avoidance"
) -> str:
    """Generate explanation for via placement.
    
    Args:
        from_layer: Source layer index
        to_layer: Destination layer index
        reason: Why the via was needed
        
    Returns:
        Natural language explanation
    """
    return f"Via from L{from_layer+1} to L{to_layer+1} for {reason}"


def explain_route_failure(net_name: str, reason: str | None = None) -> str:
    """Generate explanation for routing failure.
    
    Args:
        net_name: Name of net that failed
        reason: Failure reason if known
        
    Returns:
        Natural language explanation
    """
    if reason:
        return f"Failed to route {net_name}: {reason}"
    else:
        return f"Failed to route {net_name}: no path found"


def route_net_with_trace(
    router: MazeRouter,
    net_name: str,
    start: tuple[int, int],
    end: tuple[int, int],
    layer: int = 0,
    allow_layer_change: bool = False,
    net_class: str = "Signal",
) -> tuple[list[GridCell] | None, Trace]:
    """Route a single net and return traced result.
    
    Args:
        router: MazeRouter instance
        net_name: Name of net being routed
        start: Start position (grid coordinates)
        end: End position (grid coordinates)
        layer: Starting layer
        allow_layer_change: Whether to allow vias
        net_class: Net class for layer assignment
        
    Returns:
        (path, trace) tuple where path is list of GridCells or None if failed
        
    Example:
        >>> path, trace = route_net_with_trace(
        ...     router, "VCC", (10, 10), (50, 50),
        ...     allow_layer_change=True,
        ...     net_class="Power"
        ... )
        >>> print(trace.why("VCC"))
        VCC routed because:
          - Power net can route on signal layers L1, L4
    """
    trace = Trace.empty()

    # Layer assignment decision
    if allow_layer_change:
        # In future, get from LayerStackup
        allowed_layers = [0, 1] if net_class != "HighVoltage" else [0]
        trace = trace.add(
            net_name,
            allowed_layers,
            explain_layer_assignment(net_class, allowed_layers)
        )

    # Route the path
    path = router.find_path(start, end, layer, allow_layer_change)

    if path is None:
        # Routing failed
        trace = trace.add(
            net_name,
            None,
            explain_route_failure(net_name, "blocked or unreachable")
        )
        return None, trace

    # Analyze path for vias
    via_count = 0
    for i in range(len(path) - 1):
        if path[i].layer != path[i+1].layer:
            via_count += 1
            # Record via decision
            via_pos = (path[i].x, path[i].y)
            trace = trace.add(
                net_name,
                via_pos,
                explain_via(path[i].layer, path[i+1].layer)
            )

    # Record successful routing
    if via_count == 0:
        trace = trace.add(
            net_name,
            len(path),
            f"Direct path on L{layer+1} ({len(path)} cells)"
        )

    return path, trace


def route_all_with_trace(
    router: MazeRouter,
    net_routes: list[tuple[str, tuple[int, int], tuple[int, int]]],
    allow_layer_change: bool = False,
) -> tuple[dict[str, list[GridCell] | None], Trace]:
    """Route multiple nets and return combined trace.
    
    Args:
        router: MazeRouter instance
        net_routes: List of (net_name, start, end) tuples
        allow_layer_change: Whether to allow vias
        
    Returns:
        (routes_dict, combined_trace) tuple
        
    Example:
        >>> net_routes = [
        ...     ("VCC", (10, 10), (50, 50)),
        ...     ("GND", (20, 20), (60, 60)),
        ... ]
        >>> routes, trace = route_all_with_trace(router, net_routes, True)
        >>> print(trace.why("VCC"))
        >>> print(trace.why("GND"))
    """
    routes = {}
    combined_trace = Trace.empty()

    for net_name, start, end in net_routes:
        path, trace = route_net_with_trace(
            router, net_name, start, end,
            allow_layer_change=allow_layer_change
        )
        routes[net_name] = path
        combined_trace = combined_trace + trace  # Monoid composition!

    return routes, combined_trace


def analyze_route_path(
    path: list[GridCell],
    net_name: str,
) -> Trace:
    """Analyze a route path and generate trace explaining its characteristics.
    
    Args:
        path: List of grid cells forming the route
        net_name: Name of the net
        
    Returns:
        Trace with path analysis
        
    Example:
        >>> trace = analyze_route_path(path, "VCC")
        >>> print(trace.why("VCC"))
        VCC path characteristics:
          - Length: 45 cells
          - Vias: 2
    """
    trace = Trace.empty()

    # Count vias
    via_count = sum(
        1 for i in range(len(path) - 1)
        if path[i].layer != path[i+1].layer
    )

    # Record path characteristics
    trace = trace.add(
        net_name,
        len(path),
        f"Path length: {len(path)} cells"
    )

    if via_count > 0:
        trace = trace.add(
            net_name,
            via_count,
            f"Used {via_count} via{'s' if via_count > 1 else ''}"
        )

    return trace
