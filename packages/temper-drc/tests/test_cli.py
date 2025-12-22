"""Tests for CLI commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from temper_drc.cli import cli


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_placement(tmp_path: Path) -> Path:
    """Create a sample placement YAML file."""
    placement_file = tmp_path / "test_placement.yaml"
    placement_file.write_text(
        """
board_width: 100.0
board_height: 100.0
components:
  - ref: U1
    footprint: SOIC-8
    x: 25.0
    y: 50.0
    rotation: 0.0
    layer: F.Cu
    width: 5.0
    height: 4.0
    net_class: Signal
    voltage_domain: 3V3
  - ref: U2
    footprint: SOIC-8
    x: 75.0
    y: 50.0
    rotation: 0.0
    layer: F.Cu
    width: 5.0
    height: 4.0
    net_class: Signal
    voltage_domain: 3V3
nets:
  VCC: [U1, U2]
  GND: [U1, U2]
zones:
  - name: Power
    bounds: [0, 0, 40, 100]
  - name: Digital
    bounds: [40, 0, 100, 100]
net_classes:
  VCC: Power
  GND: Power
voltage_domains:
  VCC: 3V3
  GND: GND
"""
    )
    return placement_file


@pytest.fixture
def sample_constraints(tmp_path: Path) -> Path:
    """Create a sample constraints YAML file."""
    constraints_file = tmp_path / "test_constraints.yaml"
    constraints_file.write_text(
        """
clearances:
  Signal-Signal: 0.2
  Signal-Power: 0.3
  Power-Power: 0.5
hv_clearance_mm: 10.0
creepage_mm: 8.0
isolation_mm: 6.0
courtyard_clearance_mm: 0.25
max_loop_area_mm2: 100.0
noise_sensitive_clearance_mm: 5.0
"""
    )
    return constraints_file


def test_cli_version(runner: CliRunner):
    """Test CLI version command."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help(runner: CliRunner):
    """Test CLI help."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "temper-drc" in result.output
    assert "check" in result.output
    assert "summary" in result.output


def test_list_checks(runner: CliRunner):
    """Test list-checks command."""
    result = runner.invoke(cli, ["list-checks"])
    assert result.exit_code == 0
    assert "DRC" in result.output
    assert "ERC" in result.output
    assert "Safety" in result.output
    assert "EMC" in result.output
    assert "drc_clearance" in result.output


def test_init_placement(runner: CliRunner, tmp_path: Path):
    """Test init-placement command."""
    output_file = tmp_path / "placement.yaml"
    result = runner.invoke(
        cli,
        ["init-placement", str(output_file), "--board-width", "150", "--board-height", "200"],
    )
    assert result.exit_code == 0
    assert output_file.exists()
    assert "150" in output_file.read_text()
    assert "200" in output_file.read_text()


def test_init_constraints(runner: CliRunner, tmp_path: Path):
    """Test init-constraints command."""
    output_file = tmp_path / "constraints.yaml"
    result = runner.invoke(cli, ["init-constraints", str(output_file), "--hv-clearance", "12.0"])
    assert result.exit_code == 0
    assert output_file.exists()
    assert "12.0" in output_file.read_text()


def test_check_text_output(runner: CliRunner, sample_placement: Path, sample_constraints: Path):
    """Test check command with text output."""
    result = runner.invoke(
        cli,
        [
            "check",
            str(sample_placement),
            "-c",
            str(sample_constraints),
            "--format",
            "text",
        ],
    )
    assert result.exit_code == 0
    assert "temper-drc Check Report" in result.output
    assert "Status:" in result.output


def test_check_json_output(runner: CliRunner, sample_placement: Path, sample_constraints: Path):
    """Test check command with JSON output."""
    result = runner.invoke(
        cli,
        [
            "check",
            str(sample_placement),
            "-c",
            str(sample_constraints),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "passed" in data
    assert "total_checks" in data
    assert "checks" in data


def test_check_html_output(
    runner: CliRunner, sample_placement: Path, sample_constraints: Path, tmp_path: Path
):
    """Test check command with HTML output."""
    output_file = tmp_path / "report.html"
    result = runner.invoke(
        cli,
        [
            "check",
            str(sample_placement),
            "-c",
            str(sample_constraints),
            "--format",
            "html",
            "-o",
            str(output_file),
        ],
    )
    assert result.exit_code == 0
    assert output_file.exists()
    html_content = output_file.read_text()
    assert "<!DOCTYPE html>" in html_content
    assert "temper-drc Check Report" in html_content


def test_check_category_filter(runner: CliRunner, sample_placement: Path, sample_constraints: Path):
    """Test check command with category filtering."""
    result = runner.invoke(
        cli,
        [
            "check",
            str(sample_placement),
            "-c",
            str(sample_constraints),
            "--category",
            "drc",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    # Should only have DRC checks
    check_names = [c["name"] for c in data["checks"]]
    assert all(name.startswith("drc_") for name in check_names)


def test_check_verbose(runner: CliRunner, sample_placement: Path, sample_constraints: Path):
    """Test check command with verbose output."""
    result = runner.invoke(
        cli,
        [
            "check",
            str(sample_placement),
            "-c",
            str(sample_constraints),
            "--verbose",
        ],
    )
    assert result.exit_code == 0
    # Verbose output goes to stderr
    assert "Loading placement" in result.output or "Running" in result.output


def test_summary_command(runner: CliRunner, sample_placement: Path, sample_constraints: Path):
    """Test summary command."""
    result = runner.invoke(
        cli,
        [
            "summary",
            str(sample_placement),
            "-c",
            str(sample_constraints),
        ],
    )
    assert result.exit_code == 0
    assert "temper-drc Summary" in result.output
    assert "Components:" in result.output
    assert "Check Summary:" in result.output


def test_check_missing_file(runner: CliRunner, sample_constraints: Path):
    """Test check command with missing placement file."""
    result = runner.invoke(
        cli,
        [
            "check",
            "nonexistent.yaml",
            "-c",
            str(sample_constraints),
        ],
    )
    assert result.exit_code != 0


def test_check_missing_constraints(runner: CliRunner, sample_placement: Path):
    """Test check command with missing constraints file."""
    result = runner.invoke(
        cli,
        [
            "check",
            str(sample_placement),
            "-c",
            "nonexistent.yaml",
        ],
    )
    assert result.exit_code != 0
