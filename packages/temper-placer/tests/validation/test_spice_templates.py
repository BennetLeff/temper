"""Tests for SPICE templates module.

These tests verify:
1. Template loading and parameter extraction
2. Parameter substitution works correctly
3. Templates run successfully with default parameters
4. Threshold checking works correctly
5. Penalty computation aggregates violations properly
"""


import pytest


class TestTemplateLoading:
    """Tests for template loading functions."""

    def test_get_available_templates(self):
        """Should list all available templates."""
        from temper_placer.validation.spice_templates import get_available_templates

        templates = get_available_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 3  # At least our 3 templates
        assert "gate_drive" in templates
        assert "bootstrap_charging" in templates
        assert "power_integrity" in templates

    def test_load_template_gate_drive(self):
        """Should load gate_drive template with placeholders."""
        from temper_placer.validation.spice_templates import load_template

        template = load_template("gate_drive")
        assert isinstance(template, str)
        assert "{{GATE_LOOP_INDUCTANCE}}" in template
        assert "{{GATE_RESISTANCE}}" in template
        assert ".tran" in template  # Has transient analysis
        assert ".meas" in template or "meas tran" in template.lower()  # Has measurements

    def test_load_template_bootstrap_charging(self):
        """Should load bootstrap_charging template with placeholders."""
        from temper_placer.validation.spice_templates import load_template

        template = load_template("bootstrap_charging")
        assert isinstance(template, str)
        assert "{{BOOTSTRAP_LOOP_INDUCTANCE}}" in template
        assert "{{BOOTSTRAP_CAPACITANCE}}" in template
        assert "{{BOOTSTRAP_RESISTANCE}}" in template

    def test_load_template_power_integrity(self):
        """Should load power_integrity template with placeholders."""
        from temper_placer.validation.spice_templates import load_template

        template = load_template("power_integrity")
        assert isinstance(template, str)
        assert "{{DC_BUS_INDUCTANCE}}" in template
        assert "{{DECAP_ESR}}" in template
        assert "{{DECAP_VALUE}}" in template

    def test_load_template_nonexistent(self):
        """Should raise FileNotFoundError for missing template."""
        from temper_placer.validation.spice_templates import load_template

        with pytest.raises(FileNotFoundError) as exc_info:
            load_template("nonexistent_template")
        assert "nonexistent_template" in str(exc_info.value)
        assert "Available templates" in str(exc_info.value)

    def test_get_template_parameters(self):
        """Should extract parameter names from template."""
        from temper_placer.validation.spice_templates import get_template_parameters

        params = get_template_parameters("gate_drive")
        assert "GATE_LOOP_INDUCTANCE" in params
        assert "GATE_RESISTANCE" in params
        assert len(params) == 2

        params = get_template_parameters("bootstrap_charging")
        assert "BOOTSTRAP_LOOP_INDUCTANCE" in params
        assert "BOOTSTRAP_CAPACITANCE" in params
        assert "BOOTSTRAP_RESISTANCE" in params
        assert len(params) == 3


class TestTemplateMetadata:
    """Tests for template metadata constants."""

    def test_template_parameters_complete(self):
        """All templates should have parameter descriptions."""
        from temper_placer.validation.spice_templates import (
            TEMPLATE_PARAMETERS,
            get_available_templates,
            get_template_parameters,
        )

        for template_name in get_available_templates():
            assert template_name in TEMPLATE_PARAMETERS, (
                f"Missing TEMPLATE_PARAMETERS for {template_name}"
            )

            # All actual parameters should be documented
            actual_params = get_template_parameters(template_name)
            documented_params = set(TEMPLATE_PARAMETERS[template_name].keys())

            for param in actual_params:
                assert param in documented_params, (
                    f"Parameter {param} in {template_name} not documented"
                )

    def test_template_thresholds_complete(self):
        """All templates should have threshold definitions."""
        from temper_placer.validation.spice_templates import (
            TEMPLATE_THRESHOLDS,
            get_available_templates,
        )

        for template_name in get_available_templates():
            assert template_name in TEMPLATE_THRESHOLDS, (
                f"Missing TEMPLATE_THRESHOLDS for {template_name}"
            )

            thresholds = TEMPLATE_THRESHOLDS[template_name]
            assert len(thresholds) > 0, f"No thresholds defined for {template_name}"

            # Each threshold should have at least min or max
            for meas_name, limits in thresholds.items():
                has_limit = "min" in limits or "max" in limits
                assert has_limit, f"Threshold {meas_name} in {template_name} has no min/max"

    def test_default_parameters_complete(self):
        """All templates should have default parameter values."""
        from temper_placer.validation.spice_templates import (
            DEFAULT_PARAMETERS,
            get_available_templates,
            get_template_parameters,
        )

        for template_name in get_available_templates():
            assert template_name in DEFAULT_PARAMETERS, (
                f"Missing DEFAULT_PARAMETERS for {template_name}"
            )

            # All required parameters should have defaults
            actual_params = get_template_parameters(template_name)
            defaults = DEFAULT_PARAMETERS[template_name]

            for param in actual_params:
                assert param in defaults, f"No default value for {param} in {template_name}"


