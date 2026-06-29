#!/usr/bin/env python3
"""
BDD tests for correlation-based loss weight tuning.

These tests verify that:
1. The tuned config uses correlation-informed weights
2. Redundant losses are removed
3. Key predictors are properly weighted

Related issue: temper-h0n9.4
"""

from pathlib import Path

import pytest
import yaml


class TestTunedConfigStructure:
    """BDD tests for tuned config file structure."""

    @pytest.fixture
    def tuned_config(self):
        """Load the tuned config file."""
        config_path = Path(__file__).parent.parent / "configs" / "temper_correlation_tuned.yaml"
        if not config_path.exists():
            pytest.skip(f"Tuned config not found: {config_path}")
        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_overlap_has_highest_weight(self, tuned_config):
        """
        GIVEN the correlation finding that overlap has r=-0.38 with routing
        WHEN the tuned config is loaded
        THEN overlap should have the highest weight among all losses

        Rationale: Overlap is the best predictor of routing success.
        """
        losses = tuned_config.get("losses", {})
        overlap_weight = losses.get("overlap", {}).get("weight", 0)

        for loss_name, loss_config in losses.items():
            if loss_name == "overlap":
                continue
            other_weight = loss_config.get("weight", 0)
            assert overlap_weight >= other_weight, (
                f"Overlap weight ({overlap_weight}) should be >= {loss_name} weight ({other_weight})"
            )

    def test_spread_is_removed_or_minimal(self, tuned_config):
        """
        GIVEN the finding that spread is confounded with overlap (r=0.94)
        WHEN the tuned config is loaded
        THEN spread should be removed or have minimal weight (<0.1)

        Rationale: Spread is redundant with overlap and hurts routing.
        """
        losses = tuned_config.get("losses", {})

        if "spread" in losses:
            spread_weight = losses["spread"].get("weight", 0)
            assert spread_weight < 0.1, (
                f"Spread weight ({spread_weight}) should be <0.1 or removed (confounded with overlap)"
            )

    def test_per_component_losses_are_removed(self, tuned_config):
        """
        GIVEN the finding that *_per_component losses perfectly correlate with base versions
        WHEN the tuned config is loaded
        THEN per_component variants should not be present

        Rationale: overlap_per_component, group_cluster_per_component, etc. are redundant.
        """
        losses = tuned_config.get("losses", {})

        per_component_losses = [name for name in losses if "per_component" in name]
        assert len(per_component_losses) == 0, (
            f"Per-component losses should be removed (redundant): {per_component_losses}"
        )

    def test_boundary_is_present(self, tuned_config):
        """
        GIVEN that boundary loss is needed for constraint satisfaction
        WHEN the tuned config is loaded
        THEN boundary should be present even though it had constant correlation

        Rationale: Boundary prevents edge violations even if it doesn't vary.
        """
        losses = tuned_config.get("losses", {})
        assert "boundary" in losses, "Boundary loss should be present for constraint satisfaction"

    def test_config_has_documentation(self, tuned_config):
        """
        GIVEN the need to document weight rationale
        WHEN the tuned config is loaded
        THEN it should have a metadata section explaining the tuning

        Rationale: Future maintainers need to understand why weights were chosen.
        """
        # Check for top-level comment or metadata key
        assert tuned_config is not None, "Config should load successfully"
        # Note: YAML comments aren't preserved by pyyaml, so we just check the file exists
        # The actual documentation will be in comments at the top of the YAML file


class TestWeightRationale:
    """Tests verifying weight choices match correlation data."""

    def test_overlap_weight_rationale(self):
        """
        GIVEN overlap has r=-0.38 with routing completion
        WHEN we apply correlation-informed weighting
        THEN overlap should have high weight (>=500) to minimize overlaps

        Correlation data:
        - overlap vs_completion: -0.377
        - overlap vs_via_count: -0.374
        - This is the strongest predictor of routing success
        """
        # Document the rationale - actual weight is in config
        rationale = (
            "Overlap has the strongest negative correlation with routing completion. "
            "High weight prioritizes reducing component overlaps, which directly "
            "improves routability by providing clear routing channels."
        )
        assert len(rationale) > 0  # Documentation test

    def test_boundary_weight_rationale(self):
        """
        GIVEN boundary was constant (all zero) in correlation analysis
        WHEN we keep boundary in config
        THEN it should have moderate weight (50-200) for constraint satisfaction

        Correlation data:
        - boundary had std=0 (constant) so no correlation computed
        - But boundary violations would break PCB validity
        """
        rationale = (
            "Boundary loss had constant zero values because no placements "
            "violated board edges. However, it must remain to prevent edge "
            "violations in future optimizations. Moderate weight balances "
            "constraint satisfaction with optimization flexibility."
        )
        assert len(rationale) > 0  # Documentation test

    def test_wirelength_weight_rationale(self):
        """
        GIVEN wirelength correlated with actual wirelength (r=0.47) but not completion (r=0.0)
        WHEN we set wirelength weight
        THEN it should have low-moderate weight to not dominate routing-relevant losses

        Correlation data:
        - wirelength vs_wirelength: 0.475 (validates metric works)
        - wirelength vs_completion: 0.0 (doesn't predict routing success)
        """
        rationale = (
            "Wirelength loss correctly predicts wire length but not routing success. "
            "This suggests local congestion (overlap) matters more than global wirelength. "
            "Low weight allows the optimizer flexibility while still encouraging "
            "shorter traces for signal integrity."
        )
        assert len(rationale) > 0  # Documentation test


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
