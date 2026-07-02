"""Tests for PcbSpecification loading and SafetySpec parsing."""

from pathlib import Path

import pytest

from temper_placer.core.specification import PcbSpecification, SafetySpec

# Resolve configs/ relative to the temper-placer package root.
# The test lives at tests/core/test_specification.py; go up 3 levels.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIGS_DIR = _PACKAGE_ROOT / "configs"


def test_load_pcb_spec_yaml_has_safety():
    """Happy path: PcbSpecification.load('configs/pcb_spec.yaml') reads safety section."""
    spec = PcbSpecification.load(_CONFIGS_DIR / "pcb_spec.yaml")
    assert spec.safety is not None
    assert spec.safety.mains_voltage_v == pytest.approx(230.0)
    assert spec.safety.pollution_degree == 2


def test_load_pcb_spec_yaml_name():
    """The loaded spec has the correct design name."""
    spec = PcbSpecification.load(_CONFIGS_DIR / "pcb_spec.yaml")
    assert spec.name == "Temper V1"


def test_safety_spec_defaults():
    """SafetySpec default values match IEC 60335-1 typical consumer appliance."""
    s = SafetySpec()
    assert s.mains_voltage_v == pytest.approx(230.0)
    assert s.pollution_degree == 2


def test_safety_spec_custom_values():
    """SafetySpec accepts explicit mains voltage and pollution degree."""
    s = SafetySpec(mains_voltage_v=120.0, pollution_degree=3)
    assert s.mains_voltage_v == pytest.approx(120.0)
    assert s.pollution_degree == 3


def test_pcb_spec_without_safety_defaults_to_none():
    """PcbSpecification defaults: safety is None for backward compatibility."""
    spec = PcbSpecification()
    assert spec.safety is None
