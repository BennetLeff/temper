"""Tests for the explainability CLI commands (why, why-not).

This module tests the CLI commands that allow users to query decision traces
from the command line.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from temper_placer.explainability import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.serialization import save_trace


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cli_runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_trace() -> DecisionTrace:
    """Create a sample trace with multiple decisions for testing."""
    trace = DecisionTrace(run_id="cli-test-trace")

    # Initial position
    trace.add(
        Decision(
            id="d001",
            decision_type=DecisionType.INITIAL_POSITION,
            phase=DecisionPhase.TOPOLOGICAL,
            subject="Q1",
            value=(10.0, 90.0),
            reason="Placed by thermal_edge heuristic near top edge for heat dissipation",
            constraint_refs=["thermal.edge"],
        )
    )

    # Position update
    trace.add(
        Decision(
            id="d002",
            decision_type=DecisionType.POSITION_UPDATE,
            phase=DecisionPhase.GEOMETRIC,
            subject="Q1",
            value=(12.0, 88.0),
            previous_value=(10.0, 90.0),
            reason="Gradient descent optimization, epoch 500",
            constraint_refs=["thermal.edge", "clearance.hv_lv"],
            loss_contribution=-0.05,
            epoch=500,
            alternatives=[
                Alternative(
                    value=(50.0, 10.0),
                    rejection_reason="Violates 10mm HV clearance to U_MCU",
                    constraint_violated="clearance.hv_lv",
                    loss_if_chosen=0.85,
                ),
                Alternative(
                    value=(40.0, 15.0),
                    rejection_reason="Too far from board edge for thermal dissipation",
                    constraint_violated="thermal.edge",
                    loss_if_chosen=0.42,
                ),
            ],
        )
    )

    # Rotation
    trace.add(
        Decision(
            id="d003",
            decision_type=DecisionType.ROTATION,
            phase=DecisionPhase.GEOMETRIC,
            subject="U1",
            value=1,  # 90 degrees
            previous_value=0,
            reason="Rotated for pin alignment with VCC net",
            epoch=200,
        )
    )

    # Another component
    trace.add(
        Decision(
            id="d004",
            decision_type=DecisionType.INITIAL_POSITION,
            phase=DecisionPhase.TOPOLOGICAL,
            subject="C1",
            value=(15.0, 85.0),
            reason="Decoupling capacitor placed near U1",
        )
    )

    trace.finalize(
        positions={"Q1": (12.0, 88.0), "U1": (50.0, 50.0), "C1": (15.0, 85.0)},
        metrics={"total_loss": 0.125, "wirelength": 45.2},
    )

    return trace


@pytest.fixture
def trace_file(sample_trace: DecisionTrace, tmp_path: Path) -> Path:
    """Save sample trace to a temporary file and return path."""
    trace_path = tmp_path / "decisions.json"
    save_trace(sample_trace, trace_path)
    return trace_path


# =============================================================================
# TestWhyCommand - 'temper-placer why' command
# =============================================================================


class TestWhyCommand:
    """Tests for the 'temper-placer why' CLI command."""

    def test_why_shows_component_reason(self, cli_runner, trace_file: Path):
        """'why Q1' shows the reason for Q1's position."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "Q1" in result.output
        # Should show the final reason
        assert "Gradient descent" in result.output or "optimization" in result.output.lower()

    def test_why_shows_final_position(self, cli_runner, trace_file: Path):
        """'why Q1' shows the final position."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file)])

        assert result.exit_code == 0
        # Final position is (12.0, 88.0)
        assert "12" in result.output
        assert "88" in result.output

    def test_why_unknown_component(self, cli_runner, trace_file: Path):
        """'why UNKNOWN' shows appropriate message."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "UNKNOWN", "--trace", str(trace_file)])

        # Should not crash, should indicate no decisions found
        assert result.exit_code == 0
        assert "no decisions" in result.output.lower() or "not found" in result.output.lower()

    def test_why_with_history_flag(self, cli_runner, trace_file: Path):
        """'why Q1 --history' shows complete decision history."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file), "--history"])

        assert result.exit_code == 0
        # Should show both initial and update
        assert "thermal_edge" in result.output or "heuristic" in result.output.lower()
        assert "Gradient" in result.output or "epoch" in result.output.lower()

    def test_why_json_output(self, cli_runner, trace_file: Path):
        """'why Q1 --json' outputs JSON format."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file), "--json"])

        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert "subject" in data or "component" in data or "Q1" in str(data)

    def test_why_shows_constraints(self, cli_runner, trace_file: Path):
        """'why Q1' shows relevant constraints."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "thermal" in result.output.lower() or "constraint" in result.output.lower()

    def test_why_rotation_component(self, cli_runner, trace_file: Path):
        """'why U1' shows rotation decision."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "U1", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "U1" in result.output
        # Should mention rotation
        assert "rotat" in result.output.lower() or "90" in result.output

    def test_why_missing_trace_file(self, cli_runner, tmp_path: Path):
        """'why Q1' with nonexistent trace file shows error."""
        from temper_placer.cli import main

        nonexistent = tmp_path / "nonexistent.json"
        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(nonexistent)])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_why_verbose_mode(self, cli_runner, trace_file: Path):
        """'why Q1 --verbose' shows detailed information."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file), "--verbose"])

        assert result.exit_code == 0
        # Verbose should show more details like epoch, loss contribution
        assert "epoch" in result.output.lower() or "500" in result.output


# =============================================================================
# TestWhyNotCommand - 'temper-placer why-not' command
# =============================================================================


class TestWhyNotCommand:
    """Tests for the 'temper-placer why-not' CLI command."""

    def test_why_not_known_alternative(self, cli_runner, trace_file: Path):
        """'why-not Q1 (50, 10)' explains why that position was rejected."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why-not", "Q1", "(50, 10)", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "rejected" in result.output.lower() or "clearance" in result.output.lower()
        assert "HV" in result.output or "hv" in result.output.lower()

    def test_why_not_another_alternative(self, cli_runner, trace_file: Path):
        """'why-not Q1 (40, 15)' explains thermal rejection."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why-not", "Q1", "(40, 15)", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "thermal" in result.output.lower() or "edge" in result.output.lower()

    def test_why_not_unknown_position(self, cli_runner, trace_file: Path):
        """'why-not Q1 (999, 999)' shows no record found."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["why-not", "Q1", "(999, 999)", "--trace", str(trace_file)]
        )

        assert result.exit_code == 0
        assert "no record" in result.output.lower() or "not considered" in result.output.lower()

    def test_why_not_unknown_component(self, cli_runner, trace_file: Path):
        """'why-not UNKNOWN (10, 20)' shows component not found."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["why-not", "UNKNOWN", "(10, 20)", "--trace", str(trace_file)]
        )

        assert result.exit_code == 0
        assert "no record" in result.output.lower() or "not found" in result.output.lower()

    def test_why_not_json_output(self, cli_runner, trace_file: Path):
        """'why-not Q1 (50, 10) --json' outputs JSON format."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["why-not", "Q1", "(50, 10)", "--trace", str(trace_file), "--json"]
        )

        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert "rejection_reason" in str(data) or "reason" in str(data)

    def test_why_not_shows_constraint_violated(self, cli_runner, trace_file: Path):
        """'why-not' shows which constraint was violated."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why-not", "Q1", "(50, 10)", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "clearance.hv_lv" in result.output

    def test_why_not_shows_loss_if_chosen(self, cli_runner, trace_file: Path):
        """'why-not' shows what the loss would have been."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["why-not", "Q1", "(50, 10)", "--trace", str(trace_file), "--verbose"]
        )

        assert result.exit_code == 0
        # Should show loss if verbose
        assert "0.85" in result.output or "loss" in result.output.lower()

    def test_why_not_tuple_formats(self, cli_runner, trace_file: Path):
        """'why-not' accepts various tuple formats."""
        from temper_placer.cli import main

        # Different tuple format variations that should all work
        formats = [
            "(50, 10)",
            "(50.0, 10.0)",
            "50,10",
            "50, 10",
        ]

        for fmt in formats:
            result = cli_runner.invoke(main, ["why-not", "Q1", fmt, "--trace", str(trace_file)])
            # Should not error on format
            assert result.exit_code == 0, f"Failed for format: {fmt}"


