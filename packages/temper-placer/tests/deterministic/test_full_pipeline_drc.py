import pytest
from pathlib import Path
from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules

def test_full_pipeline_includes_all_drc_stages():
    '''Pipeline should include oracle setup, routing, DRC, and connectivity.'''
    # Create minimal metadata for pipeline creation
    from temper_placer.io.kicad_metadata import KiCadMetadata
    metadata = KiCadMetadata(
        courtyards={},
        pad_sizes={},
        board_width=100.0,
        board_height=100.0
    )
    pipeline = create_drc_aware_pipeline(metadata=metadata)
    stage_names = [s.name for s in pipeline.stages]
    
    assert 'drc_oracle_setup' in stage_names
    assert 'sequential_routing' in stage_names
    assert 'drc_validation' in stage_names
    assert 'connectivity_validation' in stage_names

@pytest.mark.external
def test_temper_board_routes_successfully():
    '''Temper board should route with the deterministic pipeline.'''
    pcb_path = Path('pcb/temper.kicad_pcb')
    config_path = Path('configs/temper_deterministic_config.yaml')
    
    # We use a relative path from the project root
    # If running from packages/temper-placer, we need to go up
    if not pcb_path.exists():
        pcb_path = Path('../../pcb/temper.kicad_pcb')
        config_path = Path('../../configs/temper_deterministic_config.yaml')

    if not pcb_path.exists() or not config_path.exists():
        pytest.skip(f"Temper board or config not found at {pcb_path}")
        
    # Load data
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(config_path)
    design_rules = constraints_to_design_rules(constraints)
    metadata = extract_kicad_metadata(pcb_path)
    
    # Run pipeline
    pipeline = create_drc_aware_pipeline(design_rules=design_rules, config=constraints, metadata=metadata)
    initial_state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
    result = pipeline.run(initial_state)
    
    # Check that we have some routes
    assert len(result.routes) > 0
    
    # Check internal DRC results
    assert result.drc_violations is not None
    # Target: reasonable number of violations for a complex board
    assert len(result.drc_violations) < 100
    
    # Check connectivity
    assert result.connectivity_violations is not None
    # Unconnected pads should be reasonable
    unconnected = [v for v in result.connectivity_violations if v.type == "unconnected_pad"]
    assert len(unconnected) < 40
