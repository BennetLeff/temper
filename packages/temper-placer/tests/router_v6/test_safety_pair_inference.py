"""
Tests for Router V6 Stage 0.4: Infer Safety Pairs from Net Names

Part of temper-vha9
"""

import pytest

from temper_placer.router_v6.safety_pair_inference import SafetyPair, infer_safety_pairs


def test_infer_safety_pairs_basic():
    """Test basic HV to LV safety pair detection."""
    nets = ["AC_L", "AC_N", "3V3", "GND"]
    pairs = infer_safety_pairs(nets)

    # Should find AC_L->3V3 and AC_L->GND, AC_N->3V3, AC_N->GND
    # GND is classified as LV in this case
    assert len(pairs) >= 2

    # Check that AC nets are paired with LV nets
    ac_pairs = [p for p in pairs if "AC" in p.net_a.upper()]
    assert len(ac_pairs) > 0

    # Verify creepage requirements
    for pair in ac_pairs:
        if "3V3" in pair.net_b or "GND" in pair.net_b:
            # HV to SELV
            assert pair.required_creepage_mm == 5.0
            assert pair.required_clearance_mm == 3.0


def test_infer_safety_pairs_pgnd():
    """Test PGND (power ground) detection and requirements."""
    nets = ["AC_L", "PGND", "3V3", "GND"]
    pairs = infer_safety_pairs(nets)

    # Find AC_L -> PGND pairs (should be 3mm/2mm)
    ac_pgnd = [p for p in pairs if "AC" in p.net_a.upper() and "PGND" in p.net_b.upper()]
    assert len(ac_pgnd) > 0
    assert ac_pgnd[0].required_creepage_mm == 3.0  # HV to earth
    assert ac_pgnd[0].required_clearance_mm == 2.0

    # Find PGND -> 3V3 pairs (should be 4mm/2.5mm)
    pgnd_lv = [p for p in pairs if "PGND" in p.net_a.upper() and ("3V3" in p.net_b or "GND" in p.net_b)]
    assert len(pgnd_lv) > 0
    assert pgnd_lv[0].required_creepage_mm == 4.0  # PGND to SELV
    assert pgnd_lv[0].required_clearance_mm == 2.5


def test_infer_safety_pairs_with_net_classes():
    """Test HV detection via net class assignments."""
    nets = ["MAINS", "VCC", "SIG1"]
    net_classes = {"MAINS": "HighVoltage", "VCC": "Power", "SIG1": "Signal"}

    pairs = infer_safety_pairs(nets, net_classes)

    # MAINS should be detected as HV via net class
    hv_pairs = [p for p in pairs if "MAINS" in p.net_a]
    assert len(hv_pairs) >= 1


def test_infer_safety_pairs_no_hv():
    """Test that no pairs are generated for all-LV designs."""
    nets = ["3V3", "GND", "VCC", "CLK", "DATA"]
    pairs = infer_safety_pairs(nets)

    # No HV nets, so no safety pairs
    assert len(pairs) == 0


def test_infer_safety_pairs_hv_patterns():
    """Test various HV net naming patterns."""
    test_cases = [
        (["LINE_L", "3V3"], "LINE_L"),
        (["MAINS_HOT", "VCC"], "MAINS_HOT"),
        (["HV_BUS", "GND"], "HV_BUS"),
        (["AC", "3V3"], "AC"),
    ]

    for nets, expected_hv in test_cases:
        pairs = infer_safety_pairs(nets)
        assert len(pairs) > 0, f"Expected pairs for {nets}"
        assert any(expected_hv in p.net_a for p in pairs), f"Expected {expected_hv} as HV net"


def test_safety_pair_validation():
    """Test SafetyPair validation."""
    # Valid pair
    pair = SafetyPair(
        net_a="AC_L",
        net_b="3V3",
        required_creepage_mm=5.0,
        required_clearance_mm=3.0,
    )
    assert pair.net_a == "AC_L"

    # Invalid: same net
    with pytest.raises(ValueError, match="must be different"):
        SafetyPair(
            net_a="GND",
            net_b="GND",
            required_creepage_mm=3.0,
            required_clearance_mm=2.0,
        )

    # Invalid: creepage < clearance
    with pytest.raises(ValueError, match="Creepage.*must be"):
        SafetyPair(
            net_a="AC_L",
            net_b="3V3",
            required_creepage_mm=2.0,  # Too small
            required_clearance_mm=3.0,
        )


def test_infer_safety_pairs_temper_realistic():
    """Test with realistic Temper induction cooker net names."""
    nets = [
        "AC_L", "AC_N",  # Mains input
        "PGND",  # Power ground (IGBT source)
        "GND",  # Logic ground
        "3V3", "15V", "12V",  # Power rails
        "GATE_A", "GATE_B",  # IGBT gate signals
        "I_SENSE", "TEMP_SENSE",  # Analog signals
    ]

    pairs = infer_safety_pairs(nets)

    # Should have multiple safety pairs
    assert len(pairs) > 0

    # AC_L/AC_N to 3V3 should be 5mm/3mm
    ac_to_3v3 = [p for p in pairs if "AC" in p.net_a.upper() and "3V3" in p.net_b]
    assert len(ac_to_3v3) >= 1
    assert ac_to_3v3[0].required_creepage_mm == 5.0

    # AC to PGND should be 3mm/2mm
    ac_to_pgnd = [p for p in pairs if "AC" in p.net_a.upper() and "PGND" in p.net_b]
    assert len(ac_to_pgnd) >= 1
    assert ac_to_pgnd[0].required_creepage_mm == 3.0

    # PGND to logic signals should be 4mm/2.5mm
    pgnd_to_logic = [p for p in pairs if "PGND" in p.net_a and ("GATE" in p.net_b or "SENSE" in p.net_b)]
    if len(pgnd_to_logic) > 0:
        assert pgnd_to_logic[0].required_creepage_mm == 4.0
