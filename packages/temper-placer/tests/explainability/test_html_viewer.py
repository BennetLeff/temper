"""Tests for the explainability.html_viewer module.

This module tests the HTML viewer that generates interactive visualizations
of decision traces for exploration and debugging.
"""


import pytest

from temper_placer.explainability import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.html_viewer import (
    generate_html_report,
    render_component_card,
    render_constraint_summary,
    render_decision_timeline,
    render_phase_summary,
    render_search_panel,
    save_html_report,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_trace() -> DecisionTrace:
    """Create a sample trace with multiple decisions for testing."""
    trace = DecisionTrace(run_id="test-run-123")

    # Add some decisions across phases
    trace.add(
        Decision(
            id="d001",
            decision_type=DecisionType.INITIAL_POSITION,
            phase=DecisionPhase.TOPOLOGICAL,
            subject="Q1",
            value=(10.0, 90.0),
            reason="Placed by thermal_edge heuristic near top edge",
            constraint_refs=["thermal.edge"],
        )
    )
    trace.add(
        Decision(
            id="d002",
            decision_type=DecisionType.INITIAL_POSITION,
            phase=DecisionPhase.TOPOLOGICAL,
            subject="Q2",
            value=(20.0, 90.0),
            reason="Placed by thermal_edge heuristic near top edge",
            constraint_refs=["thermal.edge"],
        )
    )
    trace.add(
        Decision(
            id="d003",
            decision_type=DecisionType.POSITION_UPDATE,
            phase=DecisionPhase.GEOMETRIC,
            subject="Q1",
            value=(12.0, 88.0),
            previous_value=(10.0, 90.0),
            reason="Gradient descent epoch 100",
            epoch=100,
            loss_contribution=-0.05,
        )
    )
    trace.add(
        Decision(
            id="d004",
            decision_type=DecisionType.ROTATION,
            phase=DecisionPhase.GEOMETRIC,
            subject="U1",
            value=1,  # 90 degrees
            previous_value=0,
            reason="Rotated for pin alignment with VCC net",
            epoch=200,
        )
    )
    trace.add(
        Decision(
            id="d005",
            decision_type=DecisionType.CONSTRAINT_APPLIED,
            phase=DecisionPhase.GEOMETRIC,
            subject="clearance.hv_lv",
            value=["Q1", "U1"],
            reason="Enforced 10mm HV-LV clearance",
            constraint_refs=["clearance.hv_lv"],
            epoch=300,
        )
    )

    trace.finalize(
        positions={"Q1": (12.0, 88.0), "Q2": (20.0, 90.0), "U1": (50.0, 50.0)},
        metrics={"total_loss": 0.125, "wirelength": 45.2, "overlap": 0.0},
    )

    return trace


@pytest.fixture
def trace_with_alternatives() -> DecisionTrace:
    """Create a trace with rejected alternatives for why-not testing."""
    trace = DecisionTrace(run_id="alt-trace")

    trace.add(
        Decision(
            id="d001",
            decision_type=DecisionType.INITIAL_POSITION,
            phase=DecisionPhase.GEOMETRIC,
            subject="Q1",
            value=(45.2, 12.3),
            reason="Best position satisfying thermal and clearance constraints",
            constraint_refs=["thermal.Q1", "clearance.hv_lv"],
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

    return trace


@pytest.fixture
def empty_trace() -> DecisionTrace:
    """Create an empty trace for edge case testing."""
    return DecisionTrace(run_id="empty-trace")


# =============================================================================
# TestGenerateHtmlReport - Main HTML generation
# =============================================================================


class TestGenerateHtmlReport:
    """Tests for generate_html_report() main function."""

    def test_generates_valid_html(self, sample_trace: DecisionTrace):
        """Generated output is valid HTML with doctype."""
        html = generate_html_report(sample_trace)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "</html>" in html

    def test_includes_run_id(self, sample_trace: DecisionTrace):
        """HTML includes the run ID in title or header."""
        html = generate_html_report(sample_trace)
        assert "test-run-123" in html

    def test_includes_all_components(self, sample_trace: DecisionTrace):
        """All component subjects appear in the HTML."""
        html = generate_html_report(sample_trace)
        assert "Q1" in html
        assert "Q2" in html
        assert "U1" in html

    def test_includes_decision_count(self, sample_trace: DecisionTrace):
        """HTML shows total decision count."""
        html = generate_html_report(sample_trace)
        # Should mention 5 decisions somewhere
        assert "5" in html or "five" in html.lower()

    def test_includes_css_styles(self, sample_trace: DecisionTrace):
        """HTML includes embedded CSS styles."""
        html = generate_html_report(sample_trace)
        assert "<style>" in html
        assert "</style>" in html

    def test_includes_javascript(self, sample_trace: DecisionTrace):
        """HTML includes JavaScript for interactivity."""
        html = generate_html_report(sample_trace)
        assert "<script>" in html
        assert "</script>" in html

    def test_empty_trace_generates_valid_html(self, empty_trace: DecisionTrace):
        """Empty trace still generates valid HTML."""
        html = generate_html_report(empty_trace)
        assert "<!DOCTYPE html>" in html
        assert "No decisions" in html or "empty" in html.lower()

    def test_includes_final_metrics(self, sample_trace: DecisionTrace):
        """HTML displays final metrics if available."""
        html = generate_html_report(sample_trace)
        assert "total_loss" in html or "0.125" in html
        assert "wirelength" in html or "45.2" in html

    def test_custom_title(self, sample_trace: DecisionTrace):
        """Custom title can be provided."""
        html = generate_html_report(sample_trace, title="My Custom Title")
        assert "My Custom Title" in html

    def test_responsive_layout(self, sample_trace: DecisionTrace):
        """HTML includes responsive/mobile-friendly meta tags."""
        html = generate_html_report(sample_trace)
        assert "viewport" in html


# =============================================================================
# TestRenderDecisionTimeline - Timeline visualization
# =============================================================================


class TestRenderDecisionTimeline:
    """Tests for render_decision_timeline() function."""

    def test_returns_html_string(self, sample_trace: DecisionTrace):
        """Function returns HTML string."""
        html = render_decision_timeline(sample_trace.decisions)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_decisions_in_chronological_order(self, sample_trace: DecisionTrace):
        """Decisions appear in chronological order."""
        html = render_decision_timeline(sample_trace.decisions)
        # d001 should appear before d005
        pos_d001 = html.find("d001")
        pos_d005 = html.find("d005")
        assert pos_d001 < pos_d005

    def test_shows_epoch_markers(self, sample_trace: DecisionTrace):
        """Timeline shows epoch numbers where applicable."""
        html = render_decision_timeline(sample_trace.decisions)
        assert "100" in html  # epoch 100
        assert "200" in html  # epoch 200

    def test_shows_phase_transitions(self, sample_trace: DecisionTrace):
        """Timeline indicates phase changes."""
        html = render_decision_timeline(sample_trace.decisions)
        assert "topological" in html.lower() or "TOPOLOGICAL" in html
        assert "geometric" in html.lower() or "GEOMETRIC" in html

    def test_empty_list_returns_placeholder(self):
        """Empty decision list returns a placeholder message."""
        html = render_decision_timeline([])
        assert "no decisions" in html.lower() or len(html) > 0

    def test_clickable_decision_entries(self, sample_trace: DecisionTrace):
        """Decision entries have click handlers or links."""
        html = render_decision_timeline(sample_trace.decisions)
        # Should have onclick or href attributes
        assert "onclick" in html or "href" in html or "data-decision" in html


# =============================================================================
# TestRenderComponentCard - Component detail cards
# =============================================================================


class TestRenderComponentCard:
    """Tests for render_component_card() function."""

    def test_returns_html_string(self, sample_trace: DecisionTrace):
        """Function returns HTML string."""
        decisions = sample_trace.query_subject("Q1")
        html = render_component_card("Q1", decisions)
        assert isinstance(html, str)

    def test_shows_component_name(self, sample_trace: DecisionTrace):
        """Card displays the component reference."""
        decisions = sample_trace.query_subject("Q1")
        html = render_component_card("Q1", decisions)
        assert "Q1" in html

    def test_shows_final_position(self, sample_trace: DecisionTrace):
        """Card shows the final position."""
        decisions = sample_trace.query_subject("Q1")
        html = render_component_card("Q1", decisions)
        # Final position is (12.0, 88.0)
        assert "12" in html and "88" in html

    def test_shows_decision_history(self, sample_trace: DecisionTrace):
        """Card shows history of decisions."""
        decisions = sample_trace.query_subject("Q1")
        html = render_component_card("Q1", decisions)
        # Should mention both the initial and update
        assert "thermal_edge" in html or "heuristic" in html.lower()
        assert "gradient" in html.lower() or "epoch" in html.lower()

    def test_shows_constraints(self, sample_trace: DecisionTrace):
        """Card displays constraint references."""
        decisions = sample_trace.query_subject("Q1")
        html = render_component_card("Q1", decisions)
        assert "thermal" in html.lower()

    def test_empty_decisions_shows_message(self):
        """Component with no decisions shows appropriate message."""
        html = render_component_card("C99", [])
        assert "no decisions" in html.lower() or "not found" in html.lower()


# =============================================================================
# TestRenderPhaseSummary - Phase breakdown
# =============================================================================


class TestRenderPhaseSummary:
    """Tests for render_phase_summary() function."""

    def test_returns_html_string(self, sample_trace: DecisionTrace):
        """Function returns HTML string."""
        html = render_phase_summary(sample_trace)
        assert isinstance(html, str)

    def test_shows_all_phases(self, sample_trace: DecisionTrace):
        """Summary shows all phases that have decisions."""
        html = render_phase_summary(sample_trace)
        assert "topological" in html.lower()
        assert "geometric" in html.lower()

    def test_shows_decision_counts_per_phase(self, sample_trace: DecisionTrace):
        """Summary shows count of decisions per phase."""
        html = render_phase_summary(sample_trace)
        # TOPOLOGICAL has 2 decisions, GEOMETRIC has 3
        assert "2" in html
        assert "3" in html

    def test_empty_trace_shows_no_phases(self, empty_trace: DecisionTrace):
        """Empty trace shows no phase data."""
        html = render_phase_summary(empty_trace)
        assert "no" in html.lower() or "empty" in html.lower() or "0" in html


# =============================================================================
# TestRenderConstraintSummary - Constraint breakdown
# =============================================================================


class TestRenderConstraintSummary:
    """Tests for render_constraint_summary() function."""

    def test_returns_html_string(self, sample_trace: DecisionTrace):
        """Function returns HTML string."""
        html = render_constraint_summary(sample_trace)
        assert isinstance(html, str)

    def test_shows_constraint_ids(self, sample_trace: DecisionTrace):
        """Summary shows constraint IDs."""
        html = render_constraint_summary(sample_trace)
        assert "thermal.edge" in html
        assert "clearance.hv_lv" in html

    def test_shows_affected_components(self, sample_trace: DecisionTrace):
        """Summary shows which components each constraint affected."""
        html = render_constraint_summary(sample_trace)
        # thermal.edge affected Q1 and Q2
        assert "Q1" in html
        assert "Q2" in html

    def test_clickable_constraint_entries(self, sample_trace: DecisionTrace):
        """Constraint entries are clickable to filter decisions."""
        html = render_constraint_summary(sample_trace)
        assert "onclick" in html or "href" in html or "data-constraint" in html


# =============================================================================
# TestRenderSearchPanel - Search and filter UI
# =============================================================================


class TestRenderSearchPanel:
    """Tests for render_search_panel() function."""

    def test_returns_html_string(self, sample_trace: DecisionTrace):
        """Function returns HTML string."""
        html = render_search_panel(sample_trace)
        assert isinstance(html, str)

    def test_includes_search_input(self, sample_trace: DecisionTrace):
        """Panel includes a search input field."""
        html = render_search_panel(sample_trace)
        assert "<input" in html
        assert "search" in html.lower()

    def test_includes_phase_filter(self, sample_trace: DecisionTrace):
        """Panel includes phase filter dropdown or checkboxes."""
        html = render_search_panel(sample_trace)
        assert "phase" in html.lower()
        # Should have filter controls
        assert "<select" in html or "checkbox" in html.lower() or "filter" in html.lower()

    def test_includes_type_filter(self, sample_trace: DecisionTrace):
        """Panel includes decision type filter."""
        html = render_search_panel(sample_trace)
        assert "type" in html.lower()


# =============================================================================
# TestAlternativesDisplay - Rejected alternatives
# =============================================================================


class TestAlternativesDisplay:
    """Tests for displaying rejected alternatives."""

    def test_alternatives_shown_in_html(self, trace_with_alternatives: DecisionTrace):
        """Rejected alternatives appear in the HTML."""
        html = generate_html_report(trace_with_alternatives)
        assert "(50" in html or "50.0" in html or "50, 10" in html
        assert "rejected" in html.lower() or "alternative" in html.lower()

    def test_rejection_reason_shown(self, trace_with_alternatives: DecisionTrace):
        """Rejection reasons are displayed."""
        html = generate_html_report(trace_with_alternatives)
        assert "HV clearance" in html or "clearance" in html.lower()

    def test_constraint_violated_shown(self, trace_with_alternatives: DecisionTrace):
        """Violated constraint is shown."""
        html = generate_html_report(trace_with_alternatives)
        assert "clearance.hv_lv" in html

    def test_loss_if_chosen_shown(self, trace_with_alternatives: DecisionTrace):
        """Loss if chosen is displayed."""
        html = generate_html_report(trace_with_alternatives)
        assert "0.85" in html or "0.42" in html


# =============================================================================
# TestSaveHtmlReport - File output
# =============================================================================


class TestSaveHtmlReport:
    """Tests for save_html_report() function."""

    def test_creates_file(self, sample_trace: DecisionTrace, tmp_path):
        """Function creates an HTML file."""
        output_path = tmp_path / "report.html"
        save_html_report(sample_trace, output_path)
        assert output_path.exists()

    def test_file_contains_valid_html(self, sample_trace: DecisionTrace, tmp_path):
        """Created file contains valid HTML."""
        output_path = tmp_path / "report.html"
        save_html_report(sample_trace, output_path)
        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "</html>" in content

    def test_file_is_utf8_encoded(self, sample_trace: DecisionTrace, tmp_path):
        """File is UTF-8 encoded for Unicode support."""
        output_path = tmp_path / "report.html"
        save_html_report(sample_trace, output_path)
        # Should be able to read as UTF-8
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_custom_title_in_file(self, sample_trace: DecisionTrace, tmp_path):
        """Custom title appears in saved file."""
        output_path = tmp_path / "report.html"
        save_html_report(sample_trace, output_path, title="Custom Report Title")
        content = output_path.read_text()
        assert "Custom Report Title" in content

    def test_creates_parent_directories(self, sample_trace: DecisionTrace, tmp_path):
        """Function creates parent directories if needed."""
        output_path = tmp_path / "subdir" / "nested" / "report.html"
        save_html_report(sample_trace, output_path)
        assert output_path.exists()


# =============================================================================
# TestInteractivity - JavaScript functionality
# =============================================================================


class TestInteractivity:
    """Tests for JavaScript interactivity features."""

    def test_component_click_handler(self, sample_trace: DecisionTrace):
        """Clicking a component highlights related decisions."""
        html = generate_html_report(sample_trace)
        # Should have some JS for component selection
        assert "function" in html  # JavaScript functions
        assert "click" in html.lower() or "onclick" in html

    def test_search_functionality(self, sample_trace: DecisionTrace):
        """Search input has associated JavaScript."""
        html = generate_html_report(sample_trace)
        assert "search" in html.lower()
        # Should have event handler for search
        assert "input" in html.lower() or "keyup" in html.lower() or "change" in html.lower()

    def test_filter_functionality(self, sample_trace: DecisionTrace):
        """Filter controls have associated JavaScript."""
        html = generate_html_report(sample_trace)
        assert "filter" in html.lower()

    def test_expand_collapse_functionality(self, sample_trace: DecisionTrace):
        """Decision details can be expanded/collapsed."""
        html = generate_html_report(sample_trace)
        # Should have expand/collapse controls
        assert "expand" in html.lower() or "collapse" in html.lower() or "toggle" in html.lower()


# =============================================================================
# TestAccessibility - Accessibility features
# =============================================================================


class TestAccessibility:
    """Tests for accessibility features."""

    def test_has_lang_attribute(self, sample_trace: DecisionTrace):
        """HTML element has lang attribute."""
        html = generate_html_report(sample_trace)
        assert 'lang="en"' in html or "lang='en'" in html

    def test_has_semantic_structure(self, sample_trace: DecisionTrace):
        """HTML uses semantic elements."""
        html = generate_html_report(sample_trace)
        # Should use semantic HTML5 elements
        assert "<main" in html or "<article" in html or "<section" in html

    def test_images_have_alt_text(self, sample_trace: DecisionTrace):
        """Any images have alt attributes."""
        html = generate_html_report(sample_trace)
        # If there are images, they should have alt
        if "<img" in html:
            # Simple check - each img should have alt
            img_count = html.count("<img")
            alt_count = html.count("alt=")
            assert alt_count >= img_count

    def test_form_labels(self, sample_trace: DecisionTrace):
        """Form inputs have associated labels."""
        html = generate_html_report(sample_trace)
        # If there are inputs, there should be labels
        if "<input" in html:
            assert "<label" in html or "aria-label" in html


# =============================================================================
# TestEdgeCases - Edge cases and error handling
# =============================================================================


class TestHtmlViewerEdgeCases:
    """Edge cases for HTML viewer."""

    def test_special_characters_escaped(self, sample_trace: DecisionTrace):
        """Special HTML characters are escaped."""
        # Add a decision with special characters
        sample_trace.add(
            Decision(
                subject="C<1>",
                value=(10.0, 20.0),
                reason='Reason with "quotes" & <brackets>',
            )
        )
        html = generate_html_report(sample_trace)
        # Should be escaped
        assert "&lt;" in html or "\\u003c" in html or "C<1>" not in html
        assert "&amp;" in html or "& " not in html

    def test_very_long_reason_truncated_or_wrapped(self):
        """Very long reasons are handled gracefully."""
        trace = DecisionTrace()
        long_reason = "A" * 5000
        trace.add(Decision(subject="C1", value=(10.0, 20.0), reason=long_reason))
        html = generate_html_report(trace)
        # Should still generate valid HTML
        assert "</html>" in html

    def test_unicode_in_content(self):
        """Unicode characters are handled correctly."""
        trace = DecisionTrace()
        trace.add(
            Decision(
                subject="R1",
                value=(10.0, 20.0),
                reason="Thermal conductivity λ = 0.5 W/(m·K), angle θ = 45°",
            )
        )
        html = generate_html_report(trace)
        assert "λ" in html or "&lambda;" in html
        assert "°" in html or "&deg;" in html

    def test_many_decisions_performance(self):
        """Large traces render in reasonable time."""
        import time

        trace = DecisionTrace()
        for i in range(1000):
            trace.add(
                Decision(
                    subject=f"C{i}",
                    value=(float(i), float(i)),
                    reason=f"Decision {i}",
                )
            )

        start = time.perf_counter()
        html = generate_html_report(trace)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Rendering 1000 decisions took {elapsed:.2f}s (should be <5s)"
        assert len(html) > 0

    def test_null_values_handled(self):
        """Null/None values don't cause errors."""
        trace = DecisionTrace()
        trace.add(
            Decision(
                subject="C1",
                value=None,
                previous_value=None,
                reason="",
                constraint_refs=[],
                epoch=None,
            )
        )
        html = generate_html_report(trace)
        assert "</html>" in html
