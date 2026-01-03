#!/usr/bin/env python3
"""
EXP-24: Full HV/LV Zone Integration

Integration test combining power zone + control zone routing.
Key challenges: zone-to-zone creepage enforcement, inter-zone signal routing, hierarchical routing fallback.

Tests:
1. Power zone routing (HV traces, 6.5mm creepage requirements)
2. Control zone routing (LV traces, standard clearance)
3. Inter-zone routing (signals crossing HV/LV boundary)
4. Creepage enforcement at zone boundaries
5. Hierarchical routing fallback when direct path blocked
"""

import sys
import logging
from pathlib import Path
import jax.numpy as jnp
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board, Zone, LayerStackup, MountingHole
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.core.design_rules import NetClassRules
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.hierarchical import route_net_hierarchical

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def create_board_with_zones():
    """Create a board with HV and LV zones separated by creepage barrier."""
    return Board(
        width=100.0,
        height=100.0,
        zones=[
            Zone("HV_ZONE", (0, 0, 45, 100), net_classes=["HighVoltage", "Power"]),
            Zone("LV_ZONE", (55, 0, 100, 100), net_classes=["Signal", "Power"]),
        ],
        mounting_holes=[
            MountingHole((5, 5), 3.2),
            MountingHole((95, 5), 3.2),
            MountingHole((5, 95), 3.2),
            MountingHole((95, 95), 3.2),
        ],
    )


def create_integration_netlist():
    """Create netlist spanning HV and LV zones."""
    components = [
        Component(
            ref="U_ISO",
            footprint="Opto_Wide",
            bounds=(12, 8),
            initial_position=(50, 50),
            initial_side=0,
            pins=[
                Pin(name="ANODE", number="1", net="PWM_OUT_LV", position=(-4.0, -2.0)),
                Pin(name="CATHODE", number="2", net="GND_LV", position=(-4.0, 2.0)),
                Pin(name="EMITTER", number="3", net="GND_HV", position=(4.0, 2.0)),
                Pin(name="COLLECTOR", number="4", net="PWM_IN_HV", position=(4.0, -2.0)),
            ],
        ),
        Component(
            ref="J_LV",
            footprint="Header_2",
            bounds=(5, 10),
            initial_position=(20, 50),
            initial_side=0,
            pins=[
                Pin(name="1", number="1", net="PWM_OUT_LV", position=(-2.0, -3.0)),
                Pin(name="2", number="2", net="GND_LV", position=(2.0, -3.0)),
            ],
        ),
        Component(
            ref="J_HV",
            footprint="Header_2",
            bounds=(5, 10),
            initial_position=(80, 50),
            initial_side=0,
            pins=[
                Pin(name="1", number="1", net="PWM_IN_HV", position=(-2.0, -3.0)),
                Pin(name="2", number="2", net="GND_HV", position=(2.0, -3.0)),
            ],
        ),
        Component(
            ref="T_POWER",
            footprint="Transformer_SMPS",
            bounds=(15, 20),
            initial_position=(25, 20),
            initial_side=0,
            pins=[
                Pin(name="PRI_A", number="1", net="VCC_HV", position=(-5.0, 7.0)),
                Pin(name="PRI_B", number="2", net="GND_HV", position=(5.0, 7.0)),
                Pin(name="SEC_A", number="3", net="VCC_LV", position=(-5.0, -7.0)),
                Pin(name="SEC_B", number="4", net="GND_LV", position=(5.0, -7.0)),
            ],
        ),
        Component(
            ref="U_MCU",
            footprint="QFN_48",
            bounds=(7, 7),
            initial_position=(75, 80),
            initial_side=0,
            pins=[
                Pin(name="PWM", number="1", net="PWM_OUT_LV", position=(-2.5, -2.5)),
                Pin(name="GND", number="2", net="GND_LV", position=(-1.5, -2.5)),
                Pin(name="TX", number="3", net="UART_TX", position=(-0.5, -2.5)),
                Pin(name="RX", number="4", net="UART_RX", position=(0.5, -2.5)),
            ],
        ),
        Component(
            ref="J_DEBUG",
            footprint="Header_4",
            bounds=(5, 10),
            initial_position=(75, 20),
            initial_side=0,
            pins=[
                Pin(name="1", number="1", net="UART_TX", position=(-2.0, -3.0)),
                Pin(name="2", number="2", net="UART_RX", position=(0.0, -3.0)),
                Pin(name="3", number="3", net="GND_LV", position=(2.0, -3.0)),
                Pin(name="4", number="4", net="VCC_LV", position=(4.0, -3.0)),
            ],
        ),
    ]

    net_map = {
        "PWM_OUT_LV": [("U_MCU", "1"), ("U_ISO", "1"), ("J_LV", "1")],
        "PWM_IN_HV": [("U_ISO", "4"), ("J_HV", "1")],
        "GND_LV": [
            ("U_MCU", "2"),
            ("U_ISO", "2"),
            ("J_LV", "2"),
            ("T_POWER", "4"),
            ("J_DEBUG", "3"),
        ],
        "GND_HV": [("U_ISO", "3"), ("J_HV", "2"), ("T_POWER", "2")],
        "VCC_HV": [("T_POWER", "1"), ("J_HV", "2")],
        "VCC_LV": [("T_POWER", "3"), ("J_DEBUG", "4")],
        "UART_TX": [("U_MCU", "3"), ("J_DEBUG", "1")],
        "UART_RX": [("U_MCU", "4"), ("J_DEBUG", "2")],
    }

    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    return Netlist(components=components, nets=nets)


