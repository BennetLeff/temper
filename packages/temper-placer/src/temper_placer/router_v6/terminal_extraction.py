"""Router-local extraction of stable physical terminals from parsed PCB data.

This module is intentionally planning-only: it turns the parser's existing
net pin references into stable identities and positions, without inferring
pad shapes, clearance, routing permissions, or a layer that the parser did
not declare.

Wave 4 (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``extract_net_terminals`` delegates to ``temper_rust_router``
(``extract_net_terminals_py``). Verified bit-identical against a pinned
pre-migration oracle by
``tests/router_v6/test_terminal_extraction_rust_differential.py`` (oracle:
``tests/router_v6/_terminal_extraction_py_oracle.py``), including the
wire-format field list that oracle documents: ``pin.position``,
``pin.number``, ``pin.is_pth``, ``pin.layer``, ``component.ref``,
``component.initial_rotation``, ``component.initial_side``,
``component.initial_position``, and the stackup's ``name``/``index``/
``layer_type`` -- NOT ``roundrect_ratio``/``shape`` (those only feed
``pin_world_radius``, which this module never calls).

Wave-4 marshalling migration: the ``extract_net_terminals_py`` kernel now
accepts the typed pyclass objects (``Component``, ``Pin``, stackup layer)
directly and extracts their attributes by name internally.  The Python-side
``_pin_wire`` / ``_component_wire`` / ``_stackup_layer_wire`` wire-format
marshalling helpers are deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import temper_rust_router as _trr

from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.constraints_geometry import Point


@dataclass(frozen=True)
class ParsedTerminal:
    """A parsed net terminal with canonical identity and declared layer context."""

    identity: PadIdentity
    center: Point
    layer_names: tuple[str, ...]
    is_pth: bool


def extract_net_terminals(
    pcb: Any,
    net_name: str,
    net_pins: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> tuple[ParsedTerminal, ...]:
    """Extract deterministic terminals from a parsed net's ``(ref, pad)`` pairs.

    Missing components/pins are omitted rather than synthesized.  PTH layer
    context comes only from declared signal/mixed stackup layers; an unknown
    SMD layer is retained textually but has no invented numeric layer index.
    """
    components = list(getattr(pcb, "components", ()))
    stackup = getattr(pcb, "stackup", None)
    stackup_layers = list(getattr(stackup, "layers", ()) or ())

    rows = _trr.extract_net_terminals_py(net_name, list(net_pins), components, stackup_layers)
    return tuple(
        ParsedTerminal(
            identity=PadIdentity(ref, pad, net, x, y, tuple(layers)),
            center=Point(x, y),
            layer_names=tuple(layer_names),
            is_pth=is_pth,
        )
        for ref, pad, net, x, y, layers, layer_names, is_pth in rows
    )
