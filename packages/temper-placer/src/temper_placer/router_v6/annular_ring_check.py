"""
Router V6 Stage 5.2: Check Annular Rings

Validates that via annular rings meet minimum manufacturing requirements.
Part of temper-j2xd (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from temper_placer.router_v6._check_report_base import BaseCheckReport
from temper_placer.router_v6.routing_results import RoutingResults

logger = logging.getLogger(__name__)

# External (outer) layer names per the standard 4-layer stack.
_EXTERNAL_LAYERS: frozenset[str] = frozenset({"F.Cu", "B.Cu"})

# IPC-6016 Class 2 microvia annular ring minimum (mm).
_MICROVIA_DEFAULT_RING_MM: float = 0.025


def _is_external_layer(layer_name: str) -> bool:
    """Return True if *layer_name* is an outer/external copper layer."""
    return layer_name in _EXTERNAL_LAYERS


@dataclass
class AnnularRingViolation:
    """An annular ring violation on a via."""

    net_name: str
    via_position: tuple[float, float]
    pad_diameter: float  # Via pad diameter (mm)
    drill_diameter: float  # Via drill diameter (mm)
    actual_ring_width: float  # Actual annular ring width (mm)
    minimum_required: float  # Minimum required ring width (mm)

    @property
    def deficiency(self) -> float:
        """How much the ring is undersized."""
        return self.minimum_required - self.actual_ring_width


@dataclass
class AnnularRingReport(BaseCheckReport):
    """Report of annular ring violations."""

    _denominator_field = "total_vias_checked"

    violations: list[AnnularRingViolation]
    total_vias_checked: int


def _check_via(
    via: object,
    net_name: str,
    min_annular_ring: float,
    microvia_ring_mm: float,
) -> AnnularRingViolation | None:
    """Check a single via and return a violation if the ring is undersized.

    Args:
        via: A Via-like object with ``diameter``, ``drill``, ``position``,
            ``from_layer``, and ``to_layer`` attributes.  It may optionally
            carry a ``via_type`` attribute (e.g. ``"microvia"``).
        net_name: Net name for the violation report.
        min_annular_ring: Base minimum annular ring for external layers (mm).
        microvia_ring_mm: Annular ring threshold for microvias (mm).

    Returns:
        An ``AnnularRingViolation`` if the via fails, or ``None``.
    """
    # ---- guard: NaN / zero / negative drill produces invalid ring widths ----
    if (
        math.isnan(via.drill)  # type: ignore[attr-defined]
        or math.isnan(via.diameter)  # type: ignore[attr-defined]
        or via.drill <= 0.0  # type: ignore[attr-defined]
    ):
        logger.warning(
            "Via at %s on net %s has non-positive drill %.4f mm; skipping.",
            getattr(via, "position", "?"),
            net_name,
            via.drill,  # type: ignore[attr-defined]
        )
        return None

    # Calculate annular ring width
    # Ring width = (pad_diameter - drill_diameter) / 2
    ring_width = (via.diameter - via.drill) / 2.0  # type: ignore[attr-defined]

    # ---- layer-aware threshold ----
    # IPC-6012: external layers use the full *min_annular_ring*;
    # internal layers use half that value.
    from_layer: str = getattr(via, "from_layer", "")
    to_layer: str = getattr(via, "to_layer", "")
    if _is_external_layer(from_layer) or _is_external_layer(to_layer):
        threshold = min_annular_ring
    else:
        threshold = min_annular_ring * 0.5

    # ---- via-type override: microvias use IPC-6016 threshold ----
    via_type: str | None = getattr(via, "via_type", None)
    if via_type == "microvia":
        threshold = microvia_ring_mm

    # ---- guard: NaN threshold produces meaningless comparisons ----
    if math.isnan(threshold):
        logger.warning(
            "Via at %s on net %s has NaN threshold; skipping.",
            getattr(via, "position", "?"),
            net_name,
        )
        return None

    # ---- violation check (<= so boundary values are caught; ----
    # ---- small epsilon tolerates IEEE-754 rounding error)     ----
    _FP_EPSILON = 1e-12
    if ring_width <= threshold + _FP_EPSILON:
        return AnnularRingViolation(
            net_name=net_name,
            via_position=via.position,  # type: ignore[attr-defined]
            pad_diameter=via.diameter,  # type: ignore[attr-defined]
            drill_diameter=via.drill,  # type: ignore[attr-defined]
            actual_ring_width=ring_width,
            minimum_required=threshold,
        )

    return None


def check_annular_rings(
    routing_results: RoutingResults,
    min_annular_ring: float = 0.05,  # IPC-6012 Class 2: 0.05 mm minimum
    extra_vias: list | None = None,
    microvia_ring_mm: float = _MICROVIA_DEFAULT_RING_MM,
) -> AnnularRingReport:
    """
    Check via annular rings for manufacturing compliance.

    The annular ring is the copper remaining around the drill hole.
    Too small = unreliable connection, drill wander risk.

    **Layer-aware thresholds** (IPC-6012):
    Vias touching an external layer (``F.Cu`` / ``B.Cu``) are checked
    against *min_annular_ring*; vias confined to internal layers are
    checked against ``min_annular_ring * 0.5``.

    **Via-type thresholds** (IPC-6016):
    Vias with ``via_type == "microvia"`` use *microvia_ring_mm*
    (default 0.025 mm) regardless of layer.

    Args:
        routing_results: Compiled routing results from Stage 4.9.
        min_annular_ring: Minimum annular ring width for external
            layers (mm).  Must be > 0.
        extra_vias: Optional additional list of Via-like objects to
            check outside of ``compiled_routes``.
        microvia_ring_mm: Annular ring threshold for microvias (mm).

    Returns:
        AnnularRingReport with violations.

    Raises:
        ValueError: If *min_annular_ring* is not positive.

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = check_annular_rings(results)
        >>> report.violation_count >= 0
        True
    """
    # ---- validate input ----
    if math.isnan(min_annular_ring) or min_annular_ring <= 0.0:
        raise ValueError(
            f"min_annular_ring must be > 0, got {min_annular_ring}"
        )

    violations: list[AnnularRingViolation] = []
    total_vias = 0

    # ---- vias from compiled routes ----
    for net_name, compiled_route in routing_results.compiled_routes.items():
        for via in compiled_route.vias:
            total_vias += 1
            violation = _check_via(via, net_name, min_annular_ring, microvia_ring_mm)
            if violation is not None:
                violations.append(violation)

    # ---- extra vias (outside compiled_routes) ----
    if extra_vias:
        for via in extra_vias:
            total_vias += 1
            net_name: str = getattr(via, "net_name", "(extra)")
            violation = _check_via(via, net_name, min_annular_ring, microvia_ring_mm)
            if violation is not None:
                violations.append(violation)

    return AnnularRingReport(
        violations=violations,
        total_vias_checked=total_vias,
    )
