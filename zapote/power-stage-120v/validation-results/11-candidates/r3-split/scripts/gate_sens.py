#!/usr/bin/env python3
"""S2-B gate-path sensitivity: add dL (nH) in series with the gate-loop ports P3/P4 of the
native-21 s9b2 F6 decks (mutuals held constant) and re-run the worst S4 cases of each leg.
Usage: python3 -I gate_sens.py [--workers 6] ; writes ../results/gate_sens.json
Reads (read-only) the repo's d2 matrices/deck/runner; writes only under r3-split/."""
import sys, json, math, itertools, argparse, shutil
sys.dont_write_bytecode = True
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
PS = HERE.parents[3]
D2 = PS/"validation-results/01-switching-parasitics/round17/d2"
KIT = PS/"validation-plan/sim-kit"
sys.path.insert(0, str(KIT/"common")); sys.path.insert(0, str(D2)); sys.path.insert(0, str(D2.parent/"scripts"))
import run_d2  # read_L, run (ngspice runner)
from run_ngspice import run
DECK = D2/"results/f6-vneg-m1p6-legB21-s9b2/F6.cir"
MAT = {"A": D2/"legA21-h0-s9b2-n21.matrix.txt", "B": D2/"legB21-h0-s9b2-n21.matrix.txt"}
RES = {l: D2/f"results/f6-vneg-m1p6-leg{l}21-s9b2/results.json" for l in "AB"}

def params(L, dL3, dL4):
    L = [r[:] for r in L]
    L[2][2] += dL3; L[3][3] += dL4        # mutuals untouched (absolute nH)
    p = {f"LP{i+1}": f"{L[i][i]:.9g}n" for i in range(4)}
    for i in range(4):
        for j in range(i+1, 4):
            p[f"K{i+1}{j+1}"] = f"{L[i][j]/math.sqrt(L[i][i]*L[j][j]):.9g}"
    return p

def worst_cases(leg, n=3):
    rows = [r for r in json.load(open(RES[leg])) if r.get("status") == "complete"]
    sel = sorted(rows, key=lambda r: -r["vds_pk"])[:n] + sorted(rows, key=lambda r: -r["off_V"])[:n]
    out, seen = [], set()
    for r in sel:
        k = (r["temp_C"], r["case"], r["vbus"], r["il"], r["dir"], r["dt_ns"], r["esl_nH"])
        if k not in seen: seen.add(k); out.append(r)
    return out

VARIANT = "port"
def drv_deck():
    t = DECK.read_text()
    t = t.replace("Bgl gdl s_ls I={(v(gdl,s_ls)", "Bgl gdl_d s_ls I={(v(gdl_d,s_ls)").replace("+(v(gdl,s_ls)-VDRV)", "+(v(gdl_d,s_ls)-VDRV)")
    t = t.replace("Bgh gdh sw I={(v(gdh,sw)", "Bgh gdh_d sw I={(v(gdh_d,sw)").replace("+(v(gdh,sw)-VDRV)", "+(v(gdh_d,sw)-VDRV)")
    t = t.replace("Rgl gdl gdl3", "Lconnl gdl_d gdl {LCONN}\nRgl gdl gdl3").replace("Rgh gdh gdh3", "Lconnh gdh_d gdh {LCONN}\nRgh gdh gdh3")
    t = t.replace(".param LESL=", ".param LCONN=1p LESL=")
    assert t.count("gdl_d") >= 3 and t.count("gdh_d") >= 3, "deck patch failed"
    p = OUT/"raw/F6_drv.cir"; p.parent.mkdir(exist_ok=True); p.write_text(t); return p
def one(job):
    leg, r, dL = job
    p = run_d2.matrix_params(run_d2.read_L(str(MAT[leg])))
    p.update(params(run_d2.read_L(str(MAT[leg])), dL if VARIANT == "port" else 0.0, dL if VARIANT == "port" else 0.0))
    if VARIANT == "drv": p["LCONN"] = f"{max(dL, 0.001):.6g}n"
    p.update(TJ=str(r["temp_C"]), VBUS=str(r["vbus"]), IL=str(r["il"]), DIR=str(r["dir"]), DT=f'{r["dt_ns"]}n',
             LESL=f'{r["esl_nH"]}n', LSHUNT="2n", TRMAX="0.2n")
    name = f'{leg}_dL{dL}_T{r["temp_C"]}_{r["case"]}_v{r["vbus"]}_d{r["dir"]}_dt{r["dt_ns"]}_esl{r["esl_nH"]}'
    keep = OUT/"raw/gate_sens"/name
    res = run(DECK if VARIANT == "port" else drv_deck(), p, keep=keep)
    shutil.rmtree(keep, ignore_errors=True)   # keep the repo of results small
    m = res["meas"]; off = "ls" if r["dir"] == 0 else "hs"
    if res["aborted"] or res["failed"]:
        return dict(leg=leg, dL=dL, base=r, status="indeterminate")
    vds = max(m["vds_ls_die_pk"], m["vds_hs_die_pk"]); offv = m[f"vgs_{off}_off_max"]
    inc = "hs" if r["dir"] == 0 else "ls"
    return dict(variant=VARIANT, leg=leg, dL=dL, incoming_V=m[f"vds_{inc}_at_on"], case={k: r[k] for k in ("temp_C","case","vbus","il","dir","dt_ns","esl_nH")},
                base_vds=r["vds_pk"], base_off=r["off_V"], status="complete", vds_pk=vds, off_V=offv,
                vgs_abs=max(abs(m[f"vgs_{s}_die_{e}"]) for s in ("ls","hs") for e in ("min","max")))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--dl", default="0,3,6,10,20,40"); ap.add_argument("--variant", default="port")
    a = ap.parse_args(); VARIANT = a.variant
    dls = [float(x) for x in a.dl.split(",")]
    jobs = [(l, r, dl) for l in "AB" for r in worst_cases(l) for dl in dls]
    with ThreadPoolExecutor(a.workers) as ex: rows = list(ex.map(one, jobs))
    (OUT/("results/gate_sens.json" if VARIANT == "port" else "results/gate_sens_drv.json")).write_text(json.dumps(rows, indent=1))
    print(len(rows), "runs;", sum(r["status"] != "complete" for r in rows), "indeterminate")
