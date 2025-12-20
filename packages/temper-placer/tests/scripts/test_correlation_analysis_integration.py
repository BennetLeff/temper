"""
Integration test for correlation_analysis.py script.

Tests the script with a minimal fixture to ensure it runs end-to-end.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def test_pcb_path():
    """Path to a simple test PCB."""
    # Use one of the existing test fixtures
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "drc_test_placements" / "perfect.kicad_pcb"
    )
    if not fixture_path.exists():
        pytest.skip(f"Test fixture not found: {fixture_path}")
    return fixture_path


@pytest.fixture
def script_path():
    """Path to correlation_analysis.py script."""
    script = (
        Path(__file__).parent.parent.parent.parent.parent / "scripts" / "correlation_analysis.py"
    )
    if not script.exists():
        pytest.skip(f"Script not found: {script}")
    return script


def test_script_help(script_path):
    """Test that script shows help without errors."""
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"], capture_output=True, text=True, timeout=5
    )

    assert result.returncode == 0
    assert "correlation analysis" in result.stdout.lower()
    assert "--pcb" in result.stdout
    assert "--samples" in result.stdout
    assert "--quick" in result.stdout


def test_script_missing_pcb(script_path):
    """Test that script errors gracefully when PCB is missing."""
    result = subprocess.run(
        [sys.executable, str(script_path), "--pcb", "nonexistent.kicad_pcb", "--samples", "3"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert "not found" in result.stderr.lower()


def test_script_too_few_samples(script_path, test_pcb_path):
    """Test that script errors when samples < 3."""
    result = subprocess.run(
        [sys.executable, str(script_path), "--pcb", str(test_pcb_path), "--samples", "1"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert "at least 3 samples" in result.stderr.lower()


@pytest.mark.slow
def test_script_quick_mode_minimal(script_path, test_pcb_path, tmp_path):
    """
    Test script in quick mode with minimal samples (integration test).

    This is marked slow because it runs actual optimizations.
    """
    output_file = tmp_path / "correlation_report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--pcb",
            str(test_pcb_path),
            "--samples",
            "3",  # Minimal for correlation
            "--quick",  # Skip routing
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutes timeout
    )

    # Check that script completed
    assert result.returncode == 0, f"Script failed: {result.stderr}"

    # Check that output file was created
    assert output_file.exists(), "Output file not created"

    # Load and validate JSON structure
    with open(output_file) as f:
        report = json.load(f)

    # Validate required fields
    assert "pcb" in report
    assert "n_samples" in report
    assert "routing_mode" in report
    assert report["routing_mode"] == "quick"
    assert "correlations" in report
    assert "recommendations" in report
    assert "statistics" in report

    # Validate statistics
    stats = report["statistics"]
    assert "mean_completion_pct" in stats
    assert "std_completion_pct" in stats
    assert "failed_routes" in stats

    print(f"Report generated successfully with {len(report['correlations'])} loss correlations")
    print(f"Mean completion: {stats['mean_completion_pct']:.1f}%")
    print(f"Recommendations: {len(report['recommendations'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not slow"])
