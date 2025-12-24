"""Tests for markdown report generation."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.markdown_report import (
    render_component_report,
    render_markdown_report,
    save_markdown_report,
)


class TestRenderMarkdownReport:
    """Tests for the main render_markdown_report function."""

    def test_empty_trace(self):
        """Test rendering an empty trace."""
        trace = DecisionTrace(run_id="empty-test")
        report = render_markdown_report(trace)

        assert "# Placement Decision Report" in report
        assert "empty-test" in report
        assert "Total Decisions**: 0" in report

    def test_basic_trace(self):
        """Test rendering a trace with basic decisions."""
        trace = DecisionTrace(run_id="basic-test")
        trace.add(
            Decision(
                subject="Q1",
                value=(45.0, 12.0),
                reason="Thermal edge placement",
                decision_type=DecisionType.INITIAL_POSITION,
                phase=DecisionPhase.GEOMETRIC,
            )
        )
        trace.add(
            Decision(
                subject="Q2",
                value=(30.0, 40.0),
                reason="Adjacent to Q1",
                decision_type=DecisionType.INITIAL_POSITION,
                phase=DecisionPhase.GEOMETRIC,
            )
        )

        report = render_markdown_report(trace)

        # Check header
        assert "# Placement Decision Report" in report
        assert "basic-test" in report
        assert "Components**: 2" in report
        assert "Total Decisions**: 2" in report

        # Check components are listed
        assert "### Q1" in report
        assert "### Q2" in report

        # Check decisions are shown
        assert "Thermal edge placement" in report
        assert "Adjacent to Q1" in report

    def test_with_metrics(self):
        """Test rendering with final metrics."""
        trace = DecisionTrace(run_id="metrics-test")
        trace.final_metrics = {
            "total_loss": 0.0234,
            "overlap": 0.0,
            "wirelength": 1234.5,
        }

        report = render_markdown_report(trace)

        assert "## Summary Metrics" in report
        assert "total_loss" in report
        assert "0.0234" in report
        assert "wirelength" in report

    def test_with_final_positions(self):
        """Test rendering with final positions."""
        trace = DecisionTrace(run_id="pos-test")
        trace.final_positions = {
            "Q1": (45.0, 12.0),
            "Q2": (30.0, 40.0),
        }

        report = render_markdown_report(trace, include_positions=True)

        assert "## Final Positions" in report
        assert "| Q1 |" in report
        assert "45.00" in report
        assert "12.00" in report

    def test_with_config_snapshot(self):
        """Test rendering with config snapshot."""
        trace = DecisionTrace(run_id="config-test")
        trace.config_snapshot = {
            "epochs": 8000,
            "learning_rate": 0.01,
        }

        report = render_markdown_report(trace, include_config=True)

        assert "## Configuration" in report
        assert "epochs: 8000" in report
        assert "learning_rate: 0.01" in report

    def test_exclude_config(self):
        """Test excluding config from report."""
        trace = DecisionTrace(run_id="no-config")
        trace.config_snapshot = {"epochs": 8000}

        report = render_markdown_report(trace, include_config=False)

        assert "## Configuration" not in report

    def test_exclude_positions(self):
        """Test excluding positions from report."""
        trace = DecisionTrace(run_id="no-pos")
        trace.final_positions = {"Q1": (10, 20)}

        report = render_markdown_report(trace, include_positions=False)

        assert "## Final Positions" not in report

    def test_phase_summary(self):
        """Test phase summary section."""
        trace = DecisionTrace(run_id="phase-test")
        trace.add(Decision(subject="X1", phase=DecisionPhase.SEMANTIC, reason="t"))
        trace.add(Decision(subject="X2", phase=DecisionPhase.TOPOLOGICAL, reason="t"))
        trace.add(Decision(subject="X3", phase=DecisionPhase.GEOMETRIC, reason="t"))
        trace.add(Decision(subject="X4", phase=DecisionPhase.GEOMETRIC, reason="t"))

        report = render_markdown_report(trace)

        assert "## Phase Summary" in report
        assert "| Semantic | 1 |" in report
        assert "| Topological | 1 |" in report
        assert "| Geometric | 2 |" in report

    def test_type_summary(self):
        """Test decision type summary section."""
        trace = DecisionTrace(run_id="type-test")
        trace.add(
            Decision(
                subject="X1",
                decision_type=DecisionType.INITIAL_POSITION,
                reason="t",
            )
        )
        trace.add(Decision(subject="X2", decision_type=DecisionType.ROTATION, reason="t"))

        report = render_markdown_report(trace)

        assert "## Decision Types" in report
        assert "Initial Position" in report
        assert "Rotation" in report

    def test_with_duration(self):
        """Test rendering with start and end time."""
        start = datetime(2025, 12, 19, 10, 0, 0)
        end = start + timedelta(seconds=45.5)

        trace = DecisionTrace(run_id="duration-test")
        trace.start_time = start
        trace.end_time = end

        report = render_markdown_report(trace)

        assert "Duration**: 45.5 seconds" in report

    def test_with_alternatives(self):
        """Test rendering rejected alternatives."""
        trace = DecisionTrace(run_id="alt-test")
        trace.add(
            Decision(
                subject="Q1",
                value=(45, 12),
                reason="Chosen position",
                alternatives=[
                    Alternative(
                        value=(50, 10),
                        rejection_reason="Violates clearance",
                        constraint_violated="clearance.hv_lv",
                    ),
                    Alternative(
                        value=(40, 15),
                        rejection_reason="Outside zone",
                    ),
                ],
            )
        )

        report = render_markdown_report(trace)

        assert "**Rejected Alternatives**" in report
        assert "(50.0, 10.0)" in report
        assert "Violates clearance" in report
        assert "`clearance.hv_lv`" in report

    def test_with_constraints(self):
        """Test rendering binding constraints."""
        trace = DecisionTrace(run_id="constraint-test")
        trace.add(
            Decision(
                subject="Q1",
                value=(45, 12),
                reason="Placed",
                constraint_refs=["thermal.Q1_edge", "adjacent.Q1_Q2"],
            )
        )

        report = render_markdown_report(trace)

        assert "**Binding Constraints**" in report
        assert "`thermal.Q1_edge`" in report
        assert "`adjacent.Q1_Q2`" in report

    def test_many_decisions_truncated(self):
        """Test that too many decisions are truncated."""
        trace = DecisionTrace(run_id="many-test")

        # Add 20 decisions for one component
        for i in range(20):
            trace.add(
                Decision(
                    subject="Q1",
                    value=(float(i), float(i)),
                    reason=f"Decision {i}",
                    epoch=i * 100,
                )
            )

        report = render_markdown_report(trace, max_decisions_per_component=5)

        # Should show last 5 and mention omitted
        assert "10 earlier decisions omitted" in report
        assert "Decision 19" in report  # Last decision shown


class TestRenderComponentReport:
    """Tests for single-component report rendering."""

    def test_basic_component_report(self):
        """Test rendering a report for a single component."""
        trace = DecisionTrace(run_id="comp-test")
        trace.add(Decision(subject="Q1", value=(10, 20), reason="First"))
        trace.add(Decision(subject="Q1", value=(15, 25), reason="Second"))
        trace.add(Decision(subject="Q2", value=(30, 40), reason="Other"))

        report = render_component_report(trace, "Q1")

        assert "# Decision Report: Q1" in report
        assert "Total Decisions**: 2" in report
        assert "First" in report
        assert "Second" in report
        # Should not include Q2
        assert "Q2" not in report
        assert "Other" not in report

    def test_component_not_found(self):
        """Test rendering for a component with no decisions."""
        trace = DecisionTrace(run_id="empty-comp")
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Test"))

        report = render_component_report(trace, "Q999")

        assert "# Decision Report: Q999" in report
        assert "Total Decisions**: 0" in report
        assert "No decisions recorded" in report


class TestSaveMarkdownReport:
    """Tests for file output."""

    def test_save_to_file(self):
        """Test saving report to file."""
        trace = DecisionTrace(run_id="save-test")
        trace.add(Decision(subject="X1", value=(1, 2), reason="Test"))

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path = Path(f.name)

        try:
            save_markdown_report(trace, path)

            content = path.read_text()
            assert "# Placement Decision Report" in content
            assert "save-test" in content
        finally:
            path.unlink()

    def test_save_with_path_string(self):
        """Test saving with string path."""
        trace = DecisionTrace(run_id="string-path")

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path_str = f.name

        try:
            save_markdown_report(trace, path_str)

            content = Path(path_str).read_text()
            assert "string-path" in content
        finally:
            Path(path_str).unlink()


class TestFormatting:
    """Tests for value formatting in reports."""

    def test_position_tuple_format(self):
        """Test formatting of position tuples."""
        trace = DecisionTrace(run_id="format-test")
        trace.add(Decision(subject="X1", value=(45.123, 12.789), reason="Test"))

        report = render_markdown_report(trace)

        # Should be formatted with 1 decimal place
        assert "(45.1, 12.8)" in report

    def test_none_value_format(self):
        """Test formatting of None values."""
        trace = DecisionTrace(run_id="none-test")
        trace.add(Decision(subject="X1", value=None, reason="Test"))

        report = render_markdown_report(trace)

        assert "| - |" in report  # None formatted as dash

    def test_long_reason_truncated(self):
        """Test that long reasons are truncated."""
        trace = DecisionTrace(run_id="long-test")
        long_reason = "This is a very long reason " * 10
        trace.add(Decision(subject="X1", value=(1, 2), reason=long_reason))

        report = render_markdown_report(trace)

        # Should be truncated with ellipsis
        assert "..." in report
        # Should not contain the full reason
        assert long_reason not in report

    def test_dict_value_format(self):
        """Test formatting of dictionary values with x/y."""
        trace = DecisionTrace(run_id="dict-test")
        trace.add(
            Decision(
                subject="X1",
                value={"x": 45.0, "y": 12.0, "rotation": 90},
                reason="Test",
            )
        )

        report = render_markdown_report(trace)

        assert "(45.0, 12.0) @ 90" in report


class TestMarkdownValidity:
    """Tests to ensure valid markdown is generated."""

    def test_tables_have_headers(self):
        """Test that all tables have proper header rows."""
        trace = DecisionTrace(run_id="table-test")
        trace.add(Decision(subject="X1", value=(1, 2), reason="Test"))
        trace.final_metrics = {"loss": 0.5}

        report = render_markdown_report(trace)

        # All tables should have header separator
        lines = report.split("\n")
        in_table = False
        for i, line in enumerate(lines):
            if line.startswith("|") and "|" in line[1:]:
                if not in_table:
                    in_table = True
                    # Next line should be separator
                    assert i + 1 < len(lines)
                    assert lines[i + 1].startswith("|--") or lines[i + 1].startswith("|-")
            elif in_table and not line.startswith("|"):
                in_table = False

    def test_no_empty_sections(self):
        """Test that sections without content are omitted."""
        trace = DecisionTrace(run_id="empty-sections")

        report = render_markdown_report(trace)

        # Empty metrics section should be omitted
        assert "## Summary Metrics" not in report
        # Empty phase summary should be omitted
        assert "## Phase Summary" not in report