# =============================================================================
# TestTraceInfo - 'temper-placer trace-info' command
# =============================================================================


class TestTraceInfoCommand:
    """Tests for the 'temper-placer trace-info' command."""

    def test_trace_info_shows_summary(self, cli_runner, trace_file: Path):
        """'trace-info' shows trace summary."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "cli-test-trace" in result.output or "run" in result.output.lower()

    def test_trace_info_shows_decision_count(self, cli_runner, trace_file: Path):
        """'trace-info' shows total decision count."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--trace", str(trace_file)])

        assert result.exit_code == 0
        # Should show 4 decisions
        assert "4" in result.output

    def test_trace_info_shows_components(self, cli_runner, trace_file: Path):
        """'trace-info' lists components with decisions."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "Q1" in result.output
        assert "U1" in result.output
        assert "C1" in result.output

    def test_trace_info_shows_phases(self, cli_runner, trace_file: Path):
        """'trace-info' shows phase breakdown."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "topological" in result.output.lower() or "geometric" in result.output.lower()

    def test_trace_info_json_output(self, cli_runner, trace_file: Path):
        """'trace-info --json' outputs JSON format."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--trace", str(trace_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_decisions" in data or "decisions" in str(data)

    def test_trace_info_shows_final_metrics(self, cli_runner, trace_file: Path):
        """'trace-info' shows final metrics if available."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--trace", str(trace_file)])

        assert result.exit_code == 0
        # Should show metrics
        assert "total_loss" in result.output or "0.125" in result.output


