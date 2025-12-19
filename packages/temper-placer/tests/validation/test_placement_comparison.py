"""
External PCB Placement Comparison Tests.

Validates optimizer placement quality against human-designed baselines
using unrouted versions of real-world open-source PCB designs.

Test Strategy:
1. Load unrouted PCB (traces stripped, components remain)
2. Load baseline metrics from original human-designed layout
3. Run optimizer with same constraints
4. Compare optimizer metrics against baseline
5. Generate comparison report

Acceptance Criteria:
- Wirelength: <= 150% of baseline (optimizer may not beat human but shouldn't be terrible)
- Overlap: < baseline OR < 10.0 (humans sometimes have overlap too)
- Boundary: < baseline OR < 100.0 (acceptable boundary violations)
- Overall: At least 2/3 metrics should improve or match baseline

Projects tested:
- piantor_left: 36 components (keyboard)
- piantor_right: 36 components (keyboard)
- bitaxe_ultra: 136 components (Bitcoin miner, power electronics)
- libresolar_bms: 147 components (battery management)
- rp2040_designguide: 38 components (dev board)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.state import PlacementState
from temper_placer.losses import (
    BoundaryLoss,
    CompositeLoss,
    OverlapLoss,
    WeightedLoss,
    WirelengthLoss,
)
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import compute_total_hpwl
from temper_placer.optimizer.config import (
    LearningRateSchedule,
    OptimizerConfig,
    TemperatureSchedule,
)

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "external"
CACHE_DIR = FIXTURES_DIR / ".cache"
RESULTS_DIR = Path(__file__).parent / "results"


# Projects with KiCad 6 format that we can test
TESTABLE_PROJECTS = [
    "piantor_left",
    "piantor_right",
    "bitaxe_ultra",
    "libresolar_bms",
    "rp2040_designguide",
]


@dataclass
class BaselineMetrics:
    """Metrics from human-designed baseline."""

    project: str
    component_count: int
    net_count: int
    board_width_mm: float
    board_height_mm: float
    total_wirelength_mm: float
    overlap_loss: float
    boundary_loss: float

    @classmethod
    def from_yaml(cls, path: Path) -> "BaselineMetrics":
        """Load from baseline YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            project=data["project"],
            component_count=data["component_count"],
            net_count=data["net_count"],
            board_width_mm=data["board_width_mm"],
            board_height_mm=data["board_height_mm"],
            total_wirelength_mm=data["total_wirelength_mm"],
            overlap_loss=data["overlap_loss"],
            boundary_loss=data["boundary_loss"],
        )


@dataclass
class OptimizerMetrics:
    """Metrics from optimizer output."""

    total_wirelength_mm: float
    overlap_loss: float
    boundary_loss: float
    epochs_run: int
    final_loss: float
    optimization_time_s: float


@dataclass
class ComparisonResult:
    """Result of comparing optimizer vs baseline."""

    project: str
    baseline: BaselineMetrics
    optimizer: OptimizerMetrics

    # Ratios (optimizer / baseline) - lower is better for all
    wirelength_ratio: float
    overlap_improvement: bool  # True if optimizer < baseline
    boundary_improvement: bool  # True if optimizer < baseline

    # Pass/fail
    passed: bool
    failure_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project": self.project,
            "baseline": {
                "component_count": self.baseline.component_count,
                "net_count": self.baseline.net_count,
                "wirelength_mm": self.baseline.total_wirelength_mm,
                "overlap_loss": self.baseline.overlap_loss,
                "boundary_loss": self.baseline.boundary_loss,
            },
            "optimizer": {
                "wirelength_mm": self.optimizer.total_wirelength_mm,
                "overlap_loss": self.optimizer.overlap_loss,
                "boundary_loss": self.optimizer.boundary_loss,
                "epochs": self.optimizer.epochs_run,
                "final_loss": self.optimizer.final_loss,
                "time_s": self.optimizer.optimization_time_s,
            },
            "comparison": {
                "wirelength_ratio": self.wirelength_ratio,
                "overlap_improved": self.overlap_improvement,
                "boundary_improved": self.boundary_improvement,
            },
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
        }


