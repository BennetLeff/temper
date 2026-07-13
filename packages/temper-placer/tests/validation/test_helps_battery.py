"""Tests for helps_battery.py — U3 A/B harness with kill-capable verdict."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from temper_placer.regression.physics_oracle import PhysicsOracleResult
from temper_placer.validation.helps_battery import (
    ArmRunResult,
    BatteryVerdict,
    HelpsBatteryResult,
    _assert_divergence,
    _resolve_primary_gate,
    run_helps_battery,
)
from temper_placer.validation.prereg.schema import (
    BecauseThreshold,
    CheapBaseline,
    CostBudget,
    FieldPreregistration,
    KillCriterion,
    ParametricRange,
    PassBar,
    PreregistrationManifest,
    StructuralBoundingCase,
)
from temper_placer.validation.scorecard import GateMargin, MarginScorecard


# ---------------------------------------------------------------------------
# Synthetic helpers — build prereg + scorecards without real placement
# ---------------------------------------------------------------------------


def _thermal_prereg(
    *,
    created_at: str | None = None,
    version: int = 1,
) -> PreregistrationManifest:
    """Build a minimal thermal pre-registration manifest."""
    ts = created_at or "2026-07-01T00:00:00Z"
    return PreregistrationManifest.model_validate({
        "version": version,
        "created_at": ts,
        "fields": [
            {
                "field_name": "thermal",
                "independent_instrument": "physics_oracle",
                "cheap_baseline": {
                    "name": "uniform_heat_spread",
                    "description": "Uniform placement",
                    "metric": "thermal_score",
                    "target_value": 0.0,
                    "because": "Baseline",
                },
                "parametric_ranges": [
                    {
                        "parameter": "heatspread",
                        "min": 5.0,
                        "max": 40.0,
                        "because": "Cover range",
                    },
                ],
                "structural_bounding_cases": [
                    {
                        "case_name": "single_igbt",
                        "description": "Minimum config",
                        "because": "Required",
                    },
                ],
                "pass_bar": {
                    "margin_gain": {"name": "X", "value": 0.10, "because": "Meaningful improvement"},
                    "beat_cheap_baseline_by": {"name": "Y", "value": 0.05, "because": "Measurable"},
                    "across_perturbations": {"name": "N", "value": 5.0, "because": "Statistical confidence"},
                },
                "kill_criterion": {
                    "description": "Any pass-bar violation kills the field",
                    "because": "Safety-critical",
                },
                "cost_budget": {
                    "max_total_battery_seconds": 3600.0,
                    "max_rounds_budget": 20,
                    "field_convergence_round_limit": 5,
                    "thermal_grid_cells_max": 10000,
                    "target_solve_time_ms_per_field": 5000.0,
                },
            },
        ],
    })


def _fake_scorecard(
    thermal_margin: float,
    *,
    board_id: str = "test",
    scorer_id: str = "physics_oracle",
) -> MarginScorecard:
    """Build a synthetic scorecard with one scorable thermal gate."""
    return MarginScorecard(
        board_id=board_id,
        scorer_id=scorer_id,
        margins=[
            GateMargin(
                gate_name="thermal",
                value=thermal_margin,
                unit="mm",
                raw_score=0.5,
                is_scorable=True,
            ),
        ],
    )


def _fake_placement(*, positions: list[list[float]] | None = None) -> object:
    """Return a synthetic placement object with a .positions attribute."""

    class _FakePlacement:
        def __init__(self, pos):
            self.positions = np.array(pos, dtype=np.float32) if pos else np.empty((0, 2), dtype=np.float32)

    return _FakePlacement(positions)


# ---------------------------------------------------------------------------
# Unit: divergence assertion
# ---------------------------------------------------------------------------


class TestDivergenceAssertion:
    """A/B divergence: physics-field vs no-field must produce different layouts."""

    def test_identical_placements_are_noop(self):
        """Identical placements → divergence fails → field toggle is a no-op."""
        pos = [[10.0, 20.0]]
        p1 = _fake_placement(positions=pos)
        p2 = _fake_placement(positions=pos)

        ok, detail = _assert_divergence([p1], [p2])
        assert not ok
        assert "NO-OP" in detail

    def test_different_placements_pass_divergence(self):
        """Different placements → divergence passes."""
        p1 = _fake_placement(positions=[[10.0, 20.0]])
        p2 = _fake_placement(positions=[[30.0, 40.0]])

        ok, detail = _assert_divergence([p1], [p2])
        assert ok
        assert "1/1" in detail

    def test_mixed_divergence_requires_half_different(self):
        """At least 50% must differ for divergence to pass."""
        pos_a = [[10.0, 20.0]]
        pos_b = [[30.0, 40.0]]
        p1 = _fake_placement(positions=pos_a)
        p2 = _fake_placement(positions=pos_b)
        p3 = _fake_placement(positions=pos_a)

        # physics=[p1,p2], no_field=[p1,p3]
        # p1 vs p1: equal. p2 vs p3: different.
        # 1/2 = 50% → passes at >= 0.5
        ok, _ = _assert_divergence([p1, p2], [p1, p3])
        assert ok  # 50% >= 50%

    def test_below_half_is_noop(self):
        """Less than 50% different → divergence fails."""
        pa = _fake_placement(positions=[[10.0, 20.0]])
        pb = _fake_placement(positions=[[30.0, 40.0]])
        pc = _fake_placement(positions=[[50.0, 60.0]])
        pc2 = _fake_placement(positions=[[50.0, 60.0]])  # same positions as pc
        pd = _fake_placement(positions=[[70.0, 80.0]])

        # physics=[pa, pb, pc, pd], no_field=[pa, pb, pc2, pc2]
        # pa==pa, pb==pb, pc==pc2, pd!=pc2 → 1/4 = 25% < 50%
        ok, detail = _assert_divergence([pa, pb, pc, pd], [pa, pb, pc2, pc2])
        assert not ok
        assert "NO-OP" in detail

    def test_empty_lists_no_divergence(self):
        """Empty placement lists → divergence fails gracefully."""
        ok, detail = _assert_divergence([], [])
        assert not ok
        assert "No placements" in detail


# ---------------------------------------------------------------------------
# Unit: primary gate resolution
# ---------------------------------------------------------------------------


class TestResolvePrimaryGate:
    """Primary gate resolution from pre-registration metadata."""

    def test_uses_metric_to_gate_mapping(self):
        """Cheap baseline metric 'thermal_score' → gate 'thermal'."""
        prereg = FieldPreregistration.model_validate({
            "field_name": "thermal",
            "independent_instrument": "physics_oracle",
            "cheap_baseline": {
                "name": "test",
                "description": "test",
                "metric": "thermal_score",
                "target_value": 0.0,
                "because": "test",
            },
            "parametric_ranges": [],
            "structural_bounding_cases": [{"case_name": "c", "description": "d", "because": "b"}],
            "pass_bar": {
                "margin_gain": {"value": 0.1, "because": "b"},
                "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
                "across_perturbations": {"value": 5, "because": "b"},
            },
            "kill_criterion": {"description": "k", "because": "b"},
            "cost_budget": {
                "max_total_battery_seconds": 3600,
                "max_rounds_budget": 20,
                "field_convergence_round_limit": 5,
                "thermal_grid_cells_max": 10000,
                "target_solve_time_ms_per_field": 5000,
            },
        })
        gate = _resolve_primary_gate(
            prereg,
            no_field={"thermal": [1.0]},
            cheap={"thermal": [0.5]},
            physics={"thermal": [2.0]},
        )
        assert gate == "thermal"

    def test_fallback_to_common_gate(self):
        """When metric mapping doesn't match, use first common gate."""
        prereg = FieldPreregistration.model_validate({
            "field_name": "clearance",
            "independent_instrument": "physics_oracle",
            "cheap_baseline": {
                "name": "test",
                "description": "test",
                "metric": "unknown_metric",
                "target_value": 0.0,
                "because": "test",
            },
            "parametric_ranges": [],
            "structural_bounding_cases": [{"case_name": "c", "description": "d", "because": "b"}],
            "pass_bar": {
                "margin_gain": {"value": 0.1, "because": "b"},
                "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
                "across_perturbations": {"value": 5, "because": "b"},
            },
            "kill_criterion": {"description": "k", "because": "b"},
            "cost_budget": {
                "max_total_battery_seconds": 3600,
                "max_rounds_budget": 20,
                "field_convergence_round_limit": 5,
                "thermal_grid_cells_max": 10000,
                "target_solve_time_ms_per_field": 5000,
            },
        })
        gate = _resolve_primary_gate(
            prereg,
            no_field={"hv_lv_clearance": [1.0], "thermal": [0.5]},
            cheap={"hv_lv_clearance": [0.8], "thermal": [0.3]},
            physics={"hv_lv_clearance": [1.2], "thermal": [0.7]},
        )
        assert gate == "hv_lv_clearance"  # alphabetically first common

    def test_fallback_to_field_name(self):
        """When no common gates exist, fall back to field name."""
        prereg = FieldPreregistration.model_validate({
            "field_name": "my_field",
            "independent_instrument": "physics_oracle",
            "cheap_baseline": {
                "name": "test",
                "description": "test",
                "metric": "unknown",
                "target_value": 0.0,
                "because": "test",
            },
            "parametric_ranges": [],
            "structural_bounding_cases": [{"case_name": "c", "description": "d", "because": "b"}],
            "pass_bar": {
                "margin_gain": {"value": 0.1, "because": "b"},
                "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
                "across_perturbations": {"value": 5, "because": "b"},
            },
            "kill_criterion": {"description": "k", "because": "b"},
            "cost_budget": {
                "max_total_battery_seconds": 3600,
                "max_rounds_budget": 20,
                "field_convergence_round_limit": 5,
                "thermal_grid_cells_max": 10000,
                "target_solve_time_ms_per_field": 5000,
            },
        })
        gate = _resolve_primary_gate(
            prereg,
            no_field={"gate_a": [1.0]},
            cheap={"gate_a": [0.5]},
            physics={"gate_b": [2.0]},
        )
        assert gate == "my_field"


