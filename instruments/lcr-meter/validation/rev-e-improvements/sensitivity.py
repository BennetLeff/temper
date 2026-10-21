#!/usr/bin/env python3
"""Deterministic sensitivities behind the improvements study (README section 4).

S1 codec inter-channel phase drift (unpublished): error per 0.01 deg, with and without the reference check
S2 CH1 leg-gain mismatch drift (x R_iso common mode): error per 1e-4
S3 the on-board 1 kOhm CUR->POT resistors with Kelvin leads attached (same draws, 1 kOhm vs open)
S4 4T: 6 mOhm contact change on each terminal after calibration (and 2T for comparison)
S5 reference-check resolution: noise (gain, phase) per frequency and the systematic floors
S6 DAC-image alias bound at 187.5 kHz vs 375 kHz
S7 lead capacitance moved after calibration: 2T loose leads, 4T coax, 4T coax moved like loose wire
    sensitivity.py -> results/sensitivity.json
"""
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study as s  # noqa: E402
import revE_front as fe  # noqa: E402

vm = s.vm
FREQS = sorted({x for v in s.dut_freqs().values() for x in v})
NONE = frozenset()


def fixture(kelvin, n=1, c2t=100e-12, cx=s.C_COAX, rc=None, lser=None):
    return dict(rc=np.zeros((n, 4)) if rc is None else rc, c2t=np.full((n, 2), c2t), cx=np.full((n, 4), cx),
                lser=np.full(n, (s.M_4T if kelvin else s.L_LOOP_2T)[0] if lser is None else lser))


def det_errors(kelvin, meas_drift=None, meas_fix=None, cal_fix=None):
    """Perfect standards, no noise. Calibrate with cal_fix, measure with meas_fix/meas_drift.
    Returns {target: worst-frequency |error|}."""
    data = {}
    for f in FREQS:
        cf = cal_fix or fixture(kelvin)
        dn0 = fe.nominal_drift(1)

        def m(z, fx, d):
            a, b = fe.measure(f, kelvin, np.array([complex(z)]), fx, d)
            return fe.raw(a, b)
        abc = vm.cal_coeffs(m(1e-6, cf, dn0), m(s.STD1, cf, dn0), s.STD1, m(s.STD2, cf, dn0), s.STD2)
        for dn, fl in s.dut_freqs().items():
            if f in fl:
                zt = complex(vm.DUTS[dn].z(f))
                zm = vm.correct(m(zt, meas_fix or cf, meas_drift or dn0), abc)
                data[(dn, f)] = (np.repeat(zm, 2), zt)
    return {t: abs(v["bias"]) for t, v in s.evaluate(data).items()}


def s1():
    phi = math.radians(0.01)
    out = {}
    for cname in ("base", "i3", "all", "all_bp"):
        cfg = next(c for c in s.CFGS if c.name == cname)
        ev = s.evaluate(s.run(cfg, en=NONE, phi_cc=phi, sizes=(1, 1, 2)))
        out[cname] = {t: abs(v["bias"]) for t, v in ev.items()}
    return out


def s2():
    x = 1e-4 / (970.0 / (fe.NOM["Rin"] + 970.0))   # R_in change on leg 1M giving 1e-4 of leg gain
    out = {}
    for kelvin in (False, True):
        d = fe.nominal_drift(1)
        d["Rin"][0, 1] *= 1 + x
        out["4T" if kelvin else "2T"] = det_errors(kelvin, meas_drift=d)
    return out


def s3():
    cfg = next(c for c in s.CFGS if c.name == "i2")
    out = {}
    for corner in (False, True):
        a = s.run(cfg, corner=corner, rcp=1e3)
        b = s.run(cfg, corner=corner, rcp=1e12)
        res = {}
        for t in s.TARGETS:
            tid, dn, fl, q, tol, unit, _ = t
            worst = 0.0
            for f in fl:
                ea = np.asarray(s.error(q, unit, a[(dn, f)][0], a[(dn, f)][1], f, dn))
                eb = np.asarray(s.error(q, unit, b[(dn, f)][0], b[(dn, f)][1], f, dn))
                worst = max(worst, float(np.max(np.abs(ea - eb))))
            res[tid] = worst
        out["corner" if corner else "typ"] = res
    return out


