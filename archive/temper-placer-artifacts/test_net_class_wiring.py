"""Test that net class rules are properly wired to MazeRouter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from temper_placer.core.board import Board
from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.routing.maze_router import MazeRouter


def test_net_class_wiring():
    """Verify that router uses net-class-specific trace widths and via sizes."""
    # Create a simple board
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    
    # Create design rules with Temper net classes
    design_rules = create_temper_design_rules()
    
    # Create router with design rules
    router = MazeRouter.from_board(
        board,
        cell_size_mm=0.5,
        num_layers=2,
        design_rules=design_rules
    )
    
    # Verify router has design rules
    assert router.design_rules is not None
    assert router.design_rules == design_rules
    
    # Verify router gets net-specific rules for different net classes
    power_rules = router.design_rules.get_rules_for_net("+3V3")  # Should match Power pattern
    assert power_rules.name == "Power"
    assert power_rules.trace_width == 0.5  # From TEMPER_NET_CLASSES
    
    gnd_rules = router.design_rules.get_rules_for_net("GND")
    assert gnd_rules.name == "GND"
    assert gnd_rules.trace_width == 1.0  # Wide ground traces
    
    gate_rules = router.design_rules.get_rules_for_net("GATE_H")  # Should match Gate pattern
    assert gate_rules.name == "GateDrive"
    assert gate_rules.trace_width == 0.4
    
    hc_rules = router.design_rules.get_rules_for_net("DC_BUS+")  # Should match HighCurrent pattern
    assert hc_rules.name == "HighCurrent"
    assert hc_rules.trace_width == 0.5
    
    sig_rules = router.design_rules.get_rules_for_net("SPI_MOSI")  # Falls back to Default
    assert sig_rules.name == "Default"
    assert sig_rules.trace_width == 0.2
    
    print("✅ Net class rules successfully wired to MazeRouter!")
    print(f"   Power (+3V3): {power_rules.trace_width}mm")
    print(f"   Ground (GND): {gnd_rules.trace_width}mm")
    print(f"   Gate Drive (GATE_H): {gate_rules.trace_width}mm")
    print(f"   High Current (DC_BUS+): {hc_rules.trace_width}mm")
    print(f"   Signal (SPI_MOSI): {sig_rules.trace_width}mm")


if __name__ == "__main__":
    test_net_class_wiring()