def configure_net_classes(dr):
    """Configure net class rules for HV/LV separation."""
    dr.net_overrides["PWM_IN_HV"] = NetClassRules(
        name="HighVoltage",
        trace_width=0.3,
        clearance=6.5,
        creepage_mm=6.5,
        via_template="Via1x1",
    )
    dr.net_overrides["VCC_HV"] = NetClassRules(
        name="HighVoltage",
        trace_width=0.8,
        clearance=6.5,
        creepage_mm=6.5,
        via_template="Via1x1",
    )
    dr.net_overrides["GND_HV"] = NetClassRules(
        name="HighVoltage",
        trace_width=0.5,
        clearance=6.5,
        creepage_mm=6.5,
        via_template="Via1x1",
    )
    dr.net_overrides["PWM_OUT_LV"] = NetClassRules(
        name="Signal",
        trace_width=0.2,
        clearance=0.2,
        creepage_mm=0.2,
        via_template="Via1x1",
    )
    dr.net_overrides["UART_TX"] = NetClassRules(
        name="Signal",
        trace_width=0.2,
        clearance=0.2,
        via_template="Via1x1",
    )
    dr.net_overrides["UART_RX"] = NetClassRules(
        name="Signal",
        trace_width=0.2,
        clearance=0.2,
        via_template="Via1x1",
    )


