"""Tests for validation.spice_templates module."""
from temper_placer.validation.spice_templates import (
    check_thresholds,
    compute_spice_penalty,
    get_available_templates,
    get_template_parameters,
    load_template,
)


class TestSpiceTemplates:
    """Tests for spice_templates module functions."""

    def test_get_available_templates(self):
        templates = get_available_templates()
        assert isinstance(templates, list)

    def test_get_template_parameters(self):
        templates = get_available_templates()
        if templates:
            params = get_template_parameters(templates[0])
            # Returns a list of parameter names
            assert isinstance(params, list)

    def test_load_template(self):
        templates = get_available_templates()
        if templates:
            content = load_template(templates[0])
            assert isinstance(content, str)

    def test_check_thresholds_returns_dict(self):
        result = check_thresholds("gate_drive", {})
        assert isinstance(result, dict)

    def test_compute_spice_penalty(self):
        result = compute_spice_penalty({})
        assert isinstance(result, float)
        assert result == 0.0  # No violations

    def test_load_template_nonexistent(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent_template")
