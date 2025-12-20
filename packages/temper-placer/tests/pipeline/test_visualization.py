import pytest
from temper_placer.pipeline.visualization import TerminalProgress, RichDashboard
from temper_placer.pipeline.orchestrator import PipelinePhase, PipelineState, PipelineConfig
from temper_placer.optimizer.train import TrainingMetrics
from pathlib import Path

def create_metrics(epoch, loss):
    return TrainingMetrics(
        epoch=epoch,
        loss=loss,
        temperature=1.0,
        learning_rate=0.1,
        loss_breakdown={},
        grad_norm_pos=0.0,
        grad_norm_rot=0.0,
        elapsed_ms=10.0
    )

def test_terminal_progress_callbacks():
    progress = TerminalProgress(total_phases=2)
    config = PipelineConfig(input_pcb=Path("fake.kicad_pcb"))
    state = PipelineState(config=config)
    
    # Test phase start (should not crash)
    progress.on_phase_start(PipelinePhase.INPUT, state)
    assert progress.current_phase == 1
    
    # Test iteration
    progress.on_iteration(1, state)
    assert progress.current_iteration == 1
    
    # Test epoch
    metrics = create_metrics(100, 1.0)
    progress.on_epoch(metrics)

def test_rich_dashboard_layout():
    dashboard = RichDashboard()
    layout = dashboard.create_layout()
    
    # Access named regions to verify they exist
    assert layout["header"] is not None
    assert layout["body"] is not None
    assert layout["footer"] is not None
    assert layout["body"]["left"] is not None
    assert layout["body"]["right"] is not None

def test_rich_dashboard_updates():
    dashboard = RichDashboard()
    dashboard.create_layout()
    
    dashboard.on_phase_start(PipelinePhase.GEOMETRIC, None)
    assert dashboard.current_phase == PipelinePhase.GEOMETRIC
    
    metrics = create_metrics(1, 0.5)
    dashboard.on_epoch(metrics)
    assert len(dashboard.losses) == 1
    assert dashboard.metrics["loss"] == 0.5
    
    # Test update (should not crash)
    dashboard.update()