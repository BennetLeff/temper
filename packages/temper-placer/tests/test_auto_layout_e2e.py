
from temper_placer.pipeline.auto_layout import auto_layout_pcb
from temper_placer.io.kicad_parser import parse_kicad_pcb
from pathlib import Path

def test_auto_layout_temper_board():
    """Validate complete pipeline on the temper board test case."""
    pcb_path = Path("pcb/temper_ready_for_route.kicad_pcb")
    if not pcb_path.exists():
        # Fallback for different execution environments
        pcb_path = Path("/Users/bennet/Desktop/temper/pcb/temper_ready_for_route.kicad_pcb")
        
    print(f"Loading PCB from {pcb_path}")
    result = parse_kicad_pcb(pcb_path)
    
    # Run auto_layout
    positions, routes = auto_layout_pcb(result.netlist, result.board, max_outer_iterations=3)
    
    # Verify
    routed_count = sum(1 for r in routes.values() if r.success)
    total_nets = len(routes)
    
    print(f"Success: {routed_count}/{total_nets} nets routed")
    
    # Acceptance criteria from task:
    # - 16/16 signal nets routed (excluding power)
    # - Kompletes in <60 seconds (monitored by test runner)
    # - No user intervention required
    
    assert routed_count == total_nets, f"Not all nets routed: {routed_count}/{total_nets}"
    assert routed_count >= 16, "Expected at least 16 signal nets"

if __name__ == "__main__":
    test_auto_layout_temper_board()
