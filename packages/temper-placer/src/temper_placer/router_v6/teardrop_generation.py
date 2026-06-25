"""
Router V6 Stage 5.3: Insert Teardrops

Adds teardrops to pad/via connections for improved reliability.
Part of temper-q5dh (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import warnings

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class Teardrop:
    """A teardrop at a pad/via connection."""

    net_name: str
    connection_point: tuple[float, float]  # Where trace meets pad/via
    connection_type: str  # "via" or "pad"
    length_mm: float  # Teardrop length along trace
    width_mm: float  # Teardrop width at widest point
    layer: str  # PCB layer name (e.g. "F.Cu", "B.Cu")


@dataclass
class TeardropReport:
    """Report of generated teardrops."""

    teardrops: list[Teardrop]

    @property
    def teardrop_count(self) -> int:
        """Total number of teardrops generated."""
        return len(self.teardrops)

    @property
    def via_teardrop_count(self) -> int:
        """Number of via teardrops."""
        return sum(1 for t in self.teardrops if t.connection_type == "via")

    @property
    def pad_teardrop_count(self) -> int:
        """Number of pad teardrops."""
        return sum(1 for t in self.teardrops if t.connection_type == "pad")


def insert_teardrops(
    routing_results: RoutingResults,
    teardrop_length_ratio: float = 0.5,  # Length as ratio of pad/via diameter
    enable_via_teardrops: bool = True,
    enable_pad_teardrops: bool = False,  # Usually not needed for SMD pads
) -> TeardropReport:
    """
    Insert teardrops at pad/via connections.

    Teardrops provide gradual transition from narrow trace to wide pad/via,
    reducing mechanical stress and improving manufacturability.

    .. note::
        ``enable_pad_teardrops=True`` is currently a no-op; pad teardrop
        generation is not yet implemented.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        teardrop_length_ratio: Teardrop length as ratio of connection diameter.
            Clamped to [0.1, 1.0]; values outside this range emit a warning.
        enable_via_teardrops: Whether to add teardrops to vias
        enable_pad_teardrops: Whether to add teardrops to pads (currently no-op)

    Returns:
        TeardropReport with all generated teardrops

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = insert_teardrops(results)
        >>> report.teardrop_count >= 0
        True
    """
    # Clamp teardrop_length_ratio to sensible range
    if teardrop_length_ratio < 0.1 or teardrop_length_ratio > 1.0:
        warnings.warn(
            f"teardrop_length_ratio={teardrop_length_ratio} is outside [0.1, 1.0]; "
            f"clamping to [{max(0.1, min(teardrop_length_ratio, 1.0))}]."
        )
        teardrop_length_ratio = max(0.1, min(teardrop_length_ratio, 1.0))

    teardrops = []

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Add teardrops to vias if enabled
        if enable_via_teardrops:
            for via in compiled_route.vias:
                teardrop = _generate_via_teardrop(
                    net_name,
                    via,
                    compiled_route,
                    teardrop_length_ratio,
                )
                if teardrop:
                    teardrops.append(teardrop)

        # Add teardrops to pads if enabled
        if enable_pad_teardrops:
            # Would analyze path endpoints and add pad teardrops
            # Simplified for now - SMD pads typically don't need teardrops
            pass

    return TeardropReport(teardrops=teardrops)


def _generate_via_teardrop(
    net_name: str,
    via,
    compiled_route,
    length_ratio: float,
) -> Teardrop | None:
    """
    Generate teardrop for a via connection.

    Only generates a teardrop when a path segment on the compiled route's
    layer connects to this via.  The connection point is placed at the via
    annulus perimeter (offset from via centre by half the diameter toward
    the trace), and the teardrop width tapers from the trace width to at
    most ``min(via.diameter * 0.6, trace_width * 2)``.

    Args:
        net_name: Net name
        via: Via object
        compiled_route: ``CompiledRoute`` that owns this via
        length_ratio: Teardrop length ratio (already clamped)

    Returns:
        Teardrop or None if not needed
    """
    # Guard: skip vias with non-positive diameter
    if via.diameter <= 0:
        warnings.warn(
            f"Via at {via.position} for net '{net_name}' has diameter "
            f"{via.diameter} <= 0; skipping teardrop."
        )
        return None

    # Guard: only generate teardrop if the compiled route's path is on a
    # layer that this via touches.
    path_layer = getattr(compiled_route.path, "layer_name", None)
    if path_layer is None:
        return None
    if path_layer not in (via.from_layer, via.to_layer):
        return None

    # Find the path coordinate closest to the via position to determine
    # the trace approach direction.
    coords = compiled_route.path.coordinates
    if len(coords) < 2:
        return None  # no segment to infer direction from

    via_pos = via.position
    # Locate the coordinate nearest to the via centre
    nearest_idx = min(
        range(len(coords)),
        key=lambda i: math.hypot(coords[i][0] - via_pos[0], coords[i][1] - via_pos[1]),
    )

    # Pick a neighbour to compute the trace direction from the via outward.
    # Prefer the next coordinate; fall back to the previous one.
    if nearest_idx < len(coords) - 1:
        neighbour = coords[nearest_idx + 1]
    else:
        neighbour = coords[nearest_idx - 1]

    dx = neighbour[0] - via_pos[0]
    dy = neighbour[1] - via_pos[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return None  # coincident points — cannot determine direction

    # Unit vector from via centre toward the trace
    ux = dx / dist
    uy = dy / dist

    # Connection point at via annulus perimeter
    connection_point = (
        via_pos[0] + ux * via.diameter / 2.0,
        via_pos[1] + uy * via.diameter / 2.0,
    )

    # Calculate teardrop dimensions
    trace_width = compiled_route.width_mm
    teardrop_length = via.diameter * length_ratio
    teardrop_width = min(via.diameter * 0.6, trace_width * 2.0)

    # Only add teardrop if via is at least as large as the threshold
    if via.diameter >= trace_width * 1.2:
        return Teardrop(
            net_name=net_name,
            connection_point=connection_point,
            connection_type="via",
            length_mm=teardrop_length,
            width_mm=teardrop_width,
            layer=path_layer,
        )

    return None
