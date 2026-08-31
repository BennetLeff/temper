"""Pinned Python oracle for ``router_v6/terminal_extraction.py``.

DELIBERATELY RE-PINNED 2026-08-30.
==================================
The original Wave-4 oracle was a verbatim copy from commit
``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5``. It called first-match
``Component.get_pin()`` for every net-pin row, which collapses K2/K3's two
physical same-number relay contact pads onto occurrence zero. The corrected
occurrence contract and its KiCad closure evidence are recorded in
``docs/evidence/2026-08-30-duplicate-pad-occurrence-terminal-closure.md``.

This oracle remains independent Python, but its definitions are now
content-addressed by ``test_terminal_extraction_rust_differential.py``. Do not
edit without a new evidence-backed, deliberately committed re-pin.

Fields this kernel actually reads (the wire-format trap)
-----------------------------------------------------------
``extract_net_terminals`` calls ``pin_world_position`` (-> ``pin_world_position_at``,
``core/pin_geometry.py``) and ``pin_world_layer``, NOT ``pin_world_radius``.
So the fields a faithful Rust port must read are exactly:

* ``component.ref``
* ``component.pins`` -- every pin whose ``.name`` OR ``.number`` equals
  ``pad_name``, in pin-list order; repeated net rows select successive
  physical occurrences. An unmatched occurrence is omitted. Legacy duck
  fixtures with no physical ``pins`` collection retain a first-match
  ``component.get_pin(pad_name)`` fallback.
* ``pin.position`` (a ``(float, float)`` local offset)
* ``pin.number`` (identity's ``pad`` field is ``str(pin.number)``)
* ``pin.is_pth``
* ``pin.layer`` -- ``getattr(pin, "layer", None) or "F.Cu"``: an empty
  string is ALSO falsy in Python, so ``pin.layer == ""`` defaults to
  ``"F.Cu"`` too, not just ``None``/missing.
* ``component.initial_rotation_quadrant`` -- an ``int`` rotation *index* (0-3) per
  the ``Component`` contract (``core/netlist.py``); ``_normalize_rotation``
  technically also accepts a raw float-radians value, but that branch is
  unreachable through the typed ``Component.initial_rotation_quadrant: int | None``
  contract, exactly as ``net_ordering.rs``'s sibling ``pin_world_position``
  documents for the same reason -- so the Rust port takes ``Option<i64>``,
  not a tagged int/float union.
* ``component.initial_side`` -- ``0`` (no mirror) unless it is exactly
  ``1`` (bottom side: ``px = -px`` before rotation). ``comp.initial_side or
  0`` also folds ``None`` to ``0``.
* ``component.initial_position`` -- ``(0.0, 0.0)`` when ``None`` (a non-``None``
  2-tuple is never falsy in Python, even ``(0.0, 0.0)``, so this ``or`` only
  ever fires on ``None``, never on the zero tuple itself).
* the PCB's declared stackup: ``layer.name``, ``layer.index``,
  ``layer.layer_type`` (only ``"signal"``/``"mixed"`` layers feed
  ``pth_layers``; an unknown/undeclared numeric index is never invented).

``roundrect_ratio`` and ``shape`` are NOT read anywhere in this module --
those only feed ``pin_world_radius``, which ``extract_net_terminals`` never
calls. Naming this explicitly because the survey brief called out exactly
this field-omission trap for a *different*, already-defective kernel this
month; it does not apply to this one, and this file exists so a reviewer can
check that claim directly against the verbatim pin above rather than take it
on faith.

Rotation math note: ``rotate_local_to_world`` is R(-theta) --
``geometry/kicad_transform.py``'s documented, evidence-backed KiCad
footprint-child convention -- NOT the naive R(+theta). It is not
special-cased for quadrant angles (``cos(pi/2)`` is
``6.123233995736766e-17``, not exactly ``0``); an axis-swap "optimization"
changes the bit pattern and fails the differential, as
``net_ordering.rs``'s own port of this exact formula documents.

No ``math.hypot``, no ``int()`` truncation, and no ``min``/``max`` over an
iterable anywhere in this module -- position is a rotate + translate, not a
distance. The one iteration-order-sensitive construct is
``layer_indices = {layer.name: layer.index for ...}`` (last-name-wins dict
comprehension over the stackup's *own* declared order, not a hash-randomized
set) and the final ``sorted(terminals, key=lambda t: t.identity)`` (stable
timsort over ``PadIdentity``'s ``order=True`` field-tuple comparison,
pinned the same way ``net_ordering``'s is).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.constraints_geometry import Point

__all__ = ["ParsedTerminal", "extract_net_terminals"]


# --- terminal_extraction.py ------------------------------------------------


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
    occurrence_by_pin: dict[tuple[str, str], int] = {}
    for component_ref, pad_name in net_pins:
        component = components.get(component_ref)
        if component is None:
            continue
        key = (component_ref, pad_name)
        occurrence = occurrence_by_pin.get(key, 0)
        occurrence_by_pin[key] = occurrence + 1
        physical_pins = getattr(component, "pins", None)
        if physical_pins is not None:
            matches = [
                candidate
                for candidate in physical_pins
                if candidate.name == pad_name or candidate.number == pad_name
            ]
            pin = matches[occurrence] if occurrence < len(matches) else None
        else:
            pin = component.get_pin(pad_name) if hasattr(component, "get_pin") else None
        if pin is None:
            continue
        x, y = pin_world_position(pin, component)
        is_pth = bool(getattr(pin, "is_pth", False))
        layer_names = pth_layers if is_pth else (pin_world_layer(pin),)
        layer_ids = tuple(
            sorted(layer_indices[name] for name in layer_names if name in layer_indices)
        )
        terminals.append(
            ParsedTerminal(
                identity=PadIdentity(component_ref, str(pin.number), net_name, x, y, layer_ids),
                center=Point(x, y),
                layer_names=layer_names,
                is_pth=is_pth,
            )
        )
    return tuple(sorted(terminals, key=lambda terminal: terminal.identity))
