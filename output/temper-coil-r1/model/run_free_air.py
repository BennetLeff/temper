"""Free-air and installed (no pan) inductance and Litz R_ac of the coil, R43 layout and candidate turn layouts.

Every L is the 2D discrete-turn homogenised-bar result times the 3D bar factor k_free (compare_3d.py; 0.909): the 3D
sector solve with discrete bars is the number trusted, the 2D model carries it to other layouts and conditions.
Litz proximity uses the 2D discrete-turn winding field, corrected bin by bin by the 3D/2D ratio of the smeared-source
winding field (fem3d free_h0.5 vs the 2D smeared twin).
Run: .venv/bin/python model/run_free_air.py  -> model/results/free_air.json  (~3 min, 8 workers)
"""
from __future__ import annotations

import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coil_geometry as G  # noqa: E402
import coil_model as CM  # noqa: E402
import litz  # noqa: E402

FACT = json.loads((HERE / "results" / "compare_3d.json").read_text())["factors"]
K_FREE = FACT["k_free"]
FREQS = [20e3, 30e3, 40e3, 50e3, 60e3]


def prox_correction():
    """Radial ratio 3D/2D of the smeared-source winding |B|^2 (free air)."""
    p3 = json.loads((HERE / "fem3d" / "results" / "free_h0.5.json").read_text())["winding_B2_profile"]
    m = CM.build(G.R43, turn_model="smeared", r_max=0.6)
    m.solve(40e3)
    Br, Bz = m.B_cells()
    b2 = np.abs(Br) ** 2 + np.abs(Bz) ** 2
    coil = m.turn_masks[0] | m.turn_masks[1]
    rr, ratio = [], []
    for row in p3:
        a = row["r_mm"] * 1e-3
        sel = coil & (m.RC >= a - 1e-3) & (m.RC < a + 1e-3)
        if sel.any():
            b2d = float(np.sum(b2[sel] * m.dA[sel]) / np.sum(m.dA[sel]))
            rr.append(row["r_mm"])
            ratio.append(row["B2_T2_per_A2"] / b2d)
    return np.array(rr), np.array(ratio)


def solve_case(args):
    name, winding, kw = args
    m = CM.build(winding, **kw)
    res = m.solve(40e3)
    out = dict(name=name, turns=winding.turns, L2D_uH=res["L"] * 1e6, L_uH=res["L"] * 1e6 * K_FREE,
               losses_W_per_A2=res["losses"])
    return out, m


def rac_rows(winding, kw, corr, n=litz.N_STRANDS, d=litz.D_STRAND):
    m = CM.build(winding, **kw)
    m.solve(40e3)
    rr, ratio = corr
    # scale every turn's field by the 3D/2D ratio at its radius (the free-air field is real and f-independent)
    k = np.interp(np.array(m.turn_r) * 1e3, rr, ratio)
    rows = []
    for T in (25.0, 100.0):
        for f in FREQS:
            base = litz.winding_rac(m, f, T, lead_m=(winding.lead_centre_mm + winding.lead_outer_mm) / 1000.0, n=n, d=d)
            # rebuild R_prox with the corrected field
            b2 = np.array(m.turn_B2()) * k
            length = 2 * math.pi * np.array(m.turn_r) * np.array(m.turn_weights)
            rprox = float((litz.prox_per_m(b2, f, T, n, d) * length * litz.LAY).sum()
                          + litz.prox_per_m(litz.lead_b2(1.0, n, d), f, T, n, d) * 0.4 * litz.LAY)
            rac = (base["R_dc_ohm"] - litz.R_TERM) * litz.skin_factor(f, T, d) + litz.R_TERM + rprox
            rows.append(dict(T_C=T, f_kHz=f / 1e3, R_dc_mohm=base["R_dc_ohm"] * 1e3, R_prox_2D_mohm=base["R_prox_ohm"] * 1e3,
                             R_prox_mohm=rprox * 1e3, R_ac_mohm=rac * 1e3, F_R=rac / base["R_dc_ohm"],
                             B_rms_winding_mT_per_A=base["B_rms_winding_mT_per_A"] * math.sqrt(float(np.mean(k))),
                             length_m=base["length_m"]))
    return rows


def layout(n_in, n_out, name=None):
    """Turns spread over the R43 radial bands (inner r27.4-82.6, outer r93.4-114.8) at uniform pitch."""
    return G.Winding(sections=(G.Section(27.4, 82.6, n_in), G.Section(93.4, 114.8, n_out)),
                     name=name or f"{n_in:g} + {n_out:g} over the R43 bands")