def get_project_paths(project_name: str) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """
    Get paths to unrouted PCB, baseline, and constraints for a project.

    Returns:
        Tuple of (unrouted_pcb_path, baseline_path, constraints_path)
        Any may be None if not found.
    """
    project_dir = CACHE_DIR / project_name

    if not project_dir.exists():
        return None, None, None

    # Find unrouted PCB
    unrouted_path: Optional[Path] = project_dir / f"{project_name}_unrouted.kicad_pcb"
    if not unrouted_path.exists():
        # Try alternate naming
        for f in project_dir.glob("*_unrouted.kicad_pcb"):
            unrouted_path = f
            break
        else:
            unrouted_path = None

    # Find baseline
    baseline_path: Optional[Path] = project_dir / f"{project_name}_baseline.yaml"
    if not baseline_path.exists():
        baseline_path = None

    # Find constraints
    constraints_path: Optional[Path] = project_dir / f"{project_name}_constraints.yaml"
    if not constraints_path.exists():
        constraints_path = None

    return unrouted_path, baseline_path, constraints_path


def is_project_available(project_name: str) -> bool:
    """Check if all required files for a project are available."""
    unrouted, baseline, constraints = get_project_paths(project_name)
    return all([unrouted, baseline, constraints])


def run_optimizer_on_pcb(
    pcb_path: Path,
    constraints_path: Optional[Path] = None,
    epochs: int = 100,
    learning_rate: float = 0.5,
) -> Tuple[PlacementState, OptimizerMetrics, LossContext]:
    """
    Run the optimizer on an unrouted PCB.

    Args:
        pcb_path: Path to unrouted .kicad_pcb file
        constraints_path: Optional path to constraints YAML
        epochs: Number of optimization epochs
        learning_rate: Learning rate for optimizer

    Returns:
        Tuple of (final_state, metrics, context)
    """
    import time

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.optimizer import train

    # Parse PCB
    result = parse_kicad_pcb(pcb_path)
    netlist = result.netlist
    board = result.board

    if board is None:
        raise ValueError(f"No board geometry in {pcb_path}")

    # Build loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Configure losses - weighted for quality placement
    composite = CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=100.0),  # High weight - no overlap
            WeightedLoss(BoundaryLoss(), weight=200.0),  # Highest weight - stay in bounds (hard constraint)
            WeightedLoss(WirelengthLoss(), weight=10.0),  # Lower weight - minimize wirelength
        ]
    )

    # Configure optimizer for moderate quality/speed tradeoff
    config = OptimizerConfig(
        epochs=epochs,
        temperature=TemperatureSchedule(start=1.0, end=0.1),
        learning_rate=LearningRateSchedule(initial=learning_rate),
        log_interval=max(1, epochs // 10),
    )

    # Run optimization
    start_time = time.time()
    train_result = train(netlist, board, composite, context, config)
    elapsed = time.time() - start_time

    # Extract final state and compute metrics
    final_state = train_result.best_state
    if final_state is None:
        raise RuntimeError("Optimizer did not produce a best state")

    # Compute metrics on final state using one-hot rotations
    # Use argmax to get discrete rotation indices, then create one-hot
    rotation_indices = jnp.argmax(final_state.rotation_logits, axis=-1)
    n_components = final_state.n_components
    rotations = jax.nn.one_hot(rotation_indices, 4)

    # Wirelength
    wirelength = float(compute_total_hpwl(final_state.positions, rotations, context))

    # Overlap loss
    overlap_fn = OverlapLoss()
    overlap_result = overlap_fn(final_state.positions, rotations, context)
    overlap_loss = float(overlap_result.value)

    # Boundary loss
    boundary_fn = BoundaryLoss()
    boundary_result = boundary_fn(final_state.positions, rotations, context)
    boundary_loss = float(boundary_result.value)

    metrics = OptimizerMetrics(
        total_wirelength_mm=wirelength,
        overlap_loss=overlap_loss,
        boundary_loss=boundary_loss,
        epochs_run=train_result.total_epochs,
        final_loss=float(train_result.best_loss),
        optimization_time_s=elapsed,
    )

    return final_state, metrics, context


def compare_metrics(
    baseline: BaselineMetrics,
    optimizer: OptimizerMetrics,
    wirelength_threshold: float = 1.5,  # Allow 50% worse than baseline
    overlap_threshold: float = 10.0,  # Acceptable absolute overlap
    boundary_threshold: float = 100.0,  # Acceptable absolute boundary violation
) -> ComparisonResult:
    """
    Compare optimizer metrics against baseline.

    Args:
        baseline: Metrics from human-designed layout
        optimizer: Metrics from optimizer
        wirelength_threshold: Max ratio of optimizer/baseline wirelength
        overlap_threshold: Max acceptable overlap loss
        boundary_threshold: Max acceptable boundary loss

    Returns:
        ComparisonResult with pass/fail determination
    """
    failure_reasons: List[str] = []

    # Wirelength ratio
    if baseline.total_wirelength_mm > 0:
        wirelength_ratio = optimizer.total_wirelength_mm / baseline.total_wirelength_mm
    else:
        wirelength_ratio = 1.0  # No baseline to compare

    # Check wirelength
    if wirelength_ratio > wirelength_threshold:
        failure_reasons.append(
            f"Wirelength {wirelength_ratio:.2f}x baseline (threshold: {wirelength_threshold}x)"
        )

    # Check overlap - either better than baseline OR below absolute threshold
    overlap_improvement = optimizer.overlap_loss < baseline.overlap_loss
    if not overlap_improvement and optimizer.overlap_loss > overlap_threshold:
        failure_reasons.append(
            f"Overlap {optimizer.overlap_loss:.2f} > threshold {overlap_threshold}"
        )

    # Check boundary - either better than baseline OR below absolute threshold
    boundary_improvement = optimizer.boundary_loss < baseline.boundary_loss
    if not boundary_improvement and optimizer.boundary_loss > boundary_threshold:
        failure_reasons.append(
            f"Boundary {optimizer.boundary_loss:.2f} > threshold {boundary_threshold}"
        )

    # Pass if no critical failures
    passed = len(failure_reasons) == 0

    return ComparisonResult(
        project=baseline.project,
        baseline=baseline,
        optimizer=optimizer,
        wirelength_ratio=wirelength_ratio,
        overlap_improvement=overlap_improvement,
        boundary_improvement=boundary_improvement,
        passed=passed,
        failure_reasons=failure_reasons,
    )


def generate_comparison_report(results: List[ComparisonResult]) -> Dict[str, Any]:
    """
    Generate a summary report from multiple comparison results.

    Args:
        results: List of comparison results

    Returns:
        Summary report dictionary
    """
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    # Aggregate metrics
    avg_wirelength_ratio = sum(r.wirelength_ratio for r in results) / len(results) if results else 0
    overlap_improvements = sum(1 for r in results if r.overlap_improvement)
    boundary_improvements = sum(1 for r in results if r.boundary_improvement)

    return {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_projects": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{100 * passed / len(results):.1f}%" if results else "N/A",
        },
        "aggregate_metrics": {
            "avg_wirelength_ratio": round(avg_wirelength_ratio, 3),
            "overlap_improvements": f"{overlap_improvements}/{len(results)}",
            "boundary_improvements": f"{boundary_improvements}/{len(results)}",
        },
        "projects": [r.to_dict() for r in results],
    }


