"""Tests for MultiSeedConfig and OptimizerConfig multi_seed wiring."""

import logging

import pytest

from temper_placer.optimizer.config import MultiSeedConfig, OptimizerConfig


class TestMultiSeedConfig:
    def test_default_disabled(self):
        """MultiSeedConfig default is disabled."""
        c = MultiSeedConfig()
        assert c.enabled is False
        assert c.n_generate == 50
        assert c.n_select == 4
        assert c.n_triage_iters == 30
        assert c.dpp_quality_enabled is False

    def test_optimizer_config_has_multi_seed(self):
        """OptimizerConfig has multi_seed field with default."""
        oc = OptimizerConfig()
        assert oc.multi_seed.enabled is False
        assert oc.multi_seed.n_generate == 50
        assert oc.multi_seed.n_select == 4

    def test_n_generate_capped(self, caplog):
        """n_generate above 50 is capped with log message."""
        caplog.set_level(logging.INFO)
        c = MultiSeedConfig(n_generate=100)
        assert c.n_generate == 50
        assert "capped from 100 to 50" in caplog.text

    def test_n_generate_raised(self, caplog):
        """n_generate below n_select is raised with log message."""
        caplog.set_level(logging.INFO)
        c = MultiSeedConfig(n_generate=2, n_select=4)
        assert c.n_generate == 4
        assert "raised from 2 to 4" in caplog.text

    def test_n_select_range_too_low(self):
        """n_select < 2 raises ValueError."""
        with pytest.raises(ValueError, match="n_select must be in"):
            MultiSeedConfig(n_select=1)

    def test_n_select_range_too_high(self):
        """n_select > 10 raises ValueError."""
        with pytest.raises(ValueError, match="n_select must be in"):
            MultiSeedConfig(n_select=11)

    def test_n_select_valid_boundaries(self):
        """n_select=2 and n_select=10 are valid."""
        c2 = MultiSeedConfig(n_select=2)
        assert c2.n_select == 2
        c10 = MultiSeedConfig(n_select=10)
        assert c10.n_select == 10

    def test_enabled_field_wired_in_optimizer_config(self):
        """multi_seed.enabled can be set via OptimizerConfig."""
        oc = OptimizerConfig(
            multi_seed=MultiSeedConfig(enabled=True, n_generate=30, n_select=3)
        )
        assert oc.multi_seed.enabled is True
        assert oc.multi_seed.n_generate == 30
        assert oc.multi_seed.n_select == 3

    def test_n_generate_equal_n_select_valid(self):
        """n_generate == n_select is valid (no adjustment needed)."""
        c = MultiSeedConfig(n_generate=5, n_select=5)
        assert c.n_generate == 5
        assert c.n_select == 5


class TestMultiSeedConfigP2Knobs:
    """U11: Full config knob exposure."""

    def test_init_methods_default(self):
        c = MultiSeedConfig()
        assert c.init_methods == ["spectral", "zone_aware_spectral", "random"]

    def test_laplacian_options_default(self):
        c = MultiSeedConfig()
        assert c.laplacian_options == [True, False]

    def test_margin_options_default(self):
        c = MultiSeedConfig()
        assert c.margin_options == [0.05, 0.10, 0.20]

    def test_perturb_sigmas_default(self):
        c = MultiSeedConfig()
        assert c.perturb_sigmas == [0.0, 0.02, 0.05, 0.10]

    def test_triage_loss_weights_default(self):
        c = MultiSeedConfig()
        expected = {"wirelength": 1.0, "overlap": 1.0, "boundary": 1.0, "clearance": 1.0}
        assert c.triage_loss_weights == expected

    def test_dpp_quality_weight_default(self):
        c = MultiSeedConfig()
        assert c.dpp_quality_weight == 0.0

    def test_init_methods_custom(self):
        c = MultiSeedConfig(init_methods=["spectral", "random"])
        assert c.init_methods == ["spectral", "random"]

    def test_all_knobs_wired_in_optimizer_config(self):
        ms = MultiSeedConfig(
            init_methods=["spectral"],
            laplacian_options=[True],
            margin_options=[0.10],
            perturb_sigmas=[0.02],
            triage_loss_weights={"wirelength": 2.0, "overlap": 2.0},
            dpp_quality_weight=0.5,
        )
        oc = OptimizerConfig(multi_seed=ms)
        assert oc.multi_seed.init_methods == ["spectral"]
        assert oc.multi_seed.laplacian_options == [True]
        assert oc.multi_seed.triage_loss_weights["wirelength"] == 2.0
        assert oc.multi_seed.dpp_quality_weight == 0.5
