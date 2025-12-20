"""
Tests for pipeline orchestrator.
"""

import pytest
from pathlib import Path
from temper_placer.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig, PipelinePhase

@pytest.fixture
def minimal_pcb():
    return Path("tests/fixtures/minimal_board.kicad_pcb")

def test_orchestrator_dry_run(minimal_pcb):
    # We need to run from packages/temper-placer to find the relative path
    config = PipelineConfig(
        input_pcb=minimal_pcb,
        dry_run=True
    )
    
    orchestrator = PipelineOrchestrator(config)
    
    # Track phase starts
    started_phases = []
    orchestrator.on_phase_start = lambda p, s: started_phases.append(p)
    
    state = orchestrator.run()
    
    assert state.success
    assert PipelinePhase.INPUT in started_phases
    assert PipelinePhase.PREFLIGHT in started_phases
    assert PipelinePhase.GEOMETRIC not in started_phases # Skipped in dry-run
    assert state.preflight_report is not None

def test_orchestrator_full_run_fast(minimal_pcb):
    # Fast full run with minimal epochs
    config = PipelineConfig(
        input_pcb=minimal_pcb,
        epochs=10,
        dry_run=False,
        skip_routing=True # Fast test
    )
    
    orchestrator = PipelineOrchestrator(config)
    state = orchestrator.run()
    
    assert state.success
    assert state.placement_state is not None
    assert state.current_phase == PipelinePhase.OUTPUT
