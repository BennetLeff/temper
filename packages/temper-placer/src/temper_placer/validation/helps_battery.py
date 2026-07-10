"""
Helps-battery A/B harness: controlled three-arm experiment.

Arms: no-field | cheap-heuristic | physics-field.
Same seed / net order / field-only toggle across arms, scored by the
independent instrument (U2 scorecard) over N perturbations, evaluated
against the pre-registered pass bar (U1).

The harness MUST be able to conclude "kill" — that is the whole point.
"""

from __future__ import annotations

import enum
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from temper_placer.validation.prereg import (
    FieldPreregistration,
    PreregistrationManifest,
)
from temper_placer.validation.scorecard import MarginScorecard

# ---------------------------------------------------------------------------
# Verdict enum
# ---------------------------------------------------------------------------


class BatteryVerdict(str, enum.Enum):
    """Outcome of a helps-battery run — strictly from pre-registered numbers."""

    KEEP = "keep"
    KILL = "kill"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Per-arm result
# ---------------------------------------------------------------------------


@dataclass
class ArmRunResult:
    """Per-perturbation result for a single arm."""

    arm: str  # "no_field" | "cheap_heuristic" | "physics_field"
    perturbation_idx: int
    seed: int
    scorecard: MarginScorecard
    elapsed_seconds: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Battery result
# ---------------------------------------------------------------------------


@dataclass
class HelpsBatteryResult:
    """Aggregated result from a helps-battery A/B experiment.

    U10 reads ``verdict`` to decide keep/kill/inconclusive.
    """

    field_name: str
    baseline_name: str
    n_perturbations: int
    prereg: FieldPreregistration

    per_run: list[ArmRunResult] = field(default_factory=list)

    # Per-arm aggregated margins (gate name -> list of values across perturbations)
    no_field_margins: dict[str, list[float]] = field(default_factory=dict)
    cheap_margins: dict[str, list[float]] = field(default_factory=dict)
    physics_margins: dict[str, list[float]] = field(default_factory=dict)

    # Divergence check
    divergence_detected: bool = False
    divergence_detail: str = ""

    # Cost (CPU-seconds of the slowest arm, per H7)
    cost_seconds: float = 0.0
    budget_exceeded: bool = False
    budget_detail: str = ""

    # Verdict
    verdict: BatteryVerdict = BatteryVerdict.INCONCLUSIVE
    verdict_details: str = ""


# ---------------------------------------------------------------------------
# Divergence assertion
# ---------------------------------------------------------------------------


def _assert_divergence(
    physics_placements: list[Any],
    no_field_placements: list[Any],
    *,
    min_fraction_different: float = 0.5,
) -> tuple[bool, str]:
    """Check that the physics-field arm produces measurably different layouts.

    If the field toggle does nothing, the A/B is a no-op — this is a finding,
    never a pass.  We compare per-perturbation placement representations.

    Returns (divergence_detected, detail).
    """
    n = len(physics_placements)
    if n == 0:
        return False, "No placements to compare"

    different_count = 0
    for i in range(n):
        pp = physics_placements[i]
        nf = no_field_placements[i]
        if not _placements_equal(pp, nf):
            different_count += 1

    fraction = different_count / n
    detail = (
        f"Divergence: {different_count}/{n} perturbations ({fraction:.1%}) "
        f"produced measurably different layouts "
        f"(min_fraction_different={min_fraction_different:.1%})"
    )

    if fraction >= min_fraction_different:
        return True, detail
    return False, detail + " — FIELD TOGGLE IS A NO-OP"


def _placements_equal(a: Any, b: Any) -> bool:
    """Check if two placement objects are byte-identical in their position arrays."""
    try:
        a_pos = getattr(a, "positions", None)
        b_pos = getattr(b, "positions", None)
        if a_pos is None or b_pos is None:
            return a == b
        if isinstance(a_pos, np.ndarray) and isinstance(b_pos, np.ndarray):
            return bool(np.allclose(a_pos, b_pos, atol=1e-6))
        return a_pos == b_pos
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pure verdict decision (extracted from run_helps_battery for U8 direct testing)
# ---------------------------------------------------------------------------


