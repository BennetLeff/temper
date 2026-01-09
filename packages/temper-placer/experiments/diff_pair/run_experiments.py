"""
Experiment Runner for Differential Pair Routing

Executes individual experiments and compares results against baselines.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import time

from .test_fixtures import TestFixture, create_test_fixtures


@dataclass
class ExperimentResult:
    """
    Result of running a single experiment.

    Attributes:
        fixture_name: Name of the test fixture
        success: Whether routing succeeded
        routing_time_s: Time taken to route (seconds)
        drc_violations: Number of DRC violations detected
        coupling_ratio: Percentage of path within target separation
        max_skew_mm: Maximum length mismatch between P and N
        avg_separation_mm: Average P-N spacing
        error_message: Error message if routing failed
        metadata: Additional experiment-specific data
    """

    fixture_name: str
    success: bool
    routing_time_s: float
    drc_violations: int
    coupling_ratio: float
    max_skew_mm: float
    avg_separation_mm: float
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for reporting."""
        return {
            "fixture": self.fixture_name,
            "success": self.success,
            "routing_time_s": round(self.routing_time_s, 3),
            "drc_violations": self.drc_violations,
            "coupling_ratio": round(self.coupling_ratio, 1),
            "max_skew_mm": round(self.max_skew_mm, 3),
            "avg_separation_mm": round(self.avg_separation_mm, 3),
            "error": self.error_message,
            "metadata": self.metadata,
        }

    def print_summary(self):
        """Print human-readable summary."""
        status = "✓ PASS" if self.success else "✗ FAIL"
        print(f"{status} {self.fixture_name}")
        print(f"    Time: {self.routing_time_s:.3f}s")
        print(f"    DRC Violations: {self.drc_violations}")
        print(f"    Coupling: {self.coupling_ratio:.1f}%")
        print(f"    Skew: {self.max_skew_mm:.3f}mm")
        if self.error_message:
            print(f"    Error: {self.error_message}")


def run_experiment(
    fixture: TestFixture,
    router,  # Router implementation (passed as parameter)
    drc_oracle=None,  # Optional DRC oracle for validation
    verbose: bool = False,
) -> ExperimentResult:
    """
    Run a single experiment with the given fixture and router.

    Args:
        fixture: Test fixture defining the routing problem
        router: Router implementation to test
        drc_oracle: Optional DRC oracle for validation
        verbose: Print detailed progress

    Returns:
        ExperimentResult with routing metrics
    """
    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Experiment: {fixture.name}")
        print(f"Description: {fixture.description}")
        print(f"{'=' * 60}")

    start_time = time.time()

    try:
        # TODO: Call router implementation
        # For now, return placeholder result
        elapsed = time.time() - start_time

        return ExperimentResult(
            fixture_name=fixture.name,
            success=False,
            routing_time_s=elapsed,
            drc_violations=0,
            coupling_ratio=0.0,
            max_skew_mm=0.0,
            avg_separation_mm=0.0,
            error_message="Router implementation not yet available",
        )

    except Exception as e:
        elapsed = time.time() - start_time
        return ExperimentResult(
            fixture_name=fixture.name,
            success=False,
            routing_time_s=elapsed,
            drc_violations=0,
            coupling_ratio=0.0,
            max_skew_mm=0.0,
            avg_separation_mm=0.0,
            error_message=str(e),
        )


def run_all_experiments(
    router, drc_oracle=None, tag_filter: Optional[str] = None, verbose: bool = False
) -> List[ExperimentResult]:
    """
    Run all experiments (optionally filtered by tag).

    Args:
        router: Router implementation to test
        drc_oracle: Optional DRC oracle for validation
        tag_filter: Only run experiments with this tag
        verbose: Print detailed progress

    Returns:
        List of ExperimentResult objects
    """
    from .test_fixtures import get_fixtures_by_tag

    if tag_filter:
        fixtures = get_fixtures_by_tag(tag_filter)
        print(f"Running {len(fixtures)} experiments with tag '{tag_filter}'")
    else:
        fixtures = create_test_fixtures()
        print(f"Running all {len(fixtures)} experiments")

    results = []
    for fixture in fixtures:
        result = run_experiment(fixture, router, drc_oracle, verbose)
        results.append(result)

        if not verbose:
            # Print one-line summary
            status = "✓" if result.success else "✗"
            print(
                f"  {status} {fixture.name}: {result.routing_time_s:.3f}s, {result.drc_violations} violations"
            )

    # Print overall summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    passed = sum(1 for r in results if r.success)
    print(f"  Passed: {passed}/{len(results)}")
    print(f"  Total time: {sum(r.routing_time_s for r in results):.3f}s")
    print(f"{'=' * 60}\n")

    return results


def compare_results(
    baseline: List[ExperimentResult], current: List[ExperimentResult], print_diff: bool = True
) -> Dict[str, Any]:
    """
    Compare baseline results with current results.

    Args:
        baseline: Baseline experiment results
        current: Current experiment results
        print_diff: Print detailed comparison

    Returns:
        Dictionary with comparison metrics
    """
    comparison = {
        "baseline_passed": sum(1 for r in baseline if r.success),
        "current_passed": sum(1 for r in current if r.success),
        "baseline_violations": sum(r.drc_violations for r in baseline),
        "current_violations": sum(r.drc_violations for r in current),
        "baseline_time_s": sum(r.routing_time_s for r in baseline),
        "current_time_s": sum(r.routing_time_s for r in current),
        "improvements": [],
        "regressions": [],
    }

    # Match fixtures by name
    baseline_by_name = {r.fixture_name: r for r in baseline}
    current_by_name = {r.fixture_name: r for r in current}

    for name in baseline_by_name:
        if name not in current_by_name:
            continue

        b = baseline_by_name[name]
        c = current_by_name[name]

        # Check for improvements
        if not b.success and c.success:
            comparison["improvements"].append(f"{name}: Now passes")
        elif b.drc_violations > c.drc_violations:
            comparison["improvements"].append(
                f"{name}: Violations {b.drc_violations} → {c.drc_violations}"
            )

        # Check for regressions
        if b.success and not c.success:
            comparison["regressions"].append(f"{name}: Now fails")
        elif b.drc_violations < c.drc_violations:
            comparison["regressions"].append(
                f"{name}: Violations {b.drc_violations} → {c.drc_violations}"
            )

    if print_diff:
        print("\n" + "=" * 60)
        print("Comparison vs Baseline:")
        print("=" * 60)
        print(f"Tests Passed: {comparison['baseline_passed']} → {comparison['current_passed']}")
        print(
            f"Total Violations: {comparison['baseline_violations']} → {comparison['current_violations']}"
        )
        print(
            f"Total Time: {comparison['baseline_time_s']:.3f}s → {comparison['current_time_s']:.3f}s"
        )

        if comparison["improvements"]:
            print("\nImprovements:")
            for imp in comparison["improvements"]:
                print(f"  ✓ {imp}")

        if comparison["regressions"]:
            print("\nRegressions:")
            for reg in comparison["regressions"]:
                print(f"  ✗ {reg}")

        print("=" * 60 + "\n")

    return comparison
