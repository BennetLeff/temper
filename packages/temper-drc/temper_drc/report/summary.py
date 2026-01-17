"""Summary report generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_drc.core.result import RunResult
    from temper_drc.input.constraints import ConstraintSet
    from temper_drc.input.placement import Placement


def generate_summary(
    result: RunResult,
    placement: Placement,
    constraints: ConstraintSet,
) -> str:
    """
    Generate a high-level summary of check results with key metrics.

    Args:
        result: The run result to summarize.
        placement: The placement data.
        constraints: The constraint set.

    Returns:
        Formatted summary text.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("temper-drc Summary")
    lines.append("=" * 60)
    lines.append("")

    # Overall status
    status = "✓ PASS" if result.passed else "✗ FAIL"
    lines.append(f"Overall Status: {status}")
    lines.append("")

    # Basic statistics
    lines.append("Statistics:")
    lines.append(f"  Components: {len(placement.components)}")
    lines.append(f"  Nets: {len(placement.nets)}")
    lines.append(f"  Zones: {len(placement.zones)}")
    lines.append(f"  Board Size: {placement.board_width}mm × {placement.board_height}mm")
    lines.append("")

    # Check summary
    total_checks = len(result.check_results)
    passed_checks = sum(1 for r in result.check_results if r.passed)
    failed_checks = total_checks - passed_checks

    lines.append("Check Summary:")
    lines.append(f"  Total Checks: {total_checks}")
    lines.append(f"  Passed: {passed_checks}")
    lines.append(f"  Failed: {failed_checks}")
    lines.append(f"  Runtime: {result.total_elapsed_ms:.1f}ms")
    lines.append("")

    # Issue breakdown by category
    issues_by_category: dict[str, int] = {}
    for check_result in result.check_results:
        for issue in check_result.issues:
            category = issue.category
            issues_by_category[category] = issues_by_category.get(category, 0) + 1

    if issues_by_category:
        lines.append("Issues by Category:")
        for category, count in sorted(issues_by_category.items()):
            lines.append(f"  {category.upper()}: {count}")
        lines.append("")

    # Key metrics
    key_metrics = _extract_key_metrics(result)
    if key_metrics:
        lines.append("Key Metrics:")
        for metric_name, metric_value in key_metrics:
            if isinstance(metric_value, float):
                lines.append(f"  {metric_name}: {metric_value:.3f}")
            else:
                lines.append(f"  {metric_name}: {metric_value}")
        lines.append("")

    # Top issues (if any)
    all_issues = result.all_issues
    if all_issues:
        critical_count = sum(1 for i in all_issues if i.severity.name == "CRITICAL")
        error_count = sum(1 for i in all_issues if i.severity.name == "ERROR")
        warning_count = sum(1 for i in all_issues if i.severity.name == "WARNING")

        lines.append("Issue Severity Breakdown:")
        if critical_count:
            lines.append(f"  CRITICAL: {critical_count}")
        if error_count:
            lines.append(f"  ERROR: {error_count}")
        if warning_count:
            lines.append(f"  WARNING: {warning_count}")
        lines.append("")

        # Show top 5 issues
        top_issues = sorted(
            all_issues,
            key=lambda i: (
                i.severity.name == "INFO",
                i.severity.name == "WARNING",
                i.severity.name == "ERROR",
                i.severity.name == "CRITICAL",
            ),
        )[:5]

        if top_issues:
            lines.append("Top Issues:")
            for issue in top_issues:
                lines.append(f"  [{issue.severity.name}] {issue.code}: {issue.message}")
            lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


def _extract_key_metrics(result: RunResult) -> list[tuple[str, float | int]]:
    """Extract key metrics from check results."""
    metrics = []

    for check_result in result.check_results:
        if not check_result.metrics:
            continue

        # Extract specific metrics we care about
        if "min_clearance_mm" in check_result.metrics:
            metrics.append(
                (
                    "Minimum Clearance",
                    check_result.metrics["min_clearance_mm"],
                )
            )

        if "overlap_count" in check_result.metrics:
            metrics.append(
                (
                    "Component Overlaps",
                    check_result.metrics["overlap_count"],
                )
            )

        if "max_loop_area_mm2" in check_result.metrics:
            metrics.append(
                (
                    "Max Loop Area (mm²)",
                    check_result.metrics["max_loop_area_mm2"],
                )
            )

        if "ground_discontinuities" in check_result.metrics:
            metrics.append(
                (
                    "Ground Discontinuities",
                    check_result.metrics["ground_discontinuities"],
                )
            )

        if "floating_pins" in check_result.metrics:
            metrics.append(
                (
                    "Floating Pins",
                    check_result.metrics["floating_pins"],
                )
            )

    return metrics
