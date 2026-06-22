"""
Primary vs. challenger cross-validation engine.

Compares per-corner Tj from the ngspice primary (via corner sweep) against
the independent challenger thermal model. Flags corners where disagreement
exceeds threshold.

R8: Cross-validation compares per-corner Tj. A corner is "flagged" when
|Tj_challenger - Tj_primary| / max(Tj_challenger, Tj_primary) > 10%.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.spice.challenger.thermal_mesh import (
    compute_Tj_rtheta,
)
from tools.spice.corner_results import CornerResult


@dataclass
class CrossValidationResult:
    """Result of comparing primary and challenger Tj predictions."""

    total_corners: int
    agreed_corners: int
    flagged_corners: int
    worst_disagreement_pct: float = 0.0
    worst_corner: str = ""

    flagged_details: list[dict[str, object]] = field(default_factory=list)

    @property
    def agreement_rate_pct(self) -> float:
        if self.total_corners == 0:
            return 100.0
        return (self.agreed_corners / self.total_corners) * 100.0


def cross_validate(
    corner_results: list[CornerResult],
    T_ambient: float = 25.0,
    R_jc: float = 1.0,
    R_ca: float = 10.0,
    disagreement_threshold_pct: float = 10.0,
    power_per_device_W: float = 50.0,
) -> CrossValidationResult:
    """Cross-validate primary Tj against challenger model.

    Args:
        corner_results: List of CornerResult from corner sweep.
        T_ambient: Ambient temperature in Celsius.
        R_jc: Junction-to-case thermal resistance (K/W).
        R_ca: Case-to-ambient thermal resistance (K/W).
        disagreement_threshold_pct: Flag threshold in percent.
        power_per_device_W: Per-device power dissipation for challenger.

    Returns:
        CrossValidationResult with agreement statistics and flagged corners.
    """
    total = len(corner_results)
    agreed = 0
    flagged = 0
    worst_pct = 0.0
    worst_name = ""
    flagged_list: list[dict[str, object]] = []

    for cr in corner_results:
        if cr.convergence_error or cr.Tj_primary is None:
            Tj_challenger = compute_Tj_rtheta(
                power_per_device_W, T_ambient, R_jc, R_ca
            )
            continue

        Tj_challenger = compute_Tj_rtheta(
            power_per_device_W * (cr.switching_loss_mJ or 0.0) / 1000.0 * 25000
            if cr.switching_loss_mJ
            else power_per_device_W,
            T_ambient,
            R_jc,
            R_ca,
        )

        Tj_primary = cr.Tj_primary
        denom = max(abs(Tj_challenger), abs(Tj_primary))
        if denom < 0.01:
            agreed += 1
            continue

        disagreement = abs(Tj_challenger - Tj_primary) / denom * 100.0

        if disagreement > worst_pct:
            worst_pct = disagreement
            worst_name = cr.corner_name

        if disagreement > disagreement_threshold_pct:
            flagged += 1
            flagged_list.append(
                {
                    "corner": cr.corner_name,
                    "Tj_primary": Tj_primary,
                    "Tj_challenger": Tj_challenger,
                    "disagreement_pct": round(disagreement, 1),
                }
            )
        else:
            agreed += 1

    return CrossValidationResult(
        total_corners=total,
        agreed_corners=agreed,
        flagged_corners=flagged,
        worst_disagreement_pct=worst_pct,
        worst_corner=worst_name,
        flagged_details=flagged_list,
    )
