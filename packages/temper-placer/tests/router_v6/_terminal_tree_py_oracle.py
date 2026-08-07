"""Pinned Python oracle for ``router_v6/terminal_tree.py`` (Wave-4 terminal-tree slice).

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
Every executable statement below is a **verbatim** ``git show`` extraction
from commit ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``,
2026-08-03) of ``temper_placer/router_v6/terminal_tree.py``: ``TreeTerminal``,
``TerminalTreeEdge``, ``TerminalTreePlan``, ``plan_terminal_tree``,
``_manhattan`` -- the whole module except its import block and module
docstring.

Nothing has been cleaned up, refactored, or fixed.
``test_terminal_tree_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts each definition from the pinned commit and compares the source
text character for character.

Why the "no hash-order leak" claim actually holds here
--------------------------------------------------------
``plan_terminal_tree`` looks, at first read, like exactly the class of bug
``scripts/check_hash_order_determinism.py`` exists to catch: it builds
``terminals = {pad.identity: pad for pad in pads}`` (a ``dict`` -- fine,
dicts preserve insertion order) but then does
``remaining = set(terminals) - connected`` and iterates
``((source, target) for source in connected for target in remaining)`` --
**both ``connected`` and ``remaining`` are genuine Python ``set``s**, whose
iteration order depends on the process's salted string hash (PEP 456).

It does not leak, because of what the iteration feeds: ``min(..., key=lambda
pair: (_manhattan(...), pair[0], pair[1]))``. ``pair[0]`` and ``pair[1]`` are
``PadIdentity`` values (``@dataclass(frozen=True, order=True)``,
``router_v6/connectivity.py``) included **by value** in the key tuple, not
just implicitly through set membership. Since ``terminals`` is keyed by
identity, ``pads`` fed to one call never contains two distinct entries with
an equal ``PadIdentity`` after the dict dedup, so for any two *different*
``(source, target)`` pairs, ``pair[0]`` or ``pair[1]`` (or both) differ --
and PadIdentity's ``order=True`` comparison is a plain field-tuple compare,
not hash-based. The full key tuple therefore has a unique minimum regardless
of what order ``connected``/``remaining`` hand pairs to ``min``, i.e. the
result of ``plan_terminal_tree`` is a pure function of ``pads`` and does NOT
depend on ``PYTHONHASHSEED``. This is why the module docstring can say
"identity keys break all geometric ties" -- measured directly by
``test_planned_tree_is_acyclic_connected_and_permutation_invariant`` in
``test_terminal_tree_planner.py`` across permutation of pad order, and
re-verified here across ten distinct interpreter processes with
``PYTHONHASHSEED`` unset in ``test_trap_hash_order_does_not_leak_into_output``.

A Rust port therefore does NOT need to reproduce CPython set iteration order
at all -- any consistent iteration order over the connected/remaining
partition (e.g. plain ascending index) reproduces the oracle's output
exactly, because the tie-break key itself is what CPython's ``min`` actually
resolves ties on, and it is collision-free by construction.

``float`` note: ``_manhattan`` returns ``abs(x1 - x2) + abs(y1 - y2)`` -- a
Manhattan distance, not ``math.hypot`` and not ``sqrt(dx**2 + dy**2)``. Do
not substitute either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.constraints_geometry import Point

__all__ = ["TreeTerminal", "TerminalTreeEdge", "TerminalTreePlan", "plan_terminal_tree", "_manhattan"]


# --- terminal_tree.py -----------------------------------------------------


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


def plan_terminal_tree(pads: list[TreeTerminal] | tuple[TreeTerminal, ...]) -> TerminalTreePlan:
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
            ((source, target) for source in connected for target in remaining),
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


def _manhattan(left: TreeTerminal, right: TreeTerminal) -> float:
    return abs(left.center.x - right.center.x) + abs(left.center.y - right.center.y)
