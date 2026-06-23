"""Tests for golden CLI commands — U2/U5."""
import pytest
from click.testing import CliRunner

from temper_placer.cli import main


def test_golden_group_help():
    runner = CliRunner()
    result = runner.invoke(main, ["golden", "--help"])
    assert result.exit_code == 0
    assert "generate" in result.output
    assert "check" in result.output
    assert "regenerate" in result.output


def test_golden_generate_help():
    runner = CliRunner()
    result = runner.invoke(main, ["golden", "generate", "--help"])
    assert result.exit_code == 0
    assert "--stage" in result.output
    assert "--board" in result.output
    assert "--all-stages" in result.output
    assert "--all-boards" in result.output


def test_golden_check_help():
    runner = CliRunner()
    result = runner.invoke(main, ["golden", "check", "--help"])
    assert result.exit_code == 0
    assert "--stage" in result.output
    assert "--board" in result.output
    assert "--json" in result.output
    assert "--verbose" in result.output
    assert "--ci" in result.output


def test_golden_regenerate_help():
    runner = CliRunner()
    result = runner.invoke(main, ["golden", "regenerate", "--help"])
    assert result.exit_code == 0
    assert "--stage" in result.output
    assert "--board" in result.output
    assert "--force" in result.output


def test_golden_check_no_manifest():
    """check without manifest should exit 0 with informational message."""
    runner = CliRunner()
    result = runner.invoke(main, ["golden", "check"], env={"OP_ENV": "test"})
    assert result.exit_code == 0
    assert "No fixtures to check" in result.output


def test_golden_check_json_no_manifest():
    runner = CliRunner()
    result = runner.invoke(main, ["golden", "check", "--json"], env={"OP_ENV": "test"})
    assert result.exit_code == 0
    assert result.output.strip() == "[]"


def test_golden_subcommand_registered():
    assert "golden" in main.commands
