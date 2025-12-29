"""
Core data types for the Hypergraph-to-Router Bridge.

This module defines the vocabulary for Semantic Routing.
It is purely functional (immutable dataclasses) and has no dependencies
on the heavy JAX machinery, ensuring fast imports and testability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Mapping


class RoutingStrategy(Enum):
    """
    Defines the high-level tactic the router should employ for a net.
    """
    STANDARD_A_STAR = auto()
    """Default behavior: Shortest path, avoiding obstacles."""

    EDGE_HUG = auto()
    """Bias pathfinding towards the board boundary.
    Used for: Orphan traces crossing hostile zones (e.g. LV in HV zone).
    Implementation: Cost map is a valley along the edge."""

    FLOOD_FILL = auto()
    """Do not route as a trace; reserved for plane generation.
    Used for: High-current nets (>2A) like PGND, VCC."""

    DIFFERENTIAL_PAIR = auto()
    """Route parallel to a paired net.
    Used for: USB, RS485."""

    STAR_TOPOLOGY = auto()
    """Connect all pins to a single central point.
    Used for: Analog grounds, sense lines."""


class ZoneConflictType(Enum):
    """
    Classifies why a net is in conflict with its environment.
    """
    LV_NET_IN_HV_ZONE = auto()
    """Low-Voltage net pin located inside High-Voltage Zone."""

    HV_NET_IN_LV_ZONE = auto()
    """High-Voltage net pin located inside Low-Voltage Zone."""

    CURRENT_CAPACITY_EXCEEDED = auto()
    """Net current exceeds trace width capacity."""


@dataclass(frozen=True)
class ZoneConflict:
    """
    Records a specific violation of physical routing rules.
    Used for explainability ("Why did we route this along the edge?").
    """
    net_id: str
    pin_id: str
    conflict_type: ZoneConflictType
    severity: float = 1.0


@dataclass(frozen=True)
class RoutingContext:
    """
    The complete semantic routing instruction set for a board.
    Produced by the Bridge, consumed by the Router.
    """
    # What strategy to use for each net
    strategies: Mapping[str, RoutingStrategy] = field(default_factory=dict)

    # Cost multipliers for specific nets (e.g., 10.0 for critical nets)
    cost_modifiers: Mapping[str, float] = field(default_factory=dict)

    # Explainability record
    conflicts: list[ZoneConflict] = field(default_factory=list)

    def get_strategy(self, net_id: str) -> RoutingStrategy:
        """Get the strategy for a net, defaulting to STANDARD."""
        return self.strategies.get(net_id, RoutingStrategy.STANDARD_A_STAR)

    def get_cost_modifier(self, net_id: str) -> float:
        """Get the cost modifier for a net, defaulting to 1.0."""
        return self.cost_modifiers.get(net_id, 1.0)
