"""Immutable branch-aware geometry for a routed terminal tree.

Unlike a serial ``RoutePath``, a tree has multiple independent edge paths.
Keeping them separate prevents output code from accidentally drawing copper
between the endpoint of one branch and the start of another.
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge


@dataclass(frozen=True)
class TreeRouteBranch:
    """One planned terminal attachment and its actual A* geometry."""

    edge: TerminalTreeEdge
    path: RoutePath | RoutePath3D


@dataclass(frozen=True)
class TreeRouteGeometry:
    """Canonical collection of per-edge paths for one net's route tree."""

    net_name: str
    branches: tuple[TreeRouteBranch, ...]

    def __post_init__(self) -> None:
        if any(branch.path.net_name != self.net_name for branch in self.branches):
            raise ValueError("tree branch net does not match tree net")
        object.__setattr__(
            self,
            "branches",
            tuple(sorted(self.branches, key=lambda branch: (branch.edge.source, branch.edge.target))),
        )

    @property
    def via_positions(self) -> tuple[tuple[float, float], ...]:
        """Explicit via coordinates retained from 3D branch paths."""
        return tuple(
            via
            for branch in self.branches
            if isinstance(branch.path, RoutePath3D)
            for via in branch.path.via_positions
        )

    def iter_segments(
        self,
    ) -> tuple[tuple[tuple[float, float, str], tuple[float, float, str]], ...]:
        """Yield only consecutive points *within* each branch path."""
        segments: list[tuple[tuple[float, float, str], tuple[float, float, str]]] = []
        for branch in self.branches:
            path = branch.path
            if isinstance(path, RoutePath3D):
                nodes = path.segments
            else:
                nodes = [(x, y, path.layer_name) for x, y in path.coordinates]
            segments.extend(zip(nodes, nodes[1:]))
        return tuple(segments)
