#!/usr/bin/env python3
"""Rev E (TAC5112 codec) rerun of the power-spur study.

    python3 rev_e_spurs.py          (about 10 s; numpy required)  ->  rev_e_spurs.json

Rev D's alias map assumed a 1 MSPS SAR that folds every frequency onto the fit. Rev E samples
with a delta-sigma codec whose decimation filter rejects everything except bands near multiples
of the (unpublished) modulator rate, plays the source from the codec DAC on the same frame
clock, and analyses one exact DFT line of a coherent record (host/src/rev_e.rs). This script
redoes the four interference mechanisms for that chain:

1. USB SOF lines (host clock, 1 kHz +-560 ppm) against the coherent DFT line.
2. TPS65131 switcher harmonics: which ones can reach the tone bin, with what probability, and
   the error if one does. Ripple amplitudes come from ripple_chain.py (same rails, LDOs and
   op-amps as Rev D); the codec input network and decimation filter replace the FDA and SAR.
3. Codec DAC images at j*f_mod +- f. They fold exactly onto f at the ADC. Ratiometric
   cancellation removes them except for the DUT's frequency dependence, as for Rev D's AD9833
   spurs (dds_spurs.py). Reported raw and after the short + two-resistor calibration.
4. Crystal-locked digital activity and DAC harmonics (exact folding rules).

Constants cite their source. ESTIMATE marks an assumption; everything else is exact arithmetic.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np

import common as c
import ripple_chain as rcn

HERE = pathlib.Path(__file__).resolve().parent

# ------------------------------------------------------------------ acquisition (host/src/rev_e.rs)
FS = 187_500.0                     # SAMPLE_RATE_HZ, 120 MHz / 10 / 64, exact
MIN_PERIOD, MAX_PERIOD = 16, 4096
TONE_MAX_HZ = 85_000.0
CAPTURE_S = 0.25                   # DEFAULT_CAPTURE_SECONDS
# Codec low-latency ADC decimation filter at the 192 kHz class (SLASF24A Table 7-38, p63,
# docs/rev-e-acquisition-survey.md): passband 0.456 fs, stop band from 0.571 fs at >= 90.5 dB.
ADC_PASS = 0.456 * FS
ADC_STOP = 0.571 * FS
ADC_STOP_DB = 90.5
# Modulator rate: not published for 187.5 kHz. TAC5212 SLASF23 lists ADC MOD CLK 1.536 and 3.072 MHz
# (phase-calibration notes); SBAA377 (sibling TLV320ADCx140) uses 6.144 MHz. Crystal-locked multiples
# of fs. ESTIMATE: evaluate 8, 16, 32 and 64 fs.
F_MOD = {"8 fs (1.5 MHz)": 8 * FS, "16 fs (3.0 MHz)": 16 * FS, "32 fs (6.0 MHz)": 32 * FS, "64 fs (12.0 MHz)": 64 * FS}

# ------------------------------------------------------------------ circuit (cad/design.json)
K_DIV = 0.5                        # 1.00k / 1.00k divider on each codec leg
AA_POLE_HZ = 1 / (2 * math.pi * 500.0 * 560e-12)       # Thevenin 500 ohm, C69/C70/C72/C73 560 pF
SRC_POLE_HZ = 1 / (2 * math.pi * 2000.0 * 270e-12)     # U5 difference stage, 2.0k || C34/C35 270 pF
SRC_NOISE_GAIN = 1 + 2000.0 / 2200.0                   # U5 (R30/R31 2.2k in, 2.0k feedback)
V_SOURCE = 1.7                     # TONE_MAX_MV at SOURCE_BUF
R104, R_ISO, CF, C0 = 47.0, 22.0, 100e-12, 100e-12
RANGE = 100.0                      # 100 ohm range: RG = RF = 100 ohm (stage53 targets)
RS = R104 + RANGE                  # source side of the DUT
DUTS = {
    "R 15 ohm": lambda f: 15.0 + 0j * f,
    "coil 50 uH + 0.5 ohm": lambda f: 0.5 + 2j * np.pi * f * 50e-6,
    "C 100 nF": lambda f: 1 / (2j * np.pi * f * 100e-9),
    "C 500 nF": lambda f: 1 / (2j * np.pi * f * 500e-9),
    "C 9 uF": lambda f: 1 / (2j * np.pi * f * 9e-6),
}
GRID = [4096, 1000.0, 1500.0, 27000.0, 27500.0, 35000.0, 35500.0, 40000.0, 40500.0,
        50000.0, 50500.0, 60000.0, 60500.0, 80000.0, 85000.0]      # 4096 = PERIOD 4096, 1 cycle
ASSUMPTIONS = {
    "E1_modulator_rate": "unpublished; 16, 32 and 64 x fs all evaluated (crystal-locked multiples)",
    "E2_dac_image_level": "zero-order hold at the modulator rate: image at j*f_mod +- f is "
                          "|sinc(fk/f_mod)/sinc(f/f_mod)| of the tone before the U5 pole (pessimistic; "
                          "a semi-digital FIR reconstruction would be lower)",
    "E3_adc_samples_at_f_mod": "switched-capacitor-like sampling at f_mod: components within the "
                               "decimation passband of k*f_mod fold in unattenuated (a continuous-time "
                               "modulator would add anti-alias rejection)",
    "E4_transition_band": "0.456-0.571 fs attenuation unpublished: counted as 0 dB",
    "E5_codec_avdd_psrr_above_100k_db": 30.0,
    "E6_ap2112_psrr_at_MHz_db": 0.0,
    "E7_ripple": "ripple_chain.py corners: rails, LDO and op-amp PSRR exactly as Rev D (Rev D loads, "
                 "which include the removed FDA bias current: conservative)",
    "E9_adc_stf_notch": "SBAA377 (TLV320ADCx140 family, same TI audio ADC architecture): the modulator "
                        "signal transfer function has notches at N*FMOD that attenuate N*FMOD +- 20 kHz by "
                        "> 100 dB. Credited only as a variant, and only for tones <= 20 kHz; TAC5112 wideband "
                        "mode is not covered by that note",
    "E8_amplifiers": "ideal followers, TIA and source driver at the image frequencies (OPA2810/OPA810 "
                     "GBW 70 MHz against 3-12 MHz images: loop gain 6-23, ESTIMATE)",
}


# ------------------------------------------------------------------ exact helpers
def tone_for_hz(hz):
    """host tone_for_hz: smallest PERIOD 16..4096 with hz = FS*CYCLES/PERIOD exactly."""
    for period in range(MIN_PERIOD, MAX_PERIOD + 1):
        cyc = hz * period / FS
        if cyc >= 1 and abs(cyc - round(cyc)) <= 1e-9 * max(cyc, 1):
            return int(round(cyc)), period
    return None


def plan(hz):
    if hz == 4096:                                 # the 45.776 Hz lowest tone
        cyc, period = 1, 4096
    else:
        cyc, period = tone_for_hz(hz)
    periods = max(1, math.ceil(CAPTURE_S * FS / period))
    return {"cycles": cyc, "period": period, "f_hz": FS * cyc / period, "periods": periods,
            "frames": periods * period, "seconds": periods * period / FS}


def dirichlet(delta_hz, frames):
    """|DFT line response| of a coherent record of `frames` samples to a unit tone delta_hz
    away from the line (1 on the line; exact for a rectangular record)."""
    x = np.pi * np.asarray(delta_hz, dtype=float) / FS
    num = np.sin(frames * x)
    den = frames * np.sin(x)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(np.abs(den) < 1e-300, 1.0, np.abs(num / np.where(den == 0, 1, den)))
    return r


def fold(x, rate):
    a = np.mod(np.asarray(x, dtype=float), rate)
    return np.where(a > rate / 2, rate - a, a)


def adc_digital_gain(x, f_mod):
    """Decimation filter gain for an analog component at x: the modulator folds x to within
    f_mod/2; passband 1, stop band -90.5 dB, transition band counted as 1 (E4)."""
    xm = fold(x, f_mod)
    stop = 10 ** (-ADC_STOP_DB / 20)
    return np.where(xm <= ADC_STOP, 1.0, stop), np.where(xm <= ADC_PASS, "pass",
                                                         np.where(xm <= ADC_STOP, "transition", "stop"))


def aa(f):
    return 1 / (1 + 1j * np.asarray(f, dtype=float) / AA_POLE_HZ)


def src_pole(f):
    return 1 / (1 + 1j * np.asarray(f, dtype=float) / SRC_POLE_HZ)


def zb(f, rng=RANGE):
    """Current-channel transfer: B = K * I * (R_iso + RF || C104); C104 is one 100 pF on every range."""
    return R_ISO + 1 / (1 / rng + 2j * np.pi * f * CF)


def dut_terms(z, f, fk, rng=RANGE):
    """Complex relative error of A/B per unit source component at fk (relative to the tone at
    the source), before the common AA ratio: raw, and after a short + two-resistor calibration
    (which absorbs the resistor value, 1 - Zb(fk)/Zb(f), into its gain)."""
    zf, zk = z(f), z(fk)
    rs = R104 + rng
    raw = (rs + zf + R_ISO) / (rs + zk + R_ISO) * (zk / zf - zb(fk, rng) / zb(f, rng))
    resistor = 1 - zb(fk, rng) / zb(f, rng)
    return raw, raw - resistor


def signals(z, f):
    """Codec-input peak tone levels (V) on channels A and B for DUT z at the source cap."""
    i = V_SOURCE / abs(RS + z(f) + R_ISO)
    return K_DIV * i * abs(z(f)), K_DIV * i * abs(zb(f))


# ------------------------------------------------------------------ 1. USB SOF
def sof(p, harmonics=3):
    worst, where = 0.0, None
    h0 = max(1, round(p["f_hz"] / 1000))
    for h in range(max(1, h0 - harmonics), h0 + harmonics + 1):
        band = np.linspace(h * 1000 * (1 - 560e-6), h * 1000 * (1 + 560e-6), 4001)
        r = dirichlet(band - p["f_hz"], p["frames"])
        k = int(np.argmax(r))
        if r[k] > worst:
            worst, where = float(r[k]), (h, float(band[k]))
    return {"worst_response": worst, "worst_db": float(c.db(worst)), "sof_harmonic": where[0],
            "at_hz": where[1]}


def sof_sweep():
    """Every integer frequency 46..85000 Hz that the host can play exactly."""
    hz = np.arange(46, 85001)
    g = np.gcd(hz, 187_500)
    p0 = 187_500 // g
    period = p0 * np.ceil(MIN_PERIOD / p0).astype(int)
    ok = period <= MAX_PERIOD
    hz, period = hz[ok], period[ok]
    frames = period * np.ceil(CAPTURE_S * FS / period).astype(int)
    h = np.maximum(1, np.round(hz / 1000))
    worst = np.zeros(hz.size)
    for dh in (-1, 0, 1):
        hh = np.maximum(1, h + dh) * 1000
        for e in np.linspace(-560e-6, 560e-6, 113):
            worst = np.maximum(worst, dirichlet(hh * (1 + e) - hz, frames))
    hazard = worst > 0.1
    return {"exact_integer_frequencies": int(hz.size), "sof_hazard_count": int(hazard.sum()),
            "sof_hazard_fraction": float(hazard.mean()),
            "hazard_within_hz_of_whole_khz": float(np.max(np.abs(hz[hazard] - 1000 * np.round(hz[hazard] / 1000))))}


# ------------------------------------------------------------------ 2. switcher harmonics
def response_width(frames):
    """Measure (Hz) of offsets with line response > 0.1."""
    d = np.linspace(-20 * FS / frames, 20 * FS / frames, 200_001)
    return float(np.sum(dirichlet(d, frames) > 0.1) * (d[1] - d[0]))


def switcher(p, ripple):
    """Collision probability over the unknown fsw (uniform 1.25-1.50 MHz) and the error if one
    harmonic lands on the line. Only x = m*fsw = k*f_mod +- f (+- fs - f in the transition band)
    reach the line unattenuated; every other alias is >= 90.5 dB down."""
    f = p["f_hz"]
    lo, hi = c.TPS65131["fsw_min_hz"], c.TPS65131["fsw_max_hz"]
    width = response_width(p["frames"])
    out = {}
    for name, fmod in F_MOD.items():
        hits = []
        offsets = [f, -f]
        if FS - f < ADC_STOP:                      # E4: fs - f alias in the transition band
            offsets += [FS - f, -(FS - f)]
        for m in range(1, 41):
            for k in range(0, int(m * hi // fmod) + 2):
                for o in offsets:
                    x = k * fmod + o
                    if x > 0 and lo <= x / m <= hi:
                        hits.append({"m": m, "k": k, "fsw_hz": x / m, "probability": width / m / (hi - lo)})
        prob = min(1.0, sum(h["probability"] for h in hits))
        # Stop-band route: any harmonic may fold onto the line (Rev D's per-harmonic chance).
        prob_stop = min(1.0, 40 * width / (FS / 2))
        hits.sort(key=lambda h: -h["probability"])
        out[name] = {"unattenuated_collision_count": len(hits), "largest_collisions": hits[:10],
                     "probability_unattenuated": prob,
                     "probability_stopband_any": prob_stop}
    # Error if harmonic m lands on the line unattenuated, at each ripple corner.
    errs = {}
    for corner, rp in ripple.items():
        m = np.array(rp["harmonic"])
        x = m * rp["fsw"]
        e_amp = (np.array(rp["rail_p12_v"]) + np.array(rp["rail_n12_v"])) * 10 ** (-np.array(rp["opamp_psrr_db"]) / 20)
        a_in = 2 * e_amp * K_DIV * np.abs(aa(x))          # HIGH and LOW followers
        b_in = 3 * e_amp * K_DIV * np.abs(aa(x))          # LOW follower + TIA (noise gain <= 2)
        v5 = np.array(rp["v5_node_v"]) * 10 ** (-(ASSUMPTIONS["E5_codec_avdd_psrr_above_100k_db"]
                                                  + ASSUMPTIONS["E6_ap2112_psrr_at_MHz_db"]) / 20)
        v5_fb1 = v5 * np.array(rp["fb1_divider"])
        src = SRC_NOISE_GAIN * e_amp + e_amp               # U5 difference stage + U6A driver
        rows = {}
        for dname, z in DUTS.items():
            sa, sb = signals(z, f)
            rails = a_in / sa + b_in / sb
            avdd = v5 * (1 / sa + 1 / sb)
            avdd_fb1 = v5_fb1 * (1 / sa + 1 / sb)
            sb_err = np.array([abs(dut_terms(z, f, xx)[0]) for xx in x]) * src / V_SOURCE * np.abs(aa(x) / aa(f))
            rows[dname] = {"rails_12v": float(rails.max()), "rails_m": int(m[np.argmax(rails)]),
                           "avdd_no_fb1": float(avdd.max()), "avdd_fb1_credit": float(avdd_fb1.max()),
                           "source_borne": float(sb_err.max()), "source_borne_m": int(m[np.argmax(sb_err)])}
        errs[corner] = rows
    return {"line_response_width_hz": width, "by_modulator_rate": out, "error_if_collision": errs}


# ------------------------------------------------------------------ 3. DAC images
def dac_images(p, c_src=270e-12):
    f = p["f_hz"]
    pole = 1 / (2 * math.pi * 2000.0 * c_src)
    sp = lambda x: 1 / (1 + 1j * np.asarray(x, dtype=float) / pole)
    notch = 10 ** (-100 / 20) if f <= 20e3 else 1.0          # E9 variant
    out = {}
    for name, fmod in F_MOD.items():
        per = {}
        for dname, z in DUTS.items():
            raw_t = cal_t = 0.0
            parts = []
            for j in (1, 2):
                for sgn in (-1, 1):
                    fk = j * fmod + sgn * f
                    level = abs(np.sinc(fk / fmod) / np.sinc(f / fmod)) * abs(sp(fk) / sp(f))
                    h = abs(aa(fk) / aa(f))
                    raw, cal = dut_terms(z, f, fk)
                    raw_t += level * h * abs(raw)
                    cal_t += level * h * abs(cal)
                    parts.append({"fk_hz": fk, "level_dbc": float(c.db(level)), "aa_ratio_db": float(c.db(h)),
                                  "raw": float(level * h * abs(raw)), "calibrated": float(level * h * abs(cal))})
            per[dname] = {"raw": raw_t, "calibrated": cal_t, "calibrated_sbaa377_notch_credit": cal_t * notch,
                          "images": parts}
        out[name] = per
    return out


# ------------------------------------------------------------------ 4. locked clocks, DAC harmonics
def locked(p):
    clocks = {"XOSC 12 MHz": 12e6, "clk_sys 120 MHz": 120e6, "USB PLL 48 MHz": 48e6,
              "BCLK 12 MHz": 12e6, "flash SCK 60 MHz": 60e6, "FSYNC": FS}
    ratios = {k: v / FS for k, v in clocks.items()}
    every_multiple = all(abs(r - round(r)) < 1e-9 for r in ratios.values())
    cyc, period = p["cycles"], p["period"]
    # Activity periodic in the waveform period (TX DMA re-trigger every PERIOD frames) has lines
    # at multiples of fs/PERIOD, i.e. on every bin, including the tone's.
    # DAC harmonic k folds onto the tone bin when (k -+ 1) * CYCLES = 0 mod PERIOD.
    folds = [k for k in range(2, 400) if ((k - 1) * cyc) % period == 0 or ((k + 1) * cyc) % period == 0]
    k0 = folds[0] if folds else None
    in_pass = k0 is not None and fold(k0 * p["f_hz"], FS) <= ADC_PASS and k0 * p["f_hz"] <= ADC_PASS
    return {"clock_over_fs": ratios, "all_alias_to_dc": every_multiple,
            "waveform_period_activity_lands_on_tone_bin": True,
            "lowest_dac_harmonic_on_tone_bin": k0,
            "that_harmonic_attenuation_db": None if k0 is None else (0.0 if in_pass else ADC_STOP_DB),
            "dac_thd_dbc": -94.0}


def range_screen():
    """Bring-up screen without a reference meter: the DAC-image error grows with the range
    resistor (the source sees RG + R104 in series), so one inductor read on the 100 ohm and 5 kOhm
    ranges disagrees by about the 5 kOhm-range image error. Pessimistic E2/E3 levels."""
    cases = {"47 uH (cal kit L1) at 60 kHz": (lambda f: 0.1 + 2j * np.pi * f * 47e-6, 60000.0),
             "1 mH at 27.5 kHz": (lambda f: 1.0 + 2j * np.pi * f * 1e-3, 27500.0)}
    rows = {}
    for name, (z, f) in cases.items():
        rows[name] = {}
        for fname, fmod in F_MOD.items():
            per = {}
            for rng in (100.0, 5000.0):
                tot = 0.0
                for j in (1, 2):
                    for sgn in (-1, 1):
                        fk = j * fmod + sgn * f
                        level = abs(np.sinc(fk / fmod) / np.sinc(f / fmod)) * abs(src_pole(fk) / src_pole(f))
                        tot += level * abs(aa(fk) / aa(f)) * abs(dut_terms(z, f, fk, rng)[1])
                per[f"{int(rng)} ohm range"] = tot
            rows[name][fname] = per
    return rows


def source_cap_options():
    """C34/C35 (U5 feedback and ground-leg capacitors) alternatives: the tone level they leave at
    SOURCE_BUF and the calibrated DAC-image error on the coil. Ratiometric: the pole cancels in A/B."""
    rows = {}
    for cap in (270e-12, 470e-12, 680e-12, 1e-9, 2.2e-9):
        pole = 1 / (2 * math.pi * 2000.0 * cap)
        lev = {str(int(f)): float(c.db(1 / abs(1 + 1j * f / pole))) for f in (27000.0, 60000.0, 85000.0)}
        img = {}
        for f in (27000.0, 60000.0):
            d = dac_images(plan(f), cap)
            img[str(int(f))] = {n: d[n]["coil 50 uH + 0.5 ohm"]["calibrated"] for n in F_MOD}
        rows[f"{cap*1e12:.0f} pF"] = {"pole_hz": pole, "tone_level_db": lev, "coil_image_error": img}
    return rows


def main():
    ripple = {corner: rcn.propagate(corner) for corner in ("worst", "typ")}
    out = {"assumptions": ASSUMPTIONS, "fs_hz": FS, "aa_pole_hz": AA_POLE_HZ, "src_pole_hz": SRC_POLE_HZ,
           "points": {}, "sof_sweep": sof_sweep()}
    for hz in GRID:
        p = plan(hz)
        out["points"][f"{p['f_hz']:.3f}"] = {"plan": p, "sof": sof(p), "switcher": switcher(p, ripple),
                                             "dac_images": dac_images(p), "locked": locked(p)}
    out["source_cap_options"] = source_cap_options()
    out["range_screen"] = range_screen()
    (HERE / "rev_e_spurs.json").write_text(json.dumps(out, indent=1, default=float))

    print(f"AA pole {AA_POLE_HZ/1e3:.0f} kHz, source pole {SRC_POLE_HZ/1e3:.0f} kHz")
    s = out["sof_sweep"]
    print(f"SOF sweep: {s['sof_hazard_count']} of {s['exact_integer_frequencies']} exact integer tones "
          f"({100*s['sof_hazard_fraction']:.1f} %) have response > 0.1; all within "
          f"{s['hazard_within_hz_of_whole_khz']:.0f} Hz of a whole kHz")
    for key, d in out["points"].items():
        p = d["plan"]
        sw = d["switcher"]
        probs = {n: v["probability_unattenuated"] for n, v in sw["by_modulator_rate"].items()}
        wc = sw["error_if_collision"]["worst"]
        tc = sw["error_if_collision"]["typ"]
        print(f"\n== {p['f_hz']:.3f} Hz  ({p['cycles']}/{p['period']}, {p['periods']} periods, {p['seconds']:.3f} s)"
              f"  SOF {d['sof']['worst_db']:.1f} dB (h={d['sof']['sof_harmonic']})")
        print("   switcher P(unattenuated hit) " + ", ".join(f"{n.split()[0]}: {v:.1e}" for n, v in probs.items())
              + f"; stop-band route any harmonic {sw['by_modulator_rate']['16 fs (3.0 MHz)']['probability_stopband_any']:.1e} at -90.5 dB")
        for dn in ("R 15 ohm", "coil 50 uH + 0.5 ohm", "C 500 nF"):
            print(f"   if hit [{dn}]: rails worst {100*wc[dn]['rails_12v']:.4f}% typ {100*tc[dn]['rails_12v']:.4f}%;"
                  f" AVDD worst {100*wc[dn]['avdd_no_fb1']:.4f}% (FB1 {100*wc[dn]['avdd_fb1_credit']:.5f}%);"
                  f" source-borne worst {100*wc[dn]['source_borne']:.4f}%")
        for n, per in d["dac_images"].items():
            print(f"   DAC images f_mod {n}: " + "; ".join(
                f"{dn.split()[0]} {dn.split()[1]} raw {100*v['raw']:.4f}% cal {100*v['calibrated']:.4f}%"
                for dn, v in per.items()))
        lk = d["locked"]
        print(f"   locked clocks alias to DC: {lk['all_alias_to_dc']}; lowest DAC harmonic on the bin: k={lk['lowest_dac_harmonic_on_tone_bin']}"
              f" ({lk['that_harmonic_attenuation_db']} dB extra)")
    print("\nRange screen (calibrated DAC-image error, pessimistic):")
    for name, r in out["range_screen"].items():
        print(f"  {name}: " + "; ".join(f"{n.split()[0]}: " + " vs ".join(f"{100*v:.3f}%" for v in d.values()) for n, d in r.items()))
    print("\nC34/C35 options (coil, calibrated DAC-image error at 27 / 60 kHz; tone level at 27/60/85 kHz):")
    for k, r in out["source_cap_options"].items():
        print(f"  {k:>7} pole {r['pole_hz']/1e3:6.1f} kHz  level " + "/".join(f"{v:+.1f}" for v in r["tone_level_db"].values())
              + " dB  | " + "; ".join(f"{n.split()[0]}: " + "/".join(f"{100*r['coil_image_error'][f][n]:.3f}" for f in ("27000", "60000")) + "%"
                                      for n in F_MOD))


if __name__ == "__main__":
    main()
