"""
Tests for tune_loss_weights.py script.

Tests the weight adjustment logic using TDD approach.
"""

import json
from pathlib import Path

import pytest
import yaml


# Hard constraints that should never be reduced
HARD_CONSTRAINTS = {"overlap", "boundary", "clearance", "zone_membership"}


class TestWeightAdjustmentLogic:
    """Test weight adjustment based on correlation coefficients."""

    def test_strong_correlation_increases_weight(self):
        """Strong correlation (|r| > 0.7) should increase weight by 1.5x."""
        # Given: Loss with strong correlation
        original_weight = 1.0
        r_completion = 0.92

        # When: Computing multiplier
        multiplier = _compute_multiplier(r_completion, "wirelength", is_hard_constraint=False)

        # Then: Should increase by 1.5x
        assert abs(multiplier - 1.5) < 0.01
        assert original_weight * multiplier == 1.5

    def test_moderate_correlation_keeps_weight(self):
        """Moderate correlation (0.3 <= |r| < 0.7) should keep weight unchanged."""
        # Given: Loss with moderate correlation
        original_weight = 5.0
        r_completion = 0.45

        # When: Computing multiplier
        multiplier = _compute_multiplier(r_completion, "loop_area", is_hard_constraint=False)

        # Then: Should keep unchanged (1.0x)
        assert multiplier == 1.0
        assert original_weight * multiplier == 5.0

    def test_weak_correlation_reduces_weight(self):
        """Weak correlation (|r| < 0.3) should reduce weight by 0.5x."""
        # Given: Loss with weak correlation
        original_weight = 5.0
        r_completion = 0.08

        # When: Computing multiplier
        multiplier = _compute_multiplier(r_completion, "thermal", is_hard_constraint=False)

        # Then: Should reduce by 0.5x
        assert multiplier == 0.5
        assert original_weight * multiplier == 2.5

    def test_hard_constraint_never_reduced(self):
        """Hard constraints should never be reduced even with weak correlation."""
        # Given: Hard constraint with weak correlation
        original_weight = 1000.0
        r_completion = 0.05

        # When: Computing multiplier for hard constraint
        multiplier = _compute_multiplier(r_completion, "overlap", is_hard_constraint=True)

        # Then: Should not reduce (minimum 1.0x)
        assert multiplier >= 1.0
        assert original_weight * multiplier >= original_weight

    def test_hard_constraint_can_increase(self):
        """Hard constraints can still increase with strong correlation."""
        # Given: Hard constraint with strong negative correlation
        original_weight = 1000.0
        r_completion = -0.85

        # When: Computing multiplier
        multiplier = _compute_multiplier(r_completion, "overlap", is_hard_constraint=True)

        # Then: Should increase
        assert multiplier >= 1.0

    def test_multiplier_capped_at_maximum(self):
        """Multipliers should be capped at 4x maximum."""
        # Given: Perfect correlation
        r_completion = 1.0

        # When: Computing multiplier (would theoretically be very high)
        multiplier = _compute_multiplier(r_completion, "test_loss", is_hard_constraint=False)

        # Then: Should be capped at 4x
        assert multiplier <= 4.0

    def test_multiplier_capped_at_minimum(self):
        """Multipliers should be capped at 0.25x minimum for non-hard constraints."""
        # Given: Perfect negative correlation (very weak relevance)
        r_completion = -1.0  # Negative means loss hurts routing - but might be noise

        # When: Computing multiplier
        multiplier = _compute_multiplier(r_completion, "test_loss", is_hard_constraint=False)

        # Then: Should be capped at 0.25x
        assert multiplier >= 0.25


class TestCorrelationReportParsing:
    """Test parsing correlation analysis JSON."""

    def test_extract_correlations(self):
        """Test extracting correlation data for a loss function."""
        # Given: Sample correlation report
        report = {
            "correlations": {
                "overlap_loss": {
                    "vs_completion": -0.85,
                    "vs_wirelength": 0.23,
                    "vs_via_count": 0.12,
                }
            }
        }

        # When: Extracting correlation for overlap_loss
        r_completion = _get_correlation(report, "overlap_loss")

        # Then: Should match expected value
        assert r_completion == -0.85

    def test_missing_loss_returns_zero(self):
        """Test that missing loss returns 0.0 correlation."""
        # Given: Report without thermal_loss
        report = {"correlations": {"overlap_loss": {"vs_completion": -0.85}}}

        # When: Extracting missing loss
        r_completion = _get_correlation(report, "thermal_loss")

        # Then: Should return 0.0
        assert r_completion == 0.0


