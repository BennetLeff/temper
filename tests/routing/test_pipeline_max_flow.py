import sys
from pathlib import Path
import pytest
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

def test_pipeline_routability_analysis():
    """Verify that enable_routability_analysis flag works in the pipeline."""
    # Use the pre_routed_v5 board which we know is infeasible
    pcb_path = Path("pre_routed_v5.kicad_pcb")
    if not pcb_path.exists():
        pytest.skip("pre_routed_v5.kicad_pcb not found in root")
        
    # Initialize pipeline with routability analysis enabled
    pipeline = RouterV6Pipeline(
        verbose=True,
        enable_routability_analysis=True,
        enable_legalization=False, # Skip expensive legalization
        max_nets=0 # Skip actual routing stage to save time
    )
    
    # We only need to run Stage 2 to trigger the analysis
    pcb = parse_kicad_pcb_v6(pcb_path)
    
    # Capture stdout to verify print statements
    import io
    from contextlib import redirect_stdout
    
    f = io.StringIO()
    with redirect_stdout(f):
        pipeline._run_stage2(pcb, [])
        
    output = f.getvalue()
    
    # Check for expected log messages
    assert "2.9: Running Max-Flow Routability Analysis..." in output
    assert "Max-Flow Capacity:" in output
    assert "Net Demand:" in output
    # Since we know this board is unroutable for some nets
    assert "WARNING: Board is MATHEMATICALLY UNROUTABLE!" in output

if __name__ == "__main__":
    test_pipeline_routability_analysis()
    print("Integration test PASSED")
