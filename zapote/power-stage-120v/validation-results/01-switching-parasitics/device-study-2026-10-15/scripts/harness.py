#!/usr/bin/env python3
"""Device-swap harness on the as-built native-21 switching deck (read-only reuse of the repo's scripts).

Deck = c25 `results/dtband/F6.cir` (sha 55a2058f..., the as-built F6 + PMEG + -1.6 V off + 2EDR8259 Rout, Rg 8.2 ohm)
       + the c33 adoption ZVS additions (board switch-node C, ZVS crossing meas; zvs_node_c.py ADD)
       + the c25 dv/dt / slew probes (d2_c25.py PROBES)
       + die-dissipation integrals from the vendor model's own heat channels (this study, ENERGY below)
Device swap: every 'IPW65R018CFD7_L1' instance is replaced by DEVICE (another subckt in the vendor CFD7 library, or a
wrapper subckt from ../models/ with the same 3 pins and internal nodes dd, s, g, ldrd).

Board = s32 (board of record, DECISIONS 40), node caps from c33 loop-screen-b2.json via zvs_node_c.node_caps().

Run from anywhere:  python3 -I harness.py <mode> --device IPW65R018CFD7_L1 [--workers 6]
modes: repro | zvs | edge | edge2 | cm8rg | cm8rg2 | energy   (outputs under ../sims/<device>/<mode>/)
cm8rg/cm8rg2: CM8 proxy = CFD7 029 model with deck RG = R_ext + 1.0 - 3.8 ohm (R_ext 8.2/10 and 12/15)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
POWER = Path(__file__).resolve().parents[4]   # zapote/power-stage-120v (committed copy, DECISIONS 49)
ZVS = POWER / "validation-results/11-candidates/c33-six-layer/adoption/zvs"
spec = importlib.util.spec_from_file_location("zvs_node_c", ZVS / "zvs_node_c.py")
Z = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Z)          # read-only: deck_text(), node_caps(), d2c (c25 module), run_d2
d2c, run_d2 = Z.d2c, Z.run_d2

# CM8 proxy gate-resistance variants: the proxy model (IPW65R029CFD7_L1) has Rg,int 3.8 ohm (lib .PARAM Rg=3.8;
# datasheet 3.8 ohm), IPW65R018CM8 has RG 1 ohm typ (Rev 2.1 p.5 Table 4). The deck's RG is the external resistor, so
# CM8 with external R is represented by RG_deck = R_ext + 1.0 - 3.8 (same total gate resistance).
for _name, (_roh, _rol, _rg) in list(d2c.VARIANTS.items()):
    if _name.startswith("edr_rg8p2"):
        for _rext in (8.2, 10.0, 12.0, 15.0):
            d2c.VARIANTS[_name.replace("edr_rg8p2", f"cm8ext{_rext:g}".replace(".", "p"))] = (_roh, _rol, round(_rext + 1.0 - 3.8, 3))

AS_BUILT = "IPW65R018CFD7_L1"
BOARD = "s32"
MODELS = ROOT / "models"            # wrapper subckts for non-CFD7 devices (if any)

# True die dissipation from the vendor model's heat channels (cool_tech_w3: G_G_Ptot_channel / G_G_Ptot_Epi without
# the 0..100k clip). Signed integrals: summed over both dies of a leg across the transition window, the Coss energy
# exchange cancels and what is left is channel + epi + body-diode heat.
GATEQ = """
* ---- device study: window and gate-loop charge (post-processing .meas only; no added elements)
.param TW0={T1-20n} TW1={T1+DT+0.75u}
.save i(l_p3) i(l_p4)
* gate-loop charge (L_P3/L_P4 carry the whole gate current incl. the 1 nF Cgs and the PMEG branch; + = gate discharge)
.meas tran qh_win INTEG i(l_p3) from={TW0} to={TW1}
.meas tran ql_win INTEG i(l_p4) from={TW0} to={TW1}
"""

# B-sources: used in the energy mode only (they cost convergence: 2/128 repro and several edge rows aborted with them)
ENERGY = """
* ---- device study: die heat (vendor heat channels, signed) over the transition window
Bphs phs 0 V={(v(xqh.x1.d)-v(xqh.s))*i(v.xqh.x1.v_ichannel)+(v(xqh.dd)-v(xqh.x1.d1))*i(v.xqh.x1.v_iepi)+(v(xqh.dd)-v(xqh.s))*i(v.xqh.x1.v_sense2)}
Bpls pls 0 V={(v(xql.x1.d)-v(xql.s))*i(v.xql.x1.v_ichannel)+(v(xql.dd)-v(xql.x1.d1))*i(v.xql.x1.v_iepi)+(v(xql.dd)-v(xql.s))*i(v.xql.x1.v_sense2)}
.save v(phs) v(pls)
.meas tran e_hs_die INTEG v(phs) from={TW0} to={TW1}
.meas tran e_ls_die INTEG v(pls) from={TW0} to={TW1}
.meas tran p_hs_end FIND v(phs) AT={TW1-5n}
.meas tran p_ls_end FIND v(pls) AT={TW1-5n}
.meas tran p_hs_start FIND v(phs) AT={TW0}
.meas tran p_ls_start FIND v(pls) AT={TW0}
"""

DT_LOW = {"2EDR_window_min_408": 408.3, "audit_window_min_340": 340.0}


def deck_text(device: str, energy: bool = False) -> str:
    base = Z.deck_text()                                  # sha-checked c25 deck + c33 ADD
    assert base.count(AS_BUILT) == 2, base.count(AS_BUILT)
    add = d2c.PROBES + GATEQ + (ENERGY if energy else "")
    deck = base.replace("\n.end", "\n" + add + ".end")
    if device != AS_BUILT:
        deck = deck.replace(AS_BUILT, device)
        wrap = MODELS / f"{device}.lib"
        if wrap.is_file():
            deck = deck.replace(".include IFX_CFD7_650V.lib", f".include IFX_CFD7_650V.lib\n.include {wrap}", 1)
    return deck


def write_deck(device: str, out: Path, energy: bool = False) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / "deck.cir"
    p.write_text(deck_text(device, energy))
    return p


def run_one(deck: Path, out: Path, device: str, variant: str, leg: str, temp: float, vbus: float, il: float, d: int,
            dt: float, esl: float = 10, trmax: str = "0.2n", keep_fail=True) -> dict:
    roh, rol, rg = d2c.VARIANTS[variant]
    cret, cbus = Z.node_caps()[BOARD][leg]
    name = f"{variant}_{leg}_T{temp}_v{vbus}_i{il}_d{d}_dt{dt}_esl{esl}_s{trmax}"
    p = run_d2.matrix_params(run_d2.read_L(str(d2c.MATRICES[leg])))
    p.update(TJ=str(temp), VBUS=str(vbus), IL=str(il), DIR=str(d), DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n",
             TRMAX=trmax, ROH=str(roh), ROL=str(rol), RG=str(rg),
             CBRD_RET=f"{max(cret, 1e-6)}p", CBRD_BUS=f"{max(cbus, 1e-6)}p")
    keep = out / "runs" / name
    r = run_d2.run(deck, p, keep=keep)
    m = r["meas"]
    row = {"device": device, "board": BOARD, "variant": variant, "leg": leg, "temp_C": temp, "vbus": vbus, "il": il,
           "dir": d, "dt_ns": dt, "esl_nH": esl, "trmax": trmax}
    inc, off = ("hs", "ls") if d == 0 else ("ls", "hs")
    need = ["vds_ls_die_pk", "vds_hs_die_pk", f"vgs_{off}_off_max", f"vds_{inc}_at_on"] + \
        (["e_hs_die", "e_ls_die"] if "e_hs_die" in deck.read_text() else [])
    if r["aborted"] or any(k not in m for k in need):
        row["status"] = "aborted" if r["aborted"] else "indeterminate"
        row["missing"] = [k for k in need if k not in m]
        (keep / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
        if not keep_fail:
            shutil.rmtree(keep, ignore_errors=True)
        return row
    shutil.rmtree(keep, ignore_errors=True)
    t1 = 2e-6
    tz = m.get(f"t_{inc}_zvs")
    tw = (dt * 1e-9 + 0.75e-6) + 20e-9
    # conduction reference: the incoming die's steady power at the window end (it carries IL alone there)
    energy = "e_hs_die" in m
    p_end = m[f"p_{inc}_end"] if energy else None
    e_tot = m["e_hs_die"] + m["e_ls_die"] if energy else None
    row.update(status="complete", vds_pk=max(m["vds_ls_die_pk"], m["vds_hs_die_pk"]),
               off_V=m[f"vgs_{off}_off_max"], incoming_V=m[f"vds_{inc}_at_on"],
               vgs_abs=max(abs(m[f"vgs_{s}_die_{e}"]) for s in ("ls", "hs") for e in ("min", "max")),
               t_trans_ns=(tz - t1) * 1e9 if tz is not None else None,
               e_out_J=m.get(f"e_{off}_die"), e_in_J=m.get(f"e_{inc}_die"), e_tot_J=e_tot,
               p_cond_end_W=p_end, p_cond_start_W=m.get(f"p_{off}_start"),
               e_extra_J=(e_tot - p_end * tw) if energy else None,
               q_gate_hs_C=m.get("qh_win"), q_gate_ls_C=m.get("ql_win"))
    row["zvs"] = row["incoming_V"] <= 0.05 * vbus
    if "dvsw_max" in m:
        row["dvsw_abs"] = max(abs(m["dvsw_max"]), abs(m["dvsw_min"]))
        row["dvdie_abs"] = max(abs(m[k]) for k in ("dvls_max", "dvls_min", "dvhs_max", "dvhs_min"))
    t2080 = m.get("tr2080") if d == 0 else m.get("tf8020")
    if t2080 and t2080 > 0:
        row["slew2080_Vns"] = 0.6 * vbus / (t2080 * 1e9)
    t1090 = m.get("tr1090") if d == 0 else m.get("tf9010")
    if t1090 and t1090 > 0:
        row["slew1090_Vns"] = 0.8 * vbus / (t1090 * 1e9)
    return row


def screen(row: dict, case: str) -> dict:
    """c25 pass rules (d2_c25.one): die VDS <= 520 V (585 V for S2), |VGS| <= 30 V, off-gate < 3.0 V and < model screen
    at the temperature, plus the hot 1.9 V screen; S1 must be ZVS at its own on command."""
    if row["status"] != "complete":
        return row
    lim = 585 if case == "S2" else 520
    scr = d2c.SCREEN.get(row["temp_C"])
    row.update(case=case, pass_vds=row["vds_pk"] <= lim, pass_vgs=row["vgs_abs"] <= 30, pass_3V=row["off_V"] < 3.0,
               pass_1p9=row["off_V"] < 1.9, pass_model=(row["off_V"] < scr) if scr is not None else None)
    row["pass"] = row["pass_vds"] and row["pass_vgs"] and row["pass_3V"] and (row["pass_model"] is not False) and \
        (row["zvs"] if case == "S1" else True)
    row["pass_hot"] = row["pass"] and row["pass_1p9"]
    return row


def identity(device: str, deck: Path) -> dict:
    files = [d2c.MATRICES["A"], d2c.MATRICES["B"], Z.REF_DECK, ZVS / "zvs_node_c.py", Path(d2c.__file__),
             run_d2.KIT / "models/vendor/IFX_CFD7_650V.lib", Z.C33 / "screens/loop-screen-b2.json", Path(__file__), deck]
    w = MODELS / f"{device}.lib"
    if w.is_file():
        files.append(w)
    return {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}


def jobs_for(mode: str):
    if mode == "repro":
        # committed c33 adoption ZVS rows (board s32), all corners at IL 37 and the worst-threshold corners
        ref = json.loads((ZVS / "results.json").read_text())
        want = [r for r in ref if r["board"] == BOARD and r["status"] == "complete" and
                ((r["il"] == 37 and r["temp_C"] in (27, 150)) or
                 (r["variant"] == "edr_rg8p2_weak" and r["temp_C"] == 150 and r["vbus"] in (198, 280)))]
        return [("S1", r["variant"], r["leg"], r["temp_C"], r["vbus"], r["il"], r["dir"], 600) for r in want], want
    if mode == "zvs":
        corners = [("edr_rg8p2", t) for t in (27, 100, 150)] + \
                  [(v, t) for v in ("edr_rg8p2_weak", "edr_rg8p2_strong") for t in (27, 150)]
        return [("S1", v, leg, t, vb, il, d, 600) for (v, t) in corners for leg in "AB" for vb in (170, 198, 280)
                for il in (37, 25, 20, 15, 10, 7, 5, 3) for d in (0, 1)], None
    if mode == "edge":
        # c25 dtband's case set at the window edges: S1 (37 A ZVS), S2 (280 V / 71 A fault turn-off),
        # S4 (-20 A hard turn-on with body-diode recovery), S5 (0 A first edge after idle)
        pts = d2c.pts(("S1", "S2", "S4", "S5"), (340, 408, 600))
        js = [(c, "edr_rg8p2", leg, t, vb, il, d, dt) for leg in "AB" for t in (27, 100, 150)
              for (c, vb, il, dt) in pts for d in (0, 1)]
        js += [(c, v, leg, t, vb, il, d, dt) for v in ("edr_rg8p2_weak", "edr_rg8p2_strong") for leg in "AB"
               for t in (27, 150) for (c, vb, il, dt) in d2c.pts(("S1", "S2", "S4", "S5"), (340, 600)) for d in (0, 1)]
        return js, None
    if mode == "edge2":
        # the hard cases again at the low capacitor ESL (1.06 nH; c25 dtband ran both 1.06 and 10 nH)
        pts = [p for p in d2c.pts(("S2", "S4", "S5"), (340, 600))]
        js = [(c, v, leg, t, vb, il, d, dt, 1.06) for v, temps in (("edr_rg8p2", (27, 100, 150)),
              ("edr_rg8p2_weak", (27, 150)), ("edr_rg8p2_strong", (27, 150)))
              for leg in "AB" for t in temps for (c, vb, il, dt) in pts for d in (0, 1)]
        return js, None
    if mode == "cm8rg":
        js = []
        for rext in ("8p2", "10"):
            for v in (f"cm8ext{rext}", f"cm8ext{rext}_strong"):
                for leg in "AB":
                    for t in (27, 150):
                        for d in (0, 1):
                            for (c, vb, il, dt) in d2c.pts(("S1", "S2", "S4", "S5"), (340, 600)):
                                for esl in ((10,) if c == "S1" else (10, 1.06)):
                                    js.append((c, v, leg, t, vb, il, d, dt, esl))
        return js, None
    if mode == "cm8rg2":
        # follow-up: R_ext 12 / 15 ohm on the binding S4 edge (and S1 ZVS at the short dead time)
        js = []
        for rext in ("12", "15"):
            for v in (f"cm8ext{rext}", f"cm8ext{rext}_strong", f"cm8ext{rext}_weak"):
                for leg in "AB":
                    for t in (27, 150):
                        for d in (0, 1):
                            for (c, vb, il, dt) in d2c.pts(("S1", "S4"), (340, 600)):
                                if c == "S1" and (dt != 340 or not v.endswith("_weak")):
                                    continue
                                for esl in ((10,) if c == "S1" else (10, 1.06)):
                                    js.append((c, v, leg, t, vb, il, d, dt, esl))
        return js, None
    if mode == "energy":
        # die heat per transition over the line-cycle event domain (bus 20..198 V, turn-off current 2..60 A),
        # nominal driver, dead time 569 ns (2EDR window upper edge: longest body-diode interval, conservative), legs A, B
        return [("E", "edr_rg8p2", leg, t, vb, il, d, 569) for leg in "AB" for t in (100, 150)
                for vb in (20, 60, 100, 140, 170, 198) for il in (2, 5, 10, 15, 20, 30, 40, 50, 60) for d in (0, 1)], None  # dt below
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["repro", "zvs", "edge", "edge2", "cm8rg", "cm8rg2", "energy"])
    ap.add_argument("--device", default=AS_BUILT)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="first N jobs only (timing test)")
    a = ap.parse_args()
    out = ROOT / "sims" / a.device / a.mode
    deck = write_deck(a.device, out, energy=(a.mode == "energy"))
    jobs, want = jobs_for(a.mode)
    if a.limit:
        jobs = jobs[:a.limit]

    def go(j):
        case, v, leg, t, vb, il, d, dt, *esl = j
        r = run_one(deck, out, a.device, v, leg, t, vb, il, d, dt, esl=(esl[0] if esl else 10))
        return screen(r, case) if case != "E" else r

    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(go, jobs))
    # one retry at 0.1 ns for aborted rows (c25's treatment of an isolated abort)
    for i, (j, r) in enumerate(zip(jobs, rows)):
        if r["status"] != "complete":
            case, v, leg, t, vb, il, d, dt, *esl = j
            r2 = run_one(deck, out / "retry", a.device, v, leg, t, vb, il, d, dt, esl=(esl[0] if esl else 10), trmax="0.1n")
            rows[i] = screen(r2, case) if case != "E" else r2
    res = {"device": a.device, "mode": a.mode, "identity": identity(a.device, deck), "rows": rows}
    if want is not None:
        worst = {"incoming_V": 0.0, "vds_pk": 0.0, "t_trans_ns": 0.0}
        for w, r in zip(want, rows):
            r["committed"] = {k: w[k] for k in ("incoming_V_at_on", "vds_pk", "t_trans_ns")}
            if r["status"] == "complete":
                worst["incoming_V"] = max(worst["incoming_V"], abs(r["incoming_V"] - w["incoming_V_at_on"]))
                worst["vds_pk"] = max(worst["vds_pk"], abs(r["vds_pk"] - w["vds_pk"]))
                worst["t_trans_ns"] = max(worst["t_trans_ns"], abs(r["t_trans_ns"] - w["t_trans_ns"]))
        res["repro_max_abs_delta"] = worst
        res["repro_complete"] = f"{sum(r['status'] == 'complete' for r in rows)}/{len(rows)}"
        print("repro", res["repro_complete"], worst)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    bad = [r for r in rows if r["status"] != "complete"]
    print(a.device, a.mode, f"{len(rows) - len(bad)}/{len(rows)} complete")


if __name__ == "__main__":
    main()