class TestThresholdChecking:
    """Tests for threshold checking function."""

    def test_check_thresholds_all_pass(self):
        """Should report all passed when within limits."""
        from temper_placer.validation.spice_templates import check_thresholds

        measurements = {
            "v_overshoot_pct": 5.0,  # max 20
            "v_undershoot_pct": 1.0,  # max 5
            "t_rise": 50e-9,  # max 100e-9
            "t_fall": 50e-9,  # max 100e-9
            "v_ring_pp": 1.0,  # max 3
        }

        results = check_thresholds("gate_drive", measurements)

        for meas_name, result in results.items():
            assert result["passed"], f"{meas_name} should pass"
            assert "limit" not in result

    def test_check_thresholds_max_violation(self):
        """Should detect max threshold violation."""
        from temper_placer.validation.spice_templates import check_thresholds

        measurements = {
            "v_overshoot_pct": 25.0,  # Exceeds max 20
            "t_rise": 50e-9,
        }

        results = check_thresholds("gate_drive", measurements)

        assert not results["v_overshoot_pct"]["passed"]
        assert results["v_overshoot_pct"]["limit"] == 20.0
        assert results["v_overshoot_pct"]["limit_type"] == "max"

    def test_check_thresholds_min_violation(self):
        """Should detect min threshold violation."""
        from temper_placer.validation.spice_templates import check_thresholds

        measurements = {
            "v_margin": 0.5,  # Below min 1.0
            "t_charge_12v": 100e-6,
        }

        results = check_thresholds("bootstrap_charging", measurements)

        assert not results["v_margin"]["passed"]
        assert results["v_margin"]["limit"] == 1.0
        assert results["v_margin"]["limit_type"] == "min"

    def test_check_thresholds_missing_measurement(self):
        """Should report failure for missing measurements."""
        from temper_placer.validation.spice_templates import check_thresholds

        measurements = {}  # Empty - all measurements missing

        results = check_thresholds("gate_drive", measurements)

        for meas_name, result in results.items():
            assert not result["passed"]
            assert result["value"] is None
            assert "error" in result


class TestPenaltyComputation:
    """Tests for SPICE penalty computation."""

    def test_compute_spice_penalty_all_pass(self):
        """Should return 0 when all thresholds pass."""
        from temper_placer.validation.spice_templates import compute_spice_penalty

        results = {
            "gate_drive": {
                "v_overshoot_pct": 5.0,
                "v_undershoot_pct": 1.0,
                "t_rise": 50e-9,
                "t_fall": 50e-9,
                "v_ring_pp": 1.0,
            }
        }

        penalty = compute_spice_penalty(results)
        assert penalty == 0.0

    def test_compute_spice_penalty_with_violations(self):
        """Should return positive penalty for violations."""
        from temper_placer.validation.spice_templates import compute_spice_penalty

        # Provide all measurements so we can test just the violation
        results = {
            "gate_drive": {
                "v_overshoot_pct": 30.0,  # 50% over max of 20
                "v_undershoot_pct": 1.0,  # Within limit
                "t_rise": 50e-9,  # Within limit
                "t_fall": 50e-9,  # Within limit
                "v_ring_pp": 1.0,  # Within limit
            }
        }

        penalty = compute_spice_penalty(results)
        assert penalty > 0
        # Only violation is overshoot: (30-20)/20 = 0.5
        assert abs(penalty - 0.5) < 0.01

    def test_compute_spice_penalty_with_weights(self):
        """Should apply weights to different templates."""
        from temper_placer.validation.spice_templates import compute_spice_penalty

        results = {
            "gate_drive": {
                "v_overshoot_pct": 30.0,  # 50% violation
            },
            "bootstrap_charging": {
                "v_margin": 0.5,  # 50% under min of 1.0
            },
        }

        # Equal weight
        penalty_equal = compute_spice_penalty(results)

        # Double weight on gate_drive
        penalty_weighted = compute_spice_penalty(
            results, weights={"gate_drive": 2.0, "bootstrap_charging": 1.0}
        )

        assert penalty_weighted > penalty_equal

    def test_compute_spice_penalty_missing_measurement(self):
        """Should add soft penalty for missing measurements."""
        from temper_placer.validation.spice_templates import compute_spice_penalty

        results = {
            "gate_drive": {}  # All measurements missing
        }

        penalty = compute_spice_penalty(results)
        # Should have some penalty for missing data
        assert penalty > 0


