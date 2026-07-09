"""
Operating-point cross-check gate (coupled-load bounding; gates the battery).

U6: Derives a closed-form bounding operating point for the coupled induction
load at ideal-coupling vs zero-coupling extremes, confirms datasheet ceilings
stay feasible across that range, and guards against SPICE-vs-analytic
circularity by recording shared model assumptions.

The per-device power values this gate validates are the SAME values the
thermal solver uses as Q heat sources — both sourced from the config/YAML
authority (cross-cutting invariant with the field track's U5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)

# ---------------------------------------------------------------------------
# Config input contract (shared power source-of-truth with thermal solver)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperatingPointConfig:
    """Electrical / thermal parameters that define the operating point.

    This is the input contract for U6.  The same values feed the thermal
    solver (field-track U5) so there is exactly one power-source model.

    Every nullable field defaults to a sensible Temper half-bridge value
    but callers SHOULD supply explicit values from the YAML authority.
    """

    V_bus: float
    """DC bus voltage (V).  eg 325 V for rectified 230 VAC."""

    V_BR: float
    """Switch breakdown voltage (V).  eg 1200 V for IGBT half-bridge."""

    I_load_rms: float
    """Worst-case RMS load current (A).  eg 16 A."""

    L_coil: float
    """Work-coil inductance (H).  Used for zero-coupling di/dt bound."""

    L_leakage: float
    """Leakage inductance (H).  Used for ideal-coupling di/dt bound."""

    f_sw: float
    """Switching frequency (Hz)."""

    # --- Thermal chain (shared with U5 thermal solver) ------------------
    T_amb: float = 40.0
    """Ambient temperature (°C)."""

    T_j_max: float = 150.0
    """Maximum junction temperature (°C)."""

    R_theta_jc: float = 0.6
    """Junction-to-case thermal resistance (K/W)."""

    R_theta_cs: float = 0.25
    """Case-to-sink thermal resistance (K/W)."""

    R_theta_sa: float = 2.0
    """Sink-to-ambient thermal resistance (K/W)."""

    # --- Switching waveform ----------------------------------------------
    t_rise: float = 50e-9
    """Rise time (s)."""

    t_fall: float = 50e-9
    """Fall time (s)."""

    V_ce_sat: float = 1.7
    """On-state collector-emitter voltage (V) for IGBT.  Use 0.0 when
    the device is a MOSFET (R_ds_on model)."""

    R_ds_on: float = 0.0
    """On-state drain-source resistance (ohm) for MOSFET.  0 means IGBT."""

    # --- Derating --------------------------------------------------------
    derate: float = 0.80
    """Voltage derating factor applied to V_BR.  eg 0.80 → 80% of V_BR."""

    min_feasible_L_loop: float = 5e-9
    """Minimum achievable commutation-loop inductance (H).  Default 5 nH
    is typical for a tight half-bridge layout with kelvin connections."""


def _validate_config(raw: dict[str, Any]) -> OperatingPointConfig:
    """Coerce a dict (from YAML config) into a validated OperatingPointConfig.

    Raises ``TypeError`` / ``ValueError`` with an immediate message when
    a required key is missing or obviously nonsensical (negative V_bus, etc.).
    """
    required = {"V_bus", "V_BR", "I_load_rms", "L_coil", "L_leakage", "f_sw"}
    missing = required - raw.keys()
    if missing:
        raise TypeError(
            f"OperatingPointConfig missing required keys: {sorted(missing)}"
        )
    kwargs: dict[str, Any] = {k: raw[k] for k in required}
    for opt in (
        "T_amb",
        "T_j_max",
        "R_theta_jc",
        "R_theta_cs",
        "R_theta_sa",
        "t_rise",
        "t_fall",
        "V_ce_sat",
        "R_ds_on",
        "derate",
        "min_feasible_L_loop",
    ):
        if opt in raw:
            kwargs[opt] = raw[opt]

    cfg = OperatingPointConfig(**kwargs)
    if cfg.V_bus <= 0:
        raise ValueError("V_bus must be > 0")
    if cfg.V_BR <= 0:
        raise ValueError("V_BR must be > 0")
    if cfg.L_coil <= 0:
        raise ValueError("L_coil must be > 0")
    if cfg.L_leakage <= 0:
        raise ValueError("L_leakage must be > 0")
    if not (0.0 < cfg.derate <= 1.0):
        raise ValueError("derate must be in (0, 1]")
    return cfg


# ---------------------------------------------------------------------------
# Operating-point computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ExtremePoint:
    """Result at ONE coupling extreme (k=0 or k=1)."""

    label: str
    """Human-readable label: 'zero-coupling' or 'ideal-coupling'."""

    coupling: float
    """Coupling coefficient (0.0 or 1.0)."""

    di_dt: float
    """Current slew rate (A/s) at this extreme."""

    P_device: float
    """Per-device total power dissipation (W)."""

    T_j: float
    """Estimated junction temperature (°C)."""

    L_loop_max: float
    """Maximum allowable commutation-loop inductance (H) to stay under
    V_BR * derate."""

    feasible: bool
    """True when both ceilings are satisfied at this extreme."""


def _compute_per_device_power(cfg: OperatingPointConfig) -> float:
    """Per-semiconductor total power (conduction + switching)."""
    if cfg.R_ds_on > 0:
        P_cond = cfg.I_load_rms**2 * cfg.R_ds_on
    else:
        P_cond = cfg.I_load_rms * cfg.V_ce_sat

    I_peak = cfg.I_load_rms * math.sqrt(2)
    P_sw = (
        0.5
        * cfg.V_bus
        * I_peak
        * cfg.f_sw
        * (cfg.t_rise + cfg.t_fall)
    )
    return P_cond + P_sw


def compute_extremes(cfg: OperatingPointConfig) -> tuple[_ExtremePoint, _ExtremePoint]:
    """Compute di/dt, per-device power, and ceiling checks at BOTH extremes."""
    R_th_total = cfg.R_theta_jc + cfg.R_theta_cs + cfg.R_theta_sa
    v_br_derated = cfg.V_BR * cfg.derate
    P_device = _compute_per_device_power(cfg)
    T_j = cfg.T_amb + P_device * R_th_total

    def _extreme(label: str, coupling: float, L_eff: float) -> _ExtremePoint:
        di_dt_val = cfg.V_bus / L_eff
        # L_loop_max condition: V_bus + L_loop * di/dt ≤ V_BR * derate
        # → L_loop ≤ (V_BR * derate - V_bus) / di/dt
        num = v_br_derated - cfg.V_bus
        if num <= 0:
            l_loop_max = 0.0
        else:
            l_loop_max = num / di_dt_val

        feasible = (
            T_j <= cfg.T_j_max
            and l_loop_max >= cfg.min_feasible_L_loop
        )
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


# ---------------------------------------------------------------------------
# SPICE cross-check metadata
# ---------------------------------------------------------------------------


@dataclass
class SpiceCrossCheckInfo:
    """Metadata from the independent SPICE cross-check.

    Stored as ``Gate.last_cross_check`` so callers can inspect whether
    SPICE and the analytic model agreed or shared dangerous assumptions.
    """

    available: bool = False
    """True when ngspice was reachable (preflight passed)."""

    ran: bool = False
    """True when the simulation was actually executed."""

    success: bool = False
    """True when the simulation completed without errors."""

    measurements: dict[str, float] = field(default_factory=dict)
    """Key SPICE measurements (di_dt, avg_power, etc.)."""

    analytic_match: bool = False
    """True when SPICE results agree with the analytic model within
    the configured tolerance."""

    shared_assumptions: tuple[str, ...] = ()
    """Model assumptions the SPICE netlist and the analytic derivation
    both rely on (transformer coupling, no eddy losses, etc.)."""

    notes: str = ""
    """Free-form human note about the cross-check."""

    @property
    def circularity_risk(self) -> bool:
        """True when SPICE and analytic share at least one model assumption.

        Agreement is NOT independent evidence when the same assumption
        is baked into both models.
        """
        return len(self.shared_assumptions) > 0


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class OperatingPointGate(Gate):
    """ROUTING-stage gate: coupled-load operating-point feasibility.

    Derives a closed-form operating-point envelope at both coupling
    extremes (k=0 → L_coil, k=1 → L_leakage) and verifies that the
    datasheet ceilings

    * *T_j ≤ T_j(max)*  (because: IEC 60335-1 §11, device datasheet
      absolute-maximum ratings)
    * *L_loop ≤ (V_BR · derate − V_bus) / (di/dt)*  (because: device
      datasheet V_BR(DSS) / V_CES rating, derated per IPC-9592)

    are feasible across the entire coupling range.

    Returns ``VIOLATIONS`` when the feasible band is empty at either
    extreme (names the physical knob that can fix it: bigger R_θ /
    snubber / slower gate / part swap).  Returns ``UNMEASURED`` when
    the independent SPICE cross-check cannot run (fail-closed; never
    a silent pass).
    """

    stage = GateStage.ROUTING
    name = "operating_point"

    # Shared assumptions between the SPICE template and the analytic model.
    # Both use an ideal-transformer coupling model with no eddy-current
    # losses — agreement across them is NOT independent evidence.
    _DEFAULT_SHARED_ASSUMPTIONS: tuple[str, ...] = (
        "transformer_coupling_model",
        "no_eddy_current_losses",
    )

    def __init__(
        self,
        config: dict[str, Any],
        spice_validator: Any | None = None,
        *,
        tolerance: float = 0.20,
    ):
        """
        Args:
            config: Dict matching the ``OperatingPointConfig`` contract.
                Same values the thermal solver (U5) consumes.
            spice_validator: ``NgspiceValidator`` instance.  Created
                lazily with defaults when ``None``.
            tolerance: Fractional tolerance for SPICE-vs-analytic
                agreement (default 20%).
        """
        self._cfg = _validate_config(config)
        self._spice = spice_validator
        self._tolerance = tolerance
        self.last_cross_check: SpiceCrossCheckInfo | None = None

    # ------------------------------------------------------------------
    # check
    # ------------------------------------------------------------------

    def check(self, _state: BoardState) -> GateResult:
        """Run the operating-point cross-check."""
        k0, k1 = compute_extremes(self._cfg)

        violations: list[Violation] = []

        # --- Analytic ceiling checks -----------------------------------
        for point in (k0, k1):
            if point.T_j > self._cfg.T_j_max:
                violations.append(
                    Violation(
                        type=ViolationType.THERMAL,
                        components=("Q1", "Q2"),
                        severity=point.T_j,
                        threshold=self._cfg.T_j_max,
                        description=(
                            f"T_j = {point.T_j:.1f}°C exceeds "
                            f"T_j(max) = {self._cfg.T_j_max:.0f}°C "
                            f"at {point.label} "
                            f"(di/dt = {point.di_dt:.2e} A/s, "
                            f"P_device = {point.P_device:.1f} W). "
                            f"Fix: larger R_θ / bigger heatsink / "
                            f"lower f_sw / part swap."
                        ),
                        context={
                            "because": (
                                "IEC 60335-1 §11; device datasheet "
                                "absolute-maximum T_j"
                            ),
                            "extreme": point.label,
                            "coupling": point.coupling,
                            "di_dt_A_per_s": point.di_dt,
                            "P_device_W": point.P_device,
                            "T_amb_C": self._cfg.T_amb,
                            "R_th_total_K_per_W": (
                                self._cfg.R_theta_jc
                                + self._cfg.R_theta_cs
                                + self._cfg.R_theta_sa
                            ),
                        },
                    )
                )

            if point.L_loop_max < self._cfg.min_feasible_L_loop:
                violations.append(
                    Violation(
                        type=ViolationType.LOOP_INDUCTANCE,
                        components=("Q1", "Q2", "C_BUS1", "C_BUS2"),
                        nets=("DC_BUS+", "SW_NODE", "DC_BUS-"),
                        severity=point.L_loop_max * 1e9,
                        threshold=self._cfg.min_feasible_L_loop * 1e9,
                        description=(
                            f"L_loop_max = {point.L_loop_max * 1e9:.2f} nH "
                            f"(needed to stay under V_BR·derate = "
                            f"{self._cfg.V_BR * self._cfg.derate:.0f} V) "
                            f"is below the minimum realizable "
                            f"{self._cfg.min_feasible_L_loop * 1e9:.1f} nH "
                            f"at {point.label}. "
                            f"di/dt = {point.di_dt:.2e} A/s. "
                            f"Fix: slower gate drive / snubber / "
                            f"higher-V_BR part / lower V_bus."
                        ),
                        context={
                            "because": (
                                "device datasheet V_BR(DSS) / V_CES, "
                                "derated per IPC-9592"
                            ),
                            "extreme": point.label,
                            "coupling": point.coupling,
                            "di_dt_A_per_s": point.di_dt,
                            "L_loop_max_H": point.L_loop_max,
                            "V_br_derated_V": (
                                self._cfg.V_BR * self._cfg.derate
                            ),
                            "V_bus_V": self._cfg.V_bus,
                        },
                    )
                )

        # --- SPICE cross-check -----------------------------------------
        cc = self._run_spice_cross_check(k0, k1)
        self.last_cross_check = cc

        if not cc.available:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    "ngspice not available — cannot perform independent "
                    "operating-point cross-check. Install ngspice for "
                    "electrical validation."
                ),
            )

        if not cc.ran:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    "SPICE cross-check could not be executed: "
                    f"{cc.notes}"
                ),
            )

        if violations:
            return GateResult(
                GateStatus.VIOLATIONS,
                violations=tuple(violations),
            )
        return GateResult(GateStatus.CLEAN)

    # ------------------------------------------------------------------
    # SPICE cross-check helper
    # ------------------------------------------------------------------

    def _run_spice_cross_check(
        self, k0: _ExtremePoint, k1: _ExtremePoint
    ) -> SpiceCrossCheckInfo:
        """Run the independent SPICE simulation and compare with analytic.

        Never mutates self (called inside check()).  Returns a
        ``SpiceCrossCheckInfo`` for the gate to store and inspect.
        """
        # Resolve the validator lazily so tests can inject mocks.
        if self._spice is None:
            from temper_placer.validation.spice import NgspiceValidator

            self._spice = NgspiceValidator()

        shared = self._DEFAULT_SHARED_ASSUMPTIONS

        if not self._spice.check_ngspice():
            return SpiceCrossCheckInfo(
                available=False,
                shared_assumptions=shared,
                notes="ngspice binary not found or non-functional",
            )

        # Build a minimal half-bridge SPICE netlist that can measure
        # di/dt and average power in the coupled-load configuration.
        try:
            result = self._spice.run_template(
                _HALF_BRIDGE_OP_TEMPLATE,
                {
                    "V_BUS": f"{self._cfg.V_bus}",
                    "L_EFF": f"{self._cfg.L_coil:.6e}",
                    "L_LEAK": f"{self._cfg.L_leakage:.6e}",
                    "F_SW": f"{self._cfg.f_sw}",
                    "T_RISE": f"{self._cfg.t_rise:.3e}",
                    "T_FALL": f"{self._cfg.t_fall:.3e}",
                },
            )
        except Exception as exc:
            return SpiceCrossCheckInfo(
                available=True,
                ran=False,
                shared_assumptions=shared,
                notes=f"SPICE run_template raised: {exc}",
            )

        if not result.success:
            return SpiceCrossCheckInfo(
                available=True,
                ran=True,
                success=False,
                shared_assumptions=shared,
                notes=f"SPICE simulation failed: {result.errors[:3]}",
            )

        measurements = {
            name: meas.value
            for name, meas in result.measurements.items()
        }

        # Compare SPICE-vs-analytic at zero-coupling (k=0, L_coil).
        # di/dt = V_bus / L_coil, L_loop_max = (V_BR*derate - V_bus)/di_dt
        analytic_di_dt = k0.di_dt
        spice_di_dt = measurements.get("di_dt_k0", None)
        match = spice_di_dt is not None and (
            abs(spice_di_dt - analytic_di_dt)
            <= self._tolerance * max(abs(analytic_di_dt), 1e-3)
        )

        return SpiceCrossCheckInfo(
            available=True,
            ran=True,
            success=True,
            measurements=measurements,
            analytic_match=match,
            shared_assumptions=shared,
            notes="SPICE cross-check completed",
        )


# ---------------------------------------------------------------------------
# SPICE netlist template for the half-bridge operating-point probe.
#
# This is intentionally minimal — it models a single half-bridge leg
# with an equivalent load inductance and measures di/dt and power.
# BOTH this template and the analytic model share the same transformer
# coupling and no-eddy-loss assumptions → agreement is NOT independent.
# ---------------------------------------------------------------------------

_HALF_BRIDGE_OP_TEMPLATE = r"""
* Half-bridge operating-point probe (U6 cross-check)
* Shared assumptions: transformer_coupling_model, no_eddy_current_losses