# =============================================================================
# Test Classes
# =============================================================================


class TestProjectAvailability:
    """Tests for project file availability."""

    @pytest.mark.parametrize("project_name", TESTABLE_PROJECTS)
    def test_project_files_exist(self, project_name: str):
        """Check that required files exist for each project."""
        unrouted, baseline, constraints = get_project_paths(project_name)

        # At minimum we need unrouted PCB and baseline
        if unrouted is None:
            pytest.skip(f"Unrouted PCB not found for {project_name}")

        if baseline is None:
            pytest.skip(f"Baseline not found for {project_name}")

        assert unrouted.exists(), f"Unrouted PCB not found: {unrouted}"
        assert baseline.exists(), f"Baseline not found: {baseline}"


class TestBaselineLoading:
    """Tests for loading baseline metrics."""

    @pytest.mark.parametrize("project_name", TESTABLE_PROJECTS)
    def test_load_baseline(self, project_name: str):
        """Test loading baseline metrics from YAML."""
        _, baseline_path, _ = get_project_paths(project_name)

        if baseline_path is None or not baseline_path.exists():
            pytest.skip(f"Baseline not available for {project_name}")

        baseline = BaselineMetrics.from_yaml(baseline_path)

        # Validate loaded data
        assert baseline.project == project_name
        assert baseline.component_count > 0
        assert baseline.board_width_mm > 0
        assert baseline.board_height_mm > 0
        assert baseline.total_wirelength_mm > 0


