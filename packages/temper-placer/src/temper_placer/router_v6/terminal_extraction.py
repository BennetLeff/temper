"""Router-local extraction of stable physical terminals from parsed PCB data.

This module is intentionally planning-only: it turns the parser's existing
net pin references into stable identities and positions, without inferring
pad shapes, clearance, routing permissions, or a layer that the parser did
not declare.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position
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
    components = {component.ref: component for component in getattr(pcb, "components", ())}
    stackup_layers = tuple(getattr(getattr(pcb, "stackup", None), "layers", ()) or ())
    layer_indices = {
        layer.name: layer.index
        for layer in stackup_layers
        if getattr(layer, "name", None) is not None and getattr(layer, "index", None) is not None
    }
    pth_layers = tuple(
        layer.name
        for layer in stackup_layers
        if getattr(layer, "layer_type", None) in {"signal", "mixed"}
    )

    terminals: list[ParsedTerminal] = []
    for component_ref, pad_name in net_pins:
        component = components.get(component_ref)
        if component is None:
            continue
        pin = component.get_pin(pad_name) if hasattr(component, "get_pin") else None
        if pin is None:
            continue
        x, y = pin_world_position(pin, component)
        is_pth = bool(getattr(pin, "is_pth", False))
        layer_names = pth_layers if is_pth else (pin_world_layer(pin),)
        layer_ids = tuple(sorted(layer_indices[name] for name in layer_names if name in layer_indices))
        terminals.append(
            ParsedTerminal(
                identity=PadIdentity(component_ref, str(pin.number), net_name, x, y, layer_ids),
                center=Point(x, y),
                layer_names=layer_names,
                is_pth=is_pth,
            )
        )
    return tuple(sorted(terminals, key=lambda terminal: terminal.identity))
