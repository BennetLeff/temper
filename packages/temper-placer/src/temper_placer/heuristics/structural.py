"""
Structural placement heuristics.

Structural heuristics handle fundamental placement constraints:
- Keep-out zone avoidance (HARD priority - handled via placement mask)
- Connector edge snapping
- Thermal component edge placement
- Critical loop pre-minimization

These run early in the pipeline to establish the structural foundation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.io.config_loader import PlacementConstraints

# =============================================================================
# Keep-out Zone Heuristic (HARD priority)
# =============================================================================


def create_keepout_mask(
    board: Board,
    constraints: PlacementConstraints,
    resolution_mm: float = 1.0,
    buffer_mm: float = 1.0,
) -> Array:
    """
    Create a placement mask where True = valid placement, False = keep-out.

    This generates a 2D boolean array covering the board area at the given
    resolution. Keep-out regions include:
    - Board edges (board margin)
    - Mounting hole clearance zones
    - Explicit keepout_regions from board definition
    - Explicit zones from config (if any are marked as keepout)

    Args:
        board: Board definition with mounting holes, keepouts, etc.
        constraints: Placement constraints (board margin, etc.)
        resolution_mm: Grid resolution in mm (default 1.0)
        buffer_mm: Additional buffer around keepouts

    Returns:
        (H, W) boolean JAX array where True = valid for placement
    """
    ox, oy = board.origin
    width_cells = int(board.width / resolution_mm) + 1
    height_cells = int(board.height / resolution_mm) + 1

    # Start with all valid
    mask = jnp.ones((height_cells, width_cells), dtype=jnp.bool_)

    # Mark board edges as invalid (margin)
    margin = constraints.board_margin_mm + buffer_mm
    margin_cells = int(margin / resolution_mm)

    if margin_cells > 0:
        # Top and bottom edges
        mask = mask.at[:margin_cells, :].set(False)
        mask = mask.at[-margin_cells:, :].set(False)
        # Left and right edges
        mask = mask.at[:, :margin_cells].set(False)
        mask = mask.at[:, -margin_cells:].set(False)

    # Mark mounting holes as invalid
    for hole in board.mounting_holes:
        hx, hy = hole.position
        clearance = hole.keepout_radius + buffer_mm

        # Convert to mask coordinates
        cx = int((hx - ox) / resolution_mm)
        cy = int((hy - oy) / resolution_mm)
        cr = int(clearance / resolution_mm)

        # Create circular keepout
        for dy in range(-cr, cr + 1):
            for dx in range(-cr, cr + 1):
                if dx * dx + dy * dy <= cr * cr:
                    mx, my = cx + dx, cy + dy
                    if 0 <= mx < width_cells and 0 <= my < height_cells:
                        mask = mask.at[my, mx].set(False)

    # Mark explicit keepout regions
    for x_min, y_min, x_max, y_max in board.keepout_regions:
        # Add buffer
        x_min_buf = x_min - buffer_mm
        y_min_buf = y_min - buffer_mm
        x_max_buf = x_max + buffer_mm
        y_max_buf = y_max + buffer_mm

        # Convert to mask coordinates
        mx_min = max(0, int((x_min_buf - ox) / resolution_mm))
        my_min = max(0, int((y_min_buf - oy) / resolution_mm))
        mx_max = min(width_cells, int((x_max_buf - ox) / resolution_mm) + 1)
        my_max = min(height_cells, int((y_max_buf - oy) / resolution_mm) + 1)

        mask = mask.at[my_min:my_max, mx_min:mx_max].set(False)

    return mask


class KeepoutAwarenessHeuristic(Heuristic):
    """
    Keep-out zone awareness - creates placement mask but doesn't place components.

    This heuristic runs at HARD priority and sets up the keep_out_mask in the
    context. Subsequent heuristics and random fill will respect this mask.

    The mask is created from:
    - Board edges with margin
    - Mounting hole clearance zones
    - Explicit keepout regions
    """

    def __init__(self, resolution_mm: float = 1.0, buffer_mm: float = 1.0):
        """
        Initialize keepout heuristic.

        Args:
            resolution_mm: Mask resolution in mm
            buffer_mm: Additional buffer around keepouts
        """
        self.resolution_mm = resolution_mm
        self.buffer_mm = buffer_mm

    @property
    def name(self) -> str:
        return "keepout_awareness"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.HARD

    @property
    def description(self) -> str:
        return "Creates placement mask respecting keep-out zones"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """
        Create and set the keep-out mask in context.

        Note: This modifies context.keep_out_mask in place, which is then
        used by subsequent heuristics and the pipeline's random fill.
        """
        mask = create_keepout_mask(
            board=context.board,
            constraints=context.constraints,
            resolution_mm=self.resolution_mm,
            buffer_mm=self.buffer_mm,
        )

        # Update context with mask (mutation - the pipeline passes same context)
        # We use object.__setattr__ since context is a dataclass
        object.__setattr__(context, "keep_out_mask", mask)

        # Count valid cells for reporting
        valid_cells = int(jnp.sum(mask))
        total_cells = mask.size
        valid_pct = 100 * valid_cells / total_cells if total_cells > 0 else 0

        return HeuristicResult(
            placements={},  # This heuristic doesn't place components
            success=True,
            message=f"Created keepout mask: {valid_pct:.1f}% valid ({valid_cells}/{total_cells} cells)",
        )


# =============================================================================
# Connector Edge Snapping Heuristic (STRUCTURAL priority)
# =============================================================================


def identify_connectors(
    netlist: Netlist,
    _constraints: PlacementConstraints,
) -> list[tuple[Component, str]]:
    """
    Identify connector components and classify their purpose.

    Connectors are identified by:
    - Reference designator pattern (J*, P*, CON*)
    - Footprint containing connector keywords

    Returns list of (component, purpose) where purpose is one of:
    - "power_input": DC power input
    - "power_output": Power output
    - "signal": Signal I/O
    - "debug": Debug/programming interface
    - "unknown": Unclassified connector

    Args:
        netlist: Netlist with components
        constraints: Placement constraints (may have explicit classifications)

    Returns:
        List of (Component, purpose) tuples
    """
    connectors = []
    connector_patterns = [
        r"^J\d+",  # J1, J2, etc.
        r"^P\d+",  # P1, P2, etc.
        r"^CON\d*",  # CON, CON1, etc.
    ]

    footprint_keywords = [
        "conn",
        "header",
        "jst",
        "molex",
        "usb",
        "terminal",
        "barrel",
        "dc_jack",
    ]

    for comp in netlist.components:
        is_connector = False

        # Check reference designator
        for pattern in connector_patterns:
            if re.match(pattern, comp.ref, re.IGNORECASE):
                is_connector = True
                break

        # Check footprint name
        if not is_connector:
            fp_lower = comp.footprint.lower()
            for keyword in footprint_keywords:
                if keyword in fp_lower:
                    is_connector = True
                    break

        if is_connector:
            purpose = _classify_connector_purpose(comp, netlist)
            connectors.append((comp, purpose))

    return connectors


def _classify_connector_purpose(comp: Component, netlist: Netlist) -> str:
    """Classify connector purpose based on net names and attributes."""
    ref_lower = comp.ref.lower()
    fp_lower = comp.footprint.lower()

    # Check explicit naming patterns
    if any(x in ref_lower for x in ["dc", "pwr", "power", "vin", "vbus"]):
        return "power_input"
    if any(x in ref_lower for x in ["out", "load"]):
        return "power_output"
    if any(x in ref_lower for x in ["debug", "jtag", "swd", "uart", "prog"]):
        return "debug"

    # Check footprint for clues
    if any(x in fp_lower for x in ["barrel", "dc_jack", "power"]):
        return "power_input"
    if any(x in fp_lower for x in ["usb", "uart", "jtag", "swd"]):
        return "debug"

    # Check connected nets
    net_names = netlist.get_component_nets(comp.ref)
    for net in net_names:
        net_upper = net.upper()
        if any(x in net_upper for x in ["VIN", "VBUS", "+12V", "+24V", "+48V", "DC_IN"]):
            return "power_input"
        if "OUT" in net_upper and any(x in net_upper for x in ["V", "PWR"]):
            return "power_output"

    return "signal"


@dataclass
class EdgeAssignment:
    """Assignment of a connector to a board edge."""

    edge: str  # "left", "right", "top", "bottom"
    position: float  # Position along edge (0-1 normalized)
    rotation: int  # Rotation index for outward-facing


class ConnectorEdgeSnappingHeuristic(Heuristic):
    """
    Snap connectors to board edges with appropriate orientation.

    Edge assignment strategy:
    - Power input: Left edge (conventional)
    - Power output: Right edge or top
    - Debug: Bottom edge (accessible during development)
    - Signal: Distributed based on purpose

    The connector opening faces outward from the board.
    """

    def __init__(self, edge_margin_mm: float = 2.0, connector_spacing_mm: float = 10.0):
        """
        Initialize connector snapping heuristic.

        Args:
            edge_margin_mm: Distance from board edge for connector center
            connector_spacing_mm: Minimum spacing between connectors on same edge
        """
        self.edge_margin_mm = edge_margin_mm
        self.connector_spacing_mm = connector_spacing_mm

    @property
    def name(self) -> str:
        return "connector_edge_snapping"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.STRUCTURAL

    @property
    def description(self) -> str:
        return "Places connectors on board edges with outward orientation"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Place connectors on appropriate board edges."""
        connectors = identify_connectors(context.netlist, context.constraints)

        if not connectors:
            return HeuristicResult(
                placements={},
                success=True,
                message="No connectors found",
            )

        # Group connectors by target edge
        edge_assignments: dict[str, list[tuple[Component, str]]] = {
            "left": [],
            "right": [],
            "top": [],
            "bottom": [],
        }

        for comp, purpose in connectors:
            if comp.fixed:
                continue

            edge = self._get_target_edge(purpose)
            edge_assignments[edge].append((comp, purpose))

        # Place connectors on each edge
        placements: dict[str, ComponentPlacement] = {}
        conflicts: list[str] = []

        for edge, comps in edge_assignments.items():
            edge_placements = self._place_on_edge(
                edge=edge,
                components=comps,
                board=context.board,
                context=context,
            )
            placements.update(edge_placements)

        return HeuristicResult(
            placements=placements,
            conflicts=conflicts,
            success=True,
            message=f"Placed {len(placements)} connectors on edges",
        )

    def _get_target_edge(self, purpose: str) -> str:
        """Get target edge for connector based on purpose."""
        edge_map = {
            "power_input": "left",
            "power_output": "right",
            "debug": "bottom",
            "signal": "right",
            "unknown": "bottom",
        }
        return edge_map.get(purpose, "bottom")

    def _place_on_edge(
        self,
        edge: str,
        components: list[tuple[Component, str]],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place components along a board edge."""
        if not components:
            return {}

        placements = {}
        ox, oy = board.origin
        margin = self.edge_margin_mm

        # Determine edge parameters based on edge type
        # For left/right edges: vary Y position, fixed X
        # For top/bottom edges: vary X position, fixed Y
        if edge == "left":
            fixed_coord = ox + margin
            range_start = oy + board.height * 0.3
            range_end = oy + board.height * 0.7
            rotation = 3  # 270deg - opening faces left
            horizontal = False  # Component positions vary along Y
        elif edge == "right":
            fixed_coord = ox + board.width - margin
            range_start = oy + board.height * 0.3
            range_end = oy + board.height * 0.7
            rotation = 1  # 90deg - opening faces right
            horizontal = False
        elif edge == "top":
            fixed_coord = oy + board.height - margin
            range_start = ox + board.width * 0.3
            range_end = ox + board.width * 0.7
            rotation = 0  # 0deg - opening faces up
            horizontal = True  # Component positions vary along X
        else:  # bottom
            fixed_coord = oy + margin
            range_start = ox + board.width * 0.3
            range_end = ox + board.width * 0.7
            rotation = 2  # 180deg - opening faces down
            horizontal = True

        # Distribute components along edge
        n = len(components)
        for i, (comp, _purpose) in enumerate(components):
            t = i / (n - 1) if n > 1 else 0.5

            varying_coord = range_start + t * (range_end - range_start)

            if horizontal:
                pos_x = varying_coord
                pos_y = fixed_coord
            else:
                pos_x = fixed_coord
                pos_y = varying_coord

            # Check validity
            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[comp.ref] = ComponentPlacement(
                    ref=comp.ref,
                    position=(pos_x, pos_y),
                    rotation=rotation,
                    confidence=0.9,
                    placed_by=self.name,
                )

        return placements


# =============================================================================
# Thermal Component Edge Placement Heuristic (STRUCTURAL priority)
# =============================================================================


def identify_thermal_components(
    netlist: Netlist,
    constraints: PlacementConstraints,
    _power_threshold_w: float = 1.0,
) -> list[Component]:
    """
    Identify high-power/thermal components that need edge placement.

    Components are identified from:
    1. constraints.thermal_properties.high_power_components
    2. constraints.thermal_properties.thermal_pad_components
    3. Component type heuristics (IGBTs, MOSFETs, large inductors)

    Args:
        netlist: Netlist with components
        constraints: Placement constraints with thermal info
        _power_threshold_w: Power threshold for auto-detection

    Returns:
        List of thermal components
    """
    thermal_refs: set[str] = set()

    # From explicit config
    if constraints.thermal_properties:
        thermal_refs.update(constraints.thermal_properties.high_power_components)
        thermal_refs.update(constraints.thermal_properties.thermal_pad_components)

    # From thermal constraints
    for tc in constraints.thermal_constraints:
        thermal_refs.update(tc.components)

    # Auto-detect from component types
    power_patterns = [
        r"^Q\d+",  # Transistors (Q1, Q2)
        r"^U\w*IGBT",  # IGBTs
        r"^U\w*FET",  # FETs
        r"^D\d+.*PWR",  # Power diodes
    ]

    thermal_footprints = [
        "to-220",
        "to-247",
        "to-263",
        "d2pak",
        "dpak",
        "powerso",
        "hsop",
    ]

    for comp in netlist.components:
        # Skip already identified
        if comp.ref in thermal_refs:
            continue

        # Check reference patterns
        for pattern in power_patterns:
            if re.match(pattern, comp.ref, re.IGNORECASE):
                thermal_refs.add(comp.ref)
                break

        # Check footprint
        fp_lower = comp.footprint.lower()
        for kw in thermal_footprints:
            if kw in fp_lower:
                thermal_refs.add(comp.ref)
                break

    # Return components in netlist order
    return [c for c in netlist.components if c.ref in thermal_refs and not c.fixed]


class ThermalEdgePlacementHeuristic(Heuristic):
    """
    Place high-power/thermal components near board edges for heatsinking.

    Thermal components benefit from:
    - Proximity to board edge for external heatsinks
    - Better airflow access
    - Thermal via paths to chassis ground

    Components are placed along the top edge by default (common heatsink location),
    with minimum spacing between them.
    """

    def __init__(
        self,
        edge_distance_mm: float = 10.0,
        component_spacing_mm: float = 15.0,
        preferred_edge: str = "top",
    ):
        """
        Initialize thermal edge placement.

        Args:
            edge_distance_mm: Maximum distance from edge
            component_spacing_mm: Minimum spacing between thermal components
            preferred_edge: Preferred edge for thermal components
        """
        self.edge_distance_mm = edge_distance_mm
        self.component_spacing_mm = component_spacing_mm
        self.preferred_edge = preferred_edge

    @property
    def name(self) -> str:
        return "thermal_edge_placement"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.STRUCTURAL

    @property
    def description(self) -> str:
        return "Places thermal components near board edges for heatsinking"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Place thermal components along preferred edge."""
        thermal_comps = identify_thermal_components(
            context.netlist,
            context.constraints,
        )

        if not thermal_comps:
            return HeuristicResult(
                placements={},
                success=True,
                message="No thermal components identified",
            )

        placements = self._place_thermal_components(
            components=thermal_comps,
            board=context.board,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} thermal components near {self.preferred_edge} edge",
        )

    def _place_thermal_components(
        self,
        components: list[Component],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place thermal components along edge with spacing."""
        placements = {}
        ox, oy = board.origin

        # Determine edge parameters based on preferred edge
        # For top/bottom: horizontal placement (vary X, fixed Y)
        # For left/right: vertical placement (fixed X, vary Y)
        horizontal_edge = self.preferred_edge in ("top", "bottom")

        if self.preferred_edge == "top":
            fixed_coord = oy + board.height - self.edge_distance_mm
            range_start = ox + board.width * 0.2
            range_end = ox + board.width * 0.8
            rotation = 0
        elif self.preferred_edge == "bottom":
            fixed_coord = oy + self.edge_distance_mm
            range_start = ox + board.width * 0.2
            range_end = ox + board.width * 0.8
            rotation = 2
        elif self.preferred_edge == "left":
            fixed_coord = ox + self.edge_distance_mm
            range_start = oy + board.height * 0.2
            range_end = oy + board.height * 0.8
            rotation = 3
        else:  # right
            fixed_coord = ox + board.width - self.edge_distance_mm
            range_start = oy + board.height * 0.2
            range_end = oy + board.height * 0.8
            rotation = 1

        # Sort by size (largest first for priority placement)
        sorted_comps = sorted(components, key=lambda c: c.width * c.height, reverse=True)

        # Place along edge
        n = len(sorted_comps)

        for i, comp in enumerate(sorted_comps):
            t = i / (n - 1) if n > 1 else 0.5

            varying_coord = range_start + t * (range_end - range_start)

            if horizontal_edge:
                pos_x = varying_coord
                pos_y = fixed_coord
            else:
                pos_x = fixed_coord
                pos_y = varying_coord

            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[comp.ref] = ComponentPlacement(
                    ref=comp.ref,
                    position=(pos_x, pos_y),
                    rotation=rotation,
                    confidence=0.85,
                    placed_by=self.name,
                )

        return placements


# =============================================================================
# Critical Loop Pre-minimization Heuristic (STRUCTURAL priority)
# =============================================================================


class CriticalLoopHeuristic(Heuristic):
    """
    Pre-position components in critical switching loops to minimize loop area.

    Critical loops in switching converters determine EMI performance:
    - Buck: VIN -> high-side -> low-side -> input cap -> VIN
    - Half-bridge: Similar pattern with output
    - Gate drive: Driver -> gate resistor -> gate-source -> driver GND

    This heuristic clusters critical loop components tightly together.
    """

    def __init__(self, max_loop_diameter_mm: float = 15.0):
        """
        Initialize critical loop heuristic.

        Args:
            max_loop_diameter_mm: Maximum diameter for loop component cluster
        """
        self.max_loop_diameter_mm = max_loop_diameter_mm

    @property
    def name(self) -> str:
        return "critical_loop_minimization"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.STRUCTURAL

    @property
    def description(self) -> str:
        return "Clusters critical loop components to minimize loop area"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Place critical loop components in tight clusters."""
        critical_loops = context.constraints.critical_loops

        if not critical_loops:
            return HeuristicResult(
                placements={},
                success=True,
                message="No critical loops defined",
            )

        placements: dict[str, ComponentPlacement] = {}

        for loop in critical_loops:
            loop_placements = self._place_loop_components(
                _loop_name=loop.name,
                loop_nets=loop.nets,
                netlist=context.netlist,
                board=context.board,
                context=context,
                existing_placements=placements,
            )
            placements.update(loop_placements)

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} components in {len(critical_loops)} critical loops",
        )

    def _place_loop_components(
        self,
        _loop_name: str,
        loop_nets: list[str],
        netlist: Netlist,
        board: Board,
        context: PlacementContext,
        existing_placements: dict[str, ComponentPlacement],
    ) -> dict[str, ComponentPlacement]:
        """Place components belonging to a critical loop."""
        # Find all components connected to loop nets
        loop_components: set[str] = set()
        for net_name in loop_nets:
            try:
                net = netlist.get_net(net_name)
                for ref, _ in net.pins:
                    loop_components.add(ref)
            except KeyError:
                # Net not found in netlist
                continue

        if not loop_components:
            return {}

        # Filter to unplaced, non-fixed components
        to_place = [
            netlist.get_component(ref)
            for ref in loop_components
            if ref not in context.current_placements
            and ref not in existing_placements
            and not netlist.get_component(ref).fixed
        ]

        if not to_place:
            return {}

        # Find a centroid for the cluster
        # If some components are already placed, use their centroid
        # Otherwise use board center region
        placed_refs = [r for r in loop_components if r in context.current_placements]

        if placed_refs:
            cx = sum(context.current_placements[r].position[0] for r in placed_refs) / len(
                placed_refs
            )
            cy = sum(context.current_placements[r].position[1] for r in placed_refs) / len(
                placed_refs
            )
        else:
            # Default to upper-center (common for power stage)
            ox, oy = board.origin
            cx = ox + board.width * 0.5
            cy = oy + board.height * 0.7

        # Place components in a tight cluster around centroid
        placements = {}
        radius = self.max_loop_diameter_mm / 2
        n = len(to_place)

        for i, comp in enumerate(to_place):
            # Arrange in a circle pattern
            if n > 1:
                angle = 2 * 3.14159 * i / n
                offset_x = radius * 0.5 * jnp.cos(angle)
                offset_y = radius * 0.5 * jnp.sin(angle)
            else:
                offset_x, offset_y = 0.0, 0.0

            pos_x = cx + float(offset_x)
            pos_y = cy + float(offset_y)

            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[comp.ref] = ComponentPlacement(
                    ref=comp.ref,
                    position=(pos_x, pos_y),
                    rotation=0,
                    confidence=0.8,
                    placed_by=self.name,
                )

        return placements
