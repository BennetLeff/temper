"""Installed coil on representative pans: loaded L, reflected R (pan + enclosure eddy loss), copper R_ac in the loaded
field, pan heating profile, at the real stack (winding Z99-101.4, 4 mm glass, pan base on the glass at Z110).

2D discrete-turn model with the enclosure conductors (base, P1 seat ring, P2 fence ring) and the pan resolved through its
skin depth; L and R then carry the 3D bar factors k_L_pan / k_R_pan (compare_3d.py). Pan classes and their ASSUMED
permeability ranges are in materials.py (small-signal mu_nominal, swept low/high).
A large-signal ESTIMATE for 430 and cast iron (Frohlich effective-mu iteration at 17.5 A and 28 A RMS) is reported
separately: the bench LCR reading is small-signal; full power may differ, and the firmware measures f_res live.
Run: .venv/bin/python model/run_pans.py  -> model/results/pans.json  (~5 min, 8 workers)
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
import materials as M  # noqa: E402

FACT = json.loads((HERE / "results" / "compare_3d.json").read_text())["factors"]
FREE = json.loads((HERE / "results" / "free_air.json").read_text())
FREQS = [20e3, 30e3, 40e3, 50e3, 60e3]


def layouts():
    out = {"R43_21.93": G.R43}
    for key in ("70uH_out6.46", "80uH_out6.46"):
        c = FREE["candidates"][key]
        out[key] = G.Winding(sections=tuple(G.Section(s["r0"], s["r1"], s["turns"]) for s in c["sections"]), name=key)
    return out


def case(args):
    lay, cls, mu_tag, mu, diam, f = args
    w = layouts()[lay]
    pan = M.pan(cls, radius_mm=diam / 2, mu=mu)
    pan["f_grid"] = f
    m = CM.build(w, enclosure=True, pan=pan)
    r = m.solve(f)
    L = r["L"] * 1e6 * FACT["k_L_pan"]
    R = r["R"] * FACT["k_R_pan"]
    pan_W = sum(v for k, v in r["losses"].items() if k.startswith("pan"))
    encl_W = sum(v for k, v in r["losses"].items() if not k.startswith("pan"))
    row = dict(layout=lay, pan=cls, mu_tag=mu_tag, mu=mu, pan_d_mm=diam, f_kHz=f / 1e3, L_uH=L, R_refl_ohm=R,
               pan_share=pan_W / (pan_W + encl_W) if pan_W + encl_W else 0.0, L2D_uH=r["L"] * 1e6, R2D_ohm=r["R"])
    if f == 40e3:
        prof = CM.pan_profile(m)
        row["profile"] = prof
        row["share_r_lt55"] = sum(p["share"] for p in prof if p["r_mm"][1] <= 55)
        row["share_55_90"] = sum(p["share"] for p in prof if 55 <= p["r_mm"][0] and p["r_mm"][1] <= 92)
        row["share_rim_ge92"] = sum(p["share"] for p in prof if p["r_mm"][0] >= 92)
        rac = litz.winding_rac(m, f, 100.0)
        row["Rac_copper_loaded_100C_mohm_2D"] = rac["R_ac_ohm"] * 1e3
        row["B_rms_winding_loaded_mT_per_A"] = rac["B_rms_winding_mT_per_A"]
        # field at the pan underside (for the large-signal mu estimate): peak |H| per peak A at r 20-110, z just inside
        rs = np.linspace(0.02, min(0.11, diam / 2e3 - 0.005), 19)
        Br, Bz = m.B_at(rs, np.full_like(rs, G.PAN_Z0 * 1e-3 - 0.3e-3))
        row["H_pan_face_max_A_per_m_per_A"] = float(np.max(np.hypot(np.abs(Br), np.abs(Bz))) / M.MU0)
    return row


def large_signal(args):
    lay, cls, mu_lo, Js, I_rms = args
    w = layouts()[lay]
    pan = M.pan(cls, radius_mm=120.0, mu=mu_lo)
    pan["layers"] = [(t, s, mu_, M.frohlich(mu_lo, Js) if mu_ > 1 else None) for (t, s, mu_, _) in pan["layers"]]
    m = CM.build(w, enclosure=True, pan=pan)
    r = m.solve(40e3, current=I_rms * math.sqrt(2), nl_iter=40, relax=0.5)
    return dict(layout=lay, pan=cls, mu_lo=mu_lo, Js_T=Js, I_rms=I_rms, L_uH=r["L"] * 1e6 * FACT["k_L_pan"],
                R_refl_ohm=r["R"] * FACT["k_R_pan"], nl_residual=m.nl_change)


def main():
    jobs = []
    for lay in layouts():
        for cls, c in M.PAN_CLASSES.items():
            mus = {"nom": c["layers"][0][2]} if cls == "aluminium" else {"lo": c["mu_range"][0], "nom": c["layers"][0][2], "hi": c["mu_range"][1]}
            for tag, mu in mus.items():
                for d in (240.0, 180.0):
                    for f in FREQS:
                        if d == 180.0 and tag != "nom" and f != 40e3:
                            continue
                        jobs.append((lay, cls, tag, float(mu), d, f))
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(case, jobs, chunksize=2))
        ls_jobs = [(lay, cls, mu, Js, I) for lay in ("70uH_out6.46", "80uH_out6.46") for cls, mu, Js in
                   (("ss430", 200.0, 1.45), ("cast_iron", 100.0, 1.30), ("carbon_steel", 200.0, 1.9)) for I in (5.0, 17.5, 28.0)]
        ls = list(ex.map(large_signal, ls_jobs))
    out = dict(factors=FACT, note="L, R carry the 3D bar factors. R_refl = all eddy loss outside the winding (pan + "
               "enclosure) referred to the coil current; the winding's own Litz R_ac is separate.", rows=rows, large_signal=ls)
    (HERE / "results" / "pans.json").write_text(json.dumps(out, indent=1) + "\n")
    # summary
    for lay in layouts():
        Lf = FREE["candidates"][lay]["L_free_uH"]
        print(f"== {lay}  L_free {Lf:.1f}")
        for r in rows:
            if r["layout"] == lay and r["f_kHz"] == 40 and r["pan_d_mm"] == 240:
                print(f"  {r['pan']:13s} mu {r['mu']:6.0f}: L {r['L_uH']:6.2f} uH (kL {r['L_uH'] / Lf:.3f})  R {r['R_refl_ohm']:6.3f} ohm "
                      f"(r {r['R_refl_ohm'] / Lf:.4f} ohm/uH)  rim {r.get('share_rim_ge92', 0):.3f}")
    for x in ls:
        print("LS", x)


if __name__ == "__main__":
    main()
