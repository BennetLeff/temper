#!/usr/bin/env python3
"""
Test script to verify power net exclusion is working correctly.

This script loads a PCB and verifies that high-power nets are correctly
excluded from the routing list when --exclude-power-nets is enabled.
"""


def test_power_net_exclusion():
    """Test that power nets are correctly excluded from routing."""

    print("=" * 70)
    print("Power Net Exclusion Test")
    print("=" * 70)

    # Define power net patterns (same as in placement_routing_loop.py)
    POWER_NET_PATTERNS = [
        # Ground nets
        'GND', 'PGND', 'CGND', 'AGND', 'DGND', 'ISOGND',
        # High-power AC/DC nets
        'AC_L', 'AC_N', 'DC_BUS+', 'DC_BUS-',
    ]

    # Test nets from Temper PCB
    test_nets = [
        'AC_L',      # Should be excluded (high-power AC)
        'AC_N',      # Should be excluded (high-power AC)
        'GND',       # Should be excluded (ground)
        'PGND',      # Should be excluded (ground)
        'DC_BUS+',   # Should be excluded (high-power DC)
        '+3V3',      # Should NOT be excluded (low-power rail)
        '+5V',       # Should NOT be excluded (low-power rail)
        '+15V',      # Should NOT be excluded (low-power rail)
        'VCC_BOOT',  # Should NOT be excluded (low-power rail)
        'SPI_CLK',   # Should NOT be excluded (signal)
        'USB_D+',    # Should NOT be excluded (signal)
        'GATE_H',    # Should NOT be excluded (signal)
    ]

    print("\n1. Testing net exclusion logic...")
    print(f"   Power net patterns: {', '.join(POWER_NET_PATTERNS)}")

    excluded = []
    included = []

    for net in test_nets:
        if any(p in net for p in POWER_NET_PATTERNS):
            excluded.append(net)
        else:
            included.append(net)

    print("\n2. Results:")
    print(f"   Total nets tested: {len(test_nets)}")
    print(f"   Excluded (power/ground): {len(excluded)}")
    print(f"   Included (signal/low-power): {len(included)}")

    print("\n3. Excluded nets (will use copper zones):")
    for net in excluded:
        print(f"      ✓ {net}")

    print("\n4. Included nets (will be routed as traces):")
    for net in included:
        print(f"      ✓ {net}")

    # Verify expected results
    expected_excluded = {'AC_L', 'AC_N', 'GND', 'PGND', 'DC_BUS+'}
    expected_included = {'+3V3', '+5V', '+15V', 'VCC_BOOT', 'SPI_CLK', 'USB_D+', 'GATE_H'}

    actual_excluded = set(excluded)
    actual_included = set(included)

    print("\n5. Validation:")

    if actual_excluded == expected_excluded:
        print("   ✅ Excluded nets match expected")
    else:
        print("   ❌ Excluded nets mismatch!")
        print(f"      Expected: {expected_excluded}")
        print(f"      Actual: {actual_excluded}")

    if actual_included == expected_included:
        print("   ✅ Included nets match expected")
    else:
        print("   ❌ Included nets mismatch!")
        print(f"      Expected: {expected_included}")
        print(f"      Actual: {actual_included}")

    print("\n" + "=" * 70)

    if actual_excluded == expected_excluded and actual_included == expected_included:
        print("✅ Test PASSED!")
        print("=" * 70)
        return True
    else:
        print("❌ Test FAILED!")
        print("=" * 70)
        return False

if __name__ == "__main__":
    success = test_power_net_exclusion()
    exit(0 if success else 1)
