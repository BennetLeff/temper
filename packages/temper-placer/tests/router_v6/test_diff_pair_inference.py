"""
Tests for Router V6 Stage 0.2: Infer Differential Pairs from Naming

Part of temper-4av9
"""

import pytest

from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs


def test_infer_diff_pairs_plus_minus():
    """Test +/- suffix pattern."""
    nets = ["USB_D+", "USB_D-", "GND", "3V3"]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 1
    assert pairs[0].base_name == "USB_D"
    assert pairs[0].p_net == "USB_D+"
    assert pairs[0].n_net == "USB_D-"


def test_infer_diff_pairs_p_n_suffix():
    """Test _P / _N suffix pattern."""
    nets = ["CLK_P", "CLK_N", "DATA_P", "DATA_N", "GND"]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 2
    pair_dict = {p.base_name: p for p in pairs}

    assert "CLK" in pair_dict
    assert pair_dict["CLK"].p_net == "CLK_P"
    assert pair_dict["CLK"].n_net == "CLK_N"

    assert "DATA" in pair_dict
    assert pair_dict["DATA"].p_net == "DATA_P"
    assert pair_dict["DATA"].n_net == "DATA_N"


def test_infer_diff_pairs_dp_dn():
    """Test DP/DN pattern (common USB)."""
    nets = ["USB_DP", "USB_DN", "VCC"]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 1
    assert pairs[0].base_name == "USB"
    assert pairs[0].p_net == "USB_DP"
    assert pairs[0].n_net == "USB_DN"


def test_infer_diff_pairs_case_insensitive():
    """Test case insensitive matching."""
    nets = ["usb_dp", "usb_dn", "Clk_P", "Clk_N"]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 2
    # Original case should be preserved
    pair_dict = {p.base_name: p for p in pairs}

    assert "usb" in pair_dict or "USB" in pair_dict
    assert "Clk" in pair_dict or "CLK" in pair_dict


def test_infer_diff_pairs_no_match():
    """Test nets with no differential pairs."""
    nets = ["GND", "3V3", "RESET", "CLK"]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 0


def test_infer_diff_pairs_unpaired():
    """Test that unpaired nets are ignored."""
    nets = ["TX+", "RX-", "GND"]  # TX has no negative, RX has no positive
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 0


def test_infer_diff_pairs_multiple_patterns():
    """Test mixing different naming patterns."""
    nets = [
        "USB_D+", "USB_D-",      # +/- pattern
        "LVDS_P", "LVDS_N",      # P/N pattern
        "ETH_DP", "ETH_DN",      # DP/DN pattern
        "GND", "3V3"
    ]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 3
    base_names = {p.base_name for p in pairs}
    assert "USB_D" in base_names
    assert "LVDS" in base_names
    assert "ETH" in base_names


def test_diff_pair_validation():
    """Test DiffPair validation."""
    # Valid pair
    pair = DiffPair(base_name="USB_D", p_net="USB_D+", n_net="USB_D-")
    assert pair.p_net == "USB_D+"

    # Invalid pair (same net)
    with pytest.raises(ValueError, match="must be different"):
        DiffPair(base_name="BAD", p_net="NET", n_net="NET")


def test_complex_naming():
    """Test complex real-world naming."""
    nets = [
        "PCIE_TX0_P", "PCIE_TX0_N",
        "PCIE_TX1_P", "PCIE_TX1_N",
        "PCIE_RX0_P", "PCIE_RX0_N",
        "GND", "12V"
    ]
    pairs = infer_differential_pairs(nets)

    assert len(pairs) == 3
    pair_dict = {p.base_name: p for p in pairs}

    # All three pairs should be found
    assert "PCIE_TX0" in pair_dict
    assert "PCIE_TX1" in pair_dict
    assert "PCIE_RX0" in pair_dict
