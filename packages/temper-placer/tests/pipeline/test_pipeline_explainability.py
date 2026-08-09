"""Tests for pipeline explainability module."""

from temper_placer.pipeline.explainability import (
    DecisionLogger,
    generate_markdown_report,
)


class TestDecisionLogger:
    """Tests for DecisionLogger methods."""

    def test_log_placement_adds_decision(self):
        """log_placement adds a placement decision to the trace."""
        logger = DecisionLogger(run_id="test-run")
        logger.log_placement(
            component="U1",
            value=(10.0, 20.0),
            reason="optimal position",
            phase="geometric",
            constraints=["keepout_zone1"],
        )
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.subject == "U1"
        assert d.decision_type == "placement"
        assert d.value == (10.0, 20.0)
        assert d.reason == "optimal position"
        assert d.phase == "geometric"
        assert "keepout_zone1" in d.constraint_refs

    def test_log_placement_defaults(self):
        """log_placement uses sensible defaults for optional args."""
        logger = DecisionLogger()
        logger.log_placement(
            component="R1",
            value=(0.0, 0.0),
            reason="default",
        )
        d = logger.trace.decisions[0]
        assert d.phase == "geometric"
        assert d.constraint_refs == []
        assert d.alternatives_considered == []

    def test_log_routing_adds_decision(self):
        """log_routing adds a routing decision to the trace."""
        logger = DecisionLogger(run_id="test-run")
        logger.log_routing(
            net="NET1",
            value="path_abc",
            reason="shortest path",
            phase="routing",
            constraints=["min_width"],
        )
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.subject == "NET1"
        assert d.decision_type == "routing"
        assert d.value == "path_abc"
        assert d.reason == "shortest path"
        assert d.phase == "routing"
        assert "min_width" in d.constraint_refs

    def test_log_routing_defaults(self):
        """log_routing uses sensible defaults for optional args."""
        logger = DecisionLogger()
        logger.log_routing(
            net="NET2",
            value="path_xyz",
            reason="default",
        )
        d = logger.trace.decisions[0]
        assert d.phase == "routing"
        assert d.constraint_refs == []
        assert d.alternatives_considered == []

    def test_finish_records_metrics_and_end_time(self):
        """finish sets end_time and final_metrics on the trace."""
        logger = DecisionLogger(run_id="finish-test")
        logger.log_placement("U1", (5.0, 5.0), "test")
        metrics = {"loss": 0.5, "overlap": 0.0, "routed": 42}
        trace = logger.finish(metrics)
        assert trace.end_time is not None
        assert trace.final_metrics == metrics
        assert trace.final_metrics["loss"] == 0.5

    def test_multiple_decisions(self):
        """Multiple log calls produce multiple decisions."""
        logger = DecisionLogger()
        logger.log_placement("U1", (1, 1), "a")
        logger.log_placement("U2", (2, 2), "b")
        logger.log_routing("N1", "p1", "c")
        trace = logger.finish({})
        assert len(trace.decisions) == 3
        types = [d.decision_type for d in trace.decisions]
        assert types.count("placement") == 2
        assert types.count("routing") == 1


class TestGenerateMarkdownReport:
    """Tests for generate_markdown_report."""

    def test_generates_markdown_with_header(self):
        """Report includes run ID and timestamps."""
        logger = DecisionLogger(run_id="md-test-run")
        logger.log_placement("U1", (10, 20), "test")
        trace = logger.finish({"loss": 0.25, "overlap": 0.0})
        report = generate_markdown_report(trace)
        assert "# Placement Decision Trace: md-test-run" in report
        assert "Start Time" in report
        assert "End Time" in report
        assert "## Summary Metrics" in report
        assert "loss" in report
        assert "0.2500" in report
        assert "overlap" in report

    def test_generates_decision_sections(self):
        """Report includes a section for each decision."""
        logger = DecisionLogger(run_id="md-decisions")
        logger.log_placement("U1", (10, 20), "optimal")
        logger.log_routing("NET1", "path", "shortest")
        trace = logger.finish({})
        report = generate_markdown_report(trace)
        assert "## Decisions" in report
        assert "### U1" in report
        assert "### NET1" in report
        assert "placement" in report
        assert "routing" in report

    def test_handles_empty_metrics(self):
        """Report works with no final metrics."""
        logger = DecisionLogger(run_id="empty-metrics")
        trace = logger.finish({})
        report = generate_markdown_report(trace)
        assert "## Summary Metrics" in report
        # No metrics listed under summary
        lines = report.split("\n")
        summary_idx = next(i for i, l in enumerate(lines) if "## Summary Metrics" in l)
        # The line after the header should be empty or the next section
        after_summary = lines[summary_idx + 1] if summary_idx + 1 < len(lines) else ""
        assert after_summary == "" or after_summary.startswith("##")

    def test_no_end_time_shows_na(self):
        """When end_time is None, report shows N/A."""
        logger = DecisionLogger(run_id="no-end-time")
        trace = logger.finish({})
        trace.end_time = None  # simulate missing end time
        report = generate_markdown_report(trace)
        assert "N/A" in report
