"""3D discrete-bar results against the 2D homogenised-bar model on identical inputs -> bar correction factors.

The 3D runs (fem3d/run3d.py, Elmer on the remote box, results in fem3d/results/*.json) use the smeared two-section source
and an 0.6 m domain; so the 2D twin here uses turn_model="smeared" and r_max=0.6. The 2D-vs-3D air-core control isolates
the 3D discretisation/domain error, which is divided out. Factors (3D / 2D):
  k_free  : free-air L with bars
  k_L_pan, k_R_pan : L and R with a pan (430 mu 200 and cast iron mu 100; IBC pan in 3D, resolved pan in 2D)
Run: .venv/bin/python model/compare_3d.py  -> model/results/compare_3d.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coil_geometry as G  # noqa: E402
import coil_model as CM  # noqa: E402
import materials as M  # noqa: E402

R3 = HERE / "fem3d" / "results"


def j(name):
    return json.loads((R3 / f"{name}.json").read_text())


def two_d(ferrite="bars", pan=None):
    m = CM.build(G.R43, ferrite=ferrite, pan=pan, turn_model="smeared", r_max=0.6)
    return m.solve(40e3)


def main():
    out = {}
    air2 = two_d("air")["L"] * 1e6
    bars2 = two_d("bars")["L"] * 1e6
    air3 = j("air_h0.7")["L_uH_energy"]
    f3 = {h: j(f"free_h{h}")["L_uH_energy"] for h in ("1", "0.7", "0.5")}
    # Richardson (energy error ~ h^2): extrapolate from h 0.7 and 0.5
    ext = f3["0.5"] + (f3["0.5"] - f3["0.7"]) * (0.5 ** 2) / (0.7 ** 2 - 0.5 ** 2)
    ctrl = air3 / air2
    out["free_air"] = dict(L2D_air_uH=air2, L3D_air_uH=air3, control_ratio=ctrl, L2D_bars_uH=bars2, L3D_bars_uH=f3,
                           L3D_bars_extrapolated_uH=ext, k_free=ext / ctrl / bars2,
                           mu1000=dict(L3D=j("mu1000_h0.7")["L_uH_energy"] if (R3 / "mu1000_h0.7.json").exists() else None))
    pans = {}
    for case, pan in (("pan430_h0.7", M.pan("ss430", mu=200.0)), ("panCI_h0.7", dict(name="ci1mm", radius_mm=120.0,
                                                                                   layers=[(1.0, M.SIGMA["cast_iron"], 100.0, None)]))):
        r2 = two_d("bars", pan)
        r3 = j(case)
        pans[case] = dict(L2D_uH=r2["L"] * 1e6, R2D_ohm=r2["R"], L3D_uH=r3["L_uH_AdotJ"], R3D_ohm=r3["R_ohm"],
                          k_L=r3["L_uH_AdotJ"] / ctrl / (r2["L"] * 1e6), k_R=r3["R_ohm"] / r2["R"],
                          B_bar_max_3D_mT_per_A=r3["B_bar_max_mT_per_A"])
    out["pan"] = pans
    out["B_bar_3D_free_mT_per_A"] = dict(max=j("free_h0.5")["B_bar_max_mT_per_A"], p99=j("free_h0.5")["B_bar_p99_mT_per_A"],
                                         volmean=j("free_h0.5")["B_bar_volmean_mT_per_A"], profile=j("free_h0.5")["bar_profile"])
    out["pan_conv_430"] = dict(h1=j("pan430_h1")["L_uH_AdotJ"], h07=j("pan430_h0.7")["L_uH_AdotJ"],
                               R_h1=j("pan430_h1")["R_ohm"], R_h07=j("pan430_h0.7")["R_ohm"])
    ks = [p["k_L"] for p in pans.values()]
    kr = [p["k_R"] for p in pans.values()]
    out["factors"] = dict(k_free=out["free_air"]["k_free"], k_L_pan=sum(ks) / len(ks), k_R_pan=sum(kr) / len(kr),
                          k_L_pan_range=[min(ks), max(ks)], k_R_pan_range=[min(kr), max(kr)])
    # transfer check: the 80 uH candidate solved directly in 3D against 2D x factors (same smeared source, 0.6 m)
    if (R3 / "free80_h0.7.json").exists():
        sys.path.insert(0, str(HERE / "fem3d"))
        import build_mesh as BM
        w80 = BM.winding_for("80uH_out6.46")
        m = CM.build(w80, turn_model="smeared", r_max=0.6)
        L2 = m.solve(40e3)["L"] * 1e6
        m = CM.build(w80, pan=M.pan("ss430", mu=200.0), turn_model="smeared", r_max=0.6)
        rp = m.solve(40e3)
        f80, p80 = j("free80_h0.7"), j("pan80_430_h0.7")
        h_corr = ext / f3["0.7"]           # h 0.7 -> extrapolated, from the R43 series
        out["transfer_check_80uH"] = dict(
            free_3D_uH=f80["L_uH_energy"] * h_corr / ctrl, free_2D_x_k_uH=L2 * out["free_air"]["k_free"],
            pan430_L_3D_uH=p80["L_uH_AdotJ"] / ctrl, pan430_L_2D_x_k_uH=rp["L"] * 1e6 * out["factors"]["k_L_pan"],
            pan430_R_3D_ohm=p80["R_ohm"], pan430_R_2D_x_k_ohm=rp["R"] * out["factors"]["k_R_pan"],
            B_bar_max_3D_free_mT_per_A=f80["B_bar_max_mT_per_A"], B_bar_max_3D_pan_mT_per_A=p80["B_bar_max_mT_per_A"],
            B_bar_profile_free=f80["bar_profile"], B_bar_profile_pan=p80["bar_profile"])
        print(json.dumps({k: v for k, v in out["transfer_check_80uH"].items() if "profile" not in k}, indent=1))
    (HERE / "results" / "compare_3d.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["factors"], indent=1))
    print(json.dumps({k: v for k, v in out["free_air"].items()}, indent=1))
    print(json.dumps(pans, indent=1))


if __name__ == "__main__":
    main()