# ---------------------------------------------------------------------------
# Happy: verdict KEEP
# ---------------------------------------------------------------------------


class TestVerdictKeep:
    """Physics beats cheap by >= Y over >= N perturbations with no regression."""

    def test_keep_when_physics_beats_cheap(self):
        """Synthetic arms: physics margin > cheap margin above thresholds."""
        manifest = _thermal_prereg()

        # Tracked: per arm per perturbation, we build placements that diverge.
        placements_log: list[object] = []

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            # Produce different positions per arm so divergence passes.
            if arm_id == "physics_field":
                p = _fake_placement(positions=[[1.0 + pert_idx, 2.0]])
            elif arm_id == "cheap_heuristic":
                p = _fake_placement(positions=[[3.0 + pert_idx, 4.0]])
            else:
                p = _fake_placement(positions=[[5.0 + pert_idx, 6.0]])
            placements_log.append(p)
            return p

        def score_placement(placement, board, netlist):
            # physics_field: margin 0.30, cheap: margin 0.10, no_field: margin 0.05
            idx = len(placements_log) - 1
            # Arms run in order: no_field, cheap_heuristic, physics_field per perturbation
            arm_order = idx % 3
            if arm_order == 0:  # no_field
                margin = 0.05
            elif arm_order == 1:  # cheap_heuristic
                margin = 0.10
            else:  # physics_field
                margin = 0.30
            return _fake_scorecard(margin)

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.KEEP, f"Expected KEEP, got {result.verdict}: {result.verdict_details}"
        assert "KEEP" in result.verdict_details
        assert result.divergence_detected
        assert not result.budget_exceeded

    def test_keep_uses_prereg_default_n(self):
        """When n_perturbations is None, uses prereg N value (5)."""
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            return _fake_placement(positions=[[float(pert_idx + {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]), 0.0]])

        call_count = {"count": 0}

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
        )

        assert result.verdict == BatteryVerdict.KEEP
        assert result.n_perturbations == 5  # from prereg