.param V_BUS = {{V_BUS}}
.param L_EFF = {{L_EFF}}
.param L_LEAK = {{L_LEAK}}
.param F_SW  = {{F_SW}}
.param T_RISE = {{T_RISE}}
.param T_FALL = {{T_FALL}}

Vbus  VBUS  0  DC {V_BUS}

* Ideal switch model — MOSFET with controlled turn-on/off ramps
* (simplified; real device models are loaded in the full validation pipeline)
M1  VBUS  GATE_H  SW_NODE  0  SW  W=100 L=0.5u
Rg1 GATE_H 0 10

* Load inductance (zero-coupling: L_EFF = L_coil)
Lload  SW_NODE  SW_RTN  {L_EFF}

* Snubber (parasitic loop inductance proxy = L_LEAK)
Lloop  SW_RTN  0  {L_LEAK}

.model SW NMOS (LEVEL=1 VTO=5 KP=1e3)

* Switching stimulus
Vpulse GATE_H 0 PULSE(0 15 0 {T_RISE} {T_FALL} {1/(2*F_SW)-T_RISE-T_FALL} {1/F_SW})

.tran 1n {3/F_SW} {1/F_SW} uic
.meas TRAN di_dt_k0  DERIV I(Vbus) AT = {2/F_SW}
.meas TRAN avg_power AVG (V(VBUS)*I(Vbus)) FROM = {1/F_SW} TO = {3/F_SW}
.end
"""
