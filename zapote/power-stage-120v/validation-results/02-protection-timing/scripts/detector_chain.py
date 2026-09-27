#!/usr/bin/env python3
"""Bounded desk calculations for the tank-CT detector and the shutdown chain.

    python3 validation-results/02-protection-timing/scripts/detector_chain.py > .../outputs/detector_chain.json

Every constant names its source (sources/datasheets.json for URLs and hashes).
Values marked "assumed" are not datasheet numbers and are stated in the report.
This is a bounded calculation, not SPICE: it sums worst-case link delays and
does not model interaction between links. The trip-band numbers come from the
Rust corner model (tools/ct_detector) re-run at the stated leakages; this
script only records them.
"""
from __future__ import annotations

import json
import math

# ------------------------------------------------------------------ CT transfer
L_SEC = 3.2e-3          # CST3015-100ED secondary inductance, H (Coilcraft; docs/evidence/2026-08-13-tank-fault-sizing-inputs.md)
R_SEC = 1.5             # CST3015-100ED secondary DCR, ohm (same source)
R_BURDEN = 1.5          # R39, RC1206FR-071R5L
C_BURDEN = 100e-9       # C42, GRM31C5C1H104JA01L
N = 100
VT_LIMIT = 638e-6       # CST3015-100ED volt-time product, V*s


def ct_transfer(f: float) -> dict:
    w = 2 * math.pi * f
    z_load = 1 / (1 / R_BURDEN + 1j * w * C_BURDEN)        # burden || C
    z_branch = R_SEC + z_load
    z_mag = 1j * w * L_SEC
    i_load = z_mag / (z_mag + z_branch)                        # current divider, per amp of I_p/N
    v_sense = i_load * z_load / R_BURDEN                       # normalized to the ideal I_s * R_burden
    return {"f_hz": f, "gain_error_pct": round((abs(v_sense) - 1) * 100, 3),
            "phase_deg": round(math.degrees(math.atan2(v_sense.imag, v_sense.real)), 2)}


def ct_flux(i_primary_pk: float, f: float) -> float:
    """Half-cycle volt-seconds demanded by the terminated secondary (sine)."""
    v_pk = i_primary_pk / N * abs(R_SEC + R_BURDEN)
    return 2 * v_pk / (2 * math.pi * f)


# ---------------------------------------------------------- trip vs leakage
# Rust corner model (tools/ct_detector/ct_detector_model.rs) re-run with the
# total clamp leakage bound replaced; min/max over all 65,536 corners.
TRIP_BANDS = {
    "BAT54H, 25 C (model default, 4 uA)": [50.93, 59.51],
    "BAT54H, ~85 C (60 uA: 2 x Fig. 2 typical)": [45.34, 65.21],
    "BAT54H, ~125 C (600 uA: 2 x Fig. 2 typical)": [-8.71, 120.17],
    "BAT54H ~125 C with R42 = 100 ohm": [27.49, 83.42],
    "BAS116H, 150 C (2 x 80 nA max, Table 7)": "use the 25 C band: 0.16 uA is below the 4 uA default",
}

# ------------------------------------------------------ zero-cross at idle
VOS_MAX = 4e-3           # TLV3201 VIO, -40..125 C, VCM=VCC/2 (SBOS561C 6.7)
HYST_TYP = 1.2e-3        # TLV3201 input hysteresis, typical only (no min/max given)
V_PER_A = R_BURDEN / N   # 15 mV per primary amp at the comparator


def zc_phase_error(i_pk: float, v_offset: float) -> float:
    return math.degrees(math.asin(min(1.0, v_offset / (i_pk * V_PER_A))))


# ------------------------------------------------------- shutdown chain
VCC_MIN = 3.135                     # interlock contract, 3.3 V -5 %
AO3400_CISS_BOUND = 900e-12         # assumed: datasheet 630 pF at VDS 15 V, higher at low VDS
AO3400_COSS_BOUND = 150e-12         # assumed: datasheet 75 pF at VDS 15 V, higher at low VDS
DIS_PIN_AND_TRACE = 10e-12          # assumed
AO3400_VTH_MIN = 0.65               # AO3400A VGS(th) min
DIS_VIH_MAX = 2.3                   # UCC21550 VDIS_H max


def permit_to_dis(r_gate: float, r_pullup: float) -> dict:
    t_fet = r_gate * AO3400_CISS_BOUND * math.log(VCC_MIN / AO3400_VTH_MIN)   # gate discharges toward 0 V
    c_dis = AO3400_COSS_BOUND + DIS_PIN_AND_TRACE
    t_dis = r_pullup * c_dis * math.log(VCC_MIN / (VCC_MIN - DIS_VIH_MAX))
    return {"fet_off_s": t_fet, "dis_rise_s": t_dis}


