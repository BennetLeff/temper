"""
Style placement heuristics.

Style heuristics handle aesthetic and review-friendly placement:
- Star ground topology
- Signal flow preservation (left-to-right)

These run at STYLE priority (lowest), after all functional constraints are satisfied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.io.config_loader import PlacementConstraints

# =============================================================================
# Star Ground Topology Heuristic (STYLE priority)
# =============================================================================


def identify_ground_domains(
    netlist: Netlist,
    _constraints: PlacementConstraints,
) -> dict[str, str]:
    """
    Identify which ground domain each component belongs to.

    Ground domains:
    - "PGND": Power ground (high current returns)
    - "DGND": Digital ground (MCU, logic)
    - "AGND": Analog ground (sensors, precision circuits)

    Returns:
        Dict mapping component ref to ground domain name
    """
    domains: dict[str, str] = {}

    # Domain classification patterns
    power_patterns = [
        r"^Q\d+",  # Transistors
        r"^U.*BUCK",
        r"^U.*GATE",
        r"^U.*DRV",
        r"^L\d+",  # Inductors
        r"^C.*BULK",
    ]

    analog_patterns = [
        r"^U.*OPAMP",
        r"^U.*ADC",
        r"^U.*SENS",
        r"^U.*TEMP",
        r"^R.*SENSE",
    ]

    digital_patterns = [
        r"^U.*MCU",
        r"^U.*FLASH",
        r"^Y\d+",  # Crystals
    ]

    for comp in netlist.components:
        domain = "DGND"  # Default to digital

        # Check patterns
        for pattern in power_patterns:
            if re.match(pattern, comp.ref, re.IGNORECASE):
                domain = "PGND"
                break

        if domain == "DGND":
            for pattern in analog_patterns:
                if re.match(pattern, comp.ref, re.IGNORECASE):
                    domain = "AGND"
                    break

        if domain == "DGND":
            for pattern in digital_patterns:
                if re.match(pattern, comp.ref, re.IGNORECASE):
                    domain = "DGND"
                    break

        # Check net names for ground classification
        comp_nets = netlist.get_component_nets(comp.ref)
        for net_name in comp_nets:
            net_upper = net_name.upper()
            if "PGND" in net_upper or "PWRGND" in net_upper:
                domain = "PGND"
                break
            elif "AGND" in net_upper or "ANALOGGND" in net_upper:
                domain = "AGND"
                break
            elif "DGND" in net_upper or "DIGITALGND" in net_upper:
                domain = "DGND"
                break

        domains[comp.ref] = domain

    return domains


class StarGroundTopologyHeuristic(Heuristic):
    """
    Position components to enable star ground topology.

    Star ground topology:
    - Routes ground returns radially from a single point
    - Prevents high-current ground from flowing under sensitive circuits
    - Separates power, analog, and digital grounds

    Components are arranged in radial "slices" from the star point.
    """

    def __init__(self, star_point: tuple[float, float] | None = None):
        """
        Initialize star ground heuristic.

        Args:
            star_point: Optional (x, y) star ground point. If None, uses
                board center or star point from constraints.
        """
        self.star_point = star_point

    @property
    def name(self) -> str:
        return "star_ground_topology"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.STYLE

    @property
    def description(self) -> str:
        return "Arranges components for star ground topology"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Arrange components radially from star point."""
        domains = identify_ground_domains(context.netlist, context.constraints)

        # Determine star point
        star_point = self._get_star_point(context.board, context.constraints)

        placements = self._place_radially(
            domains=domains,
            star_point=star_point,
            board=context.board,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} components in star pattern",
        )

    def _get_star_point(
        self,
        board: Board,
        _constraints: PlacementConstraints,
    ) -> tuple[float, float]:
        """Get the star ground point."""
        if self.star_point:
            return self.star_point

        # Check for star point in ground domains
        for domain in board.ground_domains:
            if domain.star_point:
                return domain.star_point

        # Default to left-center of board (near power input)
        ox, oy = board.origin
        return (ox + board.width * 0.25, oy + board.height * 0.5)

    def _place_radially(
        self,
        domains: dict[str, str],
        star_point: tuple[float, float],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place components radially by ground domain."""
        placements: dict[str, ComponentPlacement] = {}
        sx, sy = star_point

        # Define angular sectors for each domain (in radians)
        # PGND: top sector (power typically at top)
        # DGND: right sector (digital at right)
        # AGND: bottom-right sector (analog isolated)
        domain_angles = {
            "PGND": (3.14159 * 0.25, 3.14159 * 0.75),  # 45deg to 135deg (top)
            "DGND": (-3.14159 * 0.25, 3.14159 * 0.25),  # -45deg to 45deg (right)
            "AGND": (-3.14159 * 0.75, -3.14159 * 0.25),  # -135deg to -45deg (bottom-right)
        }

        # Group components by domain
        domain_components: dict[str, list[str]] = {"PGND": [], "DGND": [], "AGND": []}
        for ref, domain in domains.items():
            if (
                ref not in context.current_placements
                and not context.netlist.get_component(ref).fixed
            ):
                domain_components[domain].append(ref)

        # Place each domain
        for domain, refs in domain_components.items():
            if not refs:
                continue

            angle_start, angle_end = domain_angles[domain]
            angle_range = angle_end - angle_start

            # Determine radius range (from star point to board edge)
            min_radius = 15.0  # Keep some distance from star point
            max_radius = min(board.width, board.height) * 0.4

            for i, ref in enumerate(refs):
                comp = context.netlist.get_component(ref)

                # Distribute within sector
                n = len(refs)
                t = i / (n - 1) if n > 1 else 0.5

                angle = angle_start + t * angle_range
                radius = min_radius + t * (max_radius - min_radius)

                pos_x = sx + radius * float(jnp.cos(angle))
                pos_y = sy + radius * float(jnp.sin(angle))

                if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                    placements[ref] = ComponentPlacement(
                        ref=ref,
                        position=(pos_x, pos_y),
                        rotation=0,
                        confidence=0.5,
                        placed_by=self.name,
                    )

        return placements


# =============================================================================
# Signal Flow Preservation Heuristic (STYLE priority)
# =============================================================================


@dataclass
class SignalChainNode:
    """A node in a signal chain."""

    ref: str
    chain_name: str
    position: int  # 0 = start, higher = later in chain


def extract_signal_chains(
    netlist: Netlist,
    _constraints: PlacementConstraints,
) -> list[SignalChainNode]:
    """
    Extract signal chains from netlist connectivity.

    Signal chains are sequences of components connected by signal nets:
    - Input connector -> Filter -> MCU
    - Sensor -> Amplifier -> ADC
    - MCU -> Gate Driver -> Power Stage

    Returns:
        List of SignalChainNode with chain assignments
    """
    nodes: list[SignalChainNode] = []

    # Simple heuristic: trace from connectors through ICs
    # Find input connectors
    input_connectors = []
    for comp in netlist.components:
        if comp.ref.startswith("J") and any(x in comp.ref.upper() for x in ["IN", "INPUT", "SENS"]):
            input_connectors.append(comp.ref)

    # For each input, trace the signal path
    visited: set[str] = set()

    for chain_id, start_ref in enumerate(input_connectors):
        chain_components = _trace_signal_path(netlist, start_ref, visited)
        for pos, ref in enumerate(chain_components):
            nodes.append(SignalChainNode(ref=ref, chain_name=f"chain_{chain_id}", position=pos))
            visited.add(ref)

    return nodes


def _trace_signal_path(
    netlist: Netlist,
    start_ref: str,
    exclude: set[str],
    max_depth: int = 10,
) -> list[str]:
    """Trace a signal path from a starting component."""
    path = [start_ref]
    current = start_ref
    depth = 0

    while depth < max_depth:
        # Find next component in chain (connected by signal net, not power)
        next_comp = None
        for net_name in netlist.get_component_nets(current):
            try:
                net = netlist.get_net(net_name)
            except KeyError:
                continue

            # Skip power nets
            if net.net_class == "Power":
                continue

            for ref, _ in net.pins:
                if ref != current and ref not in exclude and ref not in path:
                    # Prefer ICs over passives
                    if ref.startswith("U"):
                        next_comp = ref
                        break
                    elif next_comp is None:
                        next_comp = ref

            if next_comp and next_comp.startswith("U"):
                break

        if next_comp is None:
            break

        path.append(next_comp)
        current = next_comp
        depth += 1

    return path


class SignalFlowPreservationHeuristic(Heuristic):
    """
    Arrange components following signal flow direction.

    Engineers expect signals to flow in predictable directions:
    - Left-to-right for main signal path
    - Input on left, output on right

    This makes layouts readable and easy to review.
    """

    def __init__(self, flow_direction: str = "left_to_right"):
        """
        Initialize signal flow heuristic.

        Args:
            flow_direction: "left_to_right" or "top_to_bottom"
        """
        self.flow_direction = flow_direction

    @property
    def name(self) -> str:
        return "signal_flow_preservation"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.STYLE

    @property
    def description(self) -> str:
        return "Arranges components following signal flow direction"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Arrange components by signal flow."""
        chains = extract_signal_chains(context.netlist, context.constraints)

        if not chains:
            return HeuristicResult(
                placements={},
                success=True,
                message="No signal chains identified",
            )

        placements = self._place_by_flow(
            chains=chains,
            board=context.board,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} components by signal flow",
        )

    def _place_by_flow(
        self,
        chains: list[SignalChainNode],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place components according to signal flow."""
        placements: dict[str, ComponentPlacement] = {}
        ox, oy = board.origin
        margin = context.constraints.board_margin_mm

        # Group by chain
        chain_groups: dict[str, list[SignalChainNode]] = {}
        for node in chains:
            if node.chain_name not in chain_groups:
                chain_groups[node.chain_name] = []
            chain_groups[node.chain_name].append(node)

        # Sort each chain by position
        for _chain_name, nodes in chain_groups.items():
            nodes.sort(key=lambda n: n.position)

        # Place chains (stacked vertically, flowing horizontally)
        n_chains = len(chain_groups)
        chain_height = (board.height - 2 * margin) / max(n_chains, 1)

        for chain_idx, (_chain_name, nodes) in enumerate(chain_groups.items()):
            # Find max position for normalization
            max_pos = max(n.position for n in nodes) if nodes else 1

            y_center = oy + margin + (chain_idx + 0.5) * chain_height

            for node in nodes:
                if node.ref in context.current_placements:
                    continue
                if context.netlist.get_component(node.ref).fixed:
                    continue

                comp = context.netlist.get_component(node.ref)

                # Position along X based on chain position
                t = node.position / max_pos if max_pos > 0 else 0.5
                pos_x = ox + margin + t * (board.width - 2 * margin)
                pos_y = y_center

                if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                    placements[node.ref] = ComponentPlacement(
                        ref=node.ref,
                        position=(pos_x, pos_y),
                        rotation=0,
                        confidence=0.4,
                        placed_by=self.name,
                    )

        return placements
