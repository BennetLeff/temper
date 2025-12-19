"""
Synthetic netlist generator for scale testing.

Generates realistic PCB netlists with configurable component counts
for testing placement optimizer scalability.
"""

from __future__ import annotations

import random
from typing import List, Tuple

from temper_placer.core.netlist import Component, Net, Netlist, Pin


# Component definitions: (prefix, footprints, bounds, net_class)
COMPONENT_TYPES = {
    "passive": {
        "prefixes": ["R", "C", "L"],
        "footprints": [
            ("0805", (2.0, 1.25)),
            ("0603", (1.6, 0.8)),
            ("0402", (1.0, 0.5)),
        ],
        "net_class": "Signal",
        "pins": [("1", "1", (-0.5, 0.0)), ("2", "2", (0.5, 0.0))],
    },
    "ic": {
        "prefixes": ["U"],
        "footprints": [
            ("SOIC-8", (5.0, 4.0)),
            ("SOIC-16", (10.0, 6.0)),
            ("QFN-24", (4.5, 4.5)),
            ("TSSOP-20", (6.5, 4.4)),
        ],
        "net_class": "Signal",
        "pins": None,  # Generated based on footprint
    },
    "power": {
        "prefixes": ["Q", "D"],
        "footprints": [
            ("TO-247", (16.0, 21.0)),
            ("TO-220", (10.0, 15.0)),
        ],
        "net_class": "Power",
        "pins": [
            ("G", "1", (-5.0, 0.0)),
            ("D", "2", (0.0, 0.0)),
            ("S", "3", (5.0, 0.0)),
        ],
    },
    "connector": {
        "prefixes": ["J", "P"],
        "footprints": [
            ("Conn_01x04", (10.0, 5.0)),
            ("Conn_01x08", (20.0, 5.0)),
        ],
        "net_class": "Signal",
        "pins": None,  # Generated based on footprint
    },
}

# Distribution weights (must sum to 1.0)
DISTRIBUTION = {
    "passive": 0.40,
    "ic": 0.30,
    "power": 0.20,
    "connector": 0.10,
}


def _generate_ic_pins(
    footprint: str, bounds: Tuple[float, float]
) -> List[Tuple[str, str, Tuple[float, float]]]:
    """Generate pins for an IC based on footprint."""
    # Extract pin count from footprint name
    if "SOIC-" in footprint:
        n_pins = int(footprint.split("-")[1])
    elif "QFN-" in footprint:
        n_pins = int(footprint.split("-")[1])
    elif "TSSOP-" in footprint:
        n_pins = int(footprint.split("-")[1])
    else:
        n_pins = 8

    pins = []
    half_pins = n_pins // 2
    width, height = bounds

    # Left side pins (going down)
    for i in range(half_pins):
        y_offset = height / 2 - (i + 0.5) * (height / half_pins)
        pins.append((f"{i + 1}", f"{i + 1}", (-width / 2, y_offset)))

    # Right side pins (going up)
    for i in range(half_pins):
        pin_num = half_pins + i + 1
        y_offset = -height / 2 + (i + 0.5) * (height / half_pins)
        pins.append((f"{pin_num}", f"{pin_num}", (width / 2, y_offset)))

    return pins


def _generate_connector_pins(
    footprint: str, bounds: Tuple[float, float]
) -> List[Tuple[str, str, Tuple[float, float]]]:
    """Generate pins for a connector based on footprint."""
    # Extract pin count from footprint name (e.g., Conn_01x04 -> 4)
    n_pins = int(footprint.split("x")[1])

    pins = []
    width, height = bounds
    spacing = width / (n_pins + 1)

    for i in range(n_pins):
        x_offset = -width / 2 + (i + 1) * spacing
        pins.append((f"{i + 1}", f"{i + 1}", (x_offset, 0.0)))

    return pins


