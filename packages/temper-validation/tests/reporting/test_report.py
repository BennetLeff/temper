"""Tests for report generator module."""

import pytest
from dataclasses import dataclass
from pathlib import Path
import tempfile
import os

# Import real data structures from implementation
from temper_validation.comparison.wirelength import WirelengthResult
from temper_validation.comparison.drc_compliance import DRCComplianceResult
from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult
from temper_validation.metrics.quality_score import AggregateScoreResult


def test_markdown_report_structure():
    """Markdown report contains all required sections."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=95.0, max_score=100.0, critical_violations=0, warning_violations=1, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=95.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=95.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_markdown_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        # Read generated report
        with open(report_path, "r") as f:
            content = f.read()

        # Check required sections
        assert "# Placement Validation Report" in content, "Report should have title"

        assert "## Wirelength Comparison" in content, "Report should have wirelength section"

        assert "## DRC Compliance" in content, "Report should have DRC section"

        assert "## Routing Feasibility" in content, "Report should have routing section"

        assert "## Aggregate Quality Score" in content, "Report should have aggregate score section"

        assert "**PASS**" in content or "**FAIL**" in content, "Report should have verdict"

        # Clean up
        os.unlink(report_path)


def test_markdown_report_includes_verdict():
    """Markdown report includes overall PASS/FAIL verdict."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=75.0, max_score=100.0, critical_violations=1, warning_violations=2, verdict="FAIL"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=8,
        failed_nets=2,
        completion_rate=0.8,
        average_wirelength=60.0,
        total_vias=5,
        verdict="FAIL",
    )

    aggregate_result = AggregateScoreResult(
        total_score=82.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=75.0,
        routing_score=80.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_markdown_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Should have overall verdict from aggregate score
        assert "## Overall Verdict: **PASS**" in content, (
            "Report should include overall PASS verdict"
        )

        os.unlink(report_path)


def test_markdown_report_includes_score_breakdown():
    """Markdown report includes individual metric scores."""
    wirelength_result = WirelengthResult(
        optimized=90.0, reference=100.0, ratio=0.9, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=80.0, max_score=100.0, critical_violations=1, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=90.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=80.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_markdown_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Check score values are present
        assert "Wirelength Score:" in content, "Report should include wirelength score"

        assert "DRC Score:" in content, "Report should include DRC score"

        assert "Routing Score:" in content, "Report should include routing score"

        assert "Aggregate Score:" in content, "Report should include aggregate score"

        os.unlink(report_path)


def test_html_report_structure():
    """HTML report contains all required elements."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=95.0, max_score=100.0, critical_violations=0, warning_violations=1, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=95.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=95.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_html_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
        report_path = Path(f.name)
        generate_html_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Check HTML structure
        assert "<!DOCTYPE html>" in content.lower(), "Report should be valid HTML"

        assert "<head>" in content, "Report should have head section"

        assert "<body>" in content, "Report should have body section"

        assert "Placement Validation Report" in content, "Report should have title"

        # Check CSS styling
        assert "style" in content or "<link" in content.lower(), "Report should have styling"

        os.unlink(report_path)


def test_html_report_pass_fail_styling():
    """HTML report uses color coding for PASS/FAIL."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=75.0, max_score=100.0, critical_violations=1, warning_violations=2, verdict="FAIL"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=82.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=75.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_html_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
        report_path = Path(f.name)
        generate_html_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Check for color coding (green for PASS, red for FAIL)
        assert "green" in content.lower() or "#00ff00" in content.lower(), (
            "Report should use green color for PASS"
        )

        assert "red" in content.lower() or "#ff0000" in content.lower(), (
            "Report should use red color for FAIL"
        )

        os.unlink(report_path)


def test_report_includes_file_paths():
    """Reports include source file paths."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=100.0, max_score=100.0, critical_violations=0, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=100.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=100.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_markdown_report, generate_html_report

    # Test Markdown report
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="test_optimized.kicad_pcb",
            reference_path="test_reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        assert "test_optimized.kicad_pcb" in content, "Report should include optimized path"

        assert "test_reference.kicad_pcb" in content, "Report should include reference path"

        os.unlink(report_path)

    # Test HTML report
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
        report_path = Path(f.name)
        generate_html_report(
            report_path=report_path,
            optimized_path="test_optimized.kicad_pcb",
            reference_path="test_reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        assert "test_optimized.kicad_pcb" in content, "HTML report should include optimized path"

        assert "test_reference.kicad_pcb" in content, "HTML report should include reference path"

        os.unlink(report_path)


def test_report_timestamp():
    """Reports include generation timestamp."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=100.0, max_score=100.0, critical_violations=0, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=100.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=100.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_markdown_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Should contain date
        assert any(keyword in content for keyword in ["20", "202", "2024", "2025"]), (
            "Report should include date"
        )

        os.unlink(report_path)
