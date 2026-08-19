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

    # -----------------------------------------------------------------
    # ADDED 2026-08-19 (docs/evidence/2026-08-19-is-hv-net-blast-radius.md).
    #
    # `_handle_clearance_violation` now classifies through
    # `design_rules.get_rules_for_net()` instead of the net-NAME keyword
    # heuristic. `get_rules_for_net` returns "Default" for an unassigned
    # LV net, but `netclass_rules.yaml`'s `class_pairs` table spells that
    # bucket "Signal" -- so without the `"Default" -> "Signal"`
    # normalization that `netclass_constraints._pin_class_infos` already
    # applies (PR #1323), every HV<->LV `class_pairs` row would MISS and
    # the injected separation would drop from the table's 6.0mm to
    # `max(HV.clearance, Default.clearance)` = 2.0mm.
    #
    # This test is the ratchet against that. It fails (2.0 < 6.0) if the
    # normalization is removed.
    # -----------------------------------------------------------------

    @pytest.mark.parametrize(
        ("hv_net", "hv_class"),
        [
            ("AC_L", "ACMains"),
            ("ac_l", "ACMains"),
            ("DC_BUS+", "HighVoltage"),
            ("+170V_BUS", "HighVoltage"),
            ("DC_BUS_RTN", "HighVoltage"),
            ("hb-gnd", "HighVoltage"),
            ("tank-out", "HighVoltage"),
            ("tank.c_tank1-p2", "HighVoltageTank"),
        ],
    )
    def test_hv_to_unassigned_lv_never_loosens_below_the_class_pairs_row(
        self, design_rules, hv_net, hv_class
    ):
        """An HV net against an UNASSIGNED LV net must still get the
        ``class_pairs`` HV<->Signal figure, not the per-class max."""
        from temper_placer.placer.cp_sat.feedback import FeedbackClassifier

        assert design_rules.get_rules_for_net(hv_net).name == hv_class
        assert design_rules.get_rules_for_net("SPI_CLK").name == "Default", (
            "premise stale: SPI_CLK is no longer an unassigned net"
        )
        expected = design_rules.class_pairs[tuple(sorted([hv_class, "Signal"]))]["clearance"]

        fc = FeedbackClassifier(design_rules=design_rules)
        violation = type(
            "Violation",
            (),
            {
                "comp_a": "U_HV",
                "comp_b": "U_SIG",
                "required_mm": 0.1,
                "net_a": hv_net,
                "net_b": "SPI_CLK",
            },
        )()
        delta = fc._handle_clearance_violation(violation)
        assert delta is not None
        assert delta.constraint.min_distance_mm >= expected, (
            f"{hv_net} ({hv_class}) vs unassigned SPI_CLK loosened to "
            f"{delta.constraint.min_distance_mm}mm, below the class_pairs "
            f"{hv_class}-Signal figure of {expected}mm"
        )
