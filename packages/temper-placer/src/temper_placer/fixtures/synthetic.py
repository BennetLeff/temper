"""
Synthetic netlist generation for scale testing (temper-1my.3.3).

Generates realistic PCB netlists with configurable component counts and
connectivity patterns. Used for validation, benchmarking, and stress testing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.footprint_library import load_footprint_library


@dataclass
class ComponentDistribution:
    """Specification for component type distribution."""
    resistors: int = 80
    capacitors: int = 50
    ics: int = 25
    inductors: int = 10
    connectors: int = 15
    discretes: int = 20

    @property
    def total(self) -> int:
        return (self.resistors + self.capacitors + self.ics +
                self.inductors + self.connectors + self.discretes)


@dataclass
class NetTopology:
    """Specification for netlist topology."""
    power_nets: int = 4
    signal_nets: int = 100
    bus_nets: int = 2  # I2C, SPI, etc.


@dataclass
class SyntheticNetlistResult:
    """Result of synthetic netlist generation."""
    netlist: Netlist
    board: Board | None = None


def generate_200_component_netlist(
    seed: int = 42,
    return_board: bool = False,
) -> Netlist | SyntheticNetlistResult:
    """
    Generate a synthetic 200-component netlist with realistic connectivity.

    Component Distribution:
        - 80 resistors (0603, 0805, 2512)
        - 50 capacitors (C_0603, C_0805, C_1206)
        - 25 ICs (QFN-56, SOIC-8, TSSOP-20)
        - 10 inductors (L_0805, L_1210, Inductor_SMD_10x10)
        - 15 connectors (various JST, screw terminals)
        - 20 discretes (SOT-23, SOD-123, TO-220-3)

    Connectivity Pattern:
        - Power nets (GND, +3V3, +5V, +12V): high fanout (20-50 pins each)
        - Signal nets (~100 nets): low fanout (2-4 pins each)
        - Bus nets (I2C, SPI): medium fanout (5-10 pins each)

    Args:
        seed: Random seed for reproducibility.
        return_board: If True, return SyntheticNetlistResult with board.
                     If False, return just Netlist.

    Returns:
        Netlist with 200 components, or SyntheticNetlistResult if return_board=True.

    Example:
        >>> netlist = generate_200_component_netlist(seed=42)
        >>> len(netlist.components)
        200
    """
    rng = random.Random(seed)

    # Load footprint library
    library_path = Path("configs/footprint_library.yaml")
    if library_path.exists():
        lib = load_footprint_library(library_path)
    else:
        # Fallback: create minimal library
        lib = _create_minimal_footprint_library()

    # Generate components
    components = []

    # Resistors (80 total)
    resistor_footprints = ["0603"] * 60 + ["0805"] * 15 + ["2512"] * 5
    for i, fp in enumerate(resistor_footprints):
        spec = lib[fp]
        pins = [
            Pin("1", "1", (-spec.width/2, 0.0), net=None),
            Pin("2", "2", (spec.width/2, 0.0), net=None),
        ]
        components.append(Component(
            ref=f"R{i+1}",
            footprint=fp,
            bounds=spec.bounds,
            pins=pins,
            net_class="Signal",
        ))

    # Capacitors (50 total)
    cap_footprints = ["C_0603"] * 30 + ["C_0805"] * 15 + ["C_1206"] * 5
    for i, fp in enumerate(cap_footprints):
        spec = lib[fp]
        pins = [
            Pin("1", "1", (-spec.width/2, 0.0), net=None),
            Pin("2", "2", (spec.width/2, 0.0), net=None),
        ]
        components.append(Component(
            ref=f"C{i+1}",
            footprint=fp,
            bounds=spec.bounds,
            pins=pins,
            net_class="Signal",
        ))

    # ICs (25 total)
    ic_configs = [
        ("QFN-56", 10, 28),      # 10 MCUs with 28 pins each
        ("SOIC-8", 10, 8),        # 10 op-amps/comparators
        ("TSSOP-20", 5, 20),      # 5 specialized ICs
    ]
    ic_num = 1
    for footprint, count, num_pins in ic_configs:
        spec = lib[footprint]
        for _ in range(count):
            # Generate pins in a grid around perimeter
            pins = []
            for pin_num in range(num_pins):
                # Simple pin layout (not geometrically accurate but functional)
                angle = (pin_num / num_pins) * 2 * 3.14159
                offset_x = (spec.width / 2.5) * (1 if angle < 3.14159 else -1)
                offset_y = (spec.height / 2.5) * (1 if 0.785 < angle < 2.356 else -1)
                pins.append(Pin(
                    name=str(pin_num + 1),
                    number=str(pin_num + 1),
                    position=(offset_x, offset_y),
                    net=None,
                ))

            components.append(Component(
                ref=f"U{ic_num}",
                footprint=footprint,
                bounds=spec.bounds,
                pins=pins,
                net_class="Signal",
            ))
            ic_num += 1

    # Inductors (10 total)
    inductor_footprints = ["L_0805"] * 5 + ["L_1210"] * 3 + ["Inductor_SMD_10x10"] * 2
    for i, fp in enumerate(inductor_footprints):
        spec = lib[fp]
        pins = [
            Pin("1", "1", (-spec.width/2, 0.0), net=None),
            Pin("2", "2", (spec.width/2, 0.0), net=None),
        ]
        components.append(Component(
            ref=f"L{i+1}",
            footprint=fp,
            bounds=spec.bounds,
            pins=pins,
            net_class="Power",
        ))

    # Connectors (15 total)
    connector_footprints = ["Connector_JST_XH_2P"] * 8 + ["Connector_JST_XH_3P"] * 5 + ["Connector_Screw_Terminal_2P"] * 2
    for i, fp in enumerate(connector_footprints):
        spec = lib[fp]
        num_pins = 2 if "2P" in fp else 3
        pins = []
        for pin_num in range(num_pins):
            pins.append(Pin(
                name=str(pin_num + 1),
                number=str(pin_num + 1),
                position=(pin_num * 2.5 - (num_pins - 1) * 1.25, 0.0),
                net=None,
            ))
        components.append(Component(
            ref=f"J{i+1}",
            footprint=fp,
            bounds=spec.bounds,
            pins=pins,
            net_class="Signal",
        ))

    # Discretes (20 total)
    discrete_footprints = ["SOT-23"] * 15 + ["SOD-123"] * 3 + ["TO-220-3"] * 2
    for i, fp in enumerate(discrete_footprints):
        spec = lib[fp]
        num_pins = 3 if "SOT-23" in fp or "TO-220" in fp else 2
        pins = []
        for pin_num in range(num_pins):
            pins.append(Pin(
                name=str(pin_num + 1),
                number=str(pin_num + 1),
                position=((pin_num - num_pins/2 + 0.5) * 1.27, 0.0),
                net=None,
            ))
        components.append(Component(
            ref=f"Q{i+1}" if "TO-220" in fp else f"D{i+1}",
            footprint=fp,
            bounds=spec.bounds,
            pins=pins,
            net_class="Signal" if "SOD" in fp else "Power",
        ))

    # Generate nets
    nets = []

    # Power nets (high fanout)
    power_nets_config = [
        ("GND", 80),
        ("+3V3", 40),
        ("+5V", 30),
        ("+12V", 20),
    ]

    for net_name, target_fanout in power_nets_config:
        # Select random components for this power net
        selected_comps = rng.sample(components, min(target_fanout, len(components)))
        pins = []
        for comp in selected_comps:
            if len(comp.pins) > 0:
                # Use first available pin
                pin = comp.pins[0]
                pin.net = net_name
                pins.append((comp.ref, pin.name))

        nets.append(Net(
            name=net_name,
            pins=pins,
            net_class="Power",
            weight=2.0,
        ))

    # Signal nets (low fanout, 2-4 pins)
    signal_net_count = 100
    for i in range(signal_net_count):
        fanout = rng.choice([2, 2, 3, 3, 4])  # Weighted toward 2-3 pins
        available_comps = [c for c in components if any(p.net is None for p in c.pins)]

        if len(available_comps) < fanout:
            continue

        selected_comps = rng.sample(available_comps, fanout)
        pins = []
        for comp in selected_comps:
            # Find first unassigned pin
            unassigned_pins = [p for p in comp.pins if p.net is None]
            if unassigned_pins:
                pin = unassigned_pins[0]
                pin.net = f"SIG_{i}"
                pins.append((comp.ref, pin.name))

        if len(pins) >= 2:
            nets.append(Net(
                name=f"SIG_{i}",
                pins=pins,
                net_class="Signal",
                weight=1.0,
            ))

    # Bus nets (medium fanout, 5-10 pins)
    bus_configs = [
        ("I2C_SDA", 8),
        ("I2C_SCL", 8),
        ("SPI_MOSI", 6),
        ("SPI_MISO", 6),
        ("SPI_SCK", 6),
    ]

    for net_name, fanout in bus_configs:
        available_comps = [c for c in components if any(p.net is None for p in c.pins)]

        if len(available_comps) < fanout:
            fanout = len(available_comps)

        selected_comps = rng.sample(available_comps, min(fanout, len(available_comps)))
        pins = []
        for comp in selected_comps:
            unassigned_pins = [p for p in comp.pins if p.net is None]
            if unassigned_pins:
                pin = unassigned_pins[0]
                pin.net = net_name
                pins.append((comp.ref, pin.name))

        if len(pins) >= 2:
            nets.append(Net(
                name=net_name,
                pins=pins,
                net_class="Signal",
                weight=1.5,
            ))

    netlist = Netlist(components=components, nets=nets)

    if return_board:
        board = Board(width=150.0, height=100.0, origin=(0.0, 0.0))
        return SyntheticNetlistResult(netlist=netlist, board=board)
    else:
        return netlist


def _create_minimal_footprint_library():
    """Create minimal footprint library for testing when file not available."""
    from temper_placer.io.footprint_library import FootprintLibrary, FootprintSpec

    lib = FootprintLibrary()

    # Minimal set of footprints
    footprints = [
        ("0603", (1.6, 0.8)),
        ("0805", (2.0, 1.25)),
        ("2512", (6.4, 3.2)),
        ("C_0603", (1.6, 0.8)),
        ("C_0805", (2.0, 1.25)),
        ("C_1206", (3.2, 1.6)),
        ("L_0805", (2.0, 1.25)),
        ("L_1210", (3.2, 2.5)),
        ("Inductor_SMD_10x10", (10.5, 10.5)),
        ("QFN-56", (7.0, 7.0)),
        ("SOIC-8", (5.0, 4.0)),
        ("TSSOP-20", (6.5, 4.4)),
        ("SOT-23", (2.9, 1.3)),
        ("SOD-123", (2.7, 1.6)),
        ("TO-220-3", (10.0, 9.0)),
        ("Connector_JST_XH_2P", (7.5, 5.0)),
        ("Connector_JST_XH_3P", (10.0, 5.0)),
        ("Connector_Screw_Terminal_2P", (10.0, 8.0)),
    ]

    for name, bounds in footprints:
        lib.add(FootprintSpec(name=name, bounds=bounds))

    return lib