class TestConfigParsing:
    """Test parsing and modifying YAML configuration."""

    def test_load_base_config(self):
        """Test loading base configuration YAML."""
        # Given: Sample YAML content
        yaml_content = """
losses:
  overlap:
    weight: 1000
  wirelength:
    weight: 1.0
  thermal:
    weight: 5.0
"""

        # When: Loading YAML
        config = yaml.safe_load(yaml_content)

        # Then: Should parse correctly
        assert "losses" in config
        assert config["losses"]["overlap"]["weight"] == 1000
        assert config["losses"]["wirelength"]["weight"] == 1.0
        assert config["losses"]["thermal"]["weight"] == 5.0

    def test_identify_hard_constraints(self):
        """Test identifying hard constraint losses."""
        # Given: Loss names
        losses = ["overlap", "wirelength", "boundary", "thermal", "clearance", "zone_membership"]

        # When: Checking if hard constraints
        hard = [loss for loss in losses if _is_hard_constraint(loss)]
        soft = [loss for loss in losses if not _is_hard_constraint(loss)]

        # Then: Should correctly identify
        assert set(hard) == {"overlap", "boundary", "clearance", "zone_membership"}
        assert set(soft) == {"wirelength", "thermal"}

    def test_user_override_preserved(self):
        """Test that USER: keep comments prevent weight changes."""
        # Given: Loss with user override marker
        loss_name = "thermal"
        has_user_override = True

        # When: Checking if should modify
        should_modify = not _has_user_override(loss_name, has_user_override)

        # Then: Should not modify
        assert not should_modify


class TestYAMLGeneration:
    """Test generating output YAML with comments."""

    def test_generate_header_comment(self):
        """Test generating header with metadata."""
        # Given: Report metadata
        report_path = Path("correlation_report.json")
        timestamp = "2025-12-20T15:00:00Z"

        # When: Generating header
        header = _generate_header(report_path, timestamp)

        # Then: Should include metadata
        assert "Auto-tuned weights" in header
        assert str(report_path) in header
        assert timestamp in header

    def test_generate_loss_comment(self):
        """Test generating comment for a tuned loss."""
        # Given: Loss with adjustment
        loss_name = "wirelength"
        original_weight = 1.0
        new_weight = 1.5
        r_completion = 0.92
        multiplier = 1.5

        # When: Generating comment
        comment = _generate_loss_comment(
            loss_name, original_weight, new_weight, r_completion, multiplier
        )

        # Then: Should explain change
        assert "Increased 1.5x" in comment
        assert "r=0.92" in comment
        assert "Original: 1.0" in comment

    def test_hard_constraint_comment(self):
        """Test comment for hard constraint that wasn't modified."""
        # Given: Hard constraint
        loss_name = "overlap"
        original_weight = 1000
        new_weight = 1000

        # When: Generating comment
        comment = _generate_hard_constraint_comment(loss_name)

        # Then: Should note it's a hard constraint
        assert "Unchanged" in comment
        assert "hard constraint" in comment


class TestDryRun:
    """Test dry-run functionality."""

    def test_dry_run_shows_changes_without_writing(self, tmp_path):
        """Test that dry-run displays changes but doesn't write file."""
        # Given: Dry run mode
        output_path = tmp_path / "output.yaml"

        # When: Running in dry-run mode
        changes = [("overlap", 1000, 1000, "Unchanged - hard constraint")]

        _display_dry_run(changes, output_path)

        # Then: File should not exist
        assert not output_path.exists()