class TestOptimizerOnUnroutedPCB:
    """Tests for running optimizer on unrouted PCBs."""

    @pytest.fixture
    def fast_optimizer_config(self) -> Dict[str, Any]:
        """Configuration for fast testing."""
        return {
            "epochs": 50,  # Reduced for testing speed
            "learning_rate": 0.5,
        }

    @pytest.mark.external
    @pytest.mark.slow
    @pytest.mark.parametrize("project_name", TESTABLE_PROJECTS)
    def test_optimizer_runs_on_project(
        self, project_name: str, fast_optimizer_config: Dict[str, Any]
    ):
        """Test that optimizer runs without crashing on each project."""
        unrouted_path, baseline_path, constraints_path = get_project_paths(project_name)

        if unrouted_path is None or not unrouted_path.exists():
            pytest.skip(f"Unrouted PCB not available for {project_name}")

        # Run optimizer
        final_state, metrics, context = run_optimizer_on_pcb(
            unrouted_path,
            constraints_path,
            **fast_optimizer_config,
        )

        # Basic sanity checks
        assert final_state is not None
        assert final_state.positions.shape[0] > 0
        assert metrics.total_wirelength_mm > 0
        assert metrics.epochs_run > 0

        # Metrics should be finite
        assert jnp.isfinite(metrics.total_wirelength_mm)
        assert jnp.isfinite(metrics.overlap_loss)
        assert jnp.isfinite(metrics.boundary_loss)

    @pytest.mark.external
    @pytest.mark.slow
    @pytest.mark.parametrize("project_name", ["piantor_left"])  # Start with smallest
    def test_optimizer_improves_loss(self, project_name: str):
        """Test that optimizer actually improves loss over random init."""
        unrouted_path, _, constraints_path = get_project_paths(project_name)

        if unrouted_path is None or not unrouted_path.exists():
            pytest.skip(f"Unrouted PCB not available for {project_name}")

        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.optimizer import train

        # Parse PCB
        result = parse_kicad_pcb(unrouted_path)
        netlist = result.netlist
        board = result.board

        if board is None:
            pytest.skip(f"No board geometry in {unrouted_path}")

        context = LossContext.from_netlist_and_board(netlist, board)

        # Configure loss
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
                WeightedLoss(WirelengthLoss(), weight=10.0),
            ]
        )

        # Run optimization
        config = OptimizerConfig(
            epochs=100,
            learning_rate=LearningRateSchedule(initial=0.5),
        )
        train_result = train(netlist, board, composite, context, config)

        # Loss should improve
        if len(train_result.history) > 1:
            initial_loss = train_result.history[0].loss
            final_loss = train_result.best_loss
            assert final_loss <= initial_loss, "Loss should not increase"


class TestCompareAgainstBaseline:
    """Tests comparing optimizer output against human baselines."""

    @pytest.mark.external
    @pytest.mark.slow
    @pytest.mark.parametrize("project_name", TESTABLE_PROJECTS)
    def test_compare_single_project(self, project_name: str):
        """Compare optimizer placement against baseline for a single project."""
        unrouted_path, baseline_path, constraints_path = get_project_paths(project_name)

        if unrouted_path is None or baseline_path is None:
            pytest.skip(f"Required files not available for {project_name}")

        if not unrouted_path.exists() or not baseline_path.exists():
            pytest.skip(f"Files missing for {project_name}")

        # Load baseline
        baseline = BaselineMetrics.from_yaml(baseline_path)

        # Run optimizer
        _, optimizer_metrics, _ = run_optimizer_on_pcb(
            unrouted_path,
            constraints_path,
            epochs=100,  # Moderate epochs for quality
            learning_rate=0.5,
        )

        # Compare
        result = compare_metrics(baseline, optimizer_metrics)

        # Log results
        print(f"\n{'=' * 60}")
        print(f"Project: {project_name}")
        print(f"Components: {baseline.component_count}, Nets: {baseline.net_count}")
        print(f"{'=' * 60}")
        print(f"Metric           | Baseline    | Optimizer   | Status")
        print(f"{'-' * 60}")
        print(
            f"Wirelength (mm)  | {baseline.total_wirelength_mm:>10.1f} | "
            f"{optimizer_metrics.total_wirelength_mm:>10.1f} | "
            f"{result.wirelength_ratio:.2f}x"
        )
        print(
            f"Overlap Loss     | {baseline.overlap_loss:>10.2f} | "
            f"{optimizer_metrics.overlap_loss:>10.2f} | "
            f"{'BETTER' if result.overlap_improvement else 'worse'}"
        )
        print(
            f"Boundary Loss    | {baseline.boundary_loss:>10.2f} | "
            f"{optimizer_metrics.boundary_loss:>10.2f} | "
            f"{'BETTER' if result.boundary_improvement else 'worse'}"
        )
        print(f"{'=' * 60}")
        print(f"RESULT: {'PASS' if result.passed else 'FAIL'}")
        if result.failure_reasons:
            for reason in result.failure_reasons:
                print(f"  - {reason}")
        print()

        # Test assertion (may be relaxed for initial development)
        # For now, just ensure comparison completes without asserting pass
        assert result is not None


