"""
Organizational placement heuristics.

Organizational heuristics handle component grouping and domain layout:
- Functional module clustering
- Power flow topology placement
- Decoupling capacitor positioning
- Analog/digital domain separation

These run at ORGANIZATIONAL priority, after structural constraints are satisfied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
    order_refs_by_netlist,
)
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.router_v6.net_classification import (
    is_ground_net,
    is_power_net,
)

# =============================================================================
# Functional Module Clustering Heuristic (ORGANIZATIONAL priority)
# =============================================================================


@dataclass
class FunctionalModule:
    """A group of components that form a functional unit."""

    name: str
    components: list[str]  # Component refs
    centroid: tuple[float, float] | None = None


def identify_functional_modules(
    netlist: Netlist,
    constraints: PlacementConstraints,
) -> list[FunctionalModule]:
    """
    Identify functional modules from netlist and constraints.

    Modules are identified from:
    1. Explicit component_groups in constraints
    2. Reference prefix patterns (same prefix = same module)
    3. Schematic sheet hierarchy (if available in attributes)

    Args:
        netlist: Netlist with components
        constraints: Placement constraints with groups

    Returns:
        List of functional modules
    """
    modules: list[FunctionalModule] = []
    assigned_refs: set[str] = set()

    # From explicit config groups
    for group in constraints.component_groups:
        # Filter to components that exist in netlist
        valid_refs = [ref for ref in group.components if ref in {c.ref for c in netlist.components}]
        if valid_refs:
            modules.append(
                FunctionalModule(
                    name=group.name,
                    components=valid_refs,
                )
            )
            assigned_refs.update(valid_refs)

    # Auto-detect by reference prefix patterns
    # Group components like U1_*, R1_*, etc. (underscore-separated)
    prefix_groups: dict[str, list[str]] = {}
    for comp in netlist.components:
        if comp.ref in assigned_refs or comp.fixed:
            continue

        # Try to extract prefix (e.g., "GATE" from "GATE_DRV", "MCU" from "MCU_1")
        match = re.match(r"^([A-Z]+)_", comp.ref)
        if match:
            prefix = match.group(1)
            if prefix not in prefix_groups:
                prefix_groups[prefix] = []
            prefix_groups[prefix].append(comp.ref)

    # Convert prefix groups to modules (only if multiple components)
    for prefix, refs in prefix_groups.items():
        if len(refs) >= 2:
            modules.append(
                FunctionalModule(
                    name=f"{prefix}_module",
                    components=refs,
                )
            )
            assigned_refs.update(refs)

    # Auto-detect by high connectivity
    # Components sharing multiple nets with each other form a module
    connectivity_groups = _find_highly_connected_groups(netlist, assigned_refs)
    for i, group_refs in enumerate(connectivity_groups):
        if len(group_refs) >= 2:
            modules.append(
                FunctionalModule(
                    name=f"connected_group_{i}",
                    # Netlist order: `group_refs` is a set, and this list becomes
                    # `FunctionalModule.components`, whose index selects each
                    # component's polar angle in `_place_module_components`.
                    components=order_refs_by_netlist(netlist, group_refs),
                )
            )

    return modules


def _find_highly_connected_groups(
    netlist: Netlist,
    exclude_refs: set[str],
    min_shared_nets: int = 2,
) -> list[set[str]]:
    """Find groups of components that share multiple nets."""
    # Build component-to-component connectivity
    comp_connections: dict[str, dict[str, int]] = {}

    for net in netlist.nets:
        # Netlist order, not set order: `get_component_refs()` returns a set, and
        # set iteration order for str depends on PYTHONHASHSEED. This order
        # propagates into `comp_connections`, into the returned groups, and
        # ultimately into the polar angle each component is placed at.
        refs = order_refs_by_netlist(netlist, net.get_component_refs() - exclude_refs)
        # Skip power nets (too many connections)
        if net.net_class == "Power" or len(refs) > 10:
            continue

        for i, ref_a in enumerate(refs):
            if ref_a not in comp_connections:
                comp_connections[ref_a] = {}
            for ref_b in refs[i + 1 :]:
                if ref_b not in comp_connections:
                    comp_connections[ref_b] = {}
                comp_connections[ref_a][ref_b] = comp_connections[ref_a].get(ref_b, 0) + 1
                comp_connections[ref_b][ref_a] = comp_connections[ref_b].get(ref_a, 0) + 1

    # Find clusters of highly connected components using simple greedy
    groups: list[set[str]] = []
    used: set[str] = set()

    for ref_a, connections in comp_connections.items():
        if ref_a in used:
            continue

        group = {ref_a}
        for ref_b, count in connections.items():
            if count >= min_shared_nets and ref_b not in used:
                group.add(ref_b)

        if len(group) >= 2:
            groups.append(group)
            used.update(group)

    return groups


class FunctionalModuleClusteringHeuristic(Heuristic):
    """
    Cluster components that belong to the same functional module.

    Components that work together (same schematic block, same function)
    should be placed near each other for:
    - Shorter traces
    - Better signal integrity
    - Easier review and debugging
    """

    def __init__(self, max_spread_mm: float = 20.0, module_spacing_mm: float = 10.0):
        """
        Initialize module clustering.

        Args:
            max_spread_mm: Maximum spread of components within a module
            module_spacing_mm: Spacing between module centroids
        """
        self.max_spread_mm = max_spread_mm
        self.module_spacing_mm = module_spacing_mm

    @property
    def name(self) -> str:
        return "functional_module_clustering"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.ORGANIZATIONAL

    @property
    def description(self) -> str:
        return "Clusters components belonging to the same functional module"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Cluster functional modules."""
        modules = identify_functional_modules(context.netlist, context.constraints)

        if not modules:
            return HeuristicResult(
                placements={},
                success=True,
                message="No functional modules identified",
            )

        placements = self._place_modules(
            modules=modules,
            board=context.board,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Clustered {len(placements)} components in {len(modules)} modules",
        )

    def _place_modules(
        self,
        modules: list[FunctionalModule],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place module components in clusters.

        The grid-centroid math (cols/rows from ``sqrt(n)``, cell size, per-
        module center) is delegated to ``temper_geometry.module_grid_positions_py``
        -- see ``packages/temper-geometry/src/organizational_geometry.rs``.
        This method keeps the public API and only extracts primitives
        (``board.origin``, module count) and iterates the result, which is
        orchestration, not compute. Pinned oracle:
        ``packages/temper-placer/tests/heuristics/_organizational_py_oracle.py``;
        differential:
        ``packages/temper-placer/tests/heuristics/test_organizational_rust_differential.py``.
        """
        from temper_geometry import module_grid_positions_py

        placements: dict[str, ComponentPlacement] = {}
        ox, oy = board.origin

        centroids = module_grid_positions_py(
            len(modules), ox, oy, board.width, board.height, context.constraints.board_margin_mm
        )

        for module, (cx, cy) in zip(modules, centroids, strict=True):
            # Place components within module
            module_placements = self._place_module_components(
                module=module,
                centroid=(cx, cy),
                context=context,
            )
            placements.update(module_placements)

        return placements

    def _place_module_components(
        self,
        module: FunctionalModule,
        centroid: tuple[float, float],
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place components around module centroid.

        The circular/spiral offset math is delegated to
        ``temper_geometry.circle_offsets_py`` -- see
        ``organizational_geometry.rs``'s module doc for why it uses a
        hardcoded pi approximation (``2 * 3.14159 * i / n``, not
        ``math.pi``) and resolves cos/sin through the host libm.
        """
        from temper_geometry import circle_offsets_py

        placements: dict[str, ComponentPlacement] = {}
        cx, cy = centroid

        # Filter to unplaced components
        to_place = [
            ref
            for ref in module.components
            if ref not in context.current_placements
            and not context.netlist.get_component(ref).fixed
        ]

        if not to_place:
            return {}

        # Arrange in circle/spiral around centroid
        n = len(to_place)
        radius = min(self.max_spread_mm / 2, 8.0)
        offsets = circle_offsets_py(n, radius)

        for ref, (offset_x, offset_y) in zip(to_place, offsets, strict=True):
            comp = context.netlist.get_component(ref)

            pos_x = cx + float(offset_x)
            pos_y = cy + float(offset_y)

            if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                placements[ref] = ComponentPlacement(
                    ref=ref,
                    position=(pos_x, pos_y),
                    rotation=0,
                    confidence=0.7,
                    placed_by=self.name,
                )

        return placements


# =============================================================================
# Power Flow Topology Heuristic (ORGANIZATIONAL priority)
# =============================================================================


@dataclass
class PowerFlowNode:
    """A node in the power flow graph."""

    ref: str
    role: str  # "input", "distribution", "load"
    stage: int  # 0=input, 1=distribution, 2=load


def classify_power_topology(
    netlist: Netlist,
    _constraints: PlacementConstraints,
) -> list[PowerFlowNode]:
    """
    Classify components into power flow roles.

    Roles:
    - input: Power connectors, input fuses, bulk caps
    - distribution: Buck converters, LDOs, power distribution
    - load: MCU, gate drivers, sensors

    Args:
        netlist: Netlist with components
        constraints: Placement constraints

    Returns:
        List of PowerFlowNode with role assignments
    """
    nodes: list[PowerFlowNode] = []

    # Input patterns
    input_patterns = [
        r"^J.*DC",
        r"^J.*IN",
        r"^J.*PWR",
        r"^F\d+",  # Fuses
        r"^C.*BULK",
        r"^C.*IN",
    ]

    # Distribution patterns
    dist_patterns = [
        r"^U.*BUCK",
        r"^U.*LDO",
        r"^U.*REG",
        r"^L\d+",  # Main inductors
    ]

    # Load patterns (everything else that's an IC)
    load_patterns = [
        r"^U.*MCU",
        r"^U.*GATE",
        r"^U.*DRV",
        r"^U.*SENS",
    ]

    for comp in netlist.components:
        if comp.fixed:
            continue

        role = "load"  # Default
        stage = 2

        # Check input patterns
        for pattern in input_patterns:
            if re.match(pattern, comp.ref, re.IGNORECASE):
                role = "input"
                stage = 0
                break

        if role == "load":
            # Check distribution patterns
            for pattern in dist_patterns:
                if re.match(pattern, comp.ref, re.IGNORECASE):
                    role = "distribution"
                    stage = 1
                    break

        if role == "load":
            # Check load patterns
            for pattern in load_patterns:
                if re.match(pattern, comp.ref, re.IGNORECASE):
                    role = "load"
                    stage = 2
                    break

        # Only include ICs and major components (skip passives without explicit role)
        if role != "load" or comp.ref.startswith("U"):
            nodes.append(PowerFlowNode(ref=comp.ref, role=role, stage=stage))

    return nodes


class PowerFlowTopologyHeuristic(Heuristic):
    """
    Place components following power flow direction.

    Power flow: input -> distribution -> loads
    Typically left-to-right or top-to-bottom.
    """

    def __init__(self, flow_direction: str = "left_to_right"):
        """
        Initialize power flow heuristic.

        Args:
            flow_direction: "left_to_right" or "top_to_bottom"
        """
        self.flow_direction = flow_direction

    @property
    def name(self) -> str:
        return "power_flow_topology"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.ORGANIZATIONAL

    @property
    def description(self) -> str:
        return "Places components following power flow direction"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Place components according to power flow."""
        nodes = classify_power_topology(context.netlist, context.constraints)

        if not nodes:
            return HeuristicResult(
                placements={},
                success=True,
                message="No power flow nodes classified",
            )

        placements = self._place_power_flow(
            nodes=nodes,
            board=context.board,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} components in power flow",
        )

    def _place_power_flow(
        self,
        nodes: list[PowerFlowNode],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place components by power flow stage.

        The per-stage layout math (column/row center, linear interpolation
        along the stage) is delegated to
        ``temper_geometry.power_flow_positions_py``, which mirrors both the
        horizontal and vertical branches -- see ``organizational_geometry.rs``
        for why the vertical branch's ``y_center`` is not a simple mirror of
        the horizontal branch's ``x_center`` (it subtracts from
        ``oy + board.height`` so the input stage renders at the top).
        """
        from temper_geometry import power_flow_positions_py

        placements: dict[str, ComponentPlacement] = {}
        ox, oy = board.origin
        margin = context.constraints.board_margin_mm

        # Group by stage
        stages: dict[int, list[str]] = {0: [], 1: [], 2: []}
        for node in nodes:
            if node.ref not in context.current_placements:
                stages[node.stage].append(node.ref)

        horizontal = self.flow_direction == "left_to_right"
        stage_counts = [len(stages[0]), len(stages[1]), len(stages[2])]
        per_stage = power_flow_positions_py(
            ox, oy, board.width, board.height, margin, stage_counts, horizontal
        )

        for stage, refs in stages.items():
            for ref, (pos_x, pos_y) in zip(refs, per_stage[stage], strict=True):
                comp = context.netlist.get_component(ref)
                if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                    placements[ref] = ComponentPlacement(
                        ref=ref,
                        position=(pos_x, pos_y),
                        rotation=0,
                        confidence=0.65,
                        placed_by=self.name,
                    )

        return placements


# =============================================================================
# Decoupling Cap Pre-positioning Heuristic (ORGANIZATIONAL priority)
# =============================================================================


def identify_decoupling_caps(
    netlist: Netlist,
) -> dict[str, str]:
    """
    Identify decoupling capacitors and their associated ICs.

    Decoupling caps are identified by:
    - Value (100nF, 10nF, 1uF) on power nets
    - Naming patterns (C_DEC*, C_BYPASS*)
    - Connected to VCC/GND of an IC

    Returns:
        Dict mapping capacitor ref to IC ref
    """
    cap_to_ic: dict[str, str] = {}

    # Find caps connected to power nets
    for comp in netlist.components:
        if not comp.ref.startswith("C"):
            continue

        # Check if it's a decoupling cap by naming
        ref_upper = comp.ref.upper()
        is_decoupling = any(x in ref_upper for x in ["DEC", "BYPASS", "BYP"])

        # Check connected nets
        comp_nets = netlist.get_component_nets(comp.ref)
        power_net = None
        ground_net = None

        for net_name in comp_nets:
            if is_power_net(net_name):
                power_net = net_name
            if is_ground_net(net_name):
                ground_net = net_name

        # Must be connected to both power and ground
        if not (power_net and ground_net) and not is_decoupling:
            continue

        # Find the IC this cap decouples (shares power net with)
        if power_net:
            try:
                net = netlist.get_net(power_net)
                for ref, _ in net.pins:
                    if ref != comp.ref and ref.startswith("U"):
                        cap_to_ic[comp.ref] = ref
                        break
            except KeyError:
                pass

    return cap_to_ic


class DecouplingCapHeuristic(Heuristic):
    """
    Position decoupling capacitors adjacent to their ICs.

    Decoupling caps must be very close to IC power pins:
    - Minimizes loop inductance
    - Provides local charge reservoir
    - Standard practice: 1-3mm from IC
    """

    def __init__(self, max_distance_mm: float = 3.0):
        """
        Initialize decoupling cap heuristic.

        Args:
            max_distance_mm: Maximum distance from IC to decoupling cap
        """
        self.max_distance_mm = max_distance_mm

    @property
    def name(self) -> str:
        return "decoupling_cap_positioning"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.ORGANIZATIONAL

    @property
    def description(self) -> str:
        return "Places decoupling capacitors adjacent to their ICs"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Position decoupling caps near their ICs."""
        cap_to_ic = identify_decoupling_caps(context.netlist)

        if not cap_to_ic:
            return HeuristicResult(
                placements={},
                success=True,
                message="No decoupling caps identified",
            )

        placements = self._place_decoupling_caps(
            cap_to_ic=cap_to_ic,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Positioned {len(placements)} decoupling caps",
        )

    def _place_decoupling_caps(
        self,
        cap_to_ic: dict[str, str],
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place caps adjacent to their ICs.

        The four candidate-position offsets are delegated to
        ``temper_geometry.decoupling_candidate_positions_py``. The trial
        loop (validity + overlap check, first-fit) stays Python.
        """
        from temper_geometry import decoupling_candidate_positions_py

        placements: dict[str, ComponentPlacement] = {}

        for cap_ref, ic_ref in cap_to_ic.items():
            if cap_ref in context.current_placements:
                continue

            cap_comp = context.netlist.get_component(cap_ref)

            # Get IC position (if already placed)
            if ic_ref in context.current_placements:
                ic_pos = context.current_placements[ic_ref].position
            else:
                # IC not placed yet, skip
                continue

            # Place cap near IC (offset by component sizes)
            ic_comp = context.netlist.get_component(ic_ref)

            # Try positions around the IC: right, left, above, below.
            positions_to_try = decoupling_candidate_positions_py(
                ic_pos[0], ic_pos[1], ic_comp.width, cap_comp.width
            )

            for pos_x, pos_y in positions_to_try:
                if context.is_position_valid(
                    pos_x, pos_y, cap_comp.width, cap_comp.height
                ) and not context.check_overlap(pos_x, pos_y, cap_comp.width, cap_comp.height):
                    placements[cap_ref] = ComponentPlacement(
                        ref=cap_ref,
                        position=(pos_x, pos_y),
                        rotation=0,
                        confidence=0.8,
                        placed_by=self.name,
                    )
                    break

        return placements


# =============================================================================
# Analog/Digital Domain Separation Heuristic (ORGANIZATIONAL priority)
# =============================================================================


def classify_signal_domains(
    netlist: Netlist,
    _constraints: PlacementConstraints,
) -> dict[str, str]:
    """
    Classify components by signal domain.

    Domains:
    - "digital": MCU, logic ICs, digital signals
    - "analog": Op-amps, ADCs, sensors, precision circuits
    - "power": Converters, IGBTs, large caps, inductors

    Returns:
        Dict mapping component ref to domain
    """
    domains: dict[str, str] = {}

    # Digital patterns
    digital_patterns = [
        r"^U.*MCU",
        r"^U.*FLASH",
        r"^U.*LOGIC",
        r"^Y\d+",  # Crystals
    ]

    # Analog patterns
    analog_patterns = [
        r"^U.*OPAMP",
        r"^U.*AMP",
        r"^U.*ADC",
        r"^U.*DAC",
        r"^U.*SENS",
        r"^U.*TEMP",
        r"^R.*SENSE",
    ]

    # Power patterns
    power_patterns = [
        r"^Q\d+",  # Transistors
        r"^U.*BUCK",
        r"^U.*LDO",
        r"^U.*GATE",
        r"^L\d+",
        r"^D.*PWR",
    ]

    for comp in netlist.components:
        domain = "digital"  # Default

        # Check power patterns first (highest priority)
        for pattern in power_patterns:
            if re.match(pattern, comp.ref, re.IGNORECASE):
                domain = "power"
                break

        if domain == "digital":
            # Check analog patterns
            for pattern in analog_patterns:
                if re.match(pattern, comp.ref, re.IGNORECASE):
                    domain = "analog"
                    break

        if domain == "digital":
            # Check digital patterns
            for pattern in digital_patterns:
                if re.match(pattern, comp.ref, re.IGNORECASE):
                    domain = "digital"
                    break

        # Check net names for additional classification
        if domain == "digital":
            comp_nets = netlist.get_component_nets(comp.ref)
            for net_name in comp_nets:
                net_upper = net_name.upper()
                if any(x in net_upper for x in ["ANALOG", "SENSE", "ADC"]):
                    domain = "analog"
                    break
                if any(x in net_upper for x in ["SPI", "I2C", "UART", "GPIO"]):
                    domain = "digital"
                    break

        domains[comp.ref] = domain

    return domains


class DomainSeparationHeuristic(Heuristic):
    """
    Separate analog and digital component domains.

    Mixed-signal designs require separation between:
    - Digital noise sources (MCU, switching converters)
    - Analog sensitive circuits (sensors, ADC inputs)
    - Power domains (high voltage, high current)
    """

    def __init__(self, guard_band_mm: float = 5.0):
        """
        Initialize domain separation.

        Args:
            guard_band_mm: Minimum distance between domains
        """
        self.guard_band_mm = guard_band_mm

    @property
    def name(self) -> str:
        return "domain_separation"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.ORGANIZATIONAL

    @property
    def description(self) -> str:
        return "Separates analog and digital domains"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Separate components by domain."""
        domains = classify_signal_domains(context.netlist, context.constraints)

        placements = self._place_by_domain(
            domains=domains,
            board=context.board,
            context=context,
        )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Placed {len(placements)} components by domain",
        )

    def _place_by_domain(
        self,
        domains: dict[str, str],
        board: Board,
        context: PlacementContext,
    ) -> dict[str, ComponentPlacement]:
        """Place components in domain regions.

        The per-domain grid layout (cols/rows from ``sqrt(n)``, per-cell
        position within the region box) is delegated to
        ``temper_geometry.domain_grid_positions_py``. This uses a DIFFERENT
        floating-point operation order than ``_place_modules``'s
        ``module_grid_positions_py`` for the same-looking formula -- see
        ``organizational_geometry.rs``'s module doc; the two are not
        interchangeable. The region-box definition (board-fraction
        constants) stays Python, matching ``ox, oy = board.origin`` staying
        Python in ``create_keepout_mask``'s delegation.
        """
        from temper_geometry import domain_grid_positions_py

        placements: dict[str, ComponentPlacement] = {}
        ox, oy = board.origin
        margin = context.constraints.board_margin_mm

        # Define domain regions (power left, digital right, analog bottom-right)
        regions = {
            "power": (ox + margin, oy + margin, ox + board.width * 0.4, oy + board.height - margin),
            "digital": (
                ox + board.width * 0.5,
                oy + board.height * 0.4,
                ox + board.width - margin,
                oy + board.height - margin,
            ),
            "analog": (
                ox + board.width * 0.5,
                oy + margin,
                ox + board.width - margin,
                oy + board.height * 0.35,
            ),
        }

        # Group components by domain
        domain_components: dict[str, list[str]] = {"power": [], "digital": [], "analog": []}
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

            x_min, y_min, x_max, y_max = regions[domain]
            positions = domain_grid_positions_py(len(refs), x_min, y_min, x_max, y_max)

            for ref, (pos_x, pos_y) in zip(refs, positions, strict=True):
                comp = context.netlist.get_component(ref)
                if context.is_position_valid(pos_x, pos_y, comp.width, comp.height):
                    placements[ref] = ComponentPlacement(
                        ref=ref,
                        position=(pos_x, pos_y),
                        rotation=0,
                        confidence=0.6,
                        placed_by=self.name,
                    )

        return placements
