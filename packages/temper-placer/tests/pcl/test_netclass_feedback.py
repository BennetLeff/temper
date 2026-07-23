"""Test feedback handler with DesignRules."""

from pathlib import Path

import pytest

RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"


@pytest.fixture
def design_rules():
    from temper_placer.io.netclass_loader import load_netclass_rules

    return load_netclass_rules(RULES_PATH).design_rules


class TestFeedbackHandler:
    def test_yaml_loaded_hv_signal_violation_uses_yaml_value(self, design_rules):
        from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

        fc = FeedbackClassifier(design_rules=design_rules)
        violation = type(
            "Violation",
            (),
            {
                "comp_a": "U_HV",
                "comp_b": "U_SIG",
                "required_mm": 5.8,
                "net_a": "DC_BUS+",  # HighVoltage
                "net_b": "SPI_CLK",  # Signal
            },
        )()
        delta = fc._handle_clearance_violation(violation)
        assert delta is not None
        assert delta.constraint.min_distance_mm == 6.0  # YAML value, not 5.8

    def test_no_yaml_falls_back_to_violation_required_mm(self):
        from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

        fc = FeedbackClassifier(design_rules=None)
        violation = type(
            "Violation",
            (),
            {
                "comp_a": "U1",
                "comp_b": "U2",
                "required_mm": 5.8,
            },
        )()
        delta = fc._handle_clearance_violation(violation)
        assert delta is not None
        assert delta.constraint.min_distance_mm == 5.8  # fallback

    def test_yaml_loaded_carries_because_text(self, design_rules):
        from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

        fc = FeedbackClassifier(design_rules=design_rules)
        violation = type(
            "Violation",
            (),
            {
                "comp_a": "U_HV",
                "comp_b": "U_SIG",
                "required_mm": 5.8,
                "net_a": "AC_L",  # ACMains (maps to HV type)
                "net_b": "SPI_CLK",  # Signal
            },
        )()
        delta = fc._handle_clearance_violation(violation)
        assert delta is not None
        # The because text should come from the class_pairs entry for ACMains-Signal
        assert "IEC 60335" in delta.constraint.because
