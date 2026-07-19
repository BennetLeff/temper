"""Deterministic terminal-tree planning for future all-pad A* routing.

This module deliberately plans topology only.  A future router integration
will route each returned edge from its ``source`` pad/component into copper
already committed for this net, validate it with ``connectivity.py``, and only
then add the target to that component.  No direct geometry is created here.
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.connectivity import CopperPad, PadIdentity


@dataclass(frozen=True)
class TerminalTreeEdge:
    """A requested attachment from the connected component to one terminal."""

    source: PadIdentity
    target: PadIdentity


@dataclass(frozen=True)
class TerminalTreePlan:
    """A deterministic Prim-style tree over all required pad terminals."""

    root: PadIdentity
    edges: tuple[TerminalTreeEdge, ...]


def plan_terminal_tree(pads: list[CopperPad] | tuple[CopperPad, ...]) -> TerminalTreePlan:
    """Plan a deterministic component-aware spanning tree.

    The lexicographically smallest canonical identity is the root.  At every
    step the candidate with lowest Manhattan distance from *any* already
    connected terminal wins; identity keys break all geometric ties.  This is
    Prim-style component attachment rather than a serial nearest-neighbour
    route order, so later A* work can attach to any legal copper point in the
    existing component without changing the plan contract.
    """
    terminals = {pad.identity: pad for pad in pads}
    if not terminals:
        raise ValueError("terminal tree requires at least one pad")
    root = min(terminals)
    connected = {root}
    remaining = set(terminals) - connected
    edges: list[TerminalTreeEdge] = []

    while remaining:
        source, target = min(
            (
                (source, target)
                for source in connected
                for target in remaining
            ),
            key=lambda pair: (
                _manhattan(terminals[pair[0]], terminals[pair[1]]),
                pair[0],
                pair[1],
            ),
        )
        edges.append(TerminalTreeEdge(source, target))
        connected.add(target)
        remaining.remove(target)

    return TerminalTreePlan(root=root, edges=tuple(edges))


def _manhattan(left: CopperPad, right: CopperPad) -> float:
    return abs(left.center.x - right.center.x) + abs(left.center.y - right.center.y)
