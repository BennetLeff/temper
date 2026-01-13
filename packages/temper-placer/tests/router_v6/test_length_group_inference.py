"""
Tests for Router V6 Stage 0.5: Load/Infer Length Groups

Part of temper-scgx
"""

import pytest

from temper_placer.router_v6.diff_pair_inference import DiffPair
from temper_placer.router_v6.length_group_inference import LengthGroup, infer_length_groups


def test_infer_length_groups_diff_pairs():
    """Test automatic length group creation for differential pairs."""
    diff_pairs = [
        DiffPair(base_name="USB_D", p_net="USB_DP", n_net="USB_DN"),
        DiffPair(base_name="ETH_TX", p_net="ETH_TX_P", n_net="ETH_TX_N"),
    ]
    
    groups = infer_length_groups([], diff_pairs=diff_pairs)
    
    assert len(groups) == 2
    
    # Check USB differential pair group
    usb_group = [g for g in groups if "USB" in g.name][0]
    assert set(usb_group.nets) == {"USB_DP", "USB_DN"}
    assert usb_group.max_skew_mm == 0.1  # Tight matching for diff pairs


def test_infer_length_groups_parallel_bus():
    """Test parallel bus detection (DDR_DQ0-7)."""
    nets = ["DDR_DQ0", "DDR_DQ1", "DDR_DQ2", "DDR_DQ3", "GND", "3V3"]
    
    groups = infer_length_groups(nets)
    
    assert len(groups) == 1
    assert groups[0].name == "DDR_DQ"
    assert len(groups[0].nets) == 4
    assert "DDR_DQ0" in groups[0].nets
    assert groups[0].max_skew_mm == 0.5  # DDR = tight timing


def test_infer_length_groups_bracket_notation():
    """Test bus detection with bracket notation SPI_D[0]."""
    nets = ["SPI_D[0]", "SPI_D[1]", "SPI_D[2]", "SPI_D[3]"]
    
    groups = infer_length_groups(nets)
    
    assert len(groups) == 1
    assert groups[0].name == "SPI_D"
    assert len(groups[0].nets) == 4
    assert groups[0].max_skew_mm == 5.0  # SPI = relaxed timing


def test_infer_length_groups_clock_tree():
    """Test clock distribution tree detection."""
    nets = ["CLK_MCU_OUT_0", "CLK_MCU_OUT_1", "CLK_MCU_OUT_2"]
    
    groups = infer_length_groups(nets)
    
    # Should create clock tree group
    clock_groups = [g for g in groups if "CLK" in g.name]
    assert len(clock_groups) >= 1
    assert clock_groups[0].max_skew_mm == 0.2  # Clock = very tight


def test_infer_length_groups_no_groups():
    """Test that no groups are created for unrelated nets."""
    nets = ["GND", "3V3", "RESET", "LED"]
    
    groups = infer_length_groups(nets)
    
    assert len(groups) == 0


def test_infer_length_groups_multiple_buses():
    """Test multiple independent buses."""
    nets = [
        "DDR_DQ0", "DDR_DQ1",  # DDR data bus
        "DDR_A0", "DDR_A1", "DDR_A2",  # DDR address bus
        "SPI_D0", "SPI_D1",  # SPI data
    ]
    
    groups = infer_length_groups(nets)
    
    assert len(groups) == 3
    group_names = {g.name for g in groups}
    assert "DDR_DQ" in group_names
    assert "DDR_A" in group_names
    assert "SPI_D" in group_names


def test_length_group_validation():
    """Test LengthGroup validation."""
    # Valid group
    group = LengthGroup(
        name="DDR_DQ",
        nets=["DDR_DQ0", "DDR_DQ1"],
        max_skew_mm=0.5,
    )
    assert group.name == "DDR_DQ"

    # Invalid: too few nets
    with pytest.raises(ValueError, match="at least 2 nets"):
        LengthGroup(
            name="SINGLE",
            nets=["NET1"],
            max_skew_mm=1.0,
        )

    # Invalid: negative skew
    with pytest.raises(ValueError, match="must be positive"):
        LengthGroup(
            name="BAD",
            nets=["NET1", "NET2"],
            max_skew_mm=-1.0,
        )

    # Invalid: negative target length
    with pytest.raises(ValueError, match="must be positive"):
        LengthGroup(
            name="BAD",
            nets=["NET1", "NET2"],
            max_skew_mm=1.0,
            target_length_mm=-10.0,
        )


def test_infer_length_groups_combined():
    """Test combined scenario with diff pairs and buses."""
    nets = [
        "USB_DP", "USB_DN",  # Will be in diff pair group
        "DDR_DQ0", "DDR_DQ1", "DDR_DQ2",  # Parallel bus
        "GND", "3V3",  # No group
    ]
    
    diff_pairs = [DiffPair(base_name="USB_D", p_net="USB_DP", n_net="USB_DN")]
    
    groups = infer_length_groups(nets, diff_pairs=diff_pairs)
    
    # Should have diff pair group + DDR bus group
    assert len(groups) == 2
    
    # Check diff pair group exists
    diff_group = [g for g in groups if "DIFFPAIR" in g.name][0]
    assert set(diff_group.nets) == {"USB_DP", "USB_DN"}
    
    # Check DDR group exists
    ddr_group = [g for g in groups if "DDR" in g.name][0]
    assert len(ddr_group.nets) == 3


def test_infer_length_groups_skew_assignment():
    """Test that different bus types get appropriate skew values."""
    test_cases = [
        (["DDR_DQ0", "DDR_DQ1"], 0.5),  # DDR: tight
        (["SPI_D0", "SPI_D1"], 5.0),  # SPI: relaxed
        (["I2C_SDA0", "I2C_SDA1"], 5.0),  # I2C: relaxed
        (["DATA0", "DATA1"], 1.0),  # Generic: moderate
    ]
    
    for nets, expected_skew in test_cases:
        groups = infer_length_groups(nets)
        if len(groups) > 0:
            assert groups[0].max_skew_mm == expected_skew, f"Wrong skew for {nets}"
