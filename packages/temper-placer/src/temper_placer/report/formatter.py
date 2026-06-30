"""
Report formatting for DRC check results.

Moved from ``temper_drc.report.formatter``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from temper_placer.validation.drc_result import Severity

if TYPE_CHECKING:
    from temper_placer.validation.drc_result import RunResult
    from temper_placer.validation.drc_types import ConstraintSet


def format_text(result: RunResult) -> str:
    """Format check results as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append("temper-drc Check Report")
    lines.append("=" * 80)
    lines.append("")

    total_checks = len(result.check_results)
    passed_checks = sum(1 for r in result.check_results if r.passed)
    failed_checks = total_checks - passed_checks
    total_issues = len(result.all_issues)
    critical_issues = sum(
        1 for r in result.check_results for i in r.issues if i.severity == Severity.CRITICAL
    )
    error_issues = sum(
        1 for r in result.check_results for i in r.issues if i.severity == Severity.ERROR
    )
    warning_issues = sum(
        1 for r in result.check_results for i in r.issues if i.severity == Severity.WARNING
    )

    lines.append(f"Status: {'PASS' if result.passed else 'FAIL'}")
    lines.append(f"Checks: {passed_checks} passed, {failed_checks} failed (out of {total_checks})")
    lines.append(f"Issues: {total_issues} total")
    if critical_issues:
        lines.append(f"  - {critical_issues} CRITICAL")
    if error_issues:
        lines.append(f"  - {error_issues} ERROR")
    if warning_issues:
        lines.append(f"  - {warning_issues} WARNING")
    lines.append(f"Runtime: {result.total_elapsed_ms:.1f}ms")
    lines.append("")

    if result.check_results:
        lines.append("-" * 80)
        lines.append("Check Results:")
        lines.append("-" * 80)

        for check_result in result.check_results:
            status_symbol = "✓" if check_result.passed else "✗"
            lines.append(
                f"{status_symbol} {check_result.check_name} ({check_result.elapsed_ms:.1f}ms)"
            )

            if check_result.issues:
                for issue in check_result.issues:
                    severity_label = issue.severity.name
                    lines.append(f"    [{severity_label}] {issue.code}: {issue.message}")
                    if issue.affected_items:
                        lines.append(f"      Affected: {', '.join(issue.affected_items)}")
                    if issue.location:
                        lines.append(
                            f"      Location: ({issue.location.x:.2f}, {issue.location.y:.2f})"
                        )

            lines.append("")

    metrics_exist = any(check_result.metrics for check_result in result.check_results)
    if metrics_exist:
        lines.append("-" * 80)
        lines.append("Metrics:")
        lines.append("-" * 80)
        for check_result in result.check_results:
            if check_result.metrics:
                lines.append(f"{check_result.check_name}:")
                for key, value in check_result.metrics.items():
                    if isinstance(value, float):
                        lines.append(f"  {key}: {value:.3f}")
                    else:
                        lines.append(f"  {key}: {value}")
                lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def format_json(result: RunResult) -> str:
    """Format check results as JSON."""
    data = {
        "passed": result.passed,
        "total_checks": len(result.check_results),
        "passed_checks": sum(1 for r in result.check_results if r.passed),
        "failed_checks": sum(1 for r in result.check_results if not r.passed),
        "total_issues": len(result.all_issues),
        "runtime_ms": result.total_elapsed_ms,
        "checks": [],
    }

    for check_result in result.check_results:
        check_data = {
            "name": check_result.check_name,
            "passed": check_result.passed,
            "elapsed_ms": check_result.elapsed_ms,
            "issue_count": len(check_result.issues),
            "issues": [],
            "metrics": check_result.metrics,
        }

        for issue in check_result.issues:
            issue_data = {
                "severity": issue.severity.name,
                "code": issue.code,
                "message": issue.message,
                "category": issue.category,
                "affected_items": issue.affected_items,
            }
            if issue.location:
                issue_data["location"] = {
                    "x": issue.location.x,
                    "y": issue.location.y,
                    "layer": issue.location.layer,
                }
            if issue.details:
                issue_data["details"] = issue.details
            check_data["issues"].append(issue_data)

        data["checks"].append(check_data)

    return json.dumps(data, indent=2)


def format_html(result: RunResult, placement_name: str, _constraints: ConstraintSet) -> str:
    """Format check results as HTML report."""
    status_color = "#28a745" if result.passed else "#dc3545"
    status_text = "PASS" if result.passed else "FAIL"

    total_checks = len(result.check_results)
    passed_checks = sum(1 for r in result.check_results if r.passed)
    failed_checks = total_checks - passed_checks

    severity_counts = {
        "CRITICAL": 0,
        "ERROR": 0,
        "WARNING": 0,
        "INFO": 0,
    }

    for check_result in result.check_results:
        for issue in check_result.issues:
            severity_counts[issue.severity.name] += 1

    check_rows = []
    for check_result in result.check_results:
        status_icon = "✓" if check_result.passed else "✗"
        row_class = "table-success" if check_result.passed else "table-danger"

        issue_details = ""
        if check_result.issues:
            issue_list = ["<ul>"]
            for issue in check_result.issues:
                severity_badge = f'<span class="badge badge-{_severity_to_bootstrap(issue.severity)}">{issue.severity.name}</span>'
                issue_list.append(f"<li>{severity_badge} {issue.code}: {issue.message}</li>")
            issue_list.append("</ul>")
            issue_details = "".join(issue_list)

        check_rows.append(
            f'<tr class="{row_class}">'
            f"<td>{status_icon}</td>"
            f"<td>{check_result.check_name}</td>"
            f"<td>{len(check_result.issues)}</td>"
            f"<td>{check_result.elapsed_ms:.1f}ms</td>"
            f"<td>{issue_details}</td>"
            f"</tr>"
        )

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>temper-drc Check Report</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <style>
        body {{ padding: 20px; }}
        .summary-card {{ margin-bottom: 20px; }}
        .metric-badge {{ font-size: 2rem; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="container-fluid">
        <h1>temper-drc Check Report</h1>
        <p class="text-muted">Placement: {placement_name}</p>

        <div class="row summary-card">
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Status</h5>
                        <div class="metric-badge" style="color: {status_color};">{status_text}</div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Checks</h5>
                        <div class="metric-badge">{passed_checks}/{total_checks}</div>
                        <p class="text-muted">{failed_checks} failed</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Issues</h5>
                        <div class="metric-badge">{len(result.all_issues)}</div>
                        <p class="text-muted">
                            <span class="badge badge-danger">{severity_counts["CRITICAL"]} Critical</span>
                            <span class="badge badge-warning">{severity_counts["ERROR"]} Error</span>
                            <span class="badge badge-info">{severity_counts["WARNING"]} Warning</span>
                        </p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Runtime</h5>
                        <div class="metric-badge">{result.total_elapsed_ms:.1f}ms</div>
                    </div>
                </div>
            </div>
        </div>

        <h2>Check Results</h2>
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Check</th>
                    <th>Issues</th>
                    <th>Time</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
                {"".join(check_rows)}
            </tbody>
        </table>

        <hr>
        <footer class="text-muted">
            <p>Generated by temper-drc</p>
        </footer>
    </div>
</body>
</html>
"""
    return html


def _severity_to_bootstrap(severity: Severity) -> str:
    """Map severity to Bootstrap badge class."""
    mapping = {
        Severity.CRITICAL: "danger",
        Severity.ERROR: "warning",
        Severity.WARNING: "info",
        Severity.INFO: "secondary",
    }
    return mapping.get(severity, "secondary")