def run_zone_integration_test():
    """Run the full HV/LV zone integration experiment."""
    print("=" * 60)
    print("EXP-24: Full HV/LV Zone Integration Test")
    print("=" * 60)

    board = create_board_with_zones()
    netlist = create_integration_netlist()

    config_path = (
        Path(__file__).parent.parent.parent
        / "packages"
        / "temper-placer"
        / "configs"
        / "temper_constraints.yaml"
    )
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)
    configure_net_classes(dr)

    print(f"\nBoard: {board.width}x{board.height}mm with zones:")
    for zone in board.zones:
        print(f"  - {zone.name}: {zone.bounds}")

    print(f"\nNetlist: {len(netlist.nets)} nets, {len(netlist.components)} components")

    router = MazeRouter(
        grid_size=(500, 500),
        cell_size_mm=0.2,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1,
    )

    router.block_pads(
        netlist.components, jnp.array([c.initial_position for c in netlist.components]), netlist
    )

    results = {}

    print("\n" + "-" * 40)
    print("TEST 1: LV Zone Routing (Control signals)")
    print("-" * 40)

    res = route_net_hierarchical(
        router,
        net_name="PWM_OUT_LV",
        pin_positions=[(75.0, 80.0), (46.0, 50.0), (18.0, 50.0)],
        assignment=LayerAssignment(
            net="PWM_OUT_LV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
        trace_width_mm=0.2,
        clearance_mm=0.2,
    )
    results["PWM_OUT_LV"] = res
    print(
        f"  Result: {'SUCCESS' if res.success else 'FAILED'} - {res.failure_reason or f'Length: {res.length:.1f}mm'}"
    )

    print("\n" + "-" * 40)
    print("TEST 2: HV Zone Routing (Power signals)")
    print("-" * 40)

    res = route_net_hierarchical(
        router,
        net_name="PWM_IN_HV",
        pin_positions=[(54.0, 50.0), (82.0, 50.0)],
        assignment=LayerAssignment(
            net="PWM_IN_HV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
        trace_width_mm=0.3,
        clearance_mm=6.5,
    )
    results["PWM_IN_HV"] = res
    print(
        f"  Result: {'SUCCESS' if res.success else 'FAILED'} - {res.failure_reason or f'Length: {res.length:.1f}mm'}"
    )

    print("\n" + "-" * 40)
    print("TEST 3: Inter-zone Routing (UART across zones)")
    print("-" * 40)

    res = route_net_hierarchical(
        router,
        net_name="UART_TX",
        pin_positions=[(72.5, 80.0), (73.0, 20.0)],
        assignment=LayerAssignment(
            net="UART_TX", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
        trace_width_mm=0.2,
        clearance_mm=0.2,
    )
    results["UART_TX"] = res
    print(
        f"  Result: {'SUCCESS' if res.success else 'FAILED'} - {res.failure_reason or f'Length: {res.length:.1f}mm'}"
    )

    print("\n" + "-" * 40)
    print("TEST 4: Power Net Routing (VCC_HV in HV zone)")
    print("-" * 40)

    res = route_net_hierarchical(
        router,
        net_name="VCC_HV",
        pin_positions=[(20.0, 27.0), (82.0, 50.0)],
        assignment=LayerAssignment(
            net="VCC_HV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
        trace_width_mm=0.8,
        clearance_mm=6.5,
    )
    results["VCC_HV"] = res
    print(
        f"  Result: {'SUCCESS' if res.success else 'FAILED'} - {res.failure_reason or f'Length: {res.length:.1f}mm'}"
    )

    print("\n" + "-" * 40)
    print("TEST 5: Ground Separation (GND_LV vs GND_HV)")
    print("-" * 40)

    res_lv = route_net_hierarchical(
        router,
        net_name="GND_LV",
        pin_positions=[(73.5, 80.0), (18.0, 47.0), (25.0, 13.0), (77.0, 17.0)],
        assignment=LayerAssignment(
            net="GND_LV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
        trace_width_mm=0.3,
        clearance_mm=0.2,
    )
    results["GND_LV"] = res_lv
    print(
        f"  GND_LV: {'SUCCESS' if res_lv.success else 'FAILED'} - {res_lv.failure_reason or f'Length: {res_lv.length:.1f}mm'}"
    )

    res_hv = route_net_hierarchical(
        router,
        net_name="GND_HV",
        pin_positions=[(54.0, 52.0), (20.0, 27.0), (82.0, 47.0)],
        assignment=LayerAssignment(
            net="GND_HV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
        trace_width_mm=0.5,
        clearance_mm=6.5,
    )
    results["GND_HV"] = res_hv
    print(
        f"  GND_HV: {'SUCCESS' if res_hv.success else 'FAILED'} - {res_hv.failure_reason or f'Length: {res_hv.length:.1f}mm'}"
    )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results.values() if r.success)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")
    for name, res in results.items():
        status = "PASS" if res.success else "FAIL"
        print(f"  [{status}] {name}")

    if passed == total:
        print("\n ALL TESTS PASSED - Zone integration working correctly")
        return True
    else:
        print(f"\n {total - passed} TEST(S) FAILED - Check routing constraints")
        return False


if __name__ == "__main__":
    success = run_zone_integration_test()
    sys.exit(0 if success else 1)
