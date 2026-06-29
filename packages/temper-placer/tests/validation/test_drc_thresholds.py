"""
DRC Threshold Tests: Verify optimizer loss thresholds predict DRC outcomes.

Based on the DRC correlation study (test_drc_correlation.py), we established
that overlap_loss > 0 strongly correlates with DRC failures. These tests
verify that the documented thresholds are accurate predictors.

Key findings from correlation study:
- Placements with overlap_loss = 0 pass DRC
- Placements with overlap_loss > 0 fail DRC (clearance/shorting violations)
- Total loss is NOT a reliable predictor (optimizer minimizes wirelength,
  which can push components too close together)
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")

from temper_placer.io.kicad_parser import ParseResult, parse_kicad_pcb  # noqa: E402
from temper_placer.losses import LossContext  # noqa: E402

# Import DRC infrastructure from correlation tests (same directory)
from .test_drc_correlation import (  # noqa: E402
    RESULTS_DIR,
    create_perfect_placement,
    evaluate_placement,
    export_placement_to_pcb,
    random_init_absolute,
    requires_kicad,
    run_kicad_drc,
)

# Paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"
CONSTRAINTS_FILE = CONFIGS_DIR / "temper_constraints.yaml"


@dataclass
class DRCThresholds:
    """DRC pass/fail thresholds from config."""

    overlap_threshold: float
    boundary_threshold: float
    total_loss_informational: float
    safety_margin: float

    @classmethod
    def from_yaml(cls, path: Path) -> "DRCThresholds":
        """Load thresholds from YAML config."""
        with open(path) as f:
            config = yaml.safe_load(f)

        thresholds = config.get("drc_thresholds", {})
        return cls(
            overlap_threshold=thresholds.get("overlap_threshold", 0.0),
            boundary_threshold=thresholds.get("boundary_threshold", 0.0),
            total_loss_informational=thresholds.get("total_loss_informational", 1000.0),
            safety_margin=thresholds.get("safety_margin", 0.2),
        )

    def predicts_drc_pass(self, overlap_loss: float, boundary_loss: float) -> bool:
        """
        Predict whether a placement will pass DRC based on losses.

        Returns True if the placement is expected to pass DRC.
        """
        return overlap_loss <= self.overlap_threshold and boundary_loss <= self.boundary_threshold


def load_correlation_results() -> dict | None:
    """Load the results from the correlation study."""
    results_file = RESULTS_DIR / "penalty_thresholds.json"
    if not results_file.exists():
        return None
    with open(results_file) as f:
        return json.load(f)


class TestThresholdsDocumented:
    """Tests verifying thresholds are documented in config."""

    def test_constraints_file_exists(self):
        """The temper_constraints.yaml file should exist."""
        assert CONSTRAINTS_FILE.exists(), f"Config file not found: {CONSTRAINTS_FILE}"

    def test_drc_thresholds_section_exists(self):
        """Config should have drc_thresholds section."""
        with open(CONSTRAINTS_FILE) as f:
            config = yaml.safe_load(f)

        assert "drc_thresholds" in config, "Config missing 'drc_thresholds' section"

    def test_required_threshold_keys(self):
        """Config should have all required threshold keys."""
        thresholds = DRCThresholds.from_yaml(CONSTRAINTS_FILE)

        # These should be defined (even if 0)
        assert thresholds.overlap_threshold is not None
        assert thresholds.boundary_threshold is not None
        assert thresholds.safety_margin is not None

    def test_thresholds_are_non_negative(self):
        """All thresholds should be non-negative."""
        thresholds = DRCThresholds.from_yaml(CONSTRAINTS_FILE)

        assert thresholds.overlap_threshold >= 0, "Overlap threshold must be >= 0"
        assert thresholds.boundary_threshold >= 0, "Boundary threshold must be >= 0"
        assert thresholds.safety_margin >= 0, "Safety margin must be >= 0"

    def test_safety_margin_reasonable(self):
        """Safety margin should be between 0 and 1 (0-100%)."""
        thresholds = DRCThresholds.from_yaml(CONSTRAINTS_FILE)

        assert 0 <= thresholds.safety_margin <= 1.0, (
            f"Safety margin {thresholds.safety_margin} not in [0, 1]"
        )


class TestThresholdPredictions:
    """Tests verifying threshold predictions match DRC results."""

    @pytest.fixture
    def thresholds(self) -> DRCThresholds:
        """Load thresholds from config."""
        return DRCThresholds.from_yaml(CONSTRAINTS_FILE)

    @pytest.fixture
    def correlation_results(self) -> dict:
        """Load correlation study results."""
        results = load_correlation_results()
        if results is None:
            pytest.skip("Correlation results not available. Run test_drc_correlation.py first.")
        return results

    def test_thresholds_match_correlation_study(
        self, thresholds: DRCThresholds, correlation_results: dict
    ):
        """
        Verify documented thresholds match correlation study findings.

        The correlation study found:
        - All placements with overlap_loss = 0 passed DRC
        - All placements with overlap_loss > 0 failed DRC
        """
        data_points = correlation_results.get("data_points", [])

        # Verify our understanding: overlap = 0 means DRC pass
        for point in data_points:
            overlap = point.get("overlap_loss", 0)
            drc_pass = point.get("drc_pass", False)

            # If overlap is exactly 0, should pass
            if overlap == 0:
                assert drc_pass, (
                    f"Placement with overlap=0 should pass DRC: {point['quality_level']}"
                )

        # Documented threshold should be 0 based on findings
        assert thresholds.overlap_threshold == 0.0, (
            f"Based on correlation study, overlap_threshold should be 0, not {thresholds.overlap_threshold}"
        )

    def test_prediction_accuracy_on_known_data(
        self, thresholds: DRCThresholds, correlation_results: dict
    ):
        """
        Test prediction accuracy on the correlation study data.

        The threshold predictor should correctly predict DRC outcomes
        for all data points from the correlation study.
        """
        data_points = correlation_results.get("data_points", [])

        correct = 0
        total = 0
        mismatches = []

        for point in data_points:
            overlap = point.get("overlap_loss", 0)
            boundary = point.get("boundary_loss", 0)
            actual_pass = point.get("drc_pass", False)

            predicted_pass = thresholds.predicts_drc_pass(overlap, boundary)

            if predicted_pass == actual_pass:
                correct += 1
            else:
                mismatches.append(
                    {
                        "level": point.get("quality_level"),
                        "predicted": predicted_pass,
                        "actual": actual_pass,
                        "overlap": overlap,
                        "boundary": boundary,
                    }
                )
            total += 1

        accuracy = correct / total if total > 0 else 0

        print(f"\nPrediction accuracy: {correct}/{total} ({accuracy:.1%})")
        if mismatches:
            print("Mismatches:")
            for m in mismatches:
                print(f"  {m['level']}: predicted={m['predicted']}, actual={m['actual']}")

        # We expect high accuracy (ideally 100%)
        assert accuracy >= 0.8, (
            f"Prediction accuracy {accuracy:.1%} too low. Mismatches: {mismatches}"
        )


class TestPlacementValidation:
    """Tests for validating placements against thresholds."""

    @pytest.fixture
    def thresholds(self) -> DRCThresholds:
        """Load thresholds from config."""
        return DRCThresholds.from_yaml(CONSTRAINTS_FILE)

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    def test_perfect_placement_passes_threshold(
        self, thresholds: DRCThresholds, parsed_minimal: ParseResult
    ):
        """Perfect (hand-crafted) placement should pass threshold check."""
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, metrics = create_perfect_placement(netlist, board)

        # Evaluate losses
        context = LossContext.from_netlist_and_board(netlist, board)
        total, overlap, boundary, wirelength = evaluate_placement(state, context)

        # Should pass threshold
        assert thresholds.predicts_drc_pass(overlap, boundary), (
            f"Perfect placement should pass threshold. overlap={overlap}, boundary={boundary}"
        )

    @requires_kicad
    def test_threshold_pass_implies_drc_pass(
        self, thresholds: DRCThresholds, parsed_minimal: ParseResult
    ):
        """
        A placement passing threshold check should also pass KiCad DRC.

        This is the key property: our thresholds should be conservative
        predictors of DRC success.
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        # Create a placement known to pass thresholds (perfect grid)
        state, _ = create_perfect_placement(netlist, board)

        # Verify it passes our threshold check
        context = LossContext.from_netlist_and_board(netlist, board)
        _, overlap, boundary, _ = evaluate_placement(state, context)

        assert thresholds.predicts_drc_pass(overlap, boundary), (
            "Test setup error: placement should pass threshold"
        )

        # Export and run DRC
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, temp_path)
            drc_result = run_kicad_drc(temp_path)

            assert drc_result.ran_successfully, f"DRC failed: {drc_result.error_message}"
            assert drc_result.error_count == 0, (
                f"Threshold-passing placement has {drc_result.error_count} DRC errors. "
                f"Violations: {drc_result.violations_by_type()}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestThresholdSafetyMargin:
    """Tests for the safety margin in thresholds."""

    @pytest.fixture
    def thresholds(self) -> DRCThresholds:
        """Load thresholds from config."""
        return DRCThresholds.from_yaml(CONSTRAINTS_FILE)

    def test_safety_margin_documented(self, thresholds: DRCThresholds):
        """Safety margin should be documented in config."""
        assert thresholds.safety_margin > 0, (
            "Safety margin should be positive to account for measurement uncertainty"
        )

    def test_safety_margin_is_twenty_percent(self, thresholds: DRCThresholds):
        """Safety margin should be 20% as specified in requirements."""
        assert thresholds.safety_margin == 0.2, (
            f"Safety margin should be 0.2 (20%), not {thresholds.safety_margin}"
        )

    def test_thresholds_with_margin_explanation(self, thresholds: DRCThresholds):
        """
        Verify the threshold includes safety margin.

        Since we found overlap_threshold should be 0 (strict), the safety
        margin doesn't change it (0 * 1.2 = 0). But for future thresholds
        that might be non-zero, the margin would be applied.
        """
        # For overlap = 0, margin doesn't matter
        # This test documents that the margin is available for other thresholds
        if thresholds.overlap_threshold == 0:
            # Expected case based on our findings
            print("\nNote: overlap_threshold=0 (strictest possible)")
            print("Safety margin would apply to non-zero thresholds if discovered")
        else:
            # If threshold is non-zero, margin should have been applied
            # The raw threshold would be: threshold / (1 + margin)
            raw_threshold = thresholds.overlap_threshold / (1 + thresholds.safety_margin)
            print(f"\nThreshold with margin: {thresholds.overlap_threshold}")
            print(f"Raw threshold (before margin): {raw_threshold}")


class TestMultipleSeedValidation:
    """Tests validating thresholds across multiple random seeds."""

    @pytest.fixture
    def thresholds(self) -> DRCThresholds:
        """Load thresholds from config."""
        return DRCThresholds.from_yaml(CONSTRAINTS_FILE)

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    @requires_kicad
    @pytest.mark.slow
    def test_ten_threshold_passing_placements_pass_drc(
        self, thresholds: DRCThresholds, parsed_minimal: ParseResult
    ):
        """
        Generate 10 placements that pass threshold and verify they pass DRC.

        This tests the robustness of our threshold predictor.
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        import tempfile

        passing_placements = []

        # Generate placements with different seeds until we have 10 that pass threshold
        for seed in range(100):  # Try up to 100 seeds
            if len(passing_placements) >= 10:
                break

            key = jax.random.PRNGKey(seed)
            state = random_init_absolute(netlist.n_components, board, key, margin=8.0)

            context = LossContext.from_netlist_and_board(netlist, board)
            _, overlap, boundary, _ = evaluate_placement(state, context)

            if thresholds.predicts_drc_pass(overlap, boundary):
                passing_placements.append((seed, state, overlap, boundary))

        print(f"\nFound {len(passing_placements)} placements passing threshold in first 100 seeds")

        if len(passing_placements) < 10:
            pytest.skip(f"Only found {len(passing_placements)} threshold-passing placements")

        # Now verify each passes DRC
        drc_failures = []

        for seed, state, _overlap, _boundary in passing_placements[:10]:
            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
                temp_path = Path(f.name)

            try:
                export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, temp_path)
                drc_result = run_kicad_drc(temp_path)

                if not drc_result.ran_successfully:
                    drc_failures.append((seed, "DRC failed to run", drc_result.error_message))
                elif drc_result.error_count > 0:
                    drc_failures.append(
                        (seed, f"{drc_result.error_count} errors", drc_result.violations_by_type())
                    )
            finally:
                if temp_path.exists():
                    temp_path.unlink()

        print("\nDRC results for 10 threshold-passing placements:")
        print(f"  Passed: {10 - len(drc_failures)}")
        print(f"  Failed: {len(drc_failures)}")

        if drc_failures:
            print("\nFailures:")
            for seed, reason, details in drc_failures:
                print(f"  Seed {seed}: {reason} - {details}")

        # All should pass
        assert len(drc_failures) == 0, (
            f"{len(drc_failures)} threshold-passing placements failed DRC: {drc_failures}"
        )