def s4():
    out = {}
    for i, name in enumerate(("Hcur", "Hpot", "Lpot", "Lcur")):
        rc = np.zeros((1, 4))
        rc[0, i] = 6e-3
        out[f"4T_{name}"] = det_errors(True, meas_fix=fixture(True, rc=rc))
    rc = np.zeros((1, 4))
    rc[0, 0] = 6e-3
    out["2T_total"] = det_errors(False, meas_fix=fixture(False, rc=rc))
    return out


def s5():
    """Reference-check resolution and floors, per frequency."""
    rows = []
    for f in FREQS:
        T = s.capture_s(f)
        row = dict(hz=f, capture_s=T)
        for kelvin, bypass, tag in ((False, False, "2T"), (True, False, "4T"), (True, True, "4T_bypass")):
            d0 = fe.nominal_drift(1)
            ref = np.array([s.RREF + s.RELAY_RC])
            fx = fixture(kelvin, c2t=s.C_LEAD_2T[0])
            a, b = fe.measure(f, kelvin, None, fx, d0, ref=ref, bypass=bypass)
            m0 = fe.raw(a, b)[0]
            sig = fe.phasor_sigma(T)
            rel = math.sqrt(sig ** 2 * (1 / abs(a[0]) ** 2 + 1 / abs(b[0]) ** 2))   # per component of dm/m
            row[f"{tag}_noise_sigma_gain"] = rel
            row[f"{tag}_noise_sigma_phase_rad"] = rel
            row[f"{tag}_a_pin_v"] = abs(a[0])
            row[f"{tag}_b_pin_v"] = abs(b[0])
            # lead / coax movement while the leads hang open: typical (+/-20 % loose, +/-1 % coax) one-sided
            mv = s.MOVE_COAX[0] if kelvin else s.MOVE_2T[0]
            fx2 = fixture(kelvin, c2t=s.C_LEAD_2T[0] * (1 + mv), cx=s.C_COAX * (1 + mv))
            a2, b2 = fe.measure(f, kelvin, None, fx2, d0, ref=ref, bypass=bypass)
            dm = fe.raw(a2, b2)[0] / m0 - 1
            row[f"{tag}_leadmove_gain"] = abs(dm.real)
            row[f"{tag}_leadmove_phase_rad"] = abs(dm.imag)
        for k, dt in (("typ", s.DT[0]), ("corner", s.DT[1])):
            row[f"rref_tcr_gain_{k}"] = s.RREF_TCR * dt
        row["relay_gain_typ"], row["relay_gain_corner"] = (x / s.RREF for x in s.RELAY_REPEAT)
        rows.append(row)
    return rows


def s6():
    """DAC image at fs - f0 aliased onto f0 by the ADC decimation; bound in target units."""
    cases = {  # (fs, DAC image rejection dB, ADC alias rejection dB) from the survey's filter tables
        "187.5k": (187.5e3, 86.9, 90.5),   # low-latency filters at 192k (TAC5212 p63 T7-38, p83 T7-64)
        "375k": (375e3, 77.7, 80.0),       # linear-phase filters at 384k (p59 T7-32, p78 T7-58)
    }
    out = {}
    for tag, (fs, dac_db, adc_db) in cases.items():
        res = {}
        for t in s.TARGETS:
            tid, dn, fl, q, tol, unit, _ = t
            worst = 0.0
            for f in fl:
                d = vm.DUTS[dn]
                fi = fs - f
                fx = fixture(False)
                d0 = fe.nominal_drift(1)
                a0, b0 = fe.measure(f, False, np.array([complex(d.z(f))]), fx, d0)
                ai, bi = fe.measure(fi, False, np.array([complex(d.z(fi))]), fx, d0)
                rc = 1 / abs(1 + 1j * fi / 295e3) / (1 / abs(1 + 1j * f / 295e3))   # source-stage pole
                g = abs(np.conj(ai[0]) / a0[0] - np.conj(bi[0]) / b0[0]) * rc
                rel = 10 ** (-dac_db / 20) * 10 ** (-adc_db / 20) * g
                z = complex(d.z(f))
                dz = rel * abs(z)
                if q in ("L", "C", "tand"):
                    v = dz / abs(z.imag)
                elif q == "R":
                    v = dz if unit == "ohm" else dz / z.real
                elif q == "f0":
                    dxdf = (d.z(f * 1.0001).imag - d.z(f * 0.9999).imag) / (f * 0.0002)
                    v = dz / dxdf / f
                else:
                    v = dz / z.real
                worst = max(worst, v)
            res[tid] = worst
        out[tag] = res
    return out


