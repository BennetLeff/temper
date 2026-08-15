"""
Thermal junction temperature estimation for PCB components.

The scalar arithmetic runs in the ``temper-thermal`` Rust kernel
(``estimate_junction_temp_py``, Wave 4 Phase A #3); this module keeps
the public API and the default thermal-resistance parameters.

**Sensor-chain model (corrected 2026-08-15).** The thermal sensor
(NTC_HS) measures **heatsink temperature Ts**, not junction temperature.
The chain is:

    Tj = Tc + P·Rjc        (junction → case)
    Tc = Ts + P·Rch        (case → heatsink, through TIM/isolator pad)
    Ts = Ta + P·Rha        (heatsink → ambient, with fan)

``estimate_junction_temp`` is the collapsed form
(``Tj = Ta + P·(Rjc + Rch + Rha + penalty - benefit)``); the explicit
per-stage chain is computed by ``measure_thermal_edges``
(``temper_thermal``), which reports ``max_ts`` so margins can be anchored
to the sensor. See
``docs/evidence/2026-08-15-thermal-threshold-decision.md`` §3 for the
chain derivation and
``docs/evidence/2026-08-15-thermal-corrections-implemented.md`` for the
corrections.

**Defaults** are the IKW40N120H3 datasheet values (the dominant power
device): Rjc = 0.31 K/W (``components/IKW40N120H3/IKW40N120H3_Documentation.md``
§1.2), Rch = 0.20 K/W (committed TIM/Sil-Pad figure,
``docs/guides/THERMAL_DESIGN_GUIDE.md`` §3.1), Rha = 0.45 K/W (HS1
Wakefield-Vette 392-120AB with fan, same source). Ambient is the 60 °C
design-limit (``docs/ENVIRONMENTAL_SPEC.md`` §1.1 derating zero-power
point; the decision doc §6.4).
"""

from __future__ import annotations

import temper_thermal as _tt

# Design-limit ambient (°C) — the zero-power point of ENVIRONMENTAL_SPEC.md's
# derating curve (100% at 40 °C → 0% at 60 °C). Decision doc §6.4.
DEFAULT_AMBIENT_C: float = 60.0

# Thermal limits per the 2026-08-15 thermal-threshold decision (§6.1, §6.4):
# the firmware over-temp trip (80 °C at the heatsink sensor, first active
# protection layer), the datasheet-recovery design-for junction limit
# (125 °C), and the IKW40N120H3 absolute junction maximum (Tvj(max) = 175 °C).
# The 150 °C that used to serve as the margin basis was the datasheet's
# STORAGE temperature (Tstg = -55…+150 °C), not a junction limit.
FIRMWARE_TRIP_TS_C: float = 80.0
T_J_DESIGN_MAX_C: float = 125.0
T_J_ABS_MAX_C: float = 175.0

# Per-component lumped thermal resistances (Rjc, Rch, Rha) in K/W, keyed by
# refdes (the analysis input unit). Datasheet-recovered values for the
# IKW40N120H3 IGBTs; every other ref is a PLACEHOLDER — the legacy flat
# stand-ins, kept because no datasheet has been recovered for those parts.
# Do not read placeholder entries as measured values. (Designators are not
# stable across branches: U5/U6 are the IGBTs on main; Q1/Q2 are the legacy
# analysis-config names for the same half-bridge devices.)
THERMAL_RESISTANCE_BY_REF: dict[str, tuple[float, float, float]] = {
    "Q1": (0.31, 0.20, 0.45),  # IKW40N120H3 (legacy analysis ref)
    "Q2": (0.31, 0.20, 0.45),  # IKW40N120H3 (legacy analysis ref)
    "U5": (0.31, 0.20, 0.45),  # IKW40N120H3 (hb.power_loop.q_high)
    "U6": (0.31, 0.20, 0.45),  # IKW40N120H3 (hb.power_loop.q_low)
}

# Placeholder (Rjc, Rch, Rha) for devices without a recovered datasheet.
# KEPT UNCHANGED from the pre-correction flat stand-ins — this is the
# documented "no datasheet" value, not a measured one.
PLACEHOLDER_RJC_RCH_RHA: tuple[float, float, float] = (0.6, 0.25, 1.0)


def thermal_resistance_for(ref: str) -> tuple[float, float, float]:
    """Return the per-component (Rjc, Rch, Rha) for a refdes.

    Datasheet-recovered values for the IKW40N120H3 IGBTs; the placeholder
    (0.6, 0.25, 1.0) K/W for every other ref — see the module docstring.
    """
    return THERMAL_RESISTANCE_BY_REF.get(ref, PLACEHOLDER_RJC_RCH_RHA)


def estimate_junction_temp(
    power_W: float,
    edge_distance_mm: float,
    copper_area_mm2: float = 0.0,
    ambient_C: float = DEFAULT_AMBIENT_C,
    Rjc: float = 0.31,
    Rch: float = 0.20,
    Rha_base: float = 0.45,
) -> float:
    """
    Estimate component junction temperature from placement and environment.

    Model: Tj = Tamb + P * (Rjc + Rch + Rha)
    Rha depends on distance to board edge (heatsink mount) and copper area.

    Args:
        power_W: Power dissipation in Watts.
        edge_distance_mm: Distance to board edge in mm.
        copper_area_mm2: Area of connected copper pour in mm².
        ambient_C: Ambient temperature in °C (default 60 — the design-limit
            ambient, `docs/ENVIRONMENTAL_SPEC.md` derating zero-power point).
        Rjc: Junction-to-case thermal resistance (K/W). Default 0.31
            (IKW40N120H3 datasheet Rth(j-c); supersedes the flat 0.6
            TO-247 stand-in).
        Rch: Case-to-heatsink thermal resistance (K/W). Default 0.20
            (committed TIM/Sil-Pad figure, THERMAL_DESIGN_GUIDE.md §3.1).
        Rha_base: Base heatsink-to-ambient resistance (K/W). Default 0.45
            (HS1 Wakefield-Vette 392-120AB with fan; supersedes the flat
            1.0 natural-convection stand-in).

    The arithmetic runs in the ``temper-thermal`` Rust kernel
    (``estimate_junction_temp_py``, Wave 4 Phase A #3), which mirrors
    this function's exact f64 operation order bit-for-bit (pinned by the
    differential suite ``tests/physics/test_thermal_rust_differential.py``).

    Returns:
        Estimated junction temperature in °C.
    """
    return _tt.estimate_junction_temp_py(
        power_W,
        edge_distance_mm,
        copper_area_mm2,
        ambient_C,
        Rjc,
        Rch,
        Rha_base,
    )
