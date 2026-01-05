import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import os

from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.deterministic.feedback import AutomatedZeroDRC, DRCViolation
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules

@pytest.mark.integration
def test_automated_drc_feedback_on_temper_board(tmp_path):
    """
    Integration test: Run AutomatedZeroDRC on the real Temper board with a mock DRC runner.
    """
    pcb_path = Path('pcb/temper.kicad_pcb')
    config_path = Path('configs/temper_deterministic_config.yaml')
    
    if not pcb_path.exists():
        pcb_path = Path('../../pcb/temper.kicad_pcb')
        config_path = Path('../../configs/temper_deterministic_config.yaml')

    if not pcb_path.exists() or not config_path.exists():
        pytest.skip(f"Temper board or config not found at {pcb_path}")
        
    # 1. Load data
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(config_path)
    design_rules = constraints_to_design_rules(constraints)
    
    # Configure feedback parameters on the constraints object
    constraints.feedback.max_iterations = 3
    constraints.feedback.violation_threshold = 2
    constraints.feedback.expansion_per_violation = 2.0
    
    # Ensure zones have expansion metadata for testing
    for zone in constraints.zones:
        zone.max_size = (50.0, 150.0)
        zone.can_expand = ['right', 'left']
    
    # 2. Setup Pipeline
    pipeline = create_drc_aware_pipeline(design_rules=design_rules, config=constraints)
    
    # 3. Setup Mock DRC Runner
    # It will return a report with violations on the first call, and none on the second.
    report_file = tmp_path / "drc_report.json"
    
    def mock_drc_runner():
        # First call: some violations in HV zone
        # HV zone is typically 0-30% (0-30mm on 100mm board)
        violations = {
            "violations": [
                {
                    "type": "clearance",
                    "description": "clearance 0.2000 mm; actual 0.1500 mm",
                    "items": ["of Q1", "of Q2"],
                    "pos": {"x": 10.0, "y": 20.0}
                },
                {
                    "type": "clearance",
                    "description": "clearance 0.2000 mm; actual 0.1800 mm",
                    "items": ["of Q1", "Pad 2"],
                    "pos": {"x": 12.0, "y": 25.0}
                }
            ],
            "unconnected_items": []
        }
        
        # Second call: empty
        if os.path.exists(report_file) and os.path.getsize(report_file) > 100:
             violations = {"violations": [], "unconnected_items": []}
             
        with open(report_file, "w") as f:
            json.dump(violations, f)
        return str(report_file)

    # 4. Run Orchestrator
    orchestrator = AutomatedZeroDRC(
        pipeline=pipeline,
        netlist=parse_result.netlist,
        initial_config=constraints,
        drc_runner=mock_drc_runner
    )
    
    initial_state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
    
    # HV Zone is index 0
    hv_zone_before = constraints.zones[0].bounds[2]
    
    final_state = orchestrator.run(initial_state)
    
    # 5. Verify
    hv_zone_after = constraints.zones[0].bounds[2]
    
    # Should have expanded because of 2 violations and threshold 2
    # excess = 2 - 2 + 1 = 1
    # expansion = 1 * 2.0 = 2.0mm
    assert hv_zone_after > hv_zone_before
    assert hv_zone_after == pytest.approx(hv_zone_before + 2.0)
    
    # Pipeline should have run twice
    # (Iteration 1: Run -> Violations -> Adjust)
    # (Iteration 2: Run -> No Violations -> Done)
    # Wait, in iteration 2 it runs and then checks violations. 
    # If no violations, it breaks. So run() is called in each iteration it enters.
    # Actually, my orchestrator does:
    # for i in range(max_iterations):
    #   state = pipeline.run(state)
    #   raw_violations = drc_runner()
    #   if not raw_violations: break
    
    # So if it fails once and passes the second time, pipeline.run is called twice.
    # Note: AutomatedZeroDRC.run() loop.