def decide_verdict(
    *,
    margin_gain: float,
    beats_cheap_by: float,
    n_actual_physics: int,
    n_actual_cheap: int,
    n_required: int,
    divergence_detected: bool,
    budget_exceeded: bool,
    pass_bar_x: float,
    pass_bar_y: float,
    kill_criterion_description: str = "",
    phys_mean: float = 0.0,
    cheap_mean: float = 0.0,
    primary_gate: str = "",
    budget_detail: str = "",
    divergence_detail: str = "",
) -> tuple[BatteryVerdict, str]:
    """Pure verdict decision from pre-registered bar and measured quantities.

    No I/O, no placement/scoring — operates only on the numbers and the
    pre-registered bar.  The priority order is:

    1. budget_exceeded → INCONCLUSIVE
    2. divergence not detected → INCONCLUSIVE
    3. insufficient perturbations → INCONCLUSIVE
    4. margin_gain >= pass_bar_x AND beats_cheap_by >= pass_bar_y → KEEP
    5. otherwise → KILL

    Returns ``(BatteryVerdict, reason_string)``.
    """
    if budget_exceeded:
        detail = f"Cost budget exceeded: {budget_detail}" if budget_detail else "Cost budget exceeded"
        return BatteryVerdict.INCONCLUSIVE, detail

    if not divergence_detected:
        detail = divergence_detail if divergence_detail else "-"
        return BatteryVerdict.INCONCLUSIVE, (
            f"A/B divergence assertion FAILED: {detail}. "
            f"The field toggle is a no-op — this is a finding, not a pass."
        )

    if n_actual_physics < n_required or n_actual_cheap < n_required:
        return BatteryVerdict.INCONCLUSIVE, (
            f"Insufficient perturbations: need >= {n_required} scorable runs "
            f"per arm, got physics={n_actual_physics} cheap={n_actual_cheap}"
        )

    margin_gain_ok = margin_gain >= pass_bar_x
    beat_cheap_ok = beats_cheap_by >= pass_bar_y

    if margin_gain_ok and beat_cheap_ok:
        return BatteryVerdict.KEEP, (
            f"KEEP: margin_gain={margin_gain:.3f} >= {pass_bar_x} (X), "
            f"beat_cheap_by={beats_cheap_by:.3f} >= {pass_bar_y} (Y), "
            f"across N={n_actual_physics} >= {n_required} perturbations, "
            f"physics_mean({primary_gate})={phys_mean:.3f}, "
            f"cheap_mean({primary_gate})={cheap_mean:.3f}"
        )

    kill_reasons: list[str] = []
    if not margin_gain_ok:
        kill_reasons.append(f"margin_gain={margin_gain:.3f} < {pass_bar_x}")
    if not beat_cheap_ok:
        kill_reasons.append(f"beat_cheap_by={beats_cheap_by:.3f} < {pass_bar_y}")
    return BatteryVerdict.KILL, (
        f"KILL ({kill_criterion_description}): "
        + "; ".join(kill_reasons)
        + f" across N={n_actual_physics} perturbations"
    )


# ---------------------------------------------------------------------------
# Battery runner
# ---------------------------------------------------------------------------


