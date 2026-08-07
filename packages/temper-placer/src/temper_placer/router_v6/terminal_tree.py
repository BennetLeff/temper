"""Deterministic terminal-tree planning for future all-pad A* routing.

This module deliberately plans topology only.  A future router integration
will route each returned edge from its ``source`` pad/component into copper
already committed for this net, validate it with ``connectivity.py``, and only
then add the target to that component.  No direct geometry is created here.

Wave 4 (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``plan_terminal_tree`` delegates to ``temper_rust_router``
(``plan_terminal_tree_py``). Verified bit-identical against a pinned
pre-migration oracle by
``tests/router_v6/test_terminal_tree_rust_differential.py`` (oracle:
``tests/router_v6/_terminal_tree_py_oracle.py``), including the argument
(documented in both the oracle and the kernel) that this kernel does not
need to reproduce CPython's hash-randomized ``set`` iteration order: the
``min(key=...)`` tie-break key embeds the candidate ``PadIdentity`` values
themselves, so it has a unique minimum regardless of iteration order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import temper_rust_router as _trr

from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.constraints_geometry import Point


class TreeTerminal(Protocol):
    """The minimal physical terminal data required by the topology planner.

    ``layer_names`` is optional at the planning stage (topology only) but
    required by the executor for multi-layer shared-layer selection.
    """

    identity: PadIdentity
    center: Point
    layer_names: tuple[str, ...] | None = None


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


def _identity_wire(identity: PadIdentity) -> tuple:
    return (
        identity.component_ref,
        identity.pad,
        identity.net,
        identity.x,
        identity.y,
        list(identity.layers),
    )


def _identity_from_wire(wire: tuple) -> PadIdentity:
    component_ref, pad, net, x, y, layers = wire
    return PadIdentity(component_ref, pad, net, x, y, tuple(layers))


def plan_terminal_tree(pads: list[TreeTerminal] | tuple[TreeTerminal, ...]) -> TerminalTreePlan:
    """Plan a deterministic component-aware spanning tree.

    The lexicographically smallest canonical identity is the root.  At every
    step the candidate with lowest Manhattan distance from *any* already
    connected terminal wins; identity keys break all geometric ties.  This is
    Prim-style component attachment rather than a serial nearest-neighbour
    route order, so later A* work can attach to any legal copper point in the
    existing component without changing the plan contract.
    """
    pads_wire = [(*_identity_wire(pad.identity), pad.center.x, pad.center.y) for pad in pads]
    # The empty-input ValueError is raised by the Rust kernel itself (not
    # pre-checked here) -- see plan_terminal_tree_py's PyValueError mapping.
    root_wire, edges_wire = _trr.plan_terminal_tree_py(pads_wire)
    root = _identity_from_wire(root_wire)
    edges = tuple(
        TerminalTreeEdge(_identity_from_wire(source), _identity_from_wire(target))
        for source, target in edges_wire
    )
    return TerminalTreePlan(root=root, edges=edges)
