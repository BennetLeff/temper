"""Report generator for validation results."""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Optional

# Import result types from other modules
from temper_validation.comparison.wirelength import WirelengthResult
from temper_validation.comparison.drc_compliance import DRCComplianceResult
from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult
from temper_validation.metrics.quality_score import AggregateScoreResult

__all__ = [
    "generate_markdown_report",
    "generate_html_report",
]


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    title: str = "Placement Validation Report"
    author: str = "temper-validation"
    show_timestamp: bool = True


def generate_markdown_report(
    report_path: Path,
    optimized_path: str,
    reference_path: str,
    wirelength_result: WirelengthResult,
    drc_result: DRCComplianceResult,
    routing_result: RoutingFeasibilityResult,
    aggregate_result: AggregateScoreResult,
    config: Optional[ReportConfig] = None
) -> None:
    """
    Generate Markdown validation report.

    Args:
        report_path: Path to output .md file
        optimized_path: Path to optimized PCB file
        reference_path: Path to reference PCB file
        wirelength_result: WirelengthResult from comparison
        drc_result: DRCComplianceResult from comparison
        routing_result: RoutingFeasibilityResult from comparison
        aggregate_result: AggregateScoreResult from metrics
        config: Optional report configuration
    """
    if config is None:
        config = ReportConfig()

    # Generate timestamp
    timestamp = datetime.now().isoformat()

    # Build content
    content = []

    # Title
    content.append(f"# {config.title}\n")
    if config.show_timestamp:
        content.append(f"**Generated:** {timestamp}\n")
    content.append(f"**Author:** {config.author}\n")

    # File paths
    content.append("## Files\n")
    content.append(f"- **Optimized:** `{optimized_path}`\n")
    content.append(f"- **Reference:** `{reference_path}`\n")

    # Overall verdict
    verdict_badge = "**PASS**" if aggregate_result.verdict == "PASS" else "**FAIL**"
    content.append(f"\n## Overall Verdict\n")
    content.append(f"Status: {verdict_badge}\n")

    # Wirelength comparison
    content.append("\n## Wirelength Comparison\n")
    content.append(f"- **Optimized:** {wirelength_result.optimized:.2f} mm\n")
    content.append(f"- **Reference:** {wirelength_result.reference:.2f} mm\n")
    content.append(f"- **Ratio:** {wirelength_result.ratio:.3f}\n")
    content.append(f"- **Verdict:** {wirelength_result.verdict}\n")

    # DRC compliance
    content.append("\n## DRC Compliance\n")
    content.append(f"- **Score:** {drc_result.score:.1f}/{drc_result.max_score:.0f}\n")
    content.append(f"- **Critical Violations:** {drc_result.critical_violations}\n")
    content.append(f"- **Warning Violations:** {drc_result.warning_violations}\n")
    content.append(f"- **Verdict:** {drc_result.verdict}\n")

    # Routing feasibility
    content.append("\n## Routing Feasibility\n")
    content.append(f"- **Total Nets:** {routing_result.total_nets}\n")
    content.append(f"- **Routed Nets:** {routing_result.routed_nets}\n")
    content.append(f"- **Failed Nets:** {routing_result.failed_nets}\n")
    content.append(f"- **Completion Rate:** {routing_result.completion_rate*100:.1f}%\n")
    content.append(f"- **Average Wirelength:** {routing_result.average_wirelength:.2f} mm\n")
    content.append(f"- **Total Vias:** {routing_result.total_vias}\n")
    content.append(f"- **Verdict:** {routing_result.verdict}\n")

    # Aggregate quality score
    content.append("\n## Aggregate Quality Score\n")
    content.append(f"- **Total Score:** {aggregate_result.total_score:.1f}/{aggregate_result.max_score:.0f}\n")
    content.append(f"- **Wirelength Score:** {aggregate_result.wirelength_score:.1f}\n")
    content.append(f"- **DRC Score:** {aggregate_result.drc_score:.1f}\n")
    content.append(f"- **Routing Score:** {aggregate_result.routing_score:.1f}\n")
    content.append(f"- **Weights:** Wirelength {aggregate_result.wirelength_weight:.1f}, "
                f"DRC {aggregate_result.drc_weight:.1f}, Routing {aggregate_result.routing_weight:.1f}\n")
    content.append(f"- **Verdict:** {aggregate_result.verdict}\n")

    # Write to file
    report_content = "".join(content)
    report_path.write_text(report_content, encoding="utf-8")