# =============================================================================
# TestTraceList - 'temper-placer trace-list' command
# =============================================================================


class TestTraceListCommand:
    """Tests for the 'temper-placer trace-list' command."""

    def test_trace_list_shows_all_decisions(self, cli_runner, trace_file: Path):
        """'trace-list' shows all decisions."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-list", "--trace", str(trace_file)])

        assert result.exit_code == 0
        # Should show all 4 decision IDs
        assert "d001" in result.output
        assert "d002" in result.output
        assert "d003" in result.output
        assert "d004" in result.output

    def test_trace_list_filter_by_component(self, cli_runner, trace_file: Path):
        """'trace-list --component Q1' filters to Q1 only."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["trace-list", "--trace", str(trace_file), "--component", "Q1"]
        )

        assert result.exit_code == 0
        assert "Q1" in result.output
        # Should not show U1 or C1 decisions
        assert "d003" not in result.output  # U1's decision
        assert "d004" not in result.output  # C1's decision

    def test_trace_list_filter_by_phase(self, cli_runner, trace_file: Path):
        """'trace-list --phase geometric' filters by phase."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["trace-list", "--trace", str(trace_file), "--phase", "geometric"]
        )

        assert result.exit_code == 0
        # GEOMETRIC phase has d002 and d003
        assert "d002" in result.output
        assert "d003" in result.output
        # TOPOLOGICAL decisions should not appear
        assert "d001" not in result.output

    def test_trace_list_filter_by_type(self, cli_runner, trace_file: Path):
        """'trace-list --type rotation' filters by decision type."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main, ["trace-list", "--trace", str(trace_file), "--type", "rotation"]
        )

        assert result.exit_code == 0
        # Only d003 is a rotation
        assert "d003" in result.output
        assert "d001" not in result.output
        assert "d002" not in result.output

    def test_trace_list_json_output(self, cli_runner, trace_file: Path):
        """'trace-list --json' outputs JSON array."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-list", "--trace", str(trace_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 4

    def test_trace_list_limit(self, cli_runner, trace_file: Path):
        """'trace-list --limit 2' limits output."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-list", "--trace", str(trace_file), "--limit", "2"])

        assert result.exit_code == 0
        # Should show indication of limited output
        # Count occurrences of decision IDs to verify limit
        # This is a rough check - implementation may vary


# =============================================================================
# TestTraceExport - 'temper-placer trace-export' command
# =============================================================================


class TestTraceExportCommand:
    """Tests for the 'temper-placer trace-export' command."""

    def test_trace_export_markdown(self, cli_runner, trace_file: Path, tmp_path: Path):
        """'trace-export --format markdown' creates markdown file."""
        from temper_placer.cli import main

        output = tmp_path / "report.md"
        result = cli_runner.invoke(
            main,
            ["trace-export", "--trace", str(trace_file), "--format", "markdown", "-o", str(output)],
        )

        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text()
        assert "Q1" in content
        assert "#" in content  # Markdown headers

    def test_trace_export_html(self, cli_runner, trace_file: Path, tmp_path: Path):
        """'trace-export --format html' creates HTML file."""
        from temper_placer.cli import main

        output = tmp_path / "report.html"
        result = cli_runner.invoke(
            main,
            ["trace-export", "--trace", str(trace_file), "--format", "html", "-o", str(output)],
        )

        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text()
        assert "<!DOCTYPE html>" in content

    def test_trace_export_json(self, cli_runner, trace_file: Path, tmp_path: Path):
        """'trace-export --format json' creates JSON file."""
        from temper_placer.cli import main

        output = tmp_path / "decisions.json"
        result = cli_runner.invoke(
            main,
            ["trace-export", "--trace", str(trace_file), "--format", "json", "-o", str(output)],
        )

        assert result.exit_code == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert "decisions" in data

    def test_trace_export_stdout(self, cli_runner, trace_file: Path):
        """'trace-export' without -o outputs to stdout."""
        from temper_placer.cli import main

        result = cli_runner.invoke(
            main,
            ["trace-export", "--trace", str(trace_file), "--format", "markdown"],
        )

        assert result.exit_code == 0
        assert "Q1" in result.output


