"""Pinned Python oracle for Wave-4 heuristics/ -- style.py.

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
Everything below the module docstring is a **verbatim** ``git show``
extraction of commit ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5``
("docs(plans): board regeneration proposal for wasm-tier R3 (Q2) (#669)", the
last commit that touched this file; ``origin/main`` at the time this
migration was pulled remains at the same text -- see
``test_oracle_is_verbatim_copy``, which re-extracts the pinned commit via
``git show`` and compares byte-for-byte against everything in this file from
``from __future__ import annotations`` onward) of
``packages/temper-placer/src/temper_placer/heuristics/style.py``.

Nothing below the marker line has been cleaned up, refactored, reformatted,
or fixed -- not even the module docstring the original file itself carried
(dropped here only because *this* file needs its own, to record the pin).
Any drift (a "helpful" fix, a reformat, a reordered import) fails
``test_oracle_is_verbatim_copy`` instead of passing quietly.

Why this file, not `structural.py`'s narrower per-function pin
-----------------------------------------------------------------
Same reasoning as `organizational.py`'s oracle
(`_organizational_py_oracle.py`): `style.py` has no single standalone
function like `structural.py`'s `create_keepout_mask`. Its two real compute
sites (`_place_radially`, `_place_by_flow`) are private methods on two
`Heuristic` subclasses, each reached only through that class's public
`apply()`, which also calls this module's *classification* helpers
(`identify_ground_domains`, `extract_signal_chains`, `_trace_signal_path`) --
regex/keyword lookup tables and graph-walk bookkeeping, not compute (see the
program's own "keyword lookup tables are NOT compute" rule), but load-bearing
for `apply()` to run standalone here. Pinning the whole module, verbatim, is
what lets the differential call each `XxxHeuristic().apply(context)` exactly
as production does (proving the kernels through their real entry point, not
a synthetic shim) without also re-implementing the classification helpers a
second time in the oracle.

Traps this pin exercises (see
``packages/temper-geometry/src/style_geometry.rs``'s module doc for the
Rust-side mirror of each)
--------------------------------------------------------------------------
* ``_place_radially``'s sector angles (``domain_angles``) are built from a
  **hardcoded pi approximation**, ``3.14159 * 0.25`` etc -- not ``math.pi``.
  Unlike `organizational.py`'s `circle_offsets`, the inexact constant is
  folded into the dict *before* the Rust boundary, so `angle_start`/
  `angle_end` arrive as plain floats already carrying the approximation.
* ``_place_radially``'s ``t = i / (n - 1) if n > 1 else 0.5`` -- the same
  interpolation shape as `organizational.py`'s kernels, but note ``n`` here
  is re-derived as ``len(refs)`` *inside* the loop (constant across
  iterations, just written redundantly).
* ``_place_by_flow``'s ``max_pos = max(n.position for n in nodes) if nodes
  else 1`` is computed from the chain's FULL node list, **before** the
  per-node ``if node.ref in context.current_placements: continue`` /
  ``if ... .fixed: continue`` skip-checks run. A naive port that filters
  nodes first and computes `max_pos` from the filtered subset changes the
  denominator whenever the skipped node held the chain's maximum position.
* ``_place_by_flow``'s ``t = node.position / max_pos if max_pos > 0 else
  0.5`` -- a single-node chain has ``position == 0``, so ``max_pos == 0``
  and this hits the ``else`` branch (midpoint), not a division by zero.
* ``extract_signal_chains``/``_trace_signal_path`` use a ``set`` (``visited``
  / ``exclude``) only for **membership testing** (``ref not in exclude``),
  never iterated for output order -- unlike `organizational.py`'s
  `_find_highly_connected_groups`, there is no PYTHONHASHSEED-dependent
  ordering to re-project through `order_refs_by_netlist` here, because
  `input_connectors` and each net's `pins` are plain lists (netlist-order,
  deterministic) throughout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

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

                pos_x = sx + radius * float(np.cos(angle))
                pos_y = sy + radius * float(np.sin(angle))

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