# ---------------------------------------------------------------------------
# Happy: verdict KILL (the harness must be ABLE to return kill)
# ---------------------------------------------------------------------------


class TestVerdictKill:
    """The harness CAN and DOES return KILL when the field fails its pass bar."""

    def test_kill_when_cheap_captures_benefit(self):
        """Cheap == physics (or physics worse) → margin_gain < X → KILL."""
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx + offset), 0.0]])

        call_count = {"count": 0}

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            # physics and cheap produce the same margin → no gain
            margins = {0: 0.05, 1: 0.30, 2: 0.30}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.KILL, (
            f"Expected KILL, got {result.verdict}: {result.verdict_details}"
        )
        assert "KILL" in result.verdict_details
        assert "margin_gain=" in result.verdict_details

    def test_kill_when_physics_is_worse_than_cheap(self):
        """Physics underperforms cheap → KILL."""
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx + offset), 0.0]])

        call_count = {"count": 0}

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            # physics is WORSE than cheap
            margins = {0: 0.01, 1: 0.50, 2: 0.15}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.KILL
        # margin_gain = 0.15 - 0.50 = -0.35 < 0.10 (X) → kill
        assert result.verdict_details.startswith("KILL")


# ---------------------------------------------------------------------------
# Edge: divergence no-op
# ---------------------------------------------------------------------------