def s7():
    out = {}
    out["2T_100pF_+20%"] = det_errors(False, cal_fix=fixture(False, c2t=100e-12),
                                      meas_fix=fixture(False, c2t=120e-12))
    out["2T_200pF_+20%"] = det_errors(False, cal_fix=fixture(False, c2t=200e-12),
                                      meas_fix=fixture(False, c2t=240e-12))
    out["4T_coax_+1%"] = det_errors(True, meas_fix=fixture(True, cx=s.C_COAX * 1.01))
    out["4T_coax_+3%"] = det_errors(True, meas_fix=fixture(True, cx=s.C_COAX * 1.03))
    out["4T_coax_+20%"] = det_errors(True, meas_fix=fixture(True, cx=s.C_COAX * 1.20))
    out["4T_mutual_+2nH"] = det_errors(True, meas_fix=fixture(True, lser=s.M_4T[0] + 2e-9))
    out["2T_loop_+10nH"] = det_errors(False, meas_fix=fixture(False, lser=s.L_LOOP_2T[0] + 10e-9))
    # loop / mutual L different on one calibration insertion (std1) than on the others
    for kelvin, tag, dl in ((True, "4T_std1_insertion_+2nH", 2e-9), (False, "2T_std1_insertion_+10nH", 10e-9)):
        data = {}
        for f in FREQS:
            l0 = (s.M_4T if kelvin else s.L_LOOP_2T)[0]
            d0 = fe.nominal_drift(1)

            def m(z, l):
                a_, b_ = fe.measure(f, kelvin, np.array([complex(z)]), fixture(kelvin, lser=l), d0)
                return fe.raw(a_, b_)
            abc = vm.cal_coeffs(m(1e-6, l0), m(s.STD1, l0 + dl), s.STD1, m(s.STD2, l0), s.STD2)
            for dn, fl in s.dut_freqs().items():
                if f in fl:
                    zt = complex(vm.DUTS[dn].z(f))
                    data[(dn, f)] = (np.repeat(vm.correct(m(zt, l0), abc), 2), zt)
        out[tag] = {t: abs(v["bias"]) for t, v in s.evaluate(data).items()}
    return out


def main():
    out = dict(S1_phase_drift_0p01deg=s1(), S2_ch1_leg_mismatch_1em4=s2(), S3_cur_pot_1k=s3(),
               S4_contact_6mohm=s4(), S5_ref_check=s5(), S6_image_alias=s6(), S7_lead_move=s7())
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/sensitivity.json").write_text(json.dumps(out, indent=1))
    show = ("coil_nopan_L", "coil_nopan_R", "coil_pan_lowR_R", "cap100n_tand", "bank500n_tand", "tank_nopan_Q")
    for k, v in out.items():
        if k == "S5_ref_check":
            continue
        print(k)
        for case, r in v.items():
            print(f"  {case:16s} " + "  ".join(f"{t}={s.fmt(t, r[t])}" for t in show))
    print("S5_ref_check (1 sigma, per component of the reference ratio)")
    for r in out["S5_ref_check"]:
        print(f"  {r['hz']:7.0f} Hz T={r['capture_s']*1e3:5.1f} ms  noise 2T {r['2T_noise_sigma_phase_rad']:.2e}  "
              f"4T {r['4T_noise_sigma_phase_rad']:.2e}  | open-lead move phase: 2T(+20%) {r['2T_leadmove_phase_rad']:.2e} "
              f"4T(+1%) {r['4T_leadmove_phase_rad']:.2e} 4T bypass {r['4T_bypass_leadmove_phase_rad']:.2e}  "
              f"| Rref TCR gain typ/corner {r['rref_tcr_gain_typ']:.1e}/{r['rref_tcr_gain_corner']:.1e}")


if __name__ == "__main__":
    main()