def run_helps_battery(
    *,
    manifest: PreregistrationManifest,
    field_name: str,
    board: Any,
    netlist: Any,
    build_arm_placement: Callable[
        [str, int, Any, Any, int], Any
    ],
    score_placement_fn: Callable[
        [Any, Any, Any], MarginScorecard
    ],
    scorer_id: str,
    base_seed: int = 42,
    n_perturbations: int | None = None,
    battery_run_timestamp: datetime | None = None,
) -> HelpsBatteryResult:
    """Run the helps-battery A/B experiment.

    Parameters
    ----------
    manifest:
        Loaded pre-registration manifest (U1).  Temporal gating is enforced
        if ``battery_run_timestamp`` is supplied.
    field_name:
        Name of the field within the manifest to evaluate.
    board:
        Board geometry.
    netlist:
        Design netlist.
    build_arm_placement:
        Callable ``(arm_id, perturbation_idx, board, netlist, seed) -> placement``.
        The harness calls this for each (arm, perturbation) combination.
        *arm_id* is one of ``"no_field"``, ``"cheap_heuristic"``, ``"physics_field"``.
    score_placement_fn:
        Callable ``(placement, board, netlist) -> MarginScorecard``.
        This MUST be the independent instrument — the harness asserts
        independence via the scorer_id / field_name check.
    scorer_id:
        Human-readable identifier for the scorer (should differ from field_name).
    base_seed:
        Base seed for deterministic reproducibility.
    n_perturbations:
        Number of perturbations.  Defaults to the pre-registered ``N`` value.
    battery_run_timestamp:
        If supplied, the manifest's ``created_at`` must predate this
        timestamp (temporal gating — U1 contract).
    """
    # Temporal gating: manifest must predate the run.
    if battery_run_timestamp is not None:
        from temper_placer.validation.prereg.schema import _parse_iso_to_utc

        created = _parse_iso_to_utc(manifest.created_at)
        normalized = battery_run_timestamp
        if battery_run_timestamp.tzinfo is None:
            normalized = battery_run_timestamp.replace(tzinfo=UTC)
        if created > normalized:
            raise ValueError(
                f"manifest created_at ({manifest.created_at}) "
                f"post-dates battery-run timestamp "
                f"({battery_run_timestamp.isoformat()}); "
                f"pre-registration must demonstrably predate results"
            )

    # Select the field from the manifest.
    field = _find_field(manifest, field_name)
    if field is None:
        raise ValueError(
            f"Field '{field_name}' not found in manifest "
            f"(available: {[f.field_name for f in manifest.fields]})"
        )

    n = n_perturbations
    if n is None:
        n = int(field.pass_bar.across_perturbations.value)

    arm_ids = ["no_field", "cheap_heuristic", "physics_field"]
    per_run: list[ArmRunResult] = []

    # Collect placements for divergence check.
    physics_placements: list[Any] = []
    no_field_placements: list[Any] = []

    # Per-arm per-gate margin accumulators.
    no_field_margins: dict[str, list[float]] = {}
    cheap_margins: dict[str, list[float]] = {}
    physics_margins: dict[str, list[float]] = {}

    # Cost: wall-clock of the slowest arm across all perturbations.
    max_arm_elapsed: float = 0.0

    rng = np.random.default_rng(base_seed)

    for pert_idx in range(n):
        seed = int(rng.integers(0, 2**31 - 1))

        for arm_id in arm_ids:
            t0 = time.time()
            error: str | None = None

            try:
                placement = build_arm_placement(
                    arm_id, pert_idx, board, netlist, seed
                )
                scorecard = score_placement_fn(placement, board, netlist)
            except Exception as exc:
                placement = None
                scorecard = MarginScorecard(
                    board_id="error",
                    scorer_id=scorer_id,
                    margins=[],
                )
                error = str(exc)

            elapsed = time.time() - t0

            run_result = ArmRunResult(
                arm=arm_id,
                perturbation_idx=pert_idx,
                seed=seed,
                scorecard=scorecard,
                elapsed_seconds=elapsed,
                error=error,
            )
            per_run.append(run_result)

            if placement is not None:
                if arm_id == "physics_field":
                    physics_placements.append(placement)
                elif arm_id == "no_field":
                    no_field_placements.append(placement)

            # Accumulate margins.
            target_map: dict[str, dict[str, list[float]]] = {
                "no_field": no_field_margins,
                "cheap_heuristic": cheap_margins,
                "physics_field": physics_margins,
            }
            margins_dict = target_map[arm_id]
            for m in scorecard.scorable_margins():
                margins_dict.setdefault(m.gate_name, []).append(m.value)

        # Track slowest arm's cumulative time per H7.
        arm0 = per_run[-3].elapsed_seconds
        arm1 = per_run[-2].elapsed_seconds
        arm2 = per_run[-1].elapsed_seconds
        max_arm_elapsed += max(arm0, arm1, arm2)

    # ---- A/B divergence assertion ----
    divergence_ok, divergence_detail = _assert_divergence(
        physics_placements, no_field_placements,
    )

    # ---- Cost budget check ----
    budget = field.cost_budget
    budget_exceeded = False
    budget_detail = ""

    if max_arm_elapsed > budget.max_total_battery_seconds:
        budget_exceeded = True
        budget_detail = (
            f"Slowest arm total: {max_arm_elapsed:.1f}s "
            f"> budget {budget.max_total_battery_seconds:.1f}s"
        )

    if n > budget.max_rounds_budget:
        budget_exceeded = True
        if budget_detail:
            budget_detail += "; "
        budget_detail += (
            f"perturbations {n} > max_rounds_budget {budget.max_rounds_budget}"
        )

    # ---- Verdict: pre-registered pass bar ----
    pass_bar = field.pass_bar

    primary_gate = _resolve_primary_gate(
        field, no_field_margins, cheap_margins, physics_margins
    )

    n_actual_physics = len(physics_margins.get(primary_gate, []))
    n_actual_cheap = len(cheap_margins.get(primary_gate, []))
    n_required = int(pass_bar.across_perturbations.value)

    phys_vals = physics_margins.get(primary_gate, [])
    cheap_vals = cheap_margins.get(primary_gate, [])

    phys_mean = statistics.mean(phys_vals) if phys_vals else 0.0
    cheap_mean = statistics.mean(cheap_vals) if cheap_vals else 0.0

    margin_gain = phys_mean - cheap_mean
    beat_cheap = phys_mean - cheap_mean

    X = pass_bar.margin_gain.value
    Y = pass_bar.beat_cheap_baseline_by.value

    verdict, verdict_details = decide_verdict(
        margin_gain=margin_gain,
        beats_cheap_by=beat_cheap,
        n_actual_physics=n_actual_physics,
        n_actual_cheap=n_actual_cheap,
        n_required=n_required,
        divergence_detected=divergence_ok,
        budget_exceeded=budget_exceeded,
        pass_bar_x=X,
        pass_bar_y=Y,
        kill_criterion_description=field.kill_criterion.description,
        phys_mean=phys_mean,
        cheap_mean=cheap_mean,
        primary_gate=primary_gate,
        budget_detail=budget_detail,
        divergence_detail=divergence_detail,
    )

    # ---- Worst-case per-perturbation check (#133) ----
    # The mean-based verdict can mask an interior violation:
    # a single perturbation that fails the bar while the rest
    # pass can KEEP on mean alone.  This guard ensures the
    # pass bar holds at *every* sampled perturbation, not just
    # on average.  If the worst perturbation fails, the verdict
    # is downgraded to INCONCLUSIVE (sampling uncertainty).
    n_paired = min(len(phys_vals), len(cheap_vals))
    if verdict == BatteryVerdict.KEEP and n_paired > 0:
        min_mg = float("inf")
        worst_idx = -1
        for i in range(n_paired):
            mg = phys_vals[i] - cheap_vals[i]
            if mg < min_mg:
                min_mg = mg
                worst_idx = i
        threshold = max(X, Y)
        if min_mg < threshold:
            verdict = BatteryVerdict.INCONCLUSIVE
            verdict_details = (
                f"INCONCLUSIVE (sampling uncertainty): mean-based verdict is "
                f"KEEP (mean_margin_gain={margin_gain:.3f} >= {threshold} "
                f"threshold), but worst perturbation (idx {worst_idx}, "
                f"margin_gain={min_mg:.3f}) fails the pass bar "
                f"(X={X}, Y={Y}). The pass bar must hold at every sampled "
                f"perturbation, not just the mean — this guards against "
                f"interior resonances or non-monotone responses missed by "
                f"favourably-sampled means."
            )

    return HelpsBatteryResult(
        field_name=field.field_name,
        baseline_name=field.cheap_baseline.name,
        n_perturbations=n,
        prereg=field,
        per_run=per_run,
        no_field_margins=no_field_margins,
        cheap_margins=cheap_margins,
        physics_margins=physics_margins,
        divergence_detected=divergence_ok,
        divergence_detail=divergence_detail,
        cost_seconds=max_arm_elapsed,
        budget_exceeded=budget_exceeded,
        budget_detail=budget_detail,
        verdict=verdict,
        verdict_details=verdict_details,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_field(
    manifest: PreregistrationManifest, field_name: str
) -> FieldPreregistration | None:
    """Find a field by name in the manifest."""
    for f in manifest.fields:
        if f.field_name == field_name:
            return f
    return None


def _resolve_primary_gate(
    field: FieldPreregistration,
    no_field: dict[str, list[float]],
    cheap: dict[str, list[float]],
    physics: dict[str, list[float]],
) -> str:
    """Determine the primary gate for pass-bar evaluation.

    Uses the cheap baseline's metric name to find the corresponding gate.
    Falls back to the first gate present in all three arms.
    """
    metric = field.cheap_baseline.metric
    metric_to_gate: dict[str, str] = {
        "thermal_score": "thermal",
        "clearance_score": "hv_lv_clearance",
        "loop_area_score": "loop_area",
        "compactness_score": "compactness",
    }
    candidate = metric_to_gate.get(metric, metric)

    if candidate in no_field and candidate in cheap and candidate in physics:
        return candidate

    common = set(no_field.keys()) & set(cheap.keys()) & set(physics.keys())
    if common:
        return sorted(common)[0]

    return field.field_name