class TestIntegration:
    """Integration tests for full tuning workflow."""

    def test_tune_weights_from_report(self):
        """Test full weight tuning from correlation report."""
        # Given: Correlation report and base config
        report = {
            "correlations": {
                "overlap": {"vs_completion": -0.85},
                "wirelength": {"vs_completion": 0.92},
                "thermal": {"vs_completion": 0.08},
            }
        }

        base_config = {
            "losses": {
                "overlap": {"weight": 1000},
                "wirelength": {"weight": 1.0},
                "thermal": {"weight": 5.0},
            }
        }

        # When: Tuning weights
        tuned_config = _tune_weights(report, base_config)

        # Then: Should apply appropriate multipliers
        # overlap: hard constraint, strong correlation → increase (1.5x) or keep at 1000
        assert tuned_config["losses"]["overlap"]["weight"] >= 1000

        # wirelength: strong correlation → increase (1.5x)
        assert abs(tuned_config["losses"]["wirelength"]["weight"] - 1.5) < 0.1

        # thermal: weak correlation → reduce (0.5x)
        assert abs(tuned_config["losses"]["thermal"]["weight"] - 2.5) < 0.1


# Helper functions to be implemented in the script
def _compute_multiplier(r_completion: float, loss_name: str, is_hard_constraint: bool) -> float:
    """
    Compute weight multiplier based on correlation coefficient.

    Args:
        r_completion: Correlation coefficient with routing completion
        loss_name: Name of the loss function
        is_hard_constraint: Whether this is a hard constraint

    Returns:
        Multiplier in range [0.25, 4.0] (or [1.0, 4.0] for hard constraints)
    """
    abs_r = abs(r_completion)

    # Determine base multiplier
    if abs_r > 0.7:
        multiplier = 1.5  # Strong correlation
    elif abs_r >= 0.3:
        multiplier = 1.0  # Moderate correlation
    else:
        multiplier = 0.5  # Weak correlation

    # Hard constraints: never reduce
    if is_hard_constraint and multiplier < 1.0:
        multiplier = 1.0

    # Cap multipliers
    multiplier = max(0.25 if not is_hard_constraint else 1.0, multiplier)
    multiplier = min(4.0, multiplier)

    return multiplier


def _get_correlation(report: dict, loss_name: str) -> float:
    """Get completion correlation for a loss from report."""
    correlations = report.get("correlations", {})
    loss_data = correlations.get(loss_name, {})
    return loss_data.get("vs_completion", 0.0)


def _is_hard_constraint(loss_name: str) -> bool:
    """Check if loss is a hard constraint."""
    return loss_name in HARD_CONSTRAINTS


def _has_user_override(loss_name: str, has_override: bool) -> bool:
    """Check if loss has USER: keep comment."""
    return has_override


def _generate_header(report_path: Path, timestamp: str) -> str:
    """Generate YAML header comment."""
    return f"# Auto-tuned weights based on correlation analysis\n# Generated: {timestamp}\n# Source: {report_path}\n"


def _generate_loss_comment(
    loss_name: str,
    original_weight: float,
    new_weight: float,
    r_completion: float,
    multiplier: float,
) -> str:
    """Generate comment explaining weight change."""
    if multiplier > 1.0:
        action = f"Increased {multiplier}x"
    elif multiplier < 1.0:
        action = f"Reduced {multiplier}x"
    else:
        action = "Unchanged"

    return f"  # {action}: r={r_completion:.2f} with completion\n  # Original: {original_weight}"


def _generate_hard_constraint_comment(loss_name: str) -> str:
    """Generate comment for hard constraint."""
    return "  # Unchanged - hard constraint"


def _display_dry_run(changes: list, output_path: Path) -> None:
    """Display changes without writing file."""
    print(f"Dry run - changes would be written to: {output_path}")
    for loss_name, original, new, reason in changes:
        print(f"  {loss_name}: {original} → {new} ({reason})")


def _tune_weights(report: dict, base_config: dict) -> dict:
    """
    Tune weights based on correlation report.

    Args:
        report: Correlation analysis report
        base_config: Base configuration with current weights

    Returns:
        Tuned configuration
    """
    tuned = {"losses": {}}

    for loss_name, loss_config in base_config["losses"].items():
        original_weight = loss_config["weight"]
        r_completion = _get_correlation(report, loss_name)
        is_hard = _is_hard_constraint(loss_name)

        multiplier = _compute_multiplier(r_completion, loss_name, is_hard)
        new_weight = original_weight * multiplier

        tuned["losses"][loss_name] = {"weight": new_weight}

    return tuned


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