def generate_netlist(n_components: int, seed: int = 42) -> Netlist:
    """
    Generate a synthetic netlist with realistic component distribution.

    Args:
        n_components: Total number of components to generate.
        seed: Random seed for reproducibility.

    Returns:
        Netlist with specified number of components and realistic nets.
    """
    rng = random.Random(seed)

    components: List[Component] = []
    component_counters: dict[str, int] = {}

    # Calculate how many of each type
    type_counts = {}
    remaining = n_components
    for comp_type, weight in DISTRIBUTION.items():
        count = int(n_components * weight)
        type_counts[comp_type] = count
        remaining -= count

    # Distribute remainder to passives (most common)
    type_counts["passive"] += remaining

    # Generate components
    for comp_type, count in type_counts.items():
        type_info = COMPONENT_TYPES[comp_type]

        for _ in range(count):
            # Select random prefix and footprint
            prefix = rng.choice(type_info["prefixes"])
            footprint_name, bounds = rng.choice(type_info["footprints"])

            # Generate unique reference
            counter = component_counters.get(prefix, 0) + 1
            component_counters[prefix] = counter
            ref = f"{prefix}{counter}"

            # Generate pins
            if type_info["pins"] is None:
                if comp_type == "ic":
                    pin_defs = _generate_ic_pins(footprint_name, bounds)
                else:  # connector
                    pin_defs = _generate_connector_pins(footprint_name, bounds)
            else:
                pin_defs = type_info["pins"]

            pins = [Pin(name=name, number=number, position=pos) for name, number, pos in pin_defs]

            components.append(
                Component(
                    ref=ref,
                    footprint=footprint_name,
                    bounds=bounds,
                    pins=pins,
                    net_class=type_info["net_class"],
                )
            )

    # Generate nets
    nets: List[Net] = []

    # 1. Power rails (VCC, GND) - connect to ICs and some passives
    ic_refs = [c.ref for c in components if c.footprint.startswith(("SOIC", "QFN", "TSSOP"))]
    power_refs = [c.ref for c in components if c.footprint.startswith(("TO-247", "TO-220"))]

    # VCC net
    vcc_pins: List[Tuple[str, str]] = []
    for ref in ic_refs:
        comp = next(c for c in components if c.ref == ref)
        # Use a pin (typically pin 8 or highest numbered for VCC)
        if comp.pins:
            vcc_pin = comp.pins[-1]  # Last pin often VCC
            vcc_pin.net = "VCC"
            vcc_pins.append((ref, vcc_pin.name))

    if vcc_pins:
        nets.append(Net("VCC", vcc_pins, net_class="Power", weight=1.0))

    # GND net
    gnd_pins: List[Tuple[str, str]] = []
    for ref in ic_refs:
        comp = next(c for c in components if c.ref == ref)
        if comp.pins and len(comp.pins) > 1:
            # Pin 1 or middle pin often GND
            gnd_pin = comp.pins[len(comp.pins) // 2]
            gnd_pin.net = "GND"
            gnd_pins.append((ref, gnd_pin.name))

    # Add power components to GND
    for ref in power_refs:
        comp = next(c for c in components if c.ref == ref)
        if comp.pins:
            s_pin = next((p for p in comp.pins if p.name == "S"), comp.pins[-1])
            s_pin.net = "GND"
            gnd_pins.append((ref, s_pin.name))

    if gnd_pins:
        nets.append(Net("GND", gnd_pins, net_class="Power", weight=1.0))

    # 2. Signal nets - connect 2-5 components each
    signal_net_count = 0
    passive_refs = [c.ref for c in components if c.footprint.startswith(("0805", "0603", "0402"))]
    all_refs = [c.ref for c in components]

    # Create signal chains
    available_for_signal = list(all_refs)
    rng.shuffle(available_for_signal)

    while len(available_for_signal) >= 2:
        # Random net size: 2-5 components
        net_size = min(rng.randint(2, 5), len(available_for_signal))
        net_refs = available_for_signal[:net_size]
        available_for_signal = available_for_signal[net_size:]

        signal_net_count += 1
        net_name = f"NET_{signal_net_count}"

        net_pins: List[Tuple[str, str]] = []
        for ref in net_refs:
            comp = next(c for c in components if c.ref == ref)
            if comp.pins:
                # Pick a random unused pin
                unused_pins = [p for p in comp.pins if p.net is None]
                if unused_pins:
                    pin = rng.choice(unused_pins)
                    pin.net = net_name
                    net_pins.append((ref, pin.name))

        if len(net_pins) >= 2:
            weight = rng.uniform(0.5, 2.0)
            nets.append(Net(net_name, net_pins, net_class="Signal", weight=weight))

    # 3. Decoupling nets - connect passives near ICs
    decap_net_count = 0
    for ic_ref in ic_refs[: len(ic_refs) // 2]:  # Half of ICs get decoupling
        if not passive_refs:
            break

        # Find a passive for decoupling
        passive_ref = passive_refs.pop(0) if passive_refs else None
        if passive_ref is None:
            continue

        ic_comp = next(c for c in components if c.ref == ic_ref)
        passive_comp = next(c for c in components if c.ref == passive_ref)

        # Connect IC VCC pin to capacitor
        if ic_comp.pins and passive_comp.pins:
            decap_net_count += 1
            net_name = f"DECAP_{decap_net_count}"

            ic_pin = ic_comp.pins[-1]  # Assume last is VCC
            cap_pin = passive_comp.pins[0]

            ic_pin.net = net_name
            cap_pin.net = net_name

            nets.append(
                Net(
                    net_name,
                    [(ic_ref, ic_pin.name), (passive_ref, cap_pin.name)],
                    net_class="Signal",
                    weight=3.0,  # High weight - decoupling should be close
                )
            )

    return Netlist(components=components, nets=nets)
