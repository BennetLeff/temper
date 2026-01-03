"""
Synthetic PCB generator for ComponentSpacingLoss calibration (EXP-03).

Creates a PCB with various component types at different proximity levels
to test and calibrate the spacing loss function.
"""

import random
from dataclasses import dataclass
from pathlib import Path

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.footprint_library import (
    load_footprint_library,
    FootprintLibrary,
    FootprintSpec,
)


@dataclass
class SpacingTestComponent:
    """Component specification for spacing tests."""

    ref: str
    footprint: str
    bounds: tuple[float, float]
    net_class: str = "Signal"


def generate_spacing_test_netlist(
    seed: int = 42,
    return_board: bool = True,
) -> tuple[Netlist, Board]:
    """
    Generate a synthetic PCB with components at various proximities for spacing loss calibration.

    This creates a board with:
    - Large power components (rectifiers, MOSFETs) that need HV spacing
    - Capacitors of various sizes
    - Small signal components
    - Deliberately close placements to test violation detection

    Args:
        seed: Random seed for reproducibility.
        return_board: If True, return tuple of (netlist, board).

    Returns:
        Tuple of (Netlist, Board) or just Netlist if return_board=False.
    """
    rng = random.Random(seed)

    lib = _create_spacing_test_footprint_library()

    components = []

    comp_id = 0

    large_power_comp_specs = [
        ("D1", "Diode_Bridge", (17.0, 10.0), "Power"),
        ("D2", "Diode_Bridge", (17.0, 10.0), "Power"),
        ("Q1", "TO-220-3", (10.0, 9.0), "Power"),
        ("Q2", "TO-220-3", (10.0, 9.0), "Power"),
        ("Q3", "TO-220-3", (10.0, 9.0), "Power"),
        ("Q4", "TO-220-3", (10.0, 9.0), "Power"),
    ]

    for ref, fp_name, bounds, net_class in large_power_comp_specs:
        spec = lib[fp_name]
        num_pins = 3
        pins = []
        for pin_num in range(num_pins):
            pins.append(
                Pin(
                    name=str(pin_num + 1),
                    number=str(pin_num + 1),
                    position=((pin_num - 1) * 2.54, 0.0),
                    net=None,
                )
            )
        components.append(
            Component(
                ref=ref,
                footprint=fp_name,
                bounds=spec.bounds,
                pins=pins,
                net_class=net_class,
            )
        )
        comp_id += 1

    bus_cap_specs = [
        ("C_BUS1", "C_1206", (3.2, 1.6), "Power"),
        ("C_BUS2", "C_1206", (3.2, 1.6), "Power"),
        ("C_BUS3", "C_1206", (3.2, 1.6), "Power"),
        ("C_BUS4", "C_1206", (3.2, 1.6), "Power"),
    ]

    for ref, fp_name, bounds, net_class in bus_cap_specs:
        spec = lib[fp_name]
        pins = [
            Pin("1", "1", (-spec.width / 2, 0.0), net=None),
            Pin("2", "2", (spec.width / 2, 0.0), net=None),
        ]
        components.append(
            Component(
                ref=ref,
                footprint=fp_name,
                bounds=spec.bounds,
                pins=pins,
                net_class=net_class,
            )
        )
        comp_id += 1

    small_cap_specs = [(f"C{i}", "C_0603", (1.6, 0.8), "Signal") for i in range(1, 21)]

    for ref, fp_name, bounds, net_class in small_cap_specs:
        spec = lib[fp_name]
        pins = [
            Pin("1", "1", (-spec.width / 2, 0.0), net=None),
            Pin("2", "2", (spec.width / 2, 0.0), net=None),
        ]
        components.append(
            Component(
                ref=ref,
                footprint=fp_name,
                bounds=spec.bounds,
                pins=pins,
                net_class=net_class,
            )
        )
        comp_id += 1

    resistor_specs = [(f"R{i}", "0805", (2.0, 1.25), "Signal") for i in range(1, 16)]

    for ref, fp_name, bounds, net_class in resistor_specs:
        spec = lib[fp_name]
        pins = [
            Pin("1", "1", (-spec.width / 2, 0.0), net=None),
            Pin("2", "2", (spec.width / 2, 0.0), net=None),
        ]
        components.append(
            Component(
                ref=ref,
                footprint=fp_name,
                bounds=spec.bounds,
                pins=pins,
                net_class=net_class,
            )
        )
        comp_id += 1

    mosfet_specs = [
        ("U1", "SOIC-8", (5.0, 4.0), "Signal"),
        ("U2", "SOIC-8", (5.0, 4.0), "Signal"),
    ]

    for ref, fp_name, bounds, net_class in mosfet_specs:
        spec = lib[fp_name]
        num_pins = 8
        pins = []
        for pin_num in range(num_pins):
            pins.append(
                Pin(
                    name=str(pin_num + 1),
                    number=str(pin_num + 1),
                    position=((pin_num % 4 - 1.5) * 1.27, (pin_num // 4 - 0.5) * 3.0),
                    net=None,
                )
            )
        components.append(
            Component(
                ref=ref,
                footprint=fp_name,
                bounds=spec.bounds,
                pins=pins,
                net_class=net_class,
            )
        )
        comp_id += 1

    nets = []

    power_nets_config = [
        ("GND", 25),
        ("+12V", 10),
        ("+5V", 8),
        ("PHASE", 6),
    ]

    for net_name, target_fanout in power_nets_config:
        selected_comps = rng.sample(components, min(target_fanout, len(components)))
        pins = []
        for comp in selected_comps:
            if len(comp.pins) > 0:
                pin = comp.pins[0]
                pin.net = net_name
                pins.append((comp.ref, pin.name))

        nets.append(
            Net(
                name=net_name,
                pins=pins,
                net_class="Power",
                weight=2.0,
            )
        )

    signal_net_count = 15
    for i in range(signal_net_count):
        fanout = rng.choice([2, 2, 3])
        available_comps = [c for c in components if any(p.net is None for p in c.pins)]

        if len(available_comps) < fanout:
            continue

        selected_comps = rng.sample(available_comps, fanout)
        pins = []
        for comp in selected_comps:
            unassigned_pins = [p for p in comp.pins if p.net is None]
            if unassigned_pins:
                pin = unassigned_pins[0]
                pin.net = f"SIG_{i}"
                pins.append((comp.ref, pin.name))

        if len(pins) >= 2:
            nets.append(
                Net(
                    name=f"SIG_{i}",
                    pins=pins,
                    net_class="Signal",
                    weight=1.0,
                )
            )

    netlist = Netlist(components=components, nets=nets)
    board = Board(width=80.0, height=60.0, origin=(0.0, 0.0))

    if return_board:
        return netlist, board
    else:
        return netlist


def _create_spacing_test_footprint_library() -> FootprintLibrary:
    """Create footprint library for spacing test components."""
    lib = FootprintLibrary()

    footprints = [
        ("Diode_Bridge", (17.74, 10.0)),
        ("TO-220-3", (10.0, 9.0)),
        ("C_1206", (3.2, 1.6)),
        ("C_0805", (2.0, 1.25)),
        ("C_0603", (1.6, 0.8)),
        ("0805", (2.0, 1.25)),
        ("0603", (1.6, 0.8)),
        ("SOIC-8", (5.0, 4.0)),
        ("QFN-28", (5.0, 5.0)),
    ]

    for name, bounds in footprints:
        lib.add(FootprintSpec(name=name, bounds=bounds))

    return lib


def get_component_positions_for_test(
    netlist: Netlist,
) -> dict[str, tuple[float, float]]:
    """
    Get predefined component positions for testing spacing violations.

    Returns positions that deliberately create spacing violations
    to test the loss function.
    """
    return {
        "D1": (20.0, 30.0),
        "D2": (25.0, 30.0),
        "Q1": (40.0, 30.0),
        "Q2": (45.0, 30.0),
        "Q3": (40.0, 35.0),
        "Q4": (45.0, 35.0),
        "C_BUS1": (22.0, 30.0),
        "C_BUS2": (23.0, 30.0),
        "C_BUS3": (42.0, 30.0),
        "C_BUS4": (43.0, 30.0),
        "C1": (10.0, 10.0),
        "C2": (12.0, 10.0),
        "C3": (14.0, 10.0),
        "C4": (16.0, 10.0),
        "C5": (18.0, 10.0),
        "C6": (10.0, 12.0),
        "C7": (12.0, 12.0),
        "C8": (14.0, 12.0),
        "C9": (16.0, 12.0),
        "C10": (18.0, 12.0),
        "C11": (50.0, 10.0),
        "C12": (52.0, 10.0),
        "C13": (54.0, 10.0),
        "C14": (56.0, 10.0),
        "C15": (58.0, 10.0),
        "C16": (50.0, 12.0),
        "C17": (52.0, 12.0),
        "C18": (54.0, 12.0),
        "C19": (56.0, 12.0),
        "C20": (58.0, 12.0),
        "R1": (10.0, 20.0),
        "R2": (12.0, 20.0),
        "R3": (14.0, 20.0),
        "R4": (16.0, 20.0),
        "R5": (18.0, 20.0),
        "R6": (10.0, 22.0),
        "R7": (12.0, 22.0),
        "R8": (14.0, 22.0),
        "R9": (16.0, 22.0),
        "R10": (18.0, 22.0),
        "R11": (50.0, 20.0),
        "R12": (52.0, 20.0),
        "R13": (54.0, 20.0),
        "R14": (56.0, 20.0),
        "R15": (58.0, 20.0),
        "U1": (30.0, 45.0),
        "U2": (55.0, 45.0),
    }


if __name__ == "__main__":
    netlist, board = generate_spacing_test_netlist(seed=42)
    print(
        f"Generated netlist with {len(netlist.components)} components and {len(netlist.nets)} nets"
    )
    print(f"Board size: {board.width}mm x {board.height}mm")
