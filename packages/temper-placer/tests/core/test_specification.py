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
    """SafetySpec defaults are 120.0V RMS / PD3 -- this design's OWN declared
    authority, not a generic "typical consumer appliance" figure.

    120V: docs/specs/REQUIREMENTS.md REQ-SYS-01 ("AC Input Voltage: 120V RMS
    +-10%, US residential mains"); elec/src/main.ato's own
    ``v_ac_nominal = 120V`` with ``assert v_ac_nominal within 100V to 130V``
    (NEMA 5-15 tolerance); docs/hardware/VOLTAGE_DOUBLER_DESIGN.md -- the
    voltage doubler exists specifically so this appliance needs no 240V
    input. PD3: the 2026-08-15 data-driven decision
    (docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md; PR
    #1224/#1229) -- the as-built board is forced-air vented with no sealed
    compartment, so PD3 (not the PD2 the struct previously defaulted to)
    governs. Corrected 2026-08-17 from a stale 230.0/PD2 default that this
    test had been asserting -- see
    docs/evidence/2026-08-17-fact-dedup-inventory-and-gate.md and
    docs/evidence/2026-08-17-safetyspec-default-repin.md. No production code
    constructs ``SafetySpec()`` bare (production always passes explicit
    config loaded from YAML), so the stale default was a latent trap rather
    than a live divergence -- but a running test asserting the wrong value
    would have failed anyone who corrected it.
    """
    s = SafetySpec()
    assert s.mains_voltage_v == pytest.approx(120.0)
    assert s.pollution_degree == 3


def test_safety_spec_custom_values():
    """SafetySpec accepts explicit mains voltage and pollution degree."""
    s = SafetySpec(mains_voltage_v=120.0, pollution_degree=3)
    assert s.mains_voltage_v == pytest.approx(120.0)
    assert s.pollution_degree == 3


def test_pcb_spec_without_safety_defaults_to_none():
    """PcbSpecification defaults: safety is None for backward compatibility."""
    spec = PcbSpecification()
    assert spec.safety is None