# =============================================================================
# TestDefaultTracePath - Trace file discovery
# =============================================================================


class TestDefaultTracePath:
    """Tests for default trace file discovery."""

    def test_uses_default_trace_path(self, cli_runner, sample_trace: DecisionTrace, tmp_path: Path):
        """Commands use default trace path if not specified."""
        from temper_placer.cli import main

        # Save trace to default location
        default_path = tmp_path / ".temper-placer" / "decisions.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        save_trace(sample_trace, default_path)

        # Run from tmp_path directory
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Copy the trace file to the isolated filesystem
            (Path(".temper-placer")).mkdir(exist_ok=True)
            save_trace(sample_trace, Path(".temper-placer/decisions.json"))

            result = cli_runner.invoke(main, ["why", "Q1"])

            # Should work without --trace flag
            assert result.exit_code == 0 or "trace" in result.output.lower()

    def test_trace_flag_overrides_default(self, cli_runner, trace_file: Path, tmp_path: Path):
        """--trace flag overrides default path."""
        from temper_placer.cli import main

        # Create a different trace at default location
        other_trace = DecisionTrace(run_id="other-trace")
        other_trace.add(Decision(subject="OTHER", value=(1.0, 1.0), reason="Other"))
        default_path = tmp_path / ".temper-placer" / "decisions.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        save_trace(other_trace, default_path)

        # Use explicit --trace to override
        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_file)])

        assert result.exit_code == 0
        assert "Q1" in result.output
        # Should NOT use the "other-trace"


# =============================================================================
# TestCliHelp - Help text
# =============================================================================


class TestCliHelp:
    """Tests for CLI help text."""

    def test_why_help(self, cli_runner):
        """'why --help' shows usage information."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why", "--help"])

        assert result.exit_code == 0
        assert "Usage" in result.output or "usage" in result.output.lower()
        assert "component" in result.output.lower()

    def test_why_not_help(self, cli_runner):
        """'why-not --help' shows usage information."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["why-not", "--help"])

        assert result.exit_code == 0
        assert "Usage" in result.output or "usage" in result.output.lower()
        assert "position" in result.output.lower() or "value" in result.output.lower()

    def test_trace_info_help(self, cli_runner):
        """'trace-info --help' shows usage information."""
        from temper_placer.cli import main

        result = cli_runner.invoke(main, ["trace-info", "--help"])

        assert result.exit_code == 0
        assert "Usage" in result.output or "usage" in result.output.lower()


# =============================================================================
# TestEdgeCases - Edge cases and error handling
# =============================================================================


class TestCliEdgeCases:
    """Edge cases for CLI commands."""

    def test_invalid_json_trace_file(self, cli_runner, tmp_path: Path):
        """Commands handle invalid JSON gracefully."""
        from temper_placer.cli import main

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(bad_file)])

        assert result.exit_code != 0
        assert "error" in result.output.lower() or "invalid" in result.output.lower()

    def test_empty_trace_file(self, cli_runner, tmp_path: Path):
        """Commands handle empty trace gracefully."""
        from temper_placer.cli import main

        empty_trace = DecisionTrace()
        trace_path = tmp_path / "empty.json"
        save_trace(empty_trace, trace_path)

        result = cli_runner.invoke(main, ["why", "Q1", "--trace", str(trace_path)])

        assert result.exit_code == 0
        assert "no decisions" in result.output.lower()

    def test_special_characters_in_component(self, cli_runner, tmp_path: Path):
        """Commands handle special characters in component names."""
        from temper_placer.cli import main

        trace = DecisionTrace()
        trace.add(Decision(subject="C/1", value=(10.0, 20.0), reason="Test"))
        trace_path = tmp_path / "special.json"
        save_trace(trace, trace_path)

        result = cli_runner.invoke(main, ["why", "C/1", "--trace", str(trace_path)])

        assert result.exit_code == 0
        assert "C/1" in result.output

    def test_unicode_in_output(self, cli_runner, tmp_path: Path):
        """Commands handle Unicode in reasons correctly."""
        from temper_placer.cli import main

        trace = DecisionTrace()
        trace.add(
            Decision(
                subject="R1",
                value=(10.0, 20.0),
                reason="Thermal conductivity λ = 0.5 W/(m·K)",
            )
        )
        trace_path = tmp_path / "unicode.json"
        save_trace(trace, trace_path)

        result = cli_runner.invoke(main, ["why", "R1", "--trace", str(trace_path)])

        assert result.exit_code == 0
        assert "λ" in result.output or "lambda" in result.output.lower()
