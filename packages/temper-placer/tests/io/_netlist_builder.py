"""Minimal Netlist construction helpers for the config-loader differentials.

Builds a two-component Netlist through the same Rust-backed contracts the
config loader produces/consumes (``temper_placer.core.netlist`` re-exports
the ``netlist_contracts`` pyclasses). Kept here so both the oracle arm and
the Rust arm drive byte-identical inputs.
"""

from __future__ import annotations

from temper_placer.core.netlist import Component, Net, Netlist


def build_two_component_netlist() -> Netlist:
    """A netlist with R1 (zones assignable) and R2 (fixed-position assignable)."""
    return Netlist(
        components=[
            Component(
                ref="R1",
                footprint="0805",
                bounds=(2.0, 1.25),
                net_class="Signal",
            ),
            Component(
                ref="R2",
                footprint="0603",
                bounds=(1.6, 0.8),
                net_class="Signal",
            ),
        ],
        nets=[
            Net(name="NET_A", pins=[("R1", "1"), ("R2", "1")], net_class="Signal"),
        ],
    )