def chain(r_gate: float, r_pullup: float, path: str) -> dict:
    links = []
    if path == "tank_ct":
        links += [
            ("burden || C42 pole (tau = 1.5 ohm x 100 nF)", R_BURDEN * C_BURDEN),
            ("R42 1 k x (2 x 10 pF BAT54H/BAS116H + 3 x 2 pF TLV input) ", 1e3 * 26e-12),
            ("TLV3201 tPD max, 20 mV overdrive, -40..125 C (SBOS561C 6.6)", 55e-9),
            ("SN74LVC1G332 tpd max at 3.3 V (SCES489E)", 4.5e-9),
        ]
    else:
        links += [
            ("OCP node filter (10 k || 10 k) x 100 pF: ramp lag = tau", 5e3 * 100e-12),
            ("TLV3201 tPD max (U6, 5 V)", 55e-9),
            ("SN74LVC1G00 tpd max at 5 V, -40..125 C (SCES212)", 5.0e-9),
            ("ISO7710 tPLH/tPHL max (SLLSER9E)", 21e-9),
            ("SN74LVC1G332 tpd max at 3.3 V", 4.5e-9),
        ]
    links += [
        ("Harness to interlock, assumed 1 m", 5e-9),
        ("SN74LVC14A tpd max at 3.3 V (x2: input and ALL_GOOD inverter)", 2 * 8.0e-9),
        ("CD74HC30 tpd max at 2 V, 125 C (bound for 3.3 V; SCHS...)", 110e-9),
        ("SN74LVC1G74 CLR->Q max, 3.3 V, -40..125 C", 7.9e-9),
    ]
    pd = permit_to_dis(r_gate, r_pullup)
    links += [
        (f"PERMIT -> AO3400A off ({r_gate:.0f} ohm x Ciss bound, to VTH min)", pd["fet_off_s"]),
        (f"DIS rise ({r_pullup:.0f} ohm pullup x Coss bound) to VDIS_H max", pd["dis_rise_s"]),
        ("UCC21550 tPD_DIS max (SLUSE89C 5.9)", 80e-9),
        ("IPW65R018CFD7 gate discharge below threshold, assumed (task 01 to confirm)", 150e-9),
    ]
    total = sum(t for _, t in links)
    return {"links": [{"link": n, "ns": round(t * 1e9, 1)} for n, t in links], "total_us": round(total * 1e6, 3)}


def overshoot(trip_max_a: float, di_dt_a_per_us: float, total_us: float) -> float:
    return round(trip_max_a + di_dt_a_per_us * total_us, 1)


def main() -> None:
    ct = [ct_transfer(f) for f in (20e3, 33e3, 39e3, 60e3, 100e3)]
    flux = {f"{a} A pk @ {f/1e3:.0f} kHz": round(ct_flux(a, f) * 1e6, 1)
            for a, f in ((37, 33e3), (88, 33e3), (88, 20e3))}
    idle = {"static_offset_bound_mV": round((VOS_MAX + 0.16e-6 * 501.5) * 1e3, 2),
            "hysteresis_typ_mV": HYST_TYP * 1e3,
            "phase_error_deg": {f"{i} A pk": round(zc_phase_error(i, VOS_MAX), 1) for i in (2, 5, 10, 37)}}
    # Tank over-current ramp: bus / coil inductance (198 V crest at 140 V rms; 280 V OVP).
    ramps = {"198 V / 70 uH": 198 / 70, "280 V / 70 uH": 280 / 70}
    as_built = {p: chain(1e3, 10e3, p) for p in ("tank_ct", "shunt_ocp")}
    improved = {p: chain(100.0, 1e3, p) for p in ("tank_ct", "shunt_ocp")}
    peak = {name: {"as_built_A": overshoot(59.51, s, as_built["tank_ct"]["total_us"]),
                   "improved_A": overshoot(59.51, s, improved["tank_ct"]["total_us"])}
            for name, s in ramps.items()}
    print(json.dumps({
        "ct_transfer": ct, "ct_flux_half_cycle_Vus": flux, "ct_flux_limit_Vus": VT_LIMIT * 1e6,
        "trip_bands_A": TRIP_BANDS, "zero_cross_idle": idle,
        "chain_as_built_R14_1k_R16_10k": as_built, "chain_improved_R14_100_R16_1k": improved,
        "tank_fault_peak_current": peak,
        "shoot_through": "UCC21550 with RDT = 39 k: 'If both inputs are high simultaneously, both outputs "
                         "will immediately be set low' (SLUSE89C, programmable dead time). Command-level "
                         "shoot-through is blocked in the driver; dv/dt false turn-on is task 01.",
    }, indent=1))


if __name__ == "__main__":
    main()
