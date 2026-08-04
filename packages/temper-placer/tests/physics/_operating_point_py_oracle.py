"""Pinned pre-migration oracle for ``temper_placer.physics.operating_point``.

**Do not edit.**  Verbatim copies of the module's *numeric core* AS
COMMITTED at ``origin/main`` before the Rust kernels in
``packages/temper-thermal/src/operating_point.rs`` existed
(``f57b52d51``): the continuous coupling model ``_l_eff``, the ceiling
arithmetic of ``compute_extremes``, and the endpoint/interior arithmetic
of ``_interior_bounding_soundness_check``.

The `Violation` payload construction, the `Gate` plumbing, the SPICE
cross-check and the config dataclass are **not** migrated and are
therefore not duplicated here; `_oracle_interior_records` reproduces only
the arithmetic and the three predicates that decide whether a violation
is emitted, in the reference's exact order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the verbatim block below annotates against the real type
    from temper_placer.physics.operating_point import OperatingPointConfig

# Number of coupling grid points for interior-sampling safeguard.
_INTERIOR_GRID_POINTS = 11  # k = 0.00, 0.10, ..., 1.00


@dataclass(frozen=True)
class _ExtremePoint:
    """Result at ONE coupling extreme (k=0 or k=1) -- oracle copy."""

    label: str
    coupling: float
    di_dt: float
    P_device: float
    T_j: float
    L_loop_max: float
    feasible: bool


def _l_eff(cfg: OperatingPointConfig, k: float) -> float:
    """Effective inductance at coupling coefficient k ∈ [0, 1].

    L_eff(k) = L_coil·(1−k) + L_leakage·k

    This linear-interpolation model is the simplest physically-grounded
    continuous coupling model: the effective inductance transitions from the
    uncoupled work-coil inductance (L_coil at k=0) to the fully-coupled
    leakage inductance (L_leakage at k=1).

    **Monotonicity proof — endpoints PROVABLY bound the interior:**

    Since L_coil > 0 and L_leakage > 0 (enforced at config validation),
    L_eff(k) is linear in k and strictly positive on [0, 1].  Therefore:

    1. di/dt(k) = V_bus / L_eff(k)
       — monotone in k because L_eff(k) is monotone in k, V_bus > 0,
       and 1/x is monotone for x > 0.

    2. P_device and T_j
       — independent of coupling (they depend on I_load_rms, V_bus, f_sw,
       R_θ, etc., none of which are functions of k).

    3. L_loop_max(k) = (V_BR·derate − V_bus) / di/dt(k)
       — monotone in k as a monotone function of di/dt(k).

    Since all quantities of interest are monotone in k, the worst-case
    (highest di/dt, lowest L_loop_max) MUST occur at an endpoint k=0
    or k=1.  The endpoints therefore provably bound all interior coupling
    values.
    """
    return cfg.L_coil * (1.0 - k) + cfg.L_leakage * k


def _oracle_compute_extremes(cfg, P_device: float):
    """Compute di/dt, per-device power, and ceiling checks at BOTH extremes.

    ``P_device`` is passed in rather than recomputed: the per-device power
    model already delegates to temper-thermal (issue #140), so re-deriving
    it here would pin the wrong thing.
    """
    R_th_total = cfg.R_theta_jc + cfg.R_theta_cs + cfg.R_theta_sa
    v_br_derated = cfg.V_BR * cfg.derate
    T_j = cfg.T_amb + P_device * R_th_total

    def _extreme(label: str, coupling: float, L_eff: float) -> _ExtremePoint:
        di_dt_val = cfg.V_bus / L_eff
        # L_loop_max condition: V_bus + L_loop * di/dt ≤ V_BR * derate
        # → L_loop ≤ (V_BR * derate - V_bus) / di/dt
        num = v_br_derated - cfg.V_bus
        l_loop_max = 0.0 if num <= 0 else num / di_dt_val

        feasible = T_j <= cfg.T_j_max and l_loop_max >= cfg.min_feasible_L_loop
        return _ExtremePoint(
            label=label,
            coupling=coupling,
            di_dt=di_dt_val,
            P_device=P_device,
            T_j=T_j,
            L_loop_max=l_loop_max,
            feasible=feasible,
        )

    k0 = _extreme("zero-coupling (k=0)", 0.0, cfg.L_coil)
    k1 = _extreme("ideal-coupling (k=1)", 1.0, cfg.L_leakage)
    return k0, k1


def _oracle_interior_records(
    cfg,
    coupling_l_eff_fn: Callable[[float], float] | None = None,
):
    """Verbatim arithmetic + predicates of ``_interior_bounding_soundness_check``.

    Returns ``(evaluated, endpoint_worst_di_dt, endpoint_worst_L_loop_max,
    l_loop_max_k0, l_loop_max_k1, records)`` where each record is
    ``(k, di_dt_val, l_loop_max, breaches_min_feasible, worse_di_dt,
    worse_l_loop_max)`` -- the three conditions that decide whether the
    reference appends a Violation, in the reference's order.
    """
    if coupling_l_eff_fn is None:

        def coupling_l_eff_fn(k):
            return _l_eff(cfg, k)

    v_br_derated = cfg.V_BR * cfg.derate
    num = v_br_derated - cfg.V_bus

    l_eff_k0 = coupling_l_eff_fn(0.0)
    l_eff_k1 = coupling_l_eff_fn(1.0)
    if l_eff_k0 <= 0 or l_eff_k1 <= 0:
        return (False, 0.0, 0.0, 0.0, 0.0, [])

    di_dt_k0 = cfg.V_bus / l_eff_k0
    di_dt_k1 = cfg.V_bus / l_eff_k1
    endpoint_worst_di_dt = max(di_dt_k0, di_dt_k1)

    l_loop_max_k0 = num / di_dt_k0 if num > 0 else 0.0
    l_loop_max_k1 = num / di_dt_k1 if num > 0 else 0.0
    endpoint_worst_L_loop_max = min(l_loop_max_k0, l_loop_max_k1)

    records = []
    for i in range(1, _INTERIOR_GRID_POINTS - 1):
        k = i / (_INTERIOR_GRID_POINTS - 1)
        L_eff_val = coupling_l_eff_fn(k)
        if L_eff_val <= 0:
            continue

        di_dt_val = cfg.V_bus / L_eff_val

        l_loop_max = num / di_dt_val if num > 0 else 0.0

        records.append(
            (
                k,
                di_dt_val,
                l_loop_max,
                l_loop_max < cfg.min_feasible_L_loop,
                di_dt_val > endpoint_worst_di_dt * (1.0 + 1e-12),
                l_loop_max < endpoint_worst_L_loop_max * (1.0 - 1e-12),
            )
        )

    return (
        True,
        endpoint_worst_di_dt,
        endpoint_worst_L_loop_max,
        l_loop_max_k0,
        l_loop_max_k1,
        records,
    )
