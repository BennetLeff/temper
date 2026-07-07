"""Tests for U5: Feedback handler reads YAML authority for clearance violations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from temper_placer.core.netclass_rules import load_netclass_rules
from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

YAML_PATH = (
    Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"
)


@dataclass
class MockDrcViolation:
    comp_a: str | None = None
    comp_b: str | None = None
    components: list[str] = field(default_factory=list)
    location: tuple[float, float] = (0.0, 0.0)
    message: str = "clearance violation"
    required_mm: float = 6.0
    net_name: str = ""
    net_a: str | None = None
    net_b: str | None = None


@dataclass
class MockPlacement:
    positions: list = field(default_factory=list)
    placed_refs: list[str] = field(default_factory=list)


# -------------------------------------------------------------------
# U5.1: With YAML loaded, HV-Signal violation uses YAML authority
# -------------------------------------------------------------------


def test_yaml_loaded_hv_signal_violation_uses_yaml_value():
    """HV-Signal violation at 5.8mm -> handler injects 6.0mm (YAML value)."""
    rules = load_netclass_rules(YAML_PATH)
    classifier = FeedbackClassifier(netclass_rules=rules)

    violation = MockDrcViolation(
        comp_a="Q1",
        comp_b="C_BUS1",
        required_mm=5.8,
        net_a="DC_BUS+",   # resolves to HighVoltage via TEMPER_NET_ASSIGNMENTS
        net_b="SDA",        # resolves to Signal via heuristic
    )

    delta = classifier._handle_clearance_violation(violation)
    assert delta is not None
    assert delta.constraint.a == "Q1"
    assert delta.constraint.b == "C_BUS1"
    assert delta.constraint.min_distance_mm == 6.0
    assert delta.priority == 5


# -------------------------------------------------------------------
# U5.2: Without YAML, handler falls back to violation.required_mm
# -------------------------------------------------------------------


def test_no_yaml_falls_back_to_violation_required_mm():
    """Without YAML (netclass_rules=None), handler uses violation.required_mm."""
    classifier = FeedbackClassifier()
    violation = MockDrcViolation(
        comp_a="Q1",
        comp_b="Q2",
        required_mm=5.8,
    )

    delta = classifier._handle_clearance_violation(violation)
    assert delta is not None
    assert delta.constraint.min_distance_mm == 5.8


# -------------------------------------------------------------------
# U5.3: With YAML, safety-critical pair carries because text
# -------------------------------------------------------------------


def test_yaml_loaded_safety_critical_pair_carries_because_text():
    """Safety-critical pair (HighVoltage-Signal) constraint carries because text."""
    rules = load_netclass_rules(YAML_PATH)
    classifier = FeedbackClassifier(netclass_rules=rules)

    violation = MockDrcViolation(
        comp_a="Q1",
        comp_b="U_MCU",
        required_mm=6.0,
        net_a="DC_BUS+",
        net_b="SDA",
    )

    delta = classifier._handle_clearance_violation(violation)
    assert delta is not None
    assert delta.constraint.min_distance_mm == 6.0
    assert "IEC" in delta.constraint.because
    assert "60335" in delta.constraint.because


# -------------------------------------------------------------------
# U5.4: With YAML but no net names, falls back to Signal-Signal
# -------------------------------------------------------------------


def test_yaml_loaded_no_net_names_uses_signal_signal_fallback():
    """When violation has no net names, both sides fall back to Signal class."""
    rules = load_netclass_rules(YAML_PATH)
    classifier = FeedbackClassifier(netclass_rules=rules)

    violation = MockDrcViolation(
        comp_a="R1",
        comp_b="R2",
        required_mm=0.2,
        net_name="",  # empty string -> resolves to Signal
    )

    delta = classifier._handle_clearance_violation(violation)
    assert delta is not None
    assert delta.constraint.min_distance_mm == 0.15  # Signal-Signal self-clearance
