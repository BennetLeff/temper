import pytest
from unittest.mock import MagicMock, patch
from temper_placer.deterministic.feedback import AutomatedZeroDRC, DRCViolation
from temper_placer.deterministic import DeterministicPipeline
from temper_placer.deterministic.state import BoardState

@pytest.fixture
def mock_netlist():
    mock = MagicMock()
    comp1 = MagicMock()
    comp1.ref = "Q1"
    mock.components = [comp1]
    return mock

@pytest.fixture
def initial_config():
    return {
        'board': {'width_mm': 100.0, 'height_mm': 100.0},
        'zones': [
            {'name': 'HV', 'bounds_ratio': [0.0, 0.0, 0.5, 1.0]},
            {'name': 'MCU', 'bounds_ratio': [0.5, 0.0, 1.0, 1.0]}
        ]
    }

def test_orchestrator_loop_terminates_on_zero_violations(mock_netlist, initial_config):
    pipeline = MagicMock(spec=DeterministicPipeline)
    pipeline.run.return_value = BoardState()
    pipeline.stages = []  # Mock stages attribute
    
    # Mock DRC runner returns path to a file
    drc_runner = MagicMock(return_value="report.json")
    
    with patch('temper_placer.deterministic.feedback.orchestrator.parse_kicad_drc', return_value=[]):
        orchestrator = AutomatedZeroDRC(pipeline, mock_netlist, initial_config, drc_runner)
        orchestrator.run()
        
    assert pipeline.run.call_count == 1
    assert drc_runner.call_count == 1

def test_orchestrator_adjusts_and_retries_on_violations(mock_netlist, initial_config):
    pipeline = MagicMock(spec=DeterministicPipeline)
    pipeline.run.return_value = BoardState()
    pipeline.stages = []  # Mock stages attribute
    
    drc_runner = MagicMock(return_value="report.json")
    
    # First call returns violations, second call returns none
    # Q1 is at (10, 10), which is in the HV zone (0-50mm)
    violations_sequence = [
        [DRCViolation(type='clearance', items=['of Q1'], pos=(10, 10))],
        []
    ]
    
    with patch('temper_placer.deterministic.feedback.orchestrator.parse_kicad_drc') as mock_parse:
        mock_parse.side_effect = violations_sequence
        
        orchestrator = AutomatedZeroDRC(pipeline, mock_netlist, initial_config, drc_runner)
        
        # Force adjustment threshold to 1 for testing
        orchestrator.adjuster.violation_threshold = 1
        orchestrator.adjuster.expansion_per_violation = 5.0 # 5mm expansion
        
        orchestrator.run()
        
    assert pipeline.run.call_count == 2
    assert drc_runner.call_count == 2
    
    # 5mm expansion on 100mm board is 0.05 ratio
    # HV was [0.0, 0.5], now should be [0.0, 0.55]
    assert initial_config['zones'][0]['bounds_ratio'][2] == pytest.approx(0.55)
    # MCU was [0.5, 1.0], now should be [0.55, 1.05] (shifted right by 0.05)
    assert initial_config['zones'][1]['bounds_ratio'][0] == pytest.approx(0.55)
    assert initial_config['zones'][1]['bounds_ratio'][2] == pytest.approx(1.05)

def test_orchestrator_stops_after_max_iterations(mock_netlist, initial_config):
    pipeline = MagicMock(spec=DeterministicPipeline)
    pipeline.run.return_value = BoardState()
    pipeline.stages = []  # Mock stages attribute
    
    drc_runner = MagicMock(return_value="report.json")
    
    # Always returns violations
    violation = DRCViolation(type='clearance', items=['of Q1'], pos=(10, 10))
    
    with patch('temper_placer.deterministic.feedback.orchestrator.parse_kicad_drc', return_value=[violation]):
        orchestrator = AutomatedZeroDRC(pipeline, mock_netlist, initial_config, drc_runner, max_iterations=3)
        orchestrator.adjuster.violation_threshold = 1
        orchestrator.run()
        
    assert pipeline.run.call_count == 3
    assert drc_runner.call_count == 3
