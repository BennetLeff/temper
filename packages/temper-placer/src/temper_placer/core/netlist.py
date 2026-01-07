"""
Component, Pin, Net, and Netlist data structures.

This module defines the netlist representation used throughout temper-placer.
Components represent physical parts, Pins are connection points, Nets define
electrical connectivity, and Netlist aggregates everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jax.numpy as jnp
from jax import Array

from temper_placer.core.units import Radians


@dataclass
class Pin:
    """
    A pin on a component.

    Attributes:
        name: Pin name (e.g., "VCC", "GND", "1").
        number: Pin number/pad number as string.
        position: (x, y) offset from component center in mm.
        net: Net name this pin connects to, or None if unconnected.
        width: Pad width in mm (for DSN export).
        height: Pad height in mm (for DSN export).
        shape: Pad shape (rect, circle, oval, roundrect, thru_hole).
        layer: Layer or "all" for through-hole pads.
    """

    name: str
    number: str
    position: tuple[float, float]
    net: str | None = None
    width: float = 1.0
    height: float = 1.0
    shape: str = "rect"
    layer: str = "F.Cu"
    drill: float = 0.0  # Drill diameter (0 = SMD)
    is_pth: bool = False  # Convenience flag for Plated Through-Hole

    @property
    def mask_expansion(self) -> float:
        """Return recommended solder mask expansion for this pin."""
        return 0.15 if self.is_pth else 0.1

    def absolute_position(
        self,
        component_pos: tuple[float, float],
        rotation_angle: Radians,
        side: int = 0,
    ) -> tuple[float, float]:
        """
        Get absolute pin position given component placement.

        Args:
            component_pos: (x, y) component center position in mm.
            rotation_angle: Component rotation in radians. Use deg_to_rad() if needed.
            side: Component side (0=Top, 1=Bottom). If 1, pin is mirrored.

        Returns:
            (x, y) absolute pin position.
        """
        cos_r = jnp.cos(rotation_angle)
        sin_r = jnp.sin(rotation_angle)
        px, py = self.position

        # If on bottom side, mirror X coordinate before rotation (standard KiCad behavior)
        if side == 1:
            px = -px

        # Rotate pin offset
        rx = px * cos_r - py * sin_r
        ry = px * sin_r + py * cos_r
        # Add component position
        return (component_pos[0] + float(rx), component_pos[1] + float(ry))


@dataclass
class Component:
    """
    A component to be placed on the PCB.

    Attributes:
        ref: Reference designator (e.g., "U1", "R5", "C10").
        footprint: Footprint name/path.
        bounds: (width, height) bounding box in mm.
        pins: List of pins on this component.
        net_class: Net class for design rule checking (e.g., "HighVoltage", "Signal").
        zone: Target placement zone name, or None for any zone.
        fixed: If True, component position is fixed (don't optimize).
        initial_position: Optional (x, y) initial/fixed position.
        initial_rotation: Optional initial rotation index (0-3 for 0°/90°/180°/270°).
        attributes: Additional component attributes (value, MPN, etc.).
    """

    ref: str
    footprint: str
    bounds: tuple[float, float]  # (width, height) in mm
    pins: list[Pin] = field(default_factory=list)
    net_class: str = "Signal"
    zone: str | None = None
    fixed: bool = False
    initial_position: tuple[float, float] | None = None
    initial_rotation: int | None = None
    initial_side: int | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def width(self) -> float:
        """Component width in mm."""
        return self.bounds[0]

    @property
    def height(self) -> float:
        """Component height in mm."""
        return self.bounds[1]

    def get_pin(self, name_or_number: str) -> Pin | None:
        """Get a pin by name or number."""
        for pin in self.pins:
            if pin.name == name_or_number or pin.number == name_or_number:
                return pin
        return None

    def get_pins_for_net(self, net_name: str) -> list[Pin]:
        """Get all pins connected to a given net."""
        return [p for p in self.pins if p.net == net_name]


@dataclass
class Net:
    """
    An electrical net connecting multiple pins.

    Attributes:
        name: Net name (e.g., "GND", "VCC", "NET-U1-1").
        pins: List of (component_ref, pin_name) tuples.
        net_class: Net class for design rules.
        weight: Importance weight for wirelength optimization.
            Higher = more important to minimize length.
        max_current: Maximum current in Amps (used for width/plane inference).
        voltage_class: Voltage classification (e.g., "LV", "HV").
    """

    name: str
    pins: list[tuple[str, str]]  # [(component_ref, pin_name), ...]
    net_class: str = "Signal"
    weight: float = 1.0
    max_current: float = 0.0  # Amps
    voltage_class: str = "LV"  # "LV", "HV"

    @property
    def pin_count(self) -> int:
        """Number of pins in this net."""
        return len(self.pins)

    def get_component_refs(self) -> set[str]:
        """Get unique component references in this net."""
        return {ref for ref, _ in self.pins}


@dataclass
class Netlist:
    """
    Complete netlist containing all components and nets.

    Attributes:
        components: List of all components.
        nets: List of all nets.
    """

    components: list[Component] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)

    # Computed indices (populated by build_indices)
    _component_index: dict[str, int] = field(default_factory=dict, repr=False)
    _net_index: dict[str, int] = field(default_factory=dict, repr=False)
    _component_nets: dict[str, list[str]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Build indices after initialization."""
        self.build_indices()

    def build_indices(self) -> None:
        """Build lookup indices for efficient queries."""
        self._component_index = {c.ref: i for i, c in enumerate(self.components)}
        self._net_index = {n.name: i for i, n in enumerate(self.nets)}

        # Build component -> nets mapping
        self._component_nets = {c.ref: [] for c in self.components}
        for net in self.nets:
            for ref, _ in net.pins:
                if ref in self._component_nets:
                    self._component_nets[ref].append(net.name)

    def get_component_index(self, ref: str) -> int:
        """Get array index for a component by reference."""
        return self._component_index[ref]

    def get_component(self, ref: str) -> Component:
        """Get a component by reference."""
        return self.components[self._component_index[ref]]

    def get_net(self, name: str) -> Net:
        """Get a net by name."""
        return self.nets[self._net_index[name]]

    def get_component_nets(self, ref: str) -> list[str]:
        """Get all net names connected to a component."""
        return self._component_nets.get(ref, [])

    def get_net_pins(self, net_name: str) -> list[tuple[str, str]]:
        """Get all (component_ref, pin_name) for a net."""
        return self.get_net(net_name).pins

    @property
    def n_components(self) -> int:
        """Number of components."""
        return len(self.components)

    @property
    def n_nets(self) -> int:
        """Number of nets."""
        return len(self.nets)

    def get_bounds_array(self) -> Array:
        """Get (N, 2) array of component bounds (width, height)."""
        return jnp.array([c.bounds for c in self.components], dtype=jnp.float32)

    def get_fixed_mask(self) -> Array:
        """Get (N,) boolean array of fixed components."""
        return jnp.array([c.fixed for c in self.components], dtype=jnp.bool_)

    def apply_net_class_mapping(self, mapping: dict[str, str]) -> int:
        """
        Apply a net_name -> net_class mapping to all nets.

        This updates the net_class attribute of each Net object based on
        the provided mapping. Nets not in the mapping retain their current
        net_class (typically the default 'Signal').

        Args:
            mapping: Dictionary mapping net names to net class names.
                     Example: {'GND': 'Ground', 'AC_L': 'HighVoltage'}

        Returns:
            Number of nets that were updated.
        """
        updated = 0
        for net in self.nets:
            if net.name in mapping:
                new_class = mapping[net.name]
                if net.net_class != new_class:
                    # Net is a frozen dataclass, need to create new one
                    # But Net is not frozen, so direct assignment works
                    net.net_class = new_class
                    updated += 1
        return updated

    def find_isomorphic_groups(self, iterations: int = 2) -> list[list[int]]:
        """
        Find groups of components that are topologically isomorphic.

        Uses Weisfeiler-Lehman (WL) neighborhood hashing to identify components
        with identical local connectivity and footprints.

        Args:
            iterations: Number of neighborhood expansion steps.
                1: Same footprint and same neighbor footprints.
                2: Also considers neighbors of neighbors.

        Returns:
            List of groups, where each group is a list of component indices.
            Only groups with >1 member are returned.
        """
        import hashlib

        n = self.n_components
        if n == 0:
            return []

        # 1. Initial labels: Footprint + Ref Prefix (to distinguish R from C)
        labels = []
        for c in self.components:
            # Extract ref prefix (all letters at start)
            import re

            match = re.match(r"^([a-zA-Z]+)", c.ref)
            prefix = match.group(1) if match else ""
            labels.append(f"{c.footprint}|{prefix}")

        # Build adjacency for hashing
        adj = build_adjacency_matrix(self)
        # Convert to list of neighbor indices for each component
        neighbor_lists = []
        for i in range(n):
            # Components connected by any net
            neighbors = jnp.where(adj[i] > 0)[0].tolist()
            neighbor_lists.append(neighbors)

        # 2. Iterative Refinement (WL algorithm)
        for _ in range(iterations):
            new_labels = []
            for i in range(n):
                # Get labels of neighbors
                neighbor_labels = sorted([labels[j] for j in neighbor_lists[i]])

                # Combine current label with neighbor labels
                sig = f"{labels[i]}|{','.join(neighbor_labels)}"
                # Hash to keep labels manageable
                h = hashlib.md5(sig.encode()).hexdigest()
                new_labels.append(h)
            labels = new_labels

        # 3. Group by final labels
        groups_dict: dict[str, list[int]] = {}
        for i, label in enumerate(labels):
            if label not in groups_dict:
                groups_dict[label] = []
            groups_dict[label].append(i)

        # 4. Filter groups with >1 member
        return [g for g in groups_dict.values() if len(g) > 1]

    def validate(self) -> list[str]:
        """
        Validate netlist consistency.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        # Check for duplicate component refs
        refs = [c.ref for c in self.components]
        if len(refs) != len(set(refs)):
            duplicates = [r for r in refs if refs.count(r) > 1]
            errors.append(f"Duplicate component refs: {set(duplicates)}")

        # Check for duplicate net names
        names = [n.name for n in self.nets]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            errors.append(f"Duplicate net names: {set(duplicates)}")

        # Check that net pins reference valid components
        for net in self.nets:
            for ref, pin_name in net.pins:
                if ref not in self._component_index:
                    errors.append(f"Net {net.name} references unknown component {ref}")
                else:
                    comp = self.get_component(ref)
                    if comp.get_pin(pin_name) is None:
                        errors.append(f"Net {net.name} references unknown pin {pin_name} on {ref}")

        return errors


def build_adjacency_matrix(netlist: Netlist) -> Array:
    """
    Build weighted adjacency matrix from netlist connectivity.

    The adjacency matrix A is symmetric with A[i,j] equal to the number of nets
    connecting components i and j. Components on the same net create edges between
    all pairs of components on that net (complete subgraph).

    Args:
        netlist: Netlist with components and nets.

    Returns:
        (N, N) symmetric adjacency matrix where A[i,j] = number of nets
        connecting components i and j. Returns (0,0) array for empty netlist.
    """
    import numpy as np

    n = len(netlist.components)

    if n == 0:
        return jnp.array([]).reshape(0, 0)

    # Build component ref -> index mapping
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    # Initialize adjacency matrix
    adj = np.zeros((n, n), dtype=np.float32)

    # For each net, connect all component pairs
    for net in netlist.nets:
        # Get component indices for this net
        comp_indices = []
        for comp_ref, _ in net.pins:
            if comp_ref in ref_to_idx:
                comp_indices.append(ref_to_idx[comp_ref])

        # Remove duplicates (component may have multiple pins on same net)
        comp_indices = list(set(comp_indices))

        # Add edges between all pairs (complete subgraph)
        for i in range(len(comp_indices)):
            for j in range(i + 1, len(comp_indices)):
                idx_i = comp_indices[i]
                idx_j = comp_indices[j]

                adj[idx_i, idx_j] += 1
                adj[idx_j, idx_i] += 1  # Symmetric

    return jnp.array(adj)


def compute_eigenvector_centrality(adjacency: Array) -> Array:
    """
    Compute eigenvector centrality for each node in the graph.

    Eigenvector centrality measures a node's importance based on the
    importance of its neighbors. It corresponds to the eigenvector
    associated with the largest eigenvalue of the adjacency matrix.

    Args:
        adjacency: (N, N) weighted adjacency matrix.

    Returns:
        (N,) array of centrality scores, normalized to sum to 1.0.
    """
    n = adjacency.shape[0]
    if n == 0:
        return jnp.array([])
    if n == 1:
        return jnp.array([1.0], dtype=jnp.float32)

    # For symmetric matrices, eigh returns eigenvalues in ascending order
    eigenvalues, eigenvectors = jnp.linalg.eigh(adjacency)

    # The leading eigenvector is the last one (largest eigenvalue)
    centrality = eigenvectors[:, -1]

    # Eigenvector centrality should be non-negative (Perron-Frobenius theorem)
    centrality = jnp.abs(centrality)

    # Normalize so they sum to 1.0
    total = jnp.sum(centrality)
    if total > 0:
        centrality = centrality / total

    return centrality
