#!/usr/bin/env python3.11
"""
Unit tests for placement_quality_report.py

Run with: python3.11 -m pytest scripts/test_placement_quality_report.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "placement_quality_report.py"
TEST_PCB = REPO_ROOT / "kicad-tutorials-a/07_Transistor_Switch/07_Transistor_Switch.kicad_pcb"


def test_script_exists():
    """Verify script exists and is executable."""
    assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"
    assert SCRIPT_PATH.stat().st_mode & 0o111, "Script is not executable"


def test_help_flag():
    """Test that --help flag works."""
    result = subprocess.run(
        ["python3.11", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Unified placement quality report" in result.stdout
    assert "--pcb" in result.stdout
    assert "--json" in result.stdout


def test_missing_pcb_file():
    """Test error handling for missing PCB file."""
    result = subprocess.run(
        ["python3.11", str(SCRIPT_PATH), "--pcb", "nonexistent.kicad_pcb"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


@pytest.mark.skipif(not TEST_PCB.exists(), reason="Test PCB not found")
def test_basic_report():
    """Test basic report generation (human-readable)."""
    result = subprocess.run(
        ["python3.11", str(SCRIPT_PATH), "--pcb", str(TEST_PCB)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Should pass or fail gracefully
    assert result.returncode in (0, 1), f"Unexpected return code: {result.returncode}"

    # Check for key sections in output
    assert "Placement Quality Report" in result.stdout
    assert "Placement Metrics:" in result.stdout
    assert "DRC Metrics:" in result.stdout
    assert "Overall Score:" in result.stdout


@pytest.mark.skipif(not TEST_PCB.exists(), reason="Test PCB not found")
def test_json_output():
    """Test JSON output format."""
    result = subprocess.run(
        ["python3.11", str(SCRIPT_PATH), "--pcb", str(TEST_PCB), "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Should produce valid JSON
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON output: {e}\n{result.stdout}")

    # Check structure
    assert "input_file" in data
    assert "timestamp" in data
    assert "placement_metrics" in data
    assert "drc_metrics" in data
    assert "quality_score" in data
    assert "passed" in data

    # Check placement metrics
    pm = data["placement_metrics"]
    assert "hpwl_mm" in pm
    assert "thermal_score" in pm
    assert "overall_placement_score" in pm

    # Check DRC metrics
    drc = data["drc_metrics"]
    assert "violations" in drc
    assert "errors" in drc
    assert "warnings" in drc
    assert "drc_available" in drc


@pytest.mark.skipif(not TEST_PCB.exists(), reason="Test PCB not found")
def test_routing_flag():
    """Test --route flag (adds routing metrics)."""
    result = subprocess.run(
        ["python3.11", str(SCRIPT_PATH), "--pcb", str(TEST_PCB), "--json", "--route"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Should produce valid JSON with routing metrics
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON output: {e}\n{result.stdout}")

    # Check routing metrics present
    assert "routing_metrics" in data
    if data["routing_metrics"]:  # May be None if routing unavailable
        rm = data["routing_metrics"]
        assert "completion_pct" in rm
        assert "total_congestion" in rm
        assert "routing_available" in rm


@pytest.mark.skipif(not TEST_PCB.exists(), reason="Test PCB not found")
def test_output_file():
    """Test --output flag writes to file."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        output_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "python3.11",
                str(SCRIPT_PATH),
                "--pcb",
                str(TEST_PCB),
                "--json",
                "--output",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should succeed
        assert result.returncode in (0, 1)

        # File should exist and contain valid JSON
        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)

        assert "quality_score" in data

    finally:
        # Cleanup
        if output_path.exists():
            output_path.unlink()


if __name__ == "__main__":
    # Run tests
    sys.exit(pytest.main([__file__, "-v"]))
