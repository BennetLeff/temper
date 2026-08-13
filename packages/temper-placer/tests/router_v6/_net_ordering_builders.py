"""Object builders for the ``net_ordering`` corpus.

``_net_ordering_cases.py`` is pure data on purpose; this module is the
data -> object adapter for the Python arms, kept out of the corpus so the
corpus imports without ``temper_placer``.
"""

from __future__ import annotations

from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType
from temper_placer.core.netlist import Component, Net, Netlist, Pin

__all__ = ["build_loops", "build_netlist", "build_order_netlist"]

_PRIORITIES = {
    "CRITICAL": LoopPriority.CRITICAL,
    "HIGH": LoopPriority.HIGH,
    "MEDIUM": LoopPriority.MEDIUM,
    "LOW": LoopPriority.LOW,
}


def build_netlist(components: list) -> Netlist:
    """``[(ref, initial_position, rotation, [(pin_number, (px, py), net)])]``."""
    def _comp(row):
        # 4-tuple keeps the historical shape; a 5th element carries
        # ``initial_side``, which pin_world_position reads (bottom-side pads
        # mirror X before rotation) and the Rust kernel did not model until
        # 2026-08-06.
        ref, position, rotation, pins = row[:4]
        side = row[4] if len(row) > 4 else None
        kw = {} if side is None else {"initial_side": side}
        return Component(
            ref=ref,
            footprint="TEST",
            bounds=(1.0, 1.0),
            pins=[
                Pin(name=num, number=num, position=pos, net=net, width=0.4, height=0.4)
                for (num, pos, net) in pins
            ],
            initial_position=position,
            initial_rotation_quadrant=rotation,
            **kw,
        )

    comps = [_comp(row) for row in components]
    return Netlist(components=comps, nets=[])


def build_order_netlist(components: list, nets: list) -> Netlist:
    """As :func:`build_netlist`, plus ``[(name, [(ref, pin)], net_class)]``.

    ``net_class`` of ``None`` leaves the ``Net`` default in place, which is
    what makes ``getattr(net, "net_class", None) or "Signal"`` take its
    fall-through branch.
    """
    base = build_netlist(components)
    built = []
    for name, pins, net_class in nets:
        if net_class is None:
            built.append(Net(name=name, pins=list(pins)))
        else:
            built.append(Net(name=name, pins=list(pins), net_class=net_class))
    return Netlist(components=base.components, nets=built)


def build_loops(loop_specs: list) -> LoopCollection:
    """``[(loop_name, priority_name, [net, ...])]`` -> a ``LoopCollection``."""
    collection = LoopCollection(name="corpus", description="")
    for loop_name, priority, nets in loop_specs:
        collection.add_loop(
            Loop(
                name=loop_name,
                loop_type=LoopType.COMMUTATION,
                priority=_PRIORITIES[priority],
                nets=list(nets),
                components=[],
                description="",
            )
        )
    return collection