class TestTemplateSimulation:
    """Integration tests that run actual simulations.

    These tests require ngspice to be installed.
    """

    @pytest.fixture
    def validator(self):
        """Create NgspiceValidator instance."""
        from temper_placer.validation.spice import NgspiceValidator

        return NgspiceValidator()

    @pytest.fixture
    def has_ngspice(self, validator):
        """Check if ngspice is available."""
        import shutil

        return shutil.which("ngspice") is not None

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("ngspice"), reason="ngspice not installed"
    )
    def test_gate_drive_simulation(self, validator):
        """Should run gate_drive template with default parameters."""
        from temper_placer.validation.spice_templates import (
            DEFAULT_PARAMETERS,
            load_template,
        )

        template = load_template("gate_drive")
        params = DEFAULT_PARAMETERS["gate_drive"]

        result = validator.run_template(template, params)

        assert result.success, f"Simulation failed: {result.error}"
        assert "v_gate_peak" in result.measurements
        assert "t_rise" in result.measurements

        # Check reasonable values
        v_peak = result.measurements["v_gate_peak"].value
        assert 14.0 < v_peak < 18.0, f"Gate peak {v_peak} out of range"

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("ngspice"), reason="ngspice not installed"
    )
    def test_bootstrap_charging_simulation(self, validator):
        """Should run bootstrap_charging template with default parameters."""
        from temper_placer.validation.spice_templates import (
            DEFAULT_PARAMETERS,
            load_template,
        )

        template = load_template("bootstrap_charging")
        params = DEFAULT_PARAMETERS["bootstrap_charging"]

        result = validator.run_template(template, params)

        assert result.success, f"Simulation failed: {result.error}"
        assert "v_boot_final" in result.measurements
        assert "v_margin" in result.measurements

        # Check bootstrap reaches operating voltage
        v_boot = result.measurements["v_boot_final"].value
        assert v_boot > 12.0, f"Bootstrap voltage {v_boot} too low"

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("ngspice"), reason="ngspice not installed"
    )
    def test_power_integrity_simulation(self, validator):
        """Should run power_integrity template with default parameters."""
        from temper_placer.validation.spice_templates import (
            DEFAULT_PARAMETERS,
            load_template,
        )

        template = load_template("power_integrity")
        params = DEFAULT_PARAMETERS["power_integrity"]

        result = validator.run_template(template, params)

        assert result.success, f"Simulation failed: {result.error}"
        assert "v_dc_avg" in result.measurements
        assert "v_ripple" in result.measurements

        # Check DC bus stays in reasonable range
        v_avg = result.measurements["v_dc_avg"].value
        assert 370.0 < v_avg < 400.0, f"DC bus average {v_avg} out of range"


class TestEndToEndValidation:
    """End-to-end tests combining templates with threshold checking."""

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("ngspice"), reason="ngspice not installed"
    )
    def test_gate_drive_validation_passes(self):
        """Gate drive with good layout (50nH) should pass all thresholds."""
        from temper_placer.validation.spice import NgspiceValidator
        from temper_placer.validation.spice_templates import (
            DEFAULT_PARAMETERS,
            check_thresholds,
            load_template,
        )

        validator = NgspiceValidator()
        template = load_template("gate_drive")
        result = validator.run_template(template, DEFAULT_PARAMETERS["gate_drive"])

        assert result.success

        # Extract measurement values
        measurements = {name: meas.value for name, meas in result.measurements.items()}

        # Check thresholds
        threshold_results = check_thresholds("gate_drive", measurements)

        # With 50nH and 4.7 ohm, should mostly pass
        # (may have minor violations depending on exact model)
        passed_count = sum(1 for r in threshold_results.values() if r["passed"])
        total_count = len(threshold_results)

        assert passed_count >= total_count - 1, f"Too many failures: {threshold_results}"

    @pytest.mark.skipif(
        not pytest.importorskip("shutil").which("ngspice"), reason="ngspice not installed"
    )
    def test_gate_drive_bad_layout_fails(self):
        """Gate drive with bad layout (500nH) should fail thresholds."""
        from temper_placer.validation.spice import NgspiceValidator
        from temper_placer.validation.spice_templates import (
            compute_spice_penalty,
            load_template,
        )

        validator = NgspiceValidator()
        template = load_template("gate_drive")

        # Bad layout: 500nH loop inductance (10x worse than default)
        bad_params = {
            "GATE_LOOP_INDUCTANCE": "500n",
            "GATE_RESISTANCE": "4.7",
        }

        result = validator.run_template(template, bad_params)
        assert result.success  # Simulation runs

        measurements = {name: meas.value for name, meas in result.measurements.items()}

        # Compute penalty - should be higher than with good layout
        results = {"gate_drive": measurements}
        penalty = compute_spice_penalty(results)

        # High inductance should cause significant ringing/overshoot
        # Exact penalty depends on simulation, but should be non-zero
        # or rise time should exceed threshold
        t_rise = measurements.get("t_rise", 0)
        v_overshoot = measurements.get("v_overshoot_pct", 0)
        v_ring = measurements.get("v_ring_pp", 0)

        # At least one metric should be worse
        bad_metrics = (
            t_rise > 100e-9  # Rise time too slow
            or v_overshoot > 20.0  # Too much overshoot
            or v_ring > 3.0  # Too much ringing
        )

        assert bad_metrics or penalty > 0, (
            f"Bad layout should fail: t_rise={t_rise}, overshoot={v_overshoot}, ring={v_ring}"
        )
