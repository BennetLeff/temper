"""
Verified-interval / worst-case bounds for thermal sensitivity sweep (L2 soundness).

Converts the helps-battery random-sample perturbation sweep from
"sound-by-sampling" to "mathematically sound" by establishing monotonicity
of the thermal FDM solution with respect to its uncertain parameters.

Since T_j is provably monotone in each swept parameter over the operating
envelope (T >= T_amb always holds for Q >= 0), the worst case over the
parameter box is bounded by evaluating at the extremes:
  - max T_j corner: max P, max T_amb, min k_eff, min h_sink
If the verdict holds at this corner, it holds for ALL configurations in
the box.

Public API
----------
.. code-block:: python

    from temper_placer.physics.parameter_bounds import (
        ParameterBound,
        build_thermal_parameter_bounds,
        worst_case_corner,
        monotonicity_proof,
        compute_thermal_soundness,
        ThermalSoundnessResult,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.validation.prereg.schema import FieldPreregistration


# ---------------------------------------------------------------------------
# Parameter bound dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterBound:
    """Bounds and monotonicity for a single uncertain parameter.

    ``monotonicity``: +1 means T_j INCREASES with this parameter (worst
    case at max); -1 means T_j DECREASES (worst case at min); 0 means the
    relationship is not provably monotone (corner-bound is NOT a guarantee
    for this parameter).
    """

    parameter: str
    min: float
    max: float
    monotonicity: int  # +1, -1, or 0
    unit: str
    because: str

    @property
    def worst_case_value(self) -> float:
        """Value that maximises T_j."""
        if self.monotonicity > 0:
            return self.max
        if self.monotonicity < 0:
            return self.min
        return self.max


@dataclass(frozen=True)
class ThermalSoundnessResult:
    """Result of the L2 soundness gate check at the worst-case corner."""

    is_sound: bool
    """True iff T_j at the worst-case corner <= T_j_max."""

    detail: str
    """Human-readable explanation."""

    corner_peak_C: float
    """Peak T_j at the corner configuration (deg C)."""

    T_j_max_C: float
    """Junction temperature ceiling used for the check."""

    all_monotone: bool
    """True iff every swept parameter is provably monotone."""

    non_monotone_params: list[str] = field(default_factory=list)
    """Parameters that are not provably monotone."""


# ---------------------------------------------------------------------------
# Parameter box builder
# ---------------------------------------------------------------------------


def build_thermal_parameter_bounds(
    prereg: FieldPreregistration,
    fdm_config: ThermalFDMConfig | None = None,
) -> list[ParameterBound]:
    """Build the uncertainty box: one ``ParameterBound`` per swept parameter.

    Parameters come from the pre-registration manifest's
    ``parametric_ranges`` plus physically-linked quantities from the FDM
    config (ambient_C, copper fraction).  Each entry carries a
    monotonicity direction with a ``because`` citation.

    Args:
        prereg: The field's pre-registration record.
        fdm_config: Optional FDM config for ambient_C bound.

    Returns:
        List of ``ParameterBound``, one per uncertain parameter.
    """
    bounds: list[ParameterBound] = []

    # --- From prereg parametric_ranges ---
    for pr in prereg.parametric_ranges:
        param_lower = pr.parameter.lower()

        if "power" in param_lower or "dissipation" in param_lower or "P_loss" in param_lower:
            bounds.append(ParameterBound(
                parameter=pr.parameter,
                min=pr.min,
                max=pr.max,
                monotonicity=+1,
                unit=pr.because,  # because field carries the reason, not a unit
                because=(
                    "b = Q_vec + h*T_amb; A unchanged.  A^{-1} >= 0 "
                    "(M-matrix property), so T = A^{-1} b increases "
                    "monotonically in Q component-wise.  -> "
                    f"T_j INCREASING in {pr.parameter}"
                ),
            ))

        elif "junction_to_case" in param_lower or "r_theta" in param_lower or "thermal_resistance" in param_lower:
            bounds.append(ParameterBound(
                parameter=pr.parameter,
                min=pr.min,
                max=pr.max,
                monotonicity=+1,
                unit=pr.because,
                because=(
                    "R_theta = 1/h for through-plane sink.  "
                    "d T / d h_i = A^{-1} e_i (T_amb - T_i) <= 0 "
                    "when T_i >= T_amb (M-matrix inverse non-negativity).  "
                    "Higher R_theta -> lower h -> higher T_j.  "
                    f"-> T_j INCREASING in {pr.parameter}"
                ),
            ))

        elif "heatspread" in param_lower or "spread" in param_lower or "copper" in param_lower:
            bounds.append(ParameterBound(
                parameter=pr.parameter,
                min=pr.min,
                max=pr.max,
                monotonicity=-1,
                unit=pr.because,
                because=(
                    "Larger heatspread -> more copper coverage -> higher "
                    "effective k_eff -> lower thermal resistance -> lower "
                    "T_j.  Scaling k_field by alpha > 1 gives A(alpha) >= "
                    "A(1) component-wise (M-matrix ordering), so "
                    "A(alpha)^{-1} <= A(1)^{-1}, b unchanged, hence "
                    f"T(alpha) <= T.  -> T_j DECREASING in {pr.parameter}"
                ),
            ))

        else:
            bounds.append(ParameterBound(
                parameter=pr.parameter,
                min=pr.min,
                max=pr.max,
                monotonicity=0,
                unit="unknown",
                because=(
                    f"No monotonicity proof for '{pr.parameter}'; "
                    "corner-bound is NOT a guarantee for this parameter."
                ),
            ))

    # --- ambient_C from config (not in prereg ranges, but physically relevant) ---
    if fdm_config is not None:
        T_amb = fdm_config.ambient_C
        bounds.append(ParameterBound(
            parameter="ambient_C",
            min=max(0.0, T_amb - 20.0),
            max=T_amb + 10.0,
            monotonicity=+1,
            unit="deg C",
            because=(
                "Dirichlet BC sets T = T_amb at the heatsink edge; "
                "sink term adds h_i * T_amb to RHS.  b increases with "
                "T_amb, A unchanged, A^{-1} >= 0.  "
                "-> T_j INCREASING in ambient_C.  "
                "Range derived from config.ambient_C +/- margin."
            ),
        ))

    # --- Effective through-plane sink (not in prereg ranges) ---
    bounds.append(ParameterBound(
        parameter="h_sink_min",
        min=0.0,
        max=0.0,
        monotonicity=-1,
        unit="W/(K·mm²)",
        because=(
            "d T / d h_i = A^{-1} e_i (T_amb - T_i) <= 0 when "
            "T_i >= T_amb (M-matrix analysis).  Minimum h_sink (= 0, "
            "no vertical sink) gives maximum T_j.  "
            "-> T_j DECREASING in h_sink."
        ),
    ))

    return bounds


# ---------------------------------------------------------------------------
# Worst-case corner
# ---------------------------------------------------------------------------


def worst_case_corner(bounds: list[ParameterBound]) -> dict[str, float]:
    """Compute the worst-case corner values for maximum T_j.

    For each parameter, picks the bound extreme that maximises T_j:
    - Monotone INCREASING (+1): use *max*
    - Monotone DECREASING (-1): use *min*
    - Unknown (0): use *max* (conservative, but not a guarantee).

    Args:
        bounds: List of ``ParameterBound`` from ``build_thermal_parameter_bounds``.

    Returns:
        ``{parameter_name: worst_case_value}``.
    """
    corner: dict[str, float] = {}
    for b in bounds:
        corner[b.parameter] = b.worst_case_value
    return corner


# ---------------------------------------------------------------------------
# Monotonicity proof summary
# ---------------------------------------------------------------------------


def monotonicity_proof() -> str:
    """Return the mathematical monotonicity proof summary.

    The proof relies on the M-matrix property of the FDM system matrix A:
    - A is an M-matrix: diagonal > 0, off-diagonal <= 0, diagonally dominant.
    - A^{-1} >= 0 element-wise (inverse of an M-matrix is non-negative).
    - The solution T = A^{-1} b inherits monotonicity from b and A.

    For each parameter:

    **Power (P)** — INCREASING
      b = Q_vec + const; A unchanged.  A^{-1} >= 0 => T increases with b.

    **Conductivity (k_eff)** — DECREASING
      If k' >= k cell-wise, then A(k') >= A(k) in the Loewner/M-matrix
      partial order.  For M-matrices, A <= B => B^{-1} <= A^{-1}.
      Since b unchanged, T(k') <= T(k).

    **Ambient (T_amb)** — INCREASING
      b gets +h_i * T_amb on RHS and Dirichlet BC terms.  A unchanged,
      A^{-1} >= 0 => T increases with T_amb.

    **Through-plane sink (h_sink)** — DECREASING
      d T / d h_i = A^{-1} e_i (T_amb - T_i).  Since A^{-1} >= 0 and
      T_i >= T_amb (always for Q >= 0), the derivative is <= 0
      component-wise.  Higher h_sink => lower T everywhere.

    All four parameters are provably monotone over the operating envelope
    T >= T_amb (always true for non-negative heat sources).
    """
    return monotonicity_proof.__doc__ or ""


# ---------------------------------------------------------------------------
# Soundness gate: worst-case corner T_j check
# ---------------------------------------------------------------------------


def compute_thermal_soundness(
    prereg: FieldPreregistration,
    fdm_config: ThermalFDMConfig | None = None,
    devices: dict[str, tuple[float, float]] | None = None,
    power_map: dict[str, float] | None = None,
    T_j_max: float = 150.0,
    _copper_grid: np.ndarray | None = None,
    _h_field: np.ndarray | None = None,
    _ambient_C: float | None = None,
) -> ThermalSoundnessResult:
    """Check whether the worst-case corner T_j is below T_j_max.

    Runs a single FDM solve at the worst-case corner configuration:
    - min k_eff: copper_grid = zeros (pure FR4)
    - max power: scaled to prereg max
    - max ambient: corner ambient_C
    - min h_sink: h_field = zeros (no vertical sink)

    If T_j_corner <= T_j_max, the field is "sound" — the verdict is
    guaranteed across the entire uncertainty box for monotone parameters.

    If T_j_corner > T_j_max, the field is "sampled-only" — the sampling
    may have missed an interior worst case.

    Args:
        prereg: Field pre-registration with parametric_ranges.
        fdm_config: FDM grid config.
        devices: ``{ref: (x_mm, y_mm)}`` nominal device positions.
        power_map: ``{ref: power_W}`` per-device dissipation.
        T_j_max: Junction temperature ceiling (deg C).
        copper_grid: Optional pre-built copper coverage.
        h_field: Optional pre-built vertical sink field.
        ambient_C: Override ambient (from config if None).

    Returns:
        ``ThermalSoundnessResult``.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    devices = devices or {}
    power_map = power_map or {}

    # Build parameter bounds
    bounds = build_thermal_parameter_bounds(prereg, fdm_config)
    corner = worst_case_corner(bounds)

    # Identify non-monotone parameters
    non_monotone = [b.parameter for b in bounds if b.monotonicity == 0]
    all_monotone = len(non_monotone) == 0

    # --- Build corner FDM config ---
    if fdm_config is None:
        corner_config = ThermalFDMConfig(
            cell_size_mm=1.0,
            origin_mm=(0.0, 0.0),
            height_cells=25,
            width_cells=25,
            ambient_C=corner.get("ambient_C", 40.0),
            heatsink_edge="TOP",
            max_cells=5000,
        )
    else:
        corner_config = ThermalFDMConfig(
            cell_size_mm=fdm_config.cell_size_mm,
            origin_mm=fdm_config.origin_mm,
            height_cells=fdm_config.height_cells,
            width_cells=fdm_config.width_cells,
            ambient_C=corner.get("ambient_C", fdm_config.ambient_C),
            heatsink_edge=fdm_config.heatsink_edge,
            k_fr4=fdm_config.k_fr4,
            k_copper=fdm_config.k_copper,
            board_thickness_mm=fdm_config.board_thickness_mm,
            max_cells=fdm_config.max_cells,
            target_solve_time_s=fdm_config.target_solve_time_s,
        )

    # --- Scale power_map to corner max ---
    power_scale = 1.0
    for b in bounds:
        if b.monotonicity > 0 and "power" in b.parameter.lower():
            base_max = max(power_map.values()) if power_map else 1.0
            if base_max > 0:
                power_scale = b.worst_case_value / base_max
            break

    corner_power_map: dict[str, float] = {}
    for ref, pwr in power_map.items():
        corner_power_map[ref] = pwr * power_scale

    # --- Corner FDM solve ---
    # Use zero copper (pure FR4) and zero h_field for worst case.
    corner_copper = np.zeros(
        (corner_config.height_cells, corner_config.width_cells),
        dtype=np.float64,
    )
    corner_h_field = np.zeros(
        (corner_config.height_cells, corner_config.width_cells),
        dtype=np.float64,
    )

    try:
        result = solve_thermal_fdm(
            config=corner_config,
            devices=devices,
            power_map=corner_power_map,
            copper_grid=corner_copper,
            Q_field=None,
            h_field=corner_h_field,
        )
    except Exception as exc:
        return ThermalSoundnessResult(
            is_sound=False,
            detail=f"Corner FDM solve failed: {exc}",
            corner_peak_C=float("inf"),
            T_j_max_C=T_j_max,
            all_monotone=all_monotone,
            non_monotone_params=non_monotone,
        )

    if not result.is_usable or result.field is None:
        return ThermalSoundnessResult(
            is_sound=False,
            detail=f"Corner FDM solve returned UNMEASURED: {result.error_message}",
            corner_peak_C=float("inf"),
            T_j_max_C=T_j_max,
            all_monotone=all_monotone,
            non_monotone_params=non_monotone,
        )

    corner_peak = float(np.max(result.field.grid))

    if corner_peak <= T_j_max:
        is_sound = True
        detail = (
            f"SOUND: worst-case corner peak T_j = {corner_peak:.1f} C "
            f"<= T_j_max = {T_j_max:.1f} C.  Verdict is mathematically "
            f"guaranteed across the entire uncertainty box for monotone "
            f"parameters."
        )
    else:
        is_sound = False
        detail = (
            f"SAMPLED-ONLY: worst-case corner peak T_j = {corner_peak:.1f} C "
            f"> T_j_max = {T_j_max:.1f} C.  The sampling-based verdict "
            f"may have missed an interior worst case.  The field is NOT "
            f"proven sound across the full parameter box."
        )

    if not all_monotone:
        detail += (
            f"  NOTE: {len(non_monotone)} parameter(s) not provably "
            f"monotone: {', '.join(non_monotone)}.  The corner-bound is "
            f"NOT a guarantee for these parameters."
        )

    corner_values_str = ", ".join(
        f"{k}={v:.3g}" for k, v in sorted(corner.items())
    )
    detail += f"  Corner: [{corner_values_str}]."

    return ThermalSoundnessResult(
        is_sound=is_sound,
        detail=detail,
        corner_peak_C=corner_peak,
        T_j_max_C=T_j_max,
        all_monotone=all_monotone,
        non_monotone_params=non_monotone,
    )
