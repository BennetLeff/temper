"""Report generator for validation results."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Import result types from other modules
from temper_validation.comparison.wirelength import WirelengthResult
from temper_validation.comparison.drc_compliance import DRCComplianceResult
from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult
from temper_validation.metrics.quality_score import AggregateScoreResult
from temper_validation.reporting.generator import ReportGenerator

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

    generator = ReportGenerator()
    generator.generate(
        "report.md.j2",
        report_path,
        config=config,
        timestamp=_get_timestamp(),
        optimized_path=optimized_path,
        reference_path=reference_path,
        wirelength_result=wirelength_result,
        drc_result=drc_result,
        routing_result=routing_result,
        aggregate_result=aggregate_result,
    )


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

    generator = ReportGenerator()
    generator.generate(
        "report.html.j2",
        report_path,
        config=config,
        timestamp=_get_timestamp(),
        optimized_path=optimized_path,
        reference_path=reference_path,
        wirelength_result=wirelength_result,
        drc_result=drc_result,
        routing_result=routing_result,
        aggregate_result=aggregate_result,
    )


def _get_timestamp() -> str:
    from datetime import datetime
    return datetime.now().isoformat()