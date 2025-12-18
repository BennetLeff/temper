"""
Component, Pin, Net, and Netlist data structures.

This module defines the netlist representation used throughout temper-placer.
Components represent physical parts, Pins are connection points, Nets define
electrical connectivity, and Netlist aggregates everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import jax.numpy as jnp
from jax import Array


@dataclass
class Pin:
    """
    A pin on a component.

    Attributes:
        name: Pin name (e.g., "VCC", "GND", "1").
        number: Pin number/pad number as string.
        position: (x, y) offset from component center in mm.
        net: Net name this pin connects to, or None if unconnected.
    """

    name: str
    number: str
    position: Tuple[float, float]
    net: Optional[str] = None

    def absolute_position(
        self,
        component_pos: Tuple[float, float],
        rotation_angle: float,
    ) -> Tuple[float, float]:
        """
        Get absolute pin position given component placement.

        Args:
            component_pos: (x, y) component center position.
            rotation_angle: Component rotation in radians.

        Returns:
            (x, y) absolute pin position.
        """
        cos_r = jnp.cos(rotation_angle)
        sin_r = jnp.sin(rotation_angle)
        px, py = self.position
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
    bounds: Tuple[float, float]  # (width, height) in mm
    pins: List[Pin] = field(default_factory=list)
    net_class: str = "Signal"
    zone: Optional[str] = None
    fixed: bool = False
    initial_position: Optional[Tuple[float, float]] = None
    initial_rotation: Optional[int] = None
    attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def width(self) -> float:
        """Component width in mm."""
        return self.bounds[0]

    @property
    def height(self) -> float:
        """Component height in mm."""
        return self.bounds[1]

    def get_pin(self, name_or_number: str) -> Optional[Pin]:
        """Get a pin by name or number."""
        for pin in self.pins:
            if pin.name == name_or_number or pin.number == name_or_number:
                return pin
        return None

    def get_pins_for_net(self, net_name: str) -> List[Pin]:
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
    """

    name: str
    pins: List[Tuple[str, str]]  # [(component_ref, pin_name), ...]
    net_class: str = "Signal"
    weight: float = 1.0

    @property
    def pin_count(self) -> int:
        """Number of pins in this net."""
        return len(self.pins)

    def get_component_refs(self) -> Set[str]:
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

    components: List[Component] = field(default_factory=list)
    nets: List[Net] = field(default_factory=list)

    # Computed indices (populated by build_indices)
    _component_index: Dict[str, int] = field(default_factory=dict, repr=False)
    _net_index: Dict[str, int] = field(default_factory=dict, repr=False)
    _component_nets: Dict[str, List[str]] = field(default_factory=dict, repr=False)

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

    def get_component_nets(self, ref: str) -> List[str]:
        """Get all net names connected to a component."""
        return self._component_nets.get(ref, [])

    def get_net_pins(self, net_name: str) -> List[Tuple[str, str]]:
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

    def validate(self) -> List[str]:
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
