"""Property-based tests for verdict totality/monotonicity and scorecard
independence-guard totality (U8 — R18, R19).

Tests the keep/kill/inconclusive verdict logic via Hypothesis PBT over
synthetic arm-score distributions and pre-registered bars, following the
pattern established in ``test_helps_battery.py``.

Verdict logic accessed through the smallest synthetic path — stubbed
``run_helps_battery`` with controlled scorecard margins — no real
placement/routing.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.validation.helps_battery import BatteryVerdict, run_helps_battery
from temper_placer.validation.prereg.schema import PreregistrationManifest
from temper_placer.validation.scorecard import (
    GateMargin,
    IndependenceViolationError,
    MarginScorecard,
    _assert_independent,
    build_scorecard,
)


# ---------------------------------------------------------------------------
# Synthetic helpers — controlled arm-score distributions without real placement
# ---------------------------------------------------------------------------


_VERDICT_ORDER: dict[BatteryVerdict, int] = {
    BatteryVerdict.KILL: 0,
    BatteryVerdict.INCONCLUSIVE: 1,
    BatteryVerdict.KEEP: 2,
}


def _prereg_with_thresholds(*, x: float, y: float, n_req: int = 5) -> PreregistrationManifest:
    """Build a minimal thermal pre-registration manifest with tunable pass-bar."""
    return PreregistrationManifest.model_validate({
        "version": 1,
        "created_at": "2026-07-01T00:00:00Z",
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
                    {"parameter": "heatspread", "min": 5.0, "max": 40.0, "because": "Cover range"},
                ],
                "structural_bounding_cases": [
                    {"case_name": "single_igbt", "description": "Min config", "because": "Required"},
                ],
                "pass_bar": {
                    "margin_gain": {"name": "X", "value": x, "because": "Gain threshold"},
                    "beat_cheap_baseline_by": {"name": "Y", "value": y, "because": "Beat threshold"},
                    "across_perturbations": {"name": "N", "value": n_req, "because": "Statistical"},
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


def _fake_placement(positions: tuple[list[list[float]]] | None = None) -> object:
    """Synthetic placement with a .positions attribute (no real placement)."""

    class _FakePlacement:
        def __init__(self, pos):
            self.positions = np.array(pos, dtype=np.float32) if pos else np.empty((0, 2), dtype=np.float32)

    return _FakePlacement(positions)


def _fake_scorecard(thermal_margin: float) -> MarginScorecard:
    """Synthetic scorecard with one scorable thermal gate."""
    return MarginScorecard(
        board_id="test",
        scorer_id="physics_oracle",
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


def _run_synthetic_battery(
    *,
    phys_mean: float,
    cheap_mean: float,
    x: float = 0.10,
    y: float = 0.05,
    n: int = 5,
    n_required: int = 5,
    budget_via_rounds: bool = False,
    budget_via_time: bool = False,
    divergence_noop: bool = False,
    base_seed: int = 42,
) -> BatteryVerdict:
    """Run a synthetic helps-battery with stubbed arm scores.

    Returns ONLY the verdict.  Divergence passes by default (each arm
    produces distinct placements).
    """
    manifest = _prereg_with_thresholds(x=x, y=y, n_req=n_required)

    if budget_via_rounds:
        manifest.fields[0].cost_budget.max_rounds_budget = n - 1
    if budget_via_time:
        manifest.fields[0].cost_budget.max_total_battery_seconds = 0.001

    call_count: dict[str, int] = {"count": 0}

    def build_arm(arm_id, pert_idx, board, netlist, seed):
        if divergence_noop:
            return _fake_placement([[0.0, 0.0]])
        offset = {"no_field": 0, "cheap_heuristic": 1, "physics_field": 2}[arm_id]
        return _fake_placement([[float(pert_idx + offset), 0.0]])

    def score_placement(placement, board, netlist):
        call_count["count"] += 1
        arm_idx = (call_count["count"] - 1) % 3
        margins = {0: 0.05, 1: cheap_mean, 2: phys_mean}
        return _fake_scorecard(margins[arm_idx])

    if budget_via_time:
        fake_time = [0.0]

        def _fake_time():
            fake_time[0] += 0.01
            return fake_time[0]

        with patch("time.time", _fake_time):
            result = _do_run(manifest, build_arm, score_placement, n, base_seed)
            return result.verdict
    else:
        result = _do_run(manifest, build_arm, score_placement, n, base_seed)
        return result.verdict


def _do_run(manifest, build_arm, score_placement, n, base_seed):
    """Helper to avoid duplicating run_helps_battery args."""
    return run_helps_battery(
        manifest=manifest,
        field_name="thermal",
        board=None,
        netlist=None,
        build_arm_placement=build_arm,
        score_placement_fn=score_placement,
        scorer_id="physics_oracle",
        base_seed=base_seed,
        n_perturbations=n,
    )


# ---------------------------------------------------------------------------
# R18 — Verdict totality
# ---------------------------------------------------------------------------


@given(
    phys_mean=st.floats(-0.5, 2.0),
    cheap_mean=st.floats(-0.5, 2.0),
    x=st.floats(0.01, 1.0),
    y=st.floats(0.01, 1.0),
    n=st.integers(1, 9),
    n_required=st.integers(1, 5),
    budget_by_rounds=st.booleans(),
    divergence_fail=st.booleans(),
)
@settings(max_examples=200)
def test_verdict_totality(phys_mean, cheap_mean, x, y, n, n_required, budget_by_rounds, divergence_fail):
    """R18 totality: every input yields exactly one valid verdict — no gaps/overlaps.

    Verifies that ``run_helps_battery`` never crashes on diverse synthetic
    inputs and always returns a ``BatteryVerdict`` enum member.
    """
    verdict = _run_synthetic_battery(
        phys_mean=phys_mean,
        cheap_mean=cheap_mean,
        x=x,
        y=y,
        n=n,
        n_required=n_required,
        budget_via_rounds=budget_by_rounds,
        divergence_noop=divergence_fail,
    )
    assert isinstance(verdict, BatteryVerdict)
    assert verdict in {BatteryVerdict.KEEP, BatteryVerdict.KILL, BatteryVerdict.INCONCLUSIVE}


# ---------------------------------------------------------------------------
# R18 — Verdict monotonicity
# ---------------------------------------------------------------------------


@given(
    cheap_mean=st.floats(0.0, 1.0),
    phys_base=st.floats(0.0, 0.9),
    delta=st.floats(0.01, 0.5),
    x=st.floats(0.02, 0.5),
    y=st.floats(0.02, 0.5),
    n=st.integers(5, 8),
    n_required=st.integers(2, 5),
)
@settings(max_examples=200)
def test_verdict_monotonicity(cheap_mean, phys_base, delta, x, y, n, n_required):
    """R18 monotonicity: improving the physics-arm margin (holding others
    fixed) never moves the verdict away from KEEP.

    The verdict ordering is KILL → INCONCLUSIVE → KEEP.  A regression
    (e.g. KEEP → KILL when physics improves) would indicate a threshold
    inversion bug such as ``>=`` vs ``>`` on the pass-bar comparisons.
    """
    v1 = _run_synthetic_battery(
        phys_mean=phys_base, cheap_mean=cheap_mean, x=x, y=y,
        n=n, n_required=n_required,
    )
    v2 = _run_synthetic_battery(
        phys_mean=phys_base + delta, cheap_mean=cheap_mean, x=x, y=y,
        n=n, n_required=n_required,
    )

    assert _VERDICT_ORDER[v2] >= _VERDICT_ORDER[v1], (
        f"Verdict monotonicity violated:\n"
        f"  phys={phys_base:.4f} → v1={v1.value}\n"
        f"  phys={phys_base + delta:.4f} → v2={v2.value}\n"
        f"  cheap={cheap_mean:.3f}, X={x:.3f}, Y={y:.3f}"
    )


# ---------------------------------------------------------------------------
# R18 — Kill-reachable
# ---------------------------------------------------------------------------


def test_verdict_kill_reachable():
    """R18 kill-reachable: the KILL region is provably nonempty.

    Constructs an input where the cheap baseline out-performs the physics
    field — the cheap-heuristic captures all the benefit, so KILL.
    """
    verdict = _run_synthetic_battery(
        phys_mean=0.05,
        cheap_mean=0.50,
        x=0.10,
        y=0.05,
        n=5,
        n_required=5,
    )
    assert verdict == BatteryVerdict.KILL, (
        f"KILL not reachable: phys=0.05, cheap=0.50 produced {verdict.value}"
    )


def test_verdict_kill_reachable_physics_worse():
    """R18 kill-reachable: physics underperforms cheap → KILL."""
    verdict = _run_synthetic_battery(
        phys_mean=0.15,
        cheap_mean=0.50,
        x=0.10,
        y=0.05,
        n=5,
        n_required=5,
    )
    assert verdict == BatteryVerdict.KILL


def test_verdict_kill_reachable_margin_gain_below_x():
    """R18 kill-reachable: margin_gain=phys-cheap < X → KILL."""
    verdict = _run_synthetic_battery(
        phys_mean=0.30,
        cheap_mean=0.25,
        x=0.10,
        y=0.02,
        n=5,
        n_required=5,
    )
    assert verdict == BatteryVerdict.KILL


# ---------------------------------------------------------------------------
# R18 — Budget dominance
# ---------------------------------------------------------------------------


def test_verdict_budget_dominance_rounds():
    """R18 budget dominance: overriding round budget ⇒ INCONCLUSIVE regardless
    of margins.  A healthy margin_gain cannot override a pre-registered budget
    violation.
    """
    verdict = _run_synthetic_battery(
        phys_mean=0.80,
        cheap_mean=0.10,
        x=0.10,
        y=0.05,
        n=5,
        n_required=5,
        budget_via_rounds=True,
    )
    assert verdict == BatteryVerdict.INCONCLUSIVE, (
        f"Budget dominance violated (rounds): expected INCONCLUSIVE, got {verdict.value}"
    )


def test_verdict_budget_dominance_time():
    """R18 budget dominance: overriding time budget ⇒ INCONCLUSIVE regardless
    of margins.
    """
    verdict = _run_synthetic_battery(
        phys_mean=0.80,
        cheap_mean=0.10,
        x=0.10,
        y=0.05,
        n=5,
        n_required=5,
        budget_via_time=True,
    )
    assert verdict == BatteryVerdict.INCONCLUSIVE, (
        f"Budget dominance violated (time): expected INCONCLUSIVE, got {verdict.value}"
    )


def test_verdict_budget_dominance_outweighs_good_margins():
    """R18 budget dominance: even stellar physics margins become INCONCLUSIVE
    when budget is exceeded.
    """
    verdict = _run_synthetic_battery(
        phys_mean=0.99,
        cheap_mean=0.01,
        x=0.10,
        y=0.05,
        n=5,
        n_required=5,
        budget_via_rounds=True,
    )
    assert verdict == BatteryVerdict.INCONCLUSIVE


# ---------------------------------------------------------------------------
# R18 — Divergence no-op ⇒ INCONCLUSIVE
# ---------------------------------------------------------------------------


def test_verdict_divergence_noop_gives_inconclusive():
    """R18: divergence failure → INCONCLUSIVE (never a silent pass)."""
    verdict = _run_synthetic_battery(
        phys_mean=0.80,
        cheap_mean=0.10,
        x=0.10,
        y=0.05,
        n=5,
        n_required=5,
        divergence_noop=True,
    )
    assert verdict == BatteryVerdict.INCONCLUSIVE


# ---------------------------------------------------------------------------
# R19 — Independence-guard totality
# ---------------------------------------------------------------------------


INDEPENDENT_IDS = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',)),
    min_size=1,
    max_size=20,
)


class TestIndependenceGuardTotality:
    """R19: For every scorer/field pair where scorer == field, the guard raises."""

    @given(same_id=INDEPENDENT_IDS)
    @settings(max_examples=100)
    def test_assert_independent_raises_same_id_pbt(self, same_id):
        """R19: ``_assert_independent`` always raises when ids are identical."""
        with pytest.raises(IndependenceViolationError):
            _assert_independent(scorer_id=same_id, field_id=same_id)

    @given(
        base=INDEPENDENT_IDS.filter(lambda s: len(s) > 0),
    )
    @settings(max_examples=100)
    def test_assert_independent_passes_on_different(self, base):
        """R19: ``_assert_independent`` passes when ids differ."""
        field_id = base + "_SUFFIX"
        assume(base != field_id)
        _assert_independent(scorer_id=base, field_id=field_id)

    def test_build_scorecard_raises_self_scoring(self):
        """R19: ``build_scorecard`` raises when scorer_id == field_id."""

        def _dummy_scorer(placement, board, netlist):
            from temper_placer.regression.physics_oracle import PhysicsOracleResult

            return PhysicsOracleResult(board_id="x", passed=True)

        with pytest.raises(IndependenceViolationError):
            build_scorecard(
                placement=None,
                board=None,
                netlist=None,
                scorer=_dummy_scorer,
                scorer_id="my_solver",
                field_id="my_solver",
            )

    @given(same_id=INDEPENDENT_IDS)
    @settings(max_examples=50)
    def test_build_scorecard_raises_self_scoring_pbt(self, same_id):
        """R19: ``build_scorecard`` raises when scorer/field ids match (PBT)."""

        def _dummy_scorer(placement, board, netlist):
            from temper_placer.regression.physics_oracle import PhysicsOracleResult

            return PhysicsOracleResult(board_id="x", passed=True)

        with pytest.raises(IndependenceViolationError):
            build_scorecard(
                placement=None,
                board=None,
                netlist=None,
                scorer=_dummy_scorer,
                scorer_id=same_id,
                field_id=same_id,
            )

    def test_build_scorecard_does_not_raise_on_different_ids(self):
        """R19: ``build_scorecard`` succeeds when scorer_id != field_id."""

        def _dummy_scorer(placement, board, netlist):
            from temper_placer.regression.physics_oracle import PhysicsOracleResult

            return PhysicsOracleResult(board_id="x", passed=True)

        sc = build_scorecard(
            placement=None,
            board=None,
            netlist=None,
            scorer=_dummy_scorer,
            scorer_id="physics_oracle",
            field_id="thermal_field",
        )
        assert isinstance(sc, MarginScorecard)
        assert sc.scorer_id == "physics_oracle"
