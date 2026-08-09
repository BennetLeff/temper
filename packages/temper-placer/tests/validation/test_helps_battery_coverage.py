"""Tests for validation.helps_battery module — decide_verdict."""
from temper_placer.validation.helps_battery import BatteryVerdict, decide_verdict


class TestDecideVerdict:
    """Tests for the pure decide_verdict function."""

    def test_keep_verdict(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test criterion",
        )
        assert verdict == BatteryVerdict.KEEP
        assert "KEEP" in detail

    def test_kill_margin_gain_too_low(self):
        verdict, detail = decide_verdict(
            margin_gain=0.1,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.KILL
        assert "KILL" in detail

    def test_kill_beat_cheap_too_low(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.1,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.KILL
        assert "KILL" in detail

    def test_kill_both_too_low(self):
        verdict, detail = decide_verdict(
            margin_gain=0.1,
            beats_cheap_by=0.1,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.KILL

    def test_inconclusive_budget_exceeded(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=True,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
            budget_detail="cost exceeded",
        )
        assert verdict == BatteryVerdict.INCONCLUSIVE
        assert "budget" in detail.lower()

    def test_inconclusive_no_divergence(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=False,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.INCONCLUSIVE
        assert "divergence" in detail.lower()

    def test_inconclusive_insufficient_physics(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=3,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.INCONCLUSIVE
        assert "perturbations" in detail.lower()

    def test_inconclusive_insufficient_cheap(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=3,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.INCONCLUSIVE
        assert "perturbations" in detail.lower()

    def test_keep_exact_boundary(self):
        """Test keep when margin_gain exactly equals pass_bar_x."""
        verdict, detail = decide_verdict(
            margin_gain=0.3,
            beats_cheap_by=0.3,
            n_actual_physics=5,
            n_actual_cheap=5,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
        )
        assert verdict == BatteryVerdict.KEEP

    def test_with_extra_params(self):
        """Test with the optional phys_mean/cheap_mean/primary_gate params."""
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
            phys_mean=2.5,
            cheap_mean=2.0,
            primary_gate="thermal",
        )
        assert verdict == BatteryVerdict.KEEP
        assert "thermal" in detail
        assert "2.5" in detail
        assert "2.0" in detail

    def test_inconclusive_no_divergence_with_detail(self):
        verdict, detail = decide_verdict(
            margin_gain=0.5,
            beats_cheap_by=0.5,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=False,
            budget_exceeded=False,
            pass_bar_x=0.3,
            pass_bar_y=0.3,
            kill_criterion_description="test",
            divergence_detail="field toggle is no-op",
        )
        assert verdict == BatteryVerdict.INCONCLUSIVE
        assert "no-op" in detail