class TestVerdictNoopDivergence:
    """Identical output across arms → divergence failure, not a pass."""

    def test_identical_placements_across_arms_is_inconclusive(self):
        """When all arms produce the same layout, verdict is INCONCLUSIVE."""
        manifest = _thermal_prereg()

        shared_pos = [[10.0, 20.0]]

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            return _fake_placement(positions=shared_pos)

        def score_placement(placement, board, netlist):
            return _fake_scorecard(0.50)

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.INCONCLUSIVE
        assert not result.divergence_detected
        assert "NO-OP" in result.verdict_details


# ---------------------------------------------------------------------------
# Error: temporal gating
# ---------------------------------------------------------------------------


class TestTemporalGating:
    """Pre-registration created_at post-dating the run is rejected."""

    def test_created_at_post_dates_battery_run_raises(self):
        """If manifest created_at > battery_run_timestamp, raise ValueError."""
        manifest = _thermal_prereg(created_at="2026-07-09T12:00:00Z")
        run_ts = datetime(2026, 7, 9, 0, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="post-dates"):
            run_helps_battery(
                manifest=manifest,
                field_name="thermal",
                board=None,
                netlist=None,
                build_arm_placement=lambda arm, pi, b, n, s: _fake_placement(),
                score_placement_fn=lambda p, b, n: _fake_scorecard(0.0),
                scorer_id="physics_oracle",
                battery_run_timestamp=run_ts,
            )

    def test_created_at_before_battery_run_passes(self):
        """If manifest created_at <= battery_run_timestamp, no error."""
        manifest = _thermal_prereg(created_at="2026-07-01T00:00:00Z")
        run_ts = datetime(2026, 7, 9, 0, 0, 0, tzinfo=timezone.utc)

        call_count = {"count": 0}

        def build_arm(arm_id, pi, b, n, s):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pi + offset), 0.0]])

        def score_fn(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_fn,
            scorer_id="physics_oracle",
            battery_run_timestamp=run_ts,
            n_perturbations=5,
        )
        assert result.verdict == BatteryVerdict.KEEP

    def test_temporal_gating_with_naive_datetime(self):
        """battery_run_timestamp without tzinfo is normalised to UTC."""
        manifest = _thermal_prereg(created_at="2026-07-09T12:00:00+00:00")
        run_ts = datetime(2026, 7, 9, 0, 0, 0)  # naive → treated as UTC

        with pytest.raises(ValueError, match="post-dates"):
            run_helps_battery(
                manifest=manifest,
                field_name="thermal",
                board=None,
                netlist=None,
                build_arm_placement=lambda *a: _fake_placement(),
                score_placement_fn=lambda p, b, n: _fake_scorecard(0.0),
                scorer_id="physics_oracle",
                battery_run_timestamp=run_ts,
            )


# ---------------------------------------------------------------------------
# Integration: U1 prereg + U2 scorecards end-to-end
# ---------------------------------------------------------------------------


