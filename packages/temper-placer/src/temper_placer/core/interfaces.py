"""Router protocol — structural interface for deterministic pipeline routing.

Deterministic stages depend on this protocol, not on concrete router_v6
implementations.  router_v6 modules implement this protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Component


@runtime_checkable
class _RoutingResultProtocol(Protocol):
    """Shape deterministic code expects from a routing result.

    Concrete sources: ``router_v6.adapter.RoutingResult``,
    pipeline-iterator ad-hoc result objects.
    """

    completion_rate: float
    """Fraction of nets successfully routed (0.0 to 1.0)."""

    unrouted_nets: list[str]
    """Net names that failed to route."""

    def is_feasible(self) -> bool: ...

    """Return True when all nets routed with no violations."""


@runtime_checkable
class _RouterProtocol(Protocol):
    """Router object that deterministic pipeline stages depend on.

    Concrete implementations:
    ``router_v6.adapter.V6RouterAdapter`` provides ``route()`` plus
    the full MazeRouter surface; ``router_v6.adapter.route_pcb`` can
    be adapted via a trivial wrapper.
    """

    def route(
        self,
        positions: Any,
    ) -> _RoutingResultProtocol:
        """Route all nets for the given component positions.

        Args:
            positions: (N, 2) array of (x, y) positions in mm, one per
                component in the board's canonical order.

        Returns:
            A routing result with at least ``completion_rate``,
            ``unrouted_nets``, and ``is_feasible()``.
        """
        ...

    @staticmethod
    def from_board(
        board: Board,
        cell_size_mm: float = 1.0,
        num_layers: int | None = None,
        design_rules: DesignRules | None = None,
        soft_blocking: bool = False,
        via_cost: float = 1.0,
    ) -> _RouterProtocol:
        """Construct a router instance from a board definition.

        Factory used by ``V6RouterAdapter`` / ``MazeRouter`` consumers.
        """
        ...

    def block_components(
        self,
        components: list[Component],
        positions: Any,
    ) -> None:
        """Register component positions before routing."""
        ...

    def get_conflict_locations(self) -> list[dict[str, Any]]:
        """Return conflict locations for congestion heatmap analysis."""
        ...
