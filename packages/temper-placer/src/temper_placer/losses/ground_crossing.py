"""
Ground crossing loss function.

This module penalizes nets that cross between ground domains without going
through designated star ground points.

For split-ground designs like the Temper board:
- PGND: Power ground (HV section)
- CGND: Control ground (LV digital)
- ISOGND: Isolated ground (gate driver)

Signals crossing between domains can cause ground loops, EMI issues, and
measurement errors. This loss ensures signals either stay within a domain
or cross only at designated star points.
"""

from __future__ import annotations

from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import GroundDomain
from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
)


def _get_domain_for_position(
    position: Array,
    domains: list[GroundDomain],
) -> str | None:
    """
    Get the ground domain containing a position.

    Args:
        position: (2,) position [x, y] in mm.
        domains: List of ground domains to check.

    Returns:
        Domain name or None if outside all domains.
    """
    x, y = float(position[0]), float(position[1])
    for domain in domains:
        if domain.contains_point(x, y):
            return domain.name
    return None


def compute_crossing_penalty_for_pair(
    pos1: Array,
    pos2: Array,
    domains: list[GroundDomain],
    star_points: dict[str, Array],
    penalty_weight: float = 1.0,
) -> Array:
    """
    Compute ground crossing penalty for a pair of connected pins.

    Args:
        pos1: (2,) first pin position.
        pos2: (2,) second pin position.
        domains: List of ground domains.
        star_points: Dict mapping domain name -> star point position.
        penalty_weight: Weight for this crossing.

    Returns:
        Penalty scalar (0 if no violation, positive otherwise).
    """
    # This is a simplified Python implementation
    # Full vectorized JAX version would need pre-computed domain masks
    x1, y1 = float(pos1[0]), float(pos1[1])
    x2, y2 = float(pos2[0]), float(pos2[1])

    domain1 = None
    domain2 = None

    for domain in domains:
        if domain.contains_point(x1, y1):
            domain1 = domain.name
        if domain.contains_point(x2, y2):
            domain2 = domain.name

    # No penalty if same domain or either outside all domains
    if domain1 is None or domain2 is None or domain1 == domain2:
        return jnp.array(0.0)

    # Check if either endpoint is near a star point
    for domain in domains:
        if domain.star_point is not None:
            sp = jnp.array(domain.star_point, dtype=jnp.float32)
            d1 = jnp.sqrt(jnp.sum((pos1 - sp) ** 2))
            d2 = jnp.sqrt(jnp.sum((pos2 - sp) ** 2))
            star_threshold = 5.0  # mm - near star point

            if d1 < star_threshold or d2 < star_threshold:
                # Crossing near star point is allowed
                return jnp.array(0.0)

    # Penalty is based on the length of the crossing
    crossing_length = jnp.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    return penalty_weight * crossing_length


def compute_ground_crossing_penalty(
    positions: Array,
    context: LossContext,
) -> Array:
    """
    Compute total ground crossing penalty for all nets.

    This function checks each net's pin-to-pin connections and penalizes
    any that cross ground domain boundaries (except at star points).

    Args:
        positions: (N, 2) component center positions.
        context: LossContext with board ground domains.

    Returns:
        Total crossing penalty (scalar).

    Note:
        This is a simplified implementation that uses Python loops.
        For full JIT compatibility with large netlists, this should be
        rewritten to use pre-computed domain masks and vectorized operations.
    """
    if not context.board.ground_domains:
        return jnp.array(0.0)

    domains = context.board.ground_domains

    # Build star points dict
    star_points: dict[str, Array] = {}
    for domain in domains:
        if domain.star_point is not None:
            star_points[domain.name] = jnp.array(domain.star_point, dtype=jnp.float32)

    total_penalty = jnp.array(0.0)

    # Check each net's connections
    for net in context.netlist.nets:
        if len(net.pins) < 2:
            continue

        # Get pin positions
        pin_positions = []
        for comp_ref, pin_name in net.pins:
            try:
                comp_idx = context.netlist.get_component_index(comp_ref)
                comp = context.netlist.get_component(comp_ref)
                pin = comp.get_pin(pin_name)

                pos = positions[comp_idx]
                if pin is not None:
                    pos = pos + jnp.array(pin.position, dtype=jnp.float32)
                pin_positions.append(pos)
            except KeyError:
                continue

        # Check consecutive pin pairs (approximation of routing)
        for i in range(len(pin_positions) - 1):
            penalty = compute_crossing_penalty_for_pair(
                pin_positions[i],
                pin_positions[i + 1],
                domains,
                star_points,
            )
            total_penalty = total_penalty + penalty

    return total_penalty


@dataclass
class GroundCrossingLoss(LossFunction):
    """
    Loss function penalizing nets that cross ground domain boundaries.

    For split-ground PCB designs, signals should either:
    1. Stay entirely within one ground domain
    2. Cross domains only at designated star ground points

    Crossing elsewhere can cause ground loops and EMI issues.

    The penalty is proportional to the crossing length, encouraging
    shorter crossings when they're unavoidable.

    Note:
        Current implementation uses Python loops and is not fully JIT-compatible.
        For large netlists (>100 nets), consider pre-computing domain masks
        for vectorized evaluation.
    """

    @property
    def name(self) -> str:
        return "ground_crossing"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute ground crossing loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with board ground domains.

        Returns:
            LossResult with total crossing penalty.
        """
        penalty = compute_ground_crossing_penalty(positions, context)
        return LossResult(value=penalty)


def detect_ground_domain_violations(
    positions: Array,
    context: LossContext,
) -> list[dict]:
    """
    Detect and report all ground domain violations for debugging.

    Args:
        positions: (N, 2) component positions.
        context: LossContext with netlist and board.

    Returns:
        List of violation dicts with net name, pin pair, and domains.
    """
    violations = []

    if not context.board.ground_domains:
        return violations

    domains = context.board.ground_domains

    for net in context.netlist.nets:
        if len(net.pins) < 2:
            continue

        # Get pin domains
        pin_info = []
        for comp_ref, pin_name in net.pins:
            try:
                comp_idx = context.netlist.get_component_index(comp_ref)
                comp = context.netlist.get_component(comp_ref)
                pin = comp.get_pin(pin_name)

                pos = positions[comp_idx]
                if pin is not None:
                    pos = pos + jnp.array(pin.position, dtype=jnp.float32)

                domain = _get_domain_for_position(pos, domains)
                pin_info.append(
                    {
                        "comp_ref": comp_ref,
                        "pin_name": pin_name,
                        "position": (float(pos[0]), float(pos[1])),
                        "domain": domain,
                    }
                )
            except KeyError:
                continue

        # Check for domain crossings
        domains_in_net = set(p["domain"] for p in pin_info if p["domain"] is not None)
        if len(domains_in_net) > 1:
            violations.append(
                {
                    "net": net.name,
                    "domains": list(domains_in_net),
                    "pins": pin_info,
                }
            )

    return violations