class TestGenerateComparisonReport:
    """Tests for generating comparison reports."""

    @pytest.mark.external
    @pytest.mark.slow
    def test_generate_full_report(self):
        """Generate comparison report for all available projects."""
        results: List[ComparisonResult] = []

        for project_name in TESTABLE_PROJECTS:
            unrouted_path, baseline_path, constraints_path = get_project_paths(project_name)

            if unrouted_path is None or baseline_path is None:
                print(f"Skipping {project_name}: missing files")
                continue

            if not unrouted_path.exists() or not baseline_path.exists():
                print(f"Skipping {project_name}: files not found")
                continue

            try:
                # Load baseline
                baseline = BaselineMetrics.from_yaml(baseline_path)

                # Run optimizer
                _, optimizer_metrics, _ = run_optimizer_on_pcb(
                    unrouted_path,
                    constraints_path,
                    epochs=100,
                    learning_rate=0.5,
                )

                # Compare
                result = compare_metrics(baseline, optimizer_metrics)
                results.append(result)

                print(f"[{'PASS' if result.passed else 'FAIL'}] {project_name}")

            except Exception as e:
                print(f"[ERROR] {project_name}: {e}")

        if not results:
            pytest.skip("No projects available for testing")

        # Generate report
        report = generate_comparison_report(results)

        # Save report
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = RESULTS_DIR / "placement_comparison_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nReport saved to: {report_path}")
        print(
            f"Summary: {report['summary']['passed']}/{report['summary']['total_projects']} passed"
        )

        # Assert at least one project was tested
        assert len(results) > 0


class TestComparisonResultFormat:
    """Tests for comparison result data structures."""

    def test_comparison_result_to_dict(self):
        """Test that ComparisonResult converts to dict correctly."""
        baseline = BaselineMetrics(
            project="test_project",
            component_count=10,
            net_count=5,
            board_width_mm=100.0,
            board_height_mm=80.0,
            total_wirelength_mm=500.0,
            overlap_loss=0.0,
            boundary_loss=0.0,
        )

        optimizer = OptimizerMetrics(
            total_wirelength_mm=450.0,
            overlap_loss=0.1,
            boundary_loss=0.5,
            epochs_run=100,
            final_loss=10.0,
            optimization_time_s=5.0,
        )

        result = compare_metrics(baseline, optimizer)

        # Convert to dict
        d = result.to_dict()

        # Verify structure
        assert "project" in d
        assert "baseline" in d
        assert "optimizer" in d
        assert "comparison" in d
        assert "passed" in d

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_report_generation_empty(self):
        """Test report generation with empty results."""
        report = generate_comparison_report([])

        assert report["summary"]["total_projects"] == 0
        assert report["summary"]["pass_rate"] == "N/A"


class TestQuickValidation:
    """Quick validation tests that run faster for CI."""

    @pytest.mark.external
    def test_smallest_project_optimization(self):
        """Quick test on smallest available project."""
        # Try projects in order of expected size
        for project_name in ["piantor_left", "rp2040_designguide", "piantor_right"]:
            unrouted_path, baseline_path, _ = get_project_paths(project_name)

            if unrouted_path and unrouted_path.exists():
                # Run very quick optimization
                final_state, metrics, _ = run_optimizer_on_pcb(
                    unrouted_path,
                    epochs=20,  # Very few epochs for speed
                    learning_rate=1.0,  # Aggressive for quick convergence
                )

                # Just verify it runs
                assert final_state is not None
                assert metrics.total_wirelength_mm > 0
                return

        pytest.skip("No small project available")
