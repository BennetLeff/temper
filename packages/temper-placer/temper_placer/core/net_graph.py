"""
Net Graph and Sub-Net Edge definitions for topology-aware routing.

This module defines data structures for decomposing nets into directed graphs
of sub-net edges, each with its own routing constraints. This enables
star-point connections (Kelvin sensing) and mixed-signal routing rules
within a single electrical net.
"""

from dataclasses import dataclass, field


@dataclass
class SubNetEdge:
    """
    A directed edge within a net graph, representing a point-to-point connection.

    Attributes:
        source_pin: Source pin reference (e.g., 'R_SENSE.1').
        sink_pin: Sink pin reference (e.g., 'LOAD.1').
        trace_width_mm: Trace width override for this edge.
        clearance_mm: Clearance override for this edge.
        priority: Routing priority (higher = routed earlier).
    """

    source_pin: str
    sink_pin: str
    trace_width_mm: float | None = None
    clearance_mm: float | None = None
    priority: int = 0


@dataclass
class NetGraph:
    """
    Topology definition for a single net.

    Attributes:
        net_name: Name of the net (e.g., 'NET_I_SENSE').
        edges: List of directed edges defining the routing topology.
        star_nodes: Set of pin references that must be treated as star points
                    (connection only at the pad, no mid-trace tapping).
    """

    net_name: str
    edges: list[SubNetEdge] = field(default_factory=list)
    star_nodes: set[str] = field(default_factory=set)

    def get_edge(self, source: str, sink: str) -> SubNetEdge | None:
        """Find an edge by source and sink pins."""
        for edge in self.edges:
            if edge.source_pin == source and edge.sink_pin == sink:
                return edge
        return None

    def get_outgoing_edges(self, pin: str) -> list[SubNetEdge]:
        """Get all edges starting from a given pin."""
        return [e for e in self.edges if e.source_pin == pin]

    def get_incoming_edges(self, pin: str) -> list[SubNetEdge]:
        """Get all edges ending at a given pin."""
        return [e for e in self.edges if e.sink_pin == pin]
