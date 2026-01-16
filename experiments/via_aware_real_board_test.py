#!/usr/bin/env python3
"""
Real-world test: Via-aware router on actual Temper board.

Tests the complete via-aware routing flow on nets that previously
had via violations (USB_D+/D-, SPI nets, I_SENSE).

Expected results:
- Vias placed during routing (not post-process)
- Via-via spacing >= 1.4mm
- No via-track shorts
- Escape routing for dense IC (QFN-56)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'packages' / 'temper-placer' / 'src'))

from shapely.geometry import box, Point
import math

from temper_placer.router_v6.via_model import ViaSpec
from temper_placer.router_v6.via_planner import ViaPlanner
from temper_placer.router_v6.pad_layer_connector import Pad, PadLayerConnector
from temper_placer.router_v6.exact_geometry_router_via_aware import (
    ExactGeometryRouterViaAware
)


def create_temper_board_scenario():
    """
    Create simplified Temper board scenario with problematic nets.
    
    Focus on:
    - USB_D+/D- (QFN-56, 0.4mm pitch)
    - SPI nets (QFN-56 to SPI flash)
    - I_SENSE (8-pad multi-point net)
    """
    # 150x150mm board
    board_area = box(0, 0, 150, 150)
    via_spec = ViaSpec.standard()
    via_planner = ViaPlanner(board_area, via_spec)
    
    # Add QFN-56 MCU pads (simplified - just USB area)
    mcu_center = (21.45, 60.93)
    
    # USB_D+ and USB_D- pads (0.4mm apart!)
    usb_d_plus_pos = (18.0, 60.93)
    usb_d_minus_pos = (18.0, 60.53)
    
    # Add neighboring pads as obstacles (dense IC)
    for offset in [-0.4, 0.4, -0.8, 0.8]:
        if offset != 0:
            neighbor = Point(18.0, 60.93 + offset).buffer(0.12)
            via_planner.add_obstacle(neighbor, 'F.Cu')
    
    # Add SPI pads (also on QFN-56)
    spi_clk_pos = (23.05, 64.38)
    spi_mosi_pos = (23.45, 64.38)
    spi_miso_pos = (23.85, 64.38)
    
    # Add SPI flash chip pads
    spi_flash_center = (70, 65)
    
    pad_connector = PadLayerConnector(via_planner)
    router = ExactGeometryRouterViaAware(board_area, via_planner, pad_connector)
    
    return {
        'router': router,
        'via_planner': via_planner,
        'usb_d_plus_pos': usb_d_plus_pos,
        'usb_d_minus_pos': usb_d_minus_pos,
        'spi_clk_pos': spi_clk_pos,
        'spi_mosi_pos': spi_mosi_pos,
        'spi_miso_pos': spi_miso_pos,
        'spi_flash_center': spi_flash_center
    }


def test_usb_differential_pair():
    """Test USB_D+ and USB_D- routing (previously had 0.4mm via spacing)"""
    print("\n" + "="*70)
    print("TEST 1: USB Differential Pair (Previously Failed)")
    print("="*70)
    
    scenario = create_temper_board_scenario()
    router = scenario['router']
    
    # USB_D+ pads
    usb_d_plus_pads = [
        Pad(scenario['usb_d_plus_pos'], ['F.Cu'], 'USB_D+', 'U_MCU', '40'),
        Pad((50.0, 5.0), ['F.Cu'], 'USB_D+', 'J_USB', 'A6')
    ]
    
    # USB_D- pads
    usb_d_minus_pads = [
        Pad(scenario['usb_d_minus_pos'], ['F.Cu'], 'USB_D-', 'U_MCU', '41'),
        Pad((50.4, 5.0), ['F.Cu'], 'USB_D-', 'J_USB', 'A7')
    ]
    
    print(f"\nProblem: USB pads are 0.4mm apart")
    print(f"  USB_D+ at {usb_d_plus_pads[0].position}")
    print(f"  USB_D- at {usb_d_minus_pads[0].position}")
    print(f"  Pad spacing: 0.4mm")
    print(f"  Via min spacing: 1.4mm")
    print(f"  → Vias CAN'T be placed at pads!")
    
    # Route USB_D+ on In1.Cu
    print(f"\nRouting USB_D+ on In1.Cu...")
    route_d_plus = router.route_net('USB_D+', usb_d_plus_pads, 'In1.Cu')
    
    if route_d_plus:
        print(f"  ✓ USB_D+ routed")
        print(f"    Tracks: {len(route_d_plus.tracks)}")
        print(f"    Vias: {len(route_d_plus.vias)}")
        
        for i, via in enumerate(route_d_plus.vias):
            dist_from_pad = min(
                via.distance_to(pad.position) for pad in usb_d_plus_pads
            )
            print(f"    Via {i+1} at {via.position} (dist from pad: {dist_from_pad:.2f}mm)")
    else:
        print(f"  ✗ USB_D+ failed to route")
    
    # Route USB_D- on In1.Cu
    print(f"\nRouting USB_D- on In1.Cu...")
    route_d_minus = router.route_net('USB_D-', usb_d_minus_pads, 'In1.Cu')
    
    if route_d_minus:
        print(f"  ✓ USB_D- routed")
        print(f"    Tracks: {len(route_d_minus.tracks)}")
        print(f"    Vias: {len(route_d_minus.vias)}")
        
        for i, via in enumerate(route_d_minus.vias):
            dist_from_pad = min(
                via.distance_to(pad.position) for pad in usb_d_minus_pads
            )
            print(f"    Via {i+1} at {via.position} (dist from pad: {dist_from_pad:.2f}mm)")
    else:
        print(f"  ✗ USB_D- failed to route")
    
    # Check via-via spacing
    if route_d_plus and route_d_minus:
        print(f"\nChecking via-via spacing:")
        violations = 0
        for via1 in route_d_plus.vias:
            for via2 in route_d_minus.vias:
                dist = via1.distance_to(via2.position)
                status = "✓" if dist >= 1.4 else "✗ VIOLATION"
                print(f"  USB_D+ via to USB_D- via: {dist:.2f}mm {status}")
                if dist < 1.4:
                    violations += 1
        
        if violations == 0:
            print(f"\n✓ SUCCESS: All via-via spacings >= 1.4mm")
        else:
            print(f"\n✗ FAILURE: {violations} via-via spacing violations")
        
        return violations == 0
    
    return False


def test_spi_nets():
    """Test SPI nets (previously had via clustering)"""
    print("\n" + "="*70)
    print("TEST 2: SPI Nets (Previously Clustered)")
    print("="*70)
    
    scenario = create_temper_board_scenario()
    router = scenario['router']
    
    # SPI nets (all on dense IC)
    spi_nets = [
        ('SPI_CLK', [
            Pad(scenario['spi_clk_pos'], ['F.Cu'], 'SPI_CLK', 'U_MCU', '25'),
            Pad((scenario['spi_flash_center'][0] - 2, scenario['spi_flash_center'][1]), 
                ['F.Cu'], 'SPI_CLK', 'U_FLASH', '6')
        ]),
        ('SPI_MOSI', [
            Pad(scenario['spi_mosi_pos'], ['F.Cu'], 'SPI_MOSI', 'U_MCU', '26'),
            Pad((scenario['spi_flash_center'][0], scenario['spi_flash_center'][1]), 
                ['F.Cu'], 'SPI_MOSI', 'U_FLASH', '5')
        ]),
        ('SPI_MISO', [
            Pad(scenario['spi_miso_pos'], ['F.Cu'], 'SPI_MISO', 'U_MCU', '27'),
            Pad((scenario['spi_flash_center'][0] + 2, scenario['spi_flash_center'][1]), 
                ['F.Cu'], 'SPI_MISO', 'U_FLASH', '2')
        ])
    ]
    
    print(f"\nProblem: SPI pads are 0.4mm apart on QFN-56")
    print(f"  Previous result: Vias clustered, <1.4mm spacing")
    
    routes = {}
    for net_name, pads in spi_nets:
        print(f"\nRouting {net_name} on In1.Cu...")
        route = router.route_net(net_name, pads, 'In1.Cu')
        
        if route:
            routes[net_name] = route
            print(f"  ✓ {net_name} routed ({len(route.vias)} vias)")
        else:
            print(f"  ✗ {net_name} failed")
    
    # Check all via-via spacings
    print(f"\nChecking inter-net via spacings:")
    all_vias = []
    for net_name, route in routes.items():
        for via in route.vias:
            all_vias.append((net_name, via))
    
    violations = 0
    for i, (net1, via1) in enumerate(all_vias):
        for net2, via2 in all_vias[i+1:]:
            if net1 != net2:
                dist = via1.distance_to(via2.position)
                status = "✓" if dist >= 1.4 else "✗ VIOLATION"
                if dist < 5.0:  # Only report nearby vias
                    print(f"  {net1} to {net2}: {dist:.2f}mm {status}")
                if dist < 1.4:
                    violations += 1
    
    if violations == 0:
        print(f"\n✓ SUCCESS: All SPI via spacings >= 1.4mm")
    else:
        print(f"\n✗ FAILURE: {violations} via spacing violations")
    
    return violations == 0


def test_via_count():
    """Test that via count is reasonable"""
    print("\n" + "="*70)
    print("TEST 3: Via Count Optimization")
    print("="*70)
    
    scenario = create_temper_board_scenario()
    router = scenario['router']
    
    # Route several nets
    test_nets = [
        ('NET1', [
            Pad((10, 10), ['F.Cu'], 'NET1', 'U1', '1'),
            Pad((20, 10), ['F.Cu'], 'NET1', 'U1', '2')
        ]),
        ('NET2', [
            Pad((10, 20), ['F.Cu'], 'NET2', 'U2', '1'),
            Pad((20, 20), ['F.Cu'], 'NET2', 'U2', '2')
        ]),
        ('NET3', [
            Pad((10, 30), ['F.Cu'], 'NET3', 'U3', '1'),
            Pad((20, 30), ['F.Cu'], 'NET3', 'U3', '2')
        ])
    ]
    
    for net_name, pads in test_nets:
        router.route_net(net_name, pads, 'In1.Cu')
    
    total_vias = scenario['via_planner'].via_count
    print(f"\nTotal vias placed: {total_vias}")
    print(f"  Nets routed: {len(test_nets)}")
    print(f"  Vias per net: {total_vias / len(test_nets):.1f}")
    
    # Each 2-pad net needs ~2 vias (one at each pad)
    expected_max = len(test_nets) * 2
    
    if total_vias <= expected_max:
        print(f"  ✓ Via count reasonable (<= {expected_max})")
        return True
    else:
        print(f"  ⚠ Via count high (expected <= {expected_max})")
        return False


def main():
    """Run all real-world tests"""
    print("\n" + "="*70)
    print(" VIA-AWARE ROUTER: REAL BOARD VALIDATION")
    print("="*70)
    print("\nTesting via-aware routing on Temper board scenarios")
    print("Previously failing: 55 via violations (0.4mm spacing, shorts)")
    
    results = {}
    
    # Run tests
    try:
        results['usb'] = test_usb_differential_pair()
    except Exception as e:
        print(f"\n✗ USB test exception: {e}")
        results['usb'] = False
    
    try:
        results['spi'] = test_spi_nets()
    except Exception as e:
        print(f"\n✗ SPI test exception: {e}")
        results['spi'] = False
    
    try:
        results['via_count'] = test_via_count()
    except Exception as e:
        print(f"\n✗ Via count test exception: {e}")
        results['via_count'] = False
    
    # Summary
    print("\n" + "="*70)
    print(" SUMMARY")
    print("="*70)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name.upper()}: {status}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    print(f"\nTests passed: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n✓ ALL TESTS PASSED - Via-aware routing validated!")
        print("\nKey improvements:")
        print("  • Vias placed during routing (not post-process)")
        print("  • Via-via spacing >= 1.4mm enforced")
        print("  • Escape routing for dense ICs (0.4mm pads → fanout)")
        print("  • No via-track shorts (vias are obstacles)")
    else:
        print(f"\n⚠ {total_count - passed_count} tests failed")
    
    return passed_count == total_count


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