def generate_html_report(
    report_path: Path,
    optimized_path: str,
    reference_path: str,
    wirelength_result: WirelengthResult,
    drc_result: DRCComplianceResult,
    routing_result: RoutingFeasibilityResult,
    aggregate_result: AggregateScoreResult,
    config: Optional[ReportConfig] = None
) -> None:
    """
    Generate HTML validation report.

    Args:
        report_path: Path to output .html file
        optimized_path: Path to optimized PCB file
        reference_path: Path to reference PCB file
        wirelength_result: WirelengthResult from comparison
        drc_result: DRCComplianceResult from comparison
        routing_result: RoutingFeasibilityResult from comparison
        aggregate_result: AggregateScoreResult from metrics
        config: Optional report configuration
    """
    if config is None:
        config = ReportConfig()

    # Generate timestamp
    timestamp = datetime.now().isoformat()

    # Helper function for verdict color
    def verdict_color(verdict: str) -> str:
        return "#28a745" if verdict == "PASS" else "#dc3545"  # green : red

    # Build HTML
    html_parts = []

    # HTML header
    html_parts.append("<!DOCTYPE html>\n")
    html_parts.append('<html lang="en">\n')
    html_parts.append("<head>\n")
    html_parts.append('  <meta charset="UTF-8">\n')
    html_parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
    html_parts.append(f'  <title>{config.title}</title>\n')

    # CSS styles
    html_parts.append("  <style>\n")
    html_parts.append("    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
                     "max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }\n")
    html_parts.append("    h1 { color: #1a1a1a; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }\n")
    html_parts.append("    h2 { color: #374151; margin-top: 30px; }\n")
    html_parts.append("    .container { background: #f9fafb; border-radius: 8px; padding: 20px; margin-bottom: 20px; }\n")
    html_parts.append("    .verdict-pass { color: #28a745; font-weight: bold; font-size: 1.2em; }\n")
    html_parts.append("    .verdict-fail { color: #dc3545; font-weight: bold; font-size: 1.2em; }\n")
    html_parts.append("    .score { font-size: 1.1em; }\n")
    html_parts.append("    .label { font-weight: 600; color: #6b7280; }\n")
    html_parts.append("    .value { font-family: 'Courier New', monospace; }\n")
    html_parts.append("    ul { list-style: none; padding: 0; }\n")
    html_parts.append("    li { margin-bottom: 8px; }\n")
    html_parts.append("  </style>\n")
    html_parts.append("</head>\n")
    html_parts.append("<body>\n")

    # Title section
    html_parts.append(f"  <h1>{config.title}</h1>\n")
    if config.show_timestamp:
        html_parts.append(f'  <p><span class="label">Generated:</span> <span class="value">{timestamp}</span></p>\n')
        html_parts.append(f'  <p><span class="label">Author:</span> <span class="value">{config.author}</span></p>\n')

    # Files section
    html_parts.append('  <div class="container">\n')
    html_parts.append("    <h2>Files</h2>\n")
    html_parts.append("    <ul>\n")
    html_parts.append(f'      <li><span class="label">Optimized:</span> <span class="value">{optimized_path}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Reference:</span> <span class="value">{reference_path}</span></li>\n')
    html_parts.append("    </ul>\n")
    html_parts.append("  </div>\n")

    # Overall verdict
    verdict_class = "verdict-pass" if aggregate_result.verdict == "PASS" else "verdict-fail"
    html_parts.append('  <div class="container">\n')
    html_parts.append(f"    <h2>Overall Verdict</h2>\n")
    html_parts.append(f'    <p class="{verdict_class}">{aggregate_result.verdict}</p>\n')
    html_parts.append("  </div>\n")

    # Wirelength comparison
    html_parts.append('  <div class="container">\n')
    html_parts.append("    <h2>Wirelength Comparison</h2>\n")
    html_parts.append("    <ul>\n")
    html_parts.append(f'      <li><span class="label">Optimized:</span> <span class="value">{wirelength_result.optimized:.2f} mm</span></li>\n')
    html_parts.append(f'      <li><span class="label">Reference:</span> <span class="value">{wirelength_result.reference:.2f} mm</span></li>\n')
    html_parts.append(f'      <li><span class="label">Ratio:</span> <span class="value">{wirelength_result.ratio:.3f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Verdict:</span> <span class="value">{wirelength_result.verdict}</span></li>\n')
    html_parts.append("    </ul>\n")
    html_parts.append("  </div>\n")

    # DRC compliance
    html_parts.append('  <div class="container">\n')
    html_parts.append("    <h2>DRC Compliance</h2>\n")
    html_parts.append("    <ul>\n")
    html_parts.append(f'      <li><span class="label">Score:</span> <span class="value">{drc_result.score:.1f}/{drc_result.max_score:.0f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Critical Violations:</span> <span class="value">{drc_result.critical_violations}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Warning Violations:</span> <span class="value">{drc_result.warning_violations}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Verdict:</span> <span class="value">{drc_result.verdict}</span></li>\n')
    html_parts.append("    </ul>\n")
    html_parts.append("  </div>\n")

    # Routing feasibility
    html_parts.append('  <div class="container">\n')
    html_parts.append("    <h2>Routing Feasibility</h2>\n")
    html_parts.append("    <ul>\n")
    html_parts.append(f'      <li><span class="label">Total Nets:</span> <span class="value">{routing_result.total_nets}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Routed Nets:</span> <span class="value">{routing_result.routed_nets}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Failed Nets:</span> <span class="value">{routing_result.failed_nets}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Completion Rate:</span> <span class="value">{routing_result.completion_rate*100:.1f}%</span></li>\n')
    html_parts.append(f'      <li><span class="label">Average Wirelength:</span> <span class="value">{routing_result.average_wirelength:.2f} mm</span></li>\n')
    html_parts.append(f'      <li><span class="label">Total Vias:</span> <span class="value">{routing_result.total_vias}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Verdict:</span> <span class="value">{routing_result.verdict}</span></li>\n')
    html_parts.append("    </ul>\n")
    html_parts.append("  </div>\n")

    # Aggregate quality score
    html_parts.append('  <div class="container">\n')
    html_parts.append("    <h2>Aggregate Quality Score</h2>\n")
    html_parts.append("    <ul>\n")
    html_parts.append(f'      <li><span class="label score">Total Score:</span> '
                 f'<span class="value">{aggregate_result.total_score:.1f}/{aggregate_result.max_score:.0f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Wirelength Score:</span> <span class="value">{aggregate_result.wirelength_score:.1f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">DRC Score:</span> <span class="value">{aggregate_result.drc_score:.1f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Routing Score:</span> <span class="value">{aggregate_result.routing_score:.1f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Weights:</span> '
                 f'<span class="value">Wirelength {aggregate_result.wirelength_weight:.1f}, '
                 f'DRC {aggregate_result.drc_weight:.1f}, Routing {aggregate_result.routing_weight:.1f}</span></li>\n')
    html_parts.append(f'      <li><span class="label">Verdict:</span> <span class="value">{aggregate_result.verdict}</span></li>\n')
    html_parts.append("    </ul>\n")
    html_parts.append("  </div>\n")

    # HTML footer
    html_parts.append("</body>\n")
    html_parts.append("</html>\n")

    # Write to file
    html_content = "".join(html_parts)
    report_path.write_text(html_content, encoding="utf-8")