class TestIntegrationEndToEnd:
    """Harness consumes U2 scorecards + U1 pre-registration end-to-end."""

    def test_integration_prereg_field_missing_raises(self):
        """Requesting a field not in the manifest raises ValueError."""
        manifest = _thermal_prereg()

        with pytest.raises(ValueError, match="Field 'nonexistent' not found"):
            run_helps_battery(
                manifest=manifest,
                field_name="nonexistent",
                board=None,
                netlist=None,
                build_arm_placement=lambda *a: _fake_placement(),
                score_placement_fn=lambda p, b, n: _fake_scorecard(0.0),
                scorer_id="physics_oracle",
            )

    def test_integration_arm_errors_are_recorded(self):
        """When an arm raises, the error is recorded in ArmRunResult."""
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            if arm_id == "cheap_heuristic":
                raise RuntimeError("cheap baseline failed")
            return _fake_placement(
                positions=[[float(pert_idx + {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}.get(arm_id, 0)), 0.0]]
            )

        def score_placement(placement, board, netlist):
            return _fake_scorecard(0.30)

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=3,
        )

        # Cheap arm errors should be recorded.
        cheap_errors = [r for r in result.per_run if r.arm == "cheap_heuristic" and r.error]
        assert len(cheap_errors) == 3
        assert all("cheap baseline failed" in r.error for r in cheap_errors)

    def test_integration_per_arm_margin_accumulation(self):
        """Margins are accumulated per arm across perturbations."""
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx + offset), 0.0]])

        call_count = {"count": 0}

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            margins = {0: 0.05, 1: 0.10, 2: 0.25}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.KEEP
        assert "thermal" in result.no_field_margins
        assert "thermal" in result.cheap_margins
        assert "thermal" in result.physics_margins
        assert len(result.physics_margins["thermal"]) == 5
        assert len(result.cheap_margins["thermal"]) == 5

    def test_integration_cost_budget_exceeded(self, monkeypatch):
        """Budget exceeded → INCONCLUSIVE with cost reason."""
        from unittest.mock import patch

        manifest = _thermal_prereg()
        manifest.fields[0].cost_budget.max_total_battery_seconds = 0.001

        call_count = {"count": 0}
        fake_time_val = [0.0]

        def fake_time_impl():
            fake_time_val[0] += 0.01
            return fake_time_val[0]

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx + offset), 0.0]])

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_idx])

        with patch("time.time", fake_time_impl):
            result = run_helps_battery(
                manifest=manifest,
                field_name="thermal",
                board=None,
                netlist=None,
                build_arm_placement=build_arm,
                score_placement_fn=score_placement,
                scorer_id="physics_oracle",
                base_seed=42,
                n_perturbations=5,
            )

        assert result.verdict == BatteryVerdict.INCONCLUSIVE
        assert result.budget_exceeded
        assert "budget" in result.verdict_details.lower()

    def test_integration_max_rounds_budget_exceeded(self):
        """Perturbations > max_rounds_budget → INCONCLUSIVE."""
        manifest = _thermal_prereg()
        manifest.fields[0].cost_budget.max_rounds_budget = 3

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx + offset), 0.0]])

        call_count = {"count": 0}

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.INCONCLUSIVE
        assert result.budget_exceeded

    def test_integration_insufficient_scorable_runs(self):
        """Not enough scorable perturbations → INCONCLUSIVE."""
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx + offset), 0.0]])

        call_count = {"count": 0}

        def score_placement(placement, board, netlist):
            call_count["count"] += 1
            arm_idx = (call_count["count"] - 1) % 3
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_idx])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=2,  # less than prereg N=5
        )

        assert result.verdict == BatteryVerdict.INCONCLUSIVE
        assert "Insufficient perturbations" in result.verdict_details


# ---------------------------------------------------------------------------
# Dataclass smoke tests
# ---------------------------------------------------------------------------


class TestDataClasses:
    """ArmRunResult and HelpsBatteryResult field access."""

    def test_arm_run_result_fields(self):
        r = ArmRunResult(
            arm="physics_field",
            perturbation_idx=0,
            seed=42,
            scorecard=_fake_scorecard(0.5),
            elapsed_seconds=1.2,
        )
        assert r.arm == "physics_field"
        assert r.perturbation_idx == 0
        assert r.seed == 42
        assert r.elapsed_seconds == 1.2
        assert r.error is None

    def test_arm_run_result_with_error(self):
        r = ArmRunResult(
            arm="no_field",
            perturbation_idx=1,
            seed=7,
            scorecard=_fake_scorecard(0.0),
            elapsed_seconds=0.0,
            error="something broke",
        )
        assert r.error == "something broke"

    def test_battery_result_defaults(self):
        prereg = FieldPreregistration.model_validate({
            "field_name": "test",
            "independent_instrument": "o",
            "cheap_baseline": {
                "name": "c", "description": "d", "metric": "m", "target_value": 0.0,
                "because": "b",
            },
            "parametric_ranges": [],
            "structural_bounding_cases": [{"case_name": "c", "description": "d", "because": "b"}],
            "pass_bar": {
                "margin_gain": {"value": 0.1, "because": "b"},
                "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
                "across_perturbations": {"value": 5, "because": "b"},
            },
            "kill_criterion": {"description": "k", "because": "b"},
            "cost_budget": {
                "max_total_battery_seconds": 100,
                "max_rounds_budget": 10,
                "field_convergence_round_limit": 3,
                "thermal_grid_cells_max": 100,
                "target_solve_time_ms_per_field": 1000,
            },
        })
        result = HelpsBatteryResult(
            field_name="test",
            baseline_name="cheap",
            n_perturbations=5,
            prereg=prereg,
        )
        assert result.verdict == BatteryVerdict.INCONCLUSIVE
        assert not result.divergence_detected
        assert not result.budget_exceeded
        assert result.per_run == []
        assert result.no_field_margins == {}
        assert result.cheap_margins == {}
        assert result.physics_margins == {}

    def test_battery_verdict_enum_values(self):
        assert BatteryVerdict.KEEP == "keep"
        assert BatteryVerdict.KILL == "kill"
        assert BatteryVerdict.INCONCLUSIVE == "inconclusive"
        assert BatteryVerdict("keep") == BatteryVerdict.KEEP
        assert BatteryVerdict("kill") == BatteryVerdict.KILL


