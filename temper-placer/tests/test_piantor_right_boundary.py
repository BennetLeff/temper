
import pytest
from pathlib import Path
import sys

# Add project root to path to allow sibling imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.validation.test_placement_comparison import get_project_paths, run_optimizer_on_pcb, compare_metrics, BaselineMetrics

@pytest.mark.external
@pytest.mark.slow
def test_piantor_right_boundary_extended():
    """
    Focused test for piantor_right with more epochs to debug boundary violations.
    """
    project_name = "piantor_right"
    unrouted_path, baseline_path, constraints_path = get_project_paths(project_name)

    if not all([unrouted_path, baseline_path, constraints_path]):
        pytest.skip(f"Required files for {project_name} not found.")

    baseline = BaselineMetrics.from_yaml(baseline_path)

    # Run optimizer with more epochs
    _, optimizer_metrics, _ = run_optimizer_on_pcb(
        unrouted_path,
        constraints_path,
        epochs=2000,  # Increased from 100 to 2000
        learning_rate=0.1, # Slower learning rate for stability
    )

    # Compare with a stricter boundary threshold
    result = compare_metrics(baseline, optimizer_metrics, boundary_threshold=5.0)

    print(f"\n{'=' * 60}")
    print(f"Project: {project_name} (Extended Epochs)")
    print(f"{'=' * 60}")
    print(f"Overlap Loss: {optimizer_metrics.overlap_loss:.2f}")
    print(f"Wirelength: {optimizer_metrics.total_wirelength_mm:.1f}")
    print(f"Boundary Loss: {optimizer_metrics.boundary_loss:.2f}")
    print(f"{'=' * 60}")

    assert result.passed, f"Boundary violation still high: {optimizer_metrics.boundary_loss}"
    assert optimizer_metrics.boundary_loss < 20.0, "Boundary loss should be below 20.0"
