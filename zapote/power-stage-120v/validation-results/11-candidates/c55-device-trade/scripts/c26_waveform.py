#!/usr/bin/env python3
"""One decision-grid row re-run in the long window with waveforms, printed as a time table (die gate voltages,
switch node, die VDS and die drain currents). Used to see why the CM8 with a large external Cgs fails S2 and the S4
off-gate screen.

    python3 -I c26_waveform.py <config> <case,drv,leg,T,vbus,il,dir,dt,esl>   -> ../results/waveforms/<config>__<row>.json
e.g. c26_waveform.py cm8_r68c6p8_tt180 S2,weak,B,27,280,71,1,340,1.06
     c26_waveform.py cm8_r68c6p8_tt180 S4,strong,B,150,170,-20,0,340,1.06
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, G, SIMS  # noqa: E402
import devices  # noqa: E402
import devlib  # noqa: E402


def main():
    import numpy as np
    name, row = sys.argv[1], sys.argv[2]
    dev = devices.get(name)
    case, drv, leg, temp, vbus, il, d, dt, esl = row.split(",")
    out = SIMS / "_waveforms" / f"{name}__{row.replace(',', '_')}"
    out.mkdir(parents=True, exist_ok=True)
    deck = out / "deck.cir"
    deck.write_text(devlib.build(dev, long=True))
    roh, rol = G.DRIVER[drv]
    cret, cbus = G.Z.node_caps()[G.H.BOARD][leg]
    p = G.run_d2.matrix_params(G.run_d2.read_L(str(G.d2c.MATRICES[leg])))
    p.update(TJ=temp, VBUS=vbus, IL=il, DIR=d, DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n", TRMAX="0.2n", ROH=str(roh),
             ROL=str(rol), RG=str(dev["ron"]), CBRD_RET=f"{max(cret, 1e-6)}p", CBRD_BUS=f"{max(cbus, 1e-6)}p",
             ROFF=str(dev["roff"]), CGS=str(dev["cgs"]))
    p.update(devlib.params_extra(dev))
    r = G.run_d2.run(deck, p, keep=out / "run", raw=True)
    assert not r["aborted"]
    sys.path.insert(0, str(G.run_d2.KIT / "common"))
    from run_ngspice import read_raw
    w = {k: np.asarray(v) for k, v in read_raw(out / "run" / "waves.raw").items()}
    rdp = dev["wrapper"][2] if dev["kind"] == "wrap" else 7.44e-5
    t = w["time"] * 1e9
    sig = {"vgs_ls": w["v(xql.g)"] - w["v(xql.s)"], "vgs_hs": w["v(xqh.g)"] - w["v(xqh.s)"], "v_sw": w["v(sw)"],
           "vds_ls": w["v(xql.dd)"] - w["v(xql.s)"], "vds_hs": w["v(xqh.dd)"] - w["v(xqh.s)"],
           "id_ls": (w["v(xql.ldrd)"] - w["v(xql.dd)"]) / rdp, "id_hs": (w["v(xqh.ldrd)"] - w["v(xqh.dd)"]) / rdp}
    grid = list(range(1960, 2100, 10)) + list(range(2100, 3300, 40))
    table = [{"t_ns": g, **{k: round(float(np.interp(g, t, v)), 2) for k, v in sig.items()}} for g in grid]
    peaks = {k: {"max": round(float(v.max()), 2), "t_max_ns": round(float(t[v.argmax()]), 1),
                 "min": round(float(v.min()), 2), "t_min_ns": round(float(t[v.argmin()]), 1)} for k, v in sig.items()}
    res = {"config": name, "row": row, "params": p, "peaks": peaks, "table": table}
    (C55 / "results/waveforms").mkdir(parents=True, exist_ok=True)
    (C55 / "results/waveforms" / f"{name}__{row.replace(',', '_')}.json").write_text(json.dumps(res, indent=1) + "\n")
    shutil.rmtree(out / "run", ignore_errors=True)
    print(json.dumps(peaks, indent=1))


if __name__ == "__main__":
    main()