# ---------------------------------------------------------------------------
# R4 — Worst-case per-perturbation guard (#133)
# ---------------------------------------------------------------------------


class TestWorstCasePerturbationGuard:
    """The pass bar must hold at every sampled perturbation, not just the mean.

    This guards against interior resonances or non-monotone responses that
    a mean-based check would mask.  An interior violation must produce
    INCONCLUSIVE, never KEEP.
    """

    def test_interior_violation_detected(self):
        """R4 fail-capable: mean passes, worst perturbation fails → INCONCLUSIVE.

        An interior resonance or non-monotone response that makes one
        perturbation fail while the others pass must not be masked by the
        mean.  The gate degrades to INCONCLUSIVE (fail-closed).
        """
        manifest = _thermal_prereg()

        # Per-perturbation margins encoded in placement positions.
        # Position = [pert_idx, arm_num] where arm_num: 0=no_field, 1=cheap, 2=physics.
        pert_margins: dict[int, dict[int, float]] = {
            0: {0: 0.05, 1: 0.10, 2: 0.30},   # margin_gain=0.20
            1: {0: 0.05, 1: 0.10, 2: 0.30},   # margin_gain=0.20
            2: {0: 0.05, 1: 0.10, 2: 0.30},   # margin_gain=0.20
            3: {0: 0.05, 1: 0.10, 2: 0.30},   # margin_gain=0.20
            4: {0: 0.05, 1: 0.10, 2: 0.12},   # margin_gain=0.02  ← INTERIOR VIOLATION
        }
        # mean_margin_gain = (0.20*4 + 0.02)/5 = 0.164 >= 0.10 → mean KEEP
        # but worst = 0.02 < 0.10 → INCONCLUSIVE (sampling uncertainty)

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            arm_num = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx), float(arm_num)]])

        def score_placement(placement, board, netlist):
            pert_idx = int(placement.positions[0][0])
            arm_num = int(placement.positions[0][1])
            return _fake_scorecard(pert_margins[pert_idx][arm_num])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.INCONCLUSIVE, (
            f"Expected INCONCLUSIVE (sampling uncertainty), got "
            f"{result.verdict}: {result.verdict_details}"
        )
        assert "sampling uncertainty" in result.verdict_details.lower()
        assert "worst perturbation" in result.verdict_details.lower()

    def test_all_perturbations_pass(self):
        """When every perturbation individually passes the bar → KEEP.

        The worst-case guard should be silent when the pass bar holds
        for the minimum per-perturbation margin_gain.
        """
        manifest = _thermal_prereg()

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            arm_num = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx), float(arm_num)]])

        def score_placement(placement, board, netlist):
            arm_num = int(placement.positions[0][1])
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_num])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=5,
        )

        assert result.verdict == BatteryVerdict.KEEP, (
            f"Expected KEEP, got {result.verdict}: {result.verdict_details}"
        )

    def test_single_perturbation_pass(self):
        """Single perturbation that passes → KEEP (n=1 worst-case = mean)."""
        manifest = _thermal_prereg()
        manifest.fields[0].pass_bar.across_perturbations.value = 1.0

        def build_arm(arm_id, pert_idx, board, netlist, seed):
            arm_num = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
            return _fake_placement(positions=[[float(pert_idx), float(arm_num)]])

        def score_placement(placement, board, netlist):
            arm_num = int(placement.positions[0][1])
            margins = {0: 0.05, 1: 0.10, 2: 0.30}
            return _fake_scorecard(margins[arm_num])

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score_placement,
            scorer_id="physics_oracle",
            base_seed=42,
            n_perturbations=1,
        )

        assert result.verdict == BatteryVerdict.KEEP
