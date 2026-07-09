"""
Canonical per-device power model (issue #140).

ONE source of truth for per-device power dissipation — used by BOTH the
U6 operating-point gate AND the U10 thermal helps-battery.  No caller
should hardcode power values; the operating point + datasheet loss params
are the authority.

Per-device power model:
- IGBT: P = V_ce_sat * I_rms + (E_on + E_off) * f_sw
  (fallback to waveform approximation when E_on/E_off not provided)
- Diode: P = V_f * I_avg + E_rr * f_sw  (I_avg approx I_rms / 2)
- MOSFET: P = I_rms^2 * R_ds_on + ...  (when R_ds_on > 0)

Public API
----------
.. code-block:: python

    from temper_placer.physics.device_power import (
        DeviceLossConfig,
        derive_power_map,
        temper_igbt_loss_config,
        temper_diode_loss_config,
    )

    power_map = derive_power_map(op_config, device_loss_configs)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from temper_placer.physics.operating_point import OperatingPointConfig


# ---------------------------------------------------------------------------
# Per-device loss config with datasheet citations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceLossConfig:
    """Per-device loss parameters with datasheet citations.

    Every loss parameter carries a ``because`` string linking it to the
    manufacturer datasheet — never a magic number.

    For IGBT/MOSFET devices:
    - Conduction: V_ce_sat * I_rms  (or I_rms^2 * R_ds_on for MOSFETs)
    - Switching: (E_on + E_off) * f_sw  (preferred) or waveform approximation

    For DIODE devices:
    - Conduction: V_f * I_avg  (I_avg approx I_rms / 2 for half-bridge)
    - Switching: E_rr * f_sw  (reverse-recovery loss)
    """

    name: str
    """Device reference designator (e.g. 'Q1', 'D1')."""

    device_type: str
    """'IGBT' or 'DIODE'."""

    # --- IGBT / MOSFET conduction ---------------------------------------
    V_ce_sat: float = 0.0
    """On-state collector-emitter voltage (V).  0.0 when using R_ds_on."""

    R_ds_on: float = 0.0
    """On-state drain-source resistance (ohm) for MOSFET.  0.0 means IGBT."""

    # --- IGBT / MOSFET switching (datasheet energy method) ---------------
    E_on: float = 0.0
    """Turn-on energy (J) per switching event."""

    E_off: float = 0.0
    """Turn-off energy (J) per switching event."""

    # --- Diode -----------------------------------------------------------
    V_f: float = 0.0
    """Forward voltage (V) for diode conduction loss."""

    E_rr: float = 0.0
    """Reverse-recovery energy (J) per switching event."""

    # --- Citations (required — no magic numbers) -------------------------
    V_ce_sat_because: str = ""
    """Datasheet citation for V_ce_sat."""

    E_on_because: str = ""
    """Datasheet citation for E_on."""

    E_off_because: str = ""
    """Datasheet citation for E_off."""

    V_f_because: str = ""
    """Datasheet citation for V_f."""

    E_rr_because: str = ""
    """Datasheet citation for E_rr."""


# ---------------------------------------------------------------------------
# Representative device loss configs for the Temper half-bridge
# ---------------------------------------------------------------------------


def temper_igbt_loss_config(name: str = "Q") -> DeviceLossConfig:
    """Representative STGW30NC60W IGBT loss config.

    STGW30NC60W: 600 V, 30 A IGBT with co-pack diode.
    Datasheet values at V_CE = 390 V, I_C = 30 A, R_G = 10 Ohm,
    T_j = 25 C (typical).
    """
    return DeviceLossConfig(
        name=name,
        device_type="IGBT",
        V_ce_sat=1.7,
        E_on=0.32e-3,
        E_off=0.21e-3,
        V_ce_sat_because=(
            "STGW30NC60W datasheet, Table 6: On-state characteristics, "
            "V_CE(sat) typ = 1.7 V at I_C = 30 A, T_j = 25 C"
        ),
        E_on_because=(
            "STGW30NC60W datasheet, Table 8: Switching characteristics, "
            "E_on typ = 0.32 mJ at V_CE = 390 V, I_C = 30 A, R_G = 10 Ohm"
        ),
        E_off_because=(
            "STGW30NC60W datasheet, Table 8: Switching characteristics, "
            "E_off typ = 0.21 mJ at V_CE = 390 V, I_C = 30 A, R_G = 10 Ohm"
        ),
    )


def temper_diode_loss_config(name: str = "D") -> DeviceLossConfig:
    """Representative fast-recovery rectifier diode loss config.

    Representative values for a 600 V, 30 A fast-recovery diode
    (e.g. STTH30R04 or equivalent) in the Temper half-bridge
    freewheeling leg.
    """
    return DeviceLossConfig(
        name=name,
        device_type="DIODE",
        V_f=1.05,
        E_rr=0.06e-3,
        V_f_because=(
            "representative fast-recovery diode V_F typ = 1.05 V at I_F = 30 A, "
            "T_j = 25 C (e.g. STTH30R04 datasheet, Table 5: Static electrical)"
        ),
        E_rr_because=(
            "estimated from Q_rr * V_R / 2: Q_rr typ approx 300 nC at I_F = 30 A, "
            "V_R = 390 V, di/dt = 200 A/us, giving E_rr approx 0.06 mJ per event "
            "(representative fast-recovery diode, not a specific BOM part)"
        ),
    )


# ---------------------------------------------------------------------------
# Core computation — ONE canonical power formula
# ---------------------------------------------------------------------------


def _compute_single_device_power(
    V_bus: float,
    I_load_rms: float,
    f_sw: float,
    device: DeviceLossConfig,
    *,
    t_rise: float = 50e-9,
    t_fall: float = 50e-9,
) -> float:
    """Compute total power dissipation for ONE device.

    This is the SINGLE canonical power formula — used by both the
    U6 operating-point gate AND the U10 thermal helps-battery.

    Args:
        V_bus: DC bus voltage (V).
        I_load_rms: Worst-case RMS load current (A).
        f_sw: Switching frequency (Hz).
        device: Per-device loss config with datasheet citations.
        t_rise: Rise time (s) — fallback for waveform switching model.
        t_fall: Fall time (s) — fallback for waveform switching model.
    """
    if device.device_type == "DIODE":
        I_avg = I_load_rms * 0.5
        P_cond = I_avg * device.V_f
        P_sw = device.E_rr * f_sw
        return P_cond + P_sw

    # IGBT or MOSFET
    if device.R_ds_on > 0:
        P_cond = I_load_rms**2 * device.R_ds_on
    else:
        P_cond = I_load_rms * device.V_ce_sat

    if device.E_on > 0 or device.E_off > 0:
        P_sw = (device.E_on + device.E_off) * f_sw
    else:
        I_peak = I_load_rms * math.sqrt(2)
        P_sw = 0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)

    return P_cond + P_sw


def derive_power_map(
    op_config: OperatingPointConfig,
    device_loss_configs: dict[str, DeviceLossConfig],
) -> dict[str, float]:
    """Derive per-device power map from shared operating point + per-device
    loss configs.

    Args:
        op_config: ``OperatingPointConfig`` providing V_bus, I_load_rms,
            f_sw, t_rise, t_fall — the shared operating point.
        device_loss_configs: ``{ref: DeviceLossConfig}`` per-device loss
            params with datasheet ``because`` citations.

    Returns:
        ``{ref: power_W}`` map suitable for ``solve_thermal_fdm``.

    Raises:
        ValueError: If a device has a required loss param missing (e.g.
            an IGBT with V_ce_sat=0 and R_ds_on=0, or a diode with V_f=0).
    """
    power_map: dict[str, float] = {}

    for ref, dev in device_loss_configs.items():
        # Fail-closed: validate required loss params are present
        if dev.device_type == "DIODE":
            if dev.V_f <= 0:
                raise ValueError(
                    f"Device '{ref}' (DIODE): V_f is missing or zero — "
                    f"cannot compute conduction loss. "
                    f"Provide a datasheet V_f with a 'because' citation."
                )
        else:
            if dev.V_ce_sat <= 0 and dev.R_ds_on <= 0:
                raise ValueError(
                    f"Device '{ref}' ({dev.device_type}): both V_ce_sat and "
                    f"R_ds_on are zero/missing — cannot compute conduction "
                    f"loss. Provide a datasheet V_ce_sat or R_ds_on with a "
                    f"'because' citation."
                )

        power_map[ref] = _compute_single_device_power(
            V_bus=op_config.V_bus,
            I_load_rms=op_config.I_load_rms,
            f_sw=op_config.f_sw,
            device=dev,
            t_rise=op_config.t_rise,
            t_fall=op_config.t_fall,
        )

    return power_map