def main():
    out = dict(k_free=K_FREE, note="L = 2D discrete-turn homogenised-bar L x k_free (3D discrete bars).")
    jobs = [("R43_free", G.R43, dict()), ("R43_aircore", G.R43, dict(ferrite="air")),
            ("R43_installed", G.R43, dict(enclosure=True)),
            ("R43_mu1000", G.R43, dict(mu_ferrite=1000.0)), ("R43_mu5000", G.R43, dict(mu_ferrite=5000.0)),
            ("R43_bars_0.5mm_lower", G.R43, dict(z_bar=(92.5, 97.5))),
            ("R43_bundle_z+0.3", G.Winding(G.R43.sections, z_c=G.Z_WIND_C + 0.3), dict())]
    # trim: remove outer turns at constant pitch (the tune move)
    for rem in np.arange(0.0, 3.01, 0.5):
        jobs.append((f"trim_outer_-{rem:.1f}", G.trimmed(G.R43, float(rem)), dict()))
    # layouts over the same radial bands
    for n_in in (12.0, 13.0, 14.0, 15.47):
        for n_out in (5.5, 6.46):
            jobs.append((f"layout_{n_in:g}+{n_out:g}", layout(n_in, n_out), dict()))
    with ProcessPoolExecutor(8) as ex:
        res = list(ex.map(_job, jobs))
    out["cases"] = {r["name"]: r for r in res}
    c = out["cases"]
    out["installed_over_free"] = c["R43_installed"]["L2D_uH"] / c["R43_free"]["L2D_uH"]
    # fit L(n_in, n_out) on the layout family: L = a n_in^2 + b n_in n_out + c n_out^2 (exact for linear media)
    rows = [(v["turns"], k) for k, v in c.items() if k.startswith("layout_")]
    A, y = [], []
    for k, v in c.items():
        if k.startswith("layout_"):
            ni, no = map(float, k.split("_")[1].split("+"))
            A.append([ni * ni, ni * no, no * no])
            y.append(v["L_uH"])
    coef, *_ = np.linalg.lstsq(np.array(A), np.array(y), rcond=None)
    out["L_fit_coef_uH"] = dict(a_in2=coef[0], b_inout=coef[1], c_out2=coef[2],
                                rms_err_uH=float(np.sqrt(np.mean((np.array(A) @ coef - np.array(y)) ** 2))))

    def n_in_for(Lt, n_out):
        a, b, cc = coef
        return float((-b * n_out + math.sqrt((b * n_out) ** 2 - 4 * a * (cc * n_out ** 2 - Lt))) / (2 * a))
    targets = {}
    for Lt in (70.0, 75.0, 80.0):
        for n_out in (6.46, 6.0):
            ni = n_in_for(Lt, n_out)
            targets[f"{Lt:g}uH_out{n_out:g}"] = dict(n_in=ni, n_out=n_out, turns=ni + n_out, inner_pitch_mm=55.2 / ni,
                                                    outer_pitch_mm=21.4 / n_out)
    out["turns_for_target_free_air"] = targets
    # verify the 70 / 80 uH candidates directly and get their R_ac
    corr = prox_correction()
    out["prox_correction_3D_over_2D"] = dict(r_mm=corr[0].tolist(), ratio=corr[1].tolist())
    cands = {"R43_21.93": G.R43}
    for key in ("70uH_out6.46", "80uH_out6.46"):
        t = targets[key]
        cands[key] = layout(round(t["n_in"], 2), 6.46, name=f"{key}: {t['n_in']:.2f} + 6.46")
    out["candidates"] = {}
    for key, w in cands.items():
        r, _ = solve_case((key, w, dict()))
        ri, _ = solve_case((key, w, dict(enclosure=True)))
        out["candidates"][key] = dict(turns=w.turns, sections=[dict(r0=s.r0, r1=s.r1, turns=s.turns, pitch=s.pitch) for s in w.sections],
                                      L_free_uH=r["L_uH"], L_installed_uH=ri["L_uH"], rac=rac_rows(w, dict(), corr))
    # alternative Litz constructions on the 80 uH layout (stock sizes; see ORDER-LIST.md)
    out["litz_alternatives_80uH"] = {}
    for label, n, d in (("270x0.10 (design, custom class 200)", 270, 0.100e-3), ("1000x0.05 (RMCybernetics 12 A stock, class 155)", 1000, 0.050e-3),
                        ("1050x0.05 (Elecify 1050/44 stock)", 1050, 0.050e-3), ("200x0.10 (Elecify 200/38 stock)", 200, 0.100e-3)):
        out["litz_alternatives_80uH"][label] = [r for r in rac_rows(cands["80uH_out6.46"], dict(), corr, n, d) if r["f_kHz"] in (40.0, 60.0)]
    (HERE / "results" / "free_air.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out["candidates"].items():
        r40 = [x for x in v["rac"] if x["f_kHz"] == 40 and x["T_C"] == 25][0]
        r40h = [x for x in v["rac"] if x["f_kHz"] == 40 and x["T_C"] == 100][0]
        print(f"{k}: N {v['turns']:.2f} L free {v['L_free_uH']:.1f} installed {v['L_installed_uH']:.1f} uH; "
              f"R_dc25 {r40['R_dc_mohm']:.1f} R_ac40 25C {r40['R_ac_mohm']:.1f} 100C {r40h['R_ac_mohm']:.1f} mOhm")
    for k in ("R43_free", "R43_aircore", "R43_installed", "R43_mu1000", "R43_mu5000", "R43_bars_0.5mm_lower", "R43_bundle_z+0.3"):
        print(k, round(c[k]["L_uH"], 2))
    print(json.dumps(targets, indent=1))


def _job(a):
    r, _ = solve_case(a)
    return r


if __name__ == "__main__":
    main()
