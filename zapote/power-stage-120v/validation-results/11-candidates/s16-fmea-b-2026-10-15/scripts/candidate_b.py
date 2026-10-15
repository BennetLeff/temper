#!/usr/bin/env python3
"""Monitor front-end rows of the FMEA for V0 (s43), V1 (1c-4420) and V2 (candidate B), in the c24 metric.

Called from scripts/fmea_metric.py (the fmea-b copy of the c24 script); not run on its own.  Reads
results/fault_sim.json (scripts/monitor_fault_sim.py), results/bands.json (scripts/bands.py) and results/sources.json
(scripts/sources.py), and writes results/fmea_b_metric.{json,md}.

Metric (c24 section 4): RWL = sum over modes of FIT x P(mode masks) x rails hidden.  The c24 chain rows hide whole
rails.  A front-end mode hides thresholds, so it is entered as thresholds/4 rail-equivalents (four thresholds = the
rail's whole protection).  RWL_total = c24 chain RWL of the as-built heartbeat chain (P2H rows; identical in V0, V1, V2)
+ 3 x the per-rail front-end RWL.  Only masking against the hard limits H counts (results/bands.json limits).

Rates (FIT = per 1e9 h; per part, per rail):
  TL431 6 FIT, FMD open 25 / short 35 / out of spec 40 %            TI SNVA914 p.1 (TL431-Q1, IEC TR 62380)
  LM339B 16 FIT SOIC-14 (die 2, package 14), FMD Hi-Z 15 / sat high 25 / sat low 25 / out of spec 30 / two pins 5 %
                                                                     TI SLCA004 Tables 1-1, 1-3 (LM2901B family proxy)
  TPS3701 4 FIT (die 2, package 2), FMD Hi-Z 30 / stuck low 30 / out of spec 40 %
                                                                     TI SLVAEM2A Tables 2-1, 3-1 (TPS3700-Q1 proxy; no
                                                                     TPS3701 document exists, ti.com product page 2026-10-15)
  alternative TPS3701 FMD: fails to trip 15 / false trip 15 / trip out of spec 65 / delay 5 %   TI SFFS944 Table 3-1
  TI MTBF/FIT estimator (HTOL, 60 % CL, 0 fails): TL431A/BIDBZR 8.0, LM339BIDR 8.0, TPS3701DDCR 0.1 FIT (sensitivity)
ASSUMED (class assumptions, as in c24): resistor 0.5 FIT (open 80 / drift 20 %), MLCC 0.5 FIT (short 50 / open 30 /
  drift 20 %); allocation B spreads the package FIT 50 % over pin opens (uniform per pin) and 50 % over the TI-listed
  adjacent-pin shorts (uniform per pair); k_u = 0.5, k_o = 0 base (c24 values), swept.
Mode -> effect comes from the fault simulation, except: out-of-specification modes (k_o on the one threshold they can
move; the TPS3701's 40 % gets no credit for its reference share), shared-reference drift (TL431, R79 / R80, rref:
k = 0 against H because bands.py shows the companion thresholds announce first; asserted below), tap-resistor drift
(k_o on its threshold).
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
NAMES = ("neg UV", "neg OV", "span UV", "span OV")
VARS = ("V0", "V1", "V2", "V2+F2ov", "V2+F2", "V2+F2+v5")
r3 = lambda x: round(x, 3)


def parts(src, case):
    s = src
    tl = dict(fit=s["TL431_FIT"]["values"]["total"], die=s["TL431_FIT"]["values"]["die"],
              pkg=s["TL431_FIT"]["values"]["package"], fmd=s["TL431_FMD"]["values"])
    lm = dict(fit=s["LM2901B_FIT"]["values"]["SOIC14_total"], die=s["LM2901B_FIT"]["values"]["die"],
              pkg=s["LM2901B_FIT"]["values"]["SOIC14_package"], fmd=s["LM2901B_FMD"]["values"])
    tp = dict(fit=s["TPS3700Q1_FIT"]["values"]["total"], die=s["TPS3700Q1_FIT"]["values"]["die"],
              pkg=s["TPS3700Q1_FIT"]["values"]["package"],
              fmd={"hiz": s["TPS3700Q1_FMD"]["values"]["hiz"], "low": s["TPS3700Q1_FMD"]["values"]["stuck_low"],
                   "oos": s["TPS3700Q1_FMD"]["values"]["out_of_spec"]})
    if case.get("tps3703_fmd"):
        f = s["TPS3703_FMD"]["values"]
        tp["fmd"] = {"hiz": f["fail_to_trip"], "low": f["false_trip"], "oos": f["trip_out_of_spec"]}
    if case.get("estimator"):
        e = s["TI_ESTIMATOR"]["values"]
        for d, k in ((tl, "TL431AIDBZR"), (lm, "LM339BIDR"), (tp, "TPS3701DDCR")):
            scale = e[k]["FIT"] / d["fit"]
            d["fit"], d["die"], d["pkg"] = e[k]["FIT"], d["die"] * scale, d["pkg"] * scale
    return {"TL431": tl, "LM339B": lm, "TPS3701": tp}


NPINS = {"TL431": 3, "LM339B": 14, "TPS3701": 6}
NPAIRS = {"TL431": 3, "LM339B": 14, "TPS3701": 6}
NCH = {"LM339B": 4, "TPS3701": 2}


def lam(f, P, p, alloc):
    """FIT of one simulated fault row."""
    k = f["kind"]
    if k == "res_open":
        return p["R"] * 0.8
    if k == "cap_short":
        return p["C"] * 0.5
    d = P[f["part"]]
    tot = d["fit"] if alloc == "A" else d["die"]
    if k == "die":
        if f["part"] == "LM339B":
            frac = (d["fmd"]["hiz"] + d["fmd"]["sat_high"]) if f["die"] == "hiz" else d["fmd"]["sat_low"]
            return tot * frac / 4
        if f["part"] == "TPS3701":
            return tot * d["fmd"][f["die"]] / 2
        return tot * d["fmd"][f["die"]]                                  # TL431 open / short
    pkg = 0.0 if alloc == "A" else d["pkg"]
    if k == "pin_open":
        return pkg * 0.5 / NPINS[f["part"]]
    if k == "pin_short":
        die_ps = (tot * d["fmd"]["pin_short"] / NPAIRS["LM339B"]) if f["part"] == "LM339B" else 0.0
        return die_ps + pkg * 0.5 / NPAIRS[f["part"]]
    raise ValueError(k)


def kv(masked, p):
    return {t: (1.0 if v == "1" else p["k_u"]) for t, v in masked.items()}


def group(f, var):
    """FMEA row each simulated fault belongs to."""
    k, part = f["kind"], f.get("part")
    if k == "res_open":
        if any(x in f["name"] for x in ("rref", "halfref")):
            return "C4"
        return "rpull" if "rpull" in f["name"] else "C5"
    if k == "cap_short":
        return "C6" if "1 nF" in f["name"] else "N7"
    if part == "TL431":
        return "C4"
    if k == "die":
        return "C2" if f["die"] == "hiz" else "C3"
    if k == "pin_open":
        pin = f["pin"]
        if part == "LM339B":
            return "N1" if pin in (3, 12) else ("C2" if pin in (1, 2, 13, 14) else "N4")
        return "N1" if pin in (2, 5) else ("C2" if pin in (1, 6) else "N4")
    if k == "pin_short":
        pr = {f["a"], f["b"]}
        if part == "LM339B" and pr == {2, 3} or part == "TPS3701" and pr == {5, 6}:
            return "N2"
        if part == "TPS3701" and pr == {4, 5}:
            return "N3"
        return "N4"
    return "other"


def frontend(var, sim, drift, p, P, alloc):
    rows = []
    for f in sim[var]:
        lm_ = lam(f, P, p, alloc)
        if lm_ == 0.0:
            continue
        rows.append({"row": group(f, var), "mode": f["label"], "fit": lm_, "k": kv(f["masked_H"], p),
                     "status": f["status"], "kind": f["kind"]})
    # non-simulated modes
    if var in ("V0", "V1"):
        d = P["LM339B"]
        tot = d["fit"] if alloc == "A" else d["die"]
        for t in NAMES:
            rows.append({"row": "C2b", "mode": f"U29 LM339B {t} channel out of specification", "fit": tot * d["fmd"]["out_of_spec"] / 4,
                         "k": {t: p["k_o"]}, "status": "dormant (k_o)", "kind": "oos"})
        d = P["TL431"]
        silent = any(v["silent_mask_vs_H"] for v in drift[var].values())
        rows.append({"row": "C4", "mode": "U17 TL431 out of specification (Vref drift: moves all four thresholds)",
                     "fit": (d["fit"] if alloc == "A" else d["die"]) * d["fmd"]["out_of_spec"],
                     "k": ({t: p["k_o"] for t in NAMES} if silent else {}),
                     "status": "bounded: companions announce before H (bands.py)" if not silent else "SILENT", "kind": "drift"})
        for nm in ("R59 rref", "R79 halfref top", "R80 halfref bottom"):
            rows.append({"row": "C4", "mode": nm + " drift (shared reference)", "fit": p["R"] * 0.2, "k": {},
                         "status": "bounded as TL431 drift", "kind": "drift"})
    else:
        d = P["TPS3701"]
        tot = d["fit"] if alloc == "A" else d["die"]
        for ic, ths in (("U29", ("neg UV", "neg OV")), ("U47", ("span UV", "span OV"))):
            for t in ths:
                rows.append({"row": "C2b", "mode": f"{ic} TPS3701 {t} out of specification (comparator or internal reference)",
                             "fit": tot * d["fmd"]["oos"] / 2, "k": {t: p["k_o"]}, "status": "dormant (k_o)", "kind": "oos"})
    for t in NAMES:
        for pos in ("top", "bottom"):
            rows.append({"row": "C5", "mode": f"{t} {pos} resistor drift", "fit": p["R"] * 0.2, "k": {t: p["k_o"]},
                         "status": "dormant (k_o)", "kind": "drift"})
    return rows


def summarise(rows):
    thr = sum(r["fit"] * sum(r["k"].values()) for r in rows)
    whole = sum(r["fit"] * min(r["k"].get(t, 0.0) for t in NAMES) for r in rows)
    per_t = {t: sum(r["fit"] * r["k"].get(t, 0.0) for r in rows) for t in NAMES}
    return {"FIT_thresholds_per_rail": thr, "RWL_per_rail": thr / 4, "FIT_whole_rail_per_rail": whole, "per_threshold": per_t}


CASES = {
    "base": {},
    "k_u = 1": dict(k_u=1.0),
    "k_u = 0": dict(k_u=0.0),
    "k_o = 0.5": dict(k_o=0.5),
    "allocation B (die FMD on die FIT; package FIT on pins)": dict(alloc="B"),
    "TI estimator FITs (8 / 8 / 0.1)": dict(estimator=True),
    "TPS3703 FMD for the TPS3701": dict(tps3703_fmd=True),
    "passives x5": dict(R=2.5, C=2.5, D=5.0, Q=5.0),
    "worst (k_u 1, k_o 0.5, passives x5, allocation B)": dict(k_u=1.0, k_o=0.5, R=2.5, C=2.5, D=5.0, Q=5.0, alloc="B"),
}


def run(rows_for, base_params, score):
    sim = {k: v for k, v in json.load(open(os.path.join(RES, "fault_sim.json")))["variants"].items()}
    drift = json.load(open(os.path.join(RES, "bands.json")))["drift"]
    src = json.load(open(os.path.join(RES, "sources.json")))
    out, bad = {"cases": {}}, []
    for cname, ch in CASES.items():
        p = dict(base_params(), **{k: v for k, v in ch.items() if k in ("k_u", "k_o", "R", "C", "D", "Q")})
        P = parts(src, ch)
        alloc = ch.get("alloc", "A")
        chain = score(rows_for("P2H", p))["RWL_chain"]
        res = {}
        for var in VARS:
            rows = frontend(var, sim, drift, p, P, alloc)
            s = summarise(rows)
            res[var] = {"chain_RWL": chain, "frontend_RWL": r3(3 * s["RWL_per_rail"]),
                        "total_RWL": r3(chain + 3 * s["RWL_per_rail"]),
                        "frontend_FIT_thresholds": r3(3 * s["FIT_thresholds_per_rail"]),
                        "FIT_whole_rail_masks": r3(3 * s["FIT_whole_rail_per_rail"]),
                        "per_threshold_FIT": {t: r3(3 * v) for t, v in s["per_threshold"].items()}}
            if cname == "base" or cname.startswith("allocation B"):
                res[var]["rows"] = [dict(r, fit=round(r["fit"], 4)) for r in rows]
        out["cases"][cname] = res
    # FMEA row table (S / O / D / RPN), per rail.  Die and passive rows from allocation A (base), pin rows from B.
    out["fmea_rows"] = fmea_rows(out)
    # proof-test coverage of the dormant front-end FIT (base case, allocation B so pin faults are present)
    out["proof_tests"] = proof_tests(out["cases"]["allocation B (die FMD on die FIT; package FIT on pins)"])
    # invariants
    for var in ("V0", "V1", "V2", "V2+F2"):
        if any(v["silent_mask_vs_H"] for v in drift[var].values()):
            bad.append(f"{var}: a shared-reference drift silently masks a threshold against H")
    json.dump(out, open(os.path.join(RES, "fmea_b_metric.json"), "w"), indent=1, sort_keys=True)
    report(out)
    return bad


S_OF = lambda n: 7 if n >= 4 else (5 if n >= 1 else 3)


def O_of(fit):
    return 6 if fit > 15 else 5 if fit >= 5 else 4 if fit >= 2 else 3 if fit >= 0.5 else 2 if fit >= 0.1 else 1


ROWDEF = {
    "C2": "comparator / supervisor output cannot pull 'good' low (die Hi-Z or saturated high, output pin open)",
    "C2b": "comparator out of specification (one threshold moves; V2 includes the internal reference)",
    "C3": "output stuck low / false trip",
    "C4": "reference: TL431 open / short / drift, rref and R79 / R80 (V0, V1); V2 has no separate part",
    "C5": "divider resistor open or drift (8 per rail)",
    "C6": "1 nF tap capacitor short",
    "N1": "supply pin open (LM339B VCC / GND; TPS3701 VDD / GND)",
    "N2": "output pin shorted to the adjacent supply pin: good tied to P (to v5 in V2+F2+v5)",
    "N3": "TPS3701 INB shorted to the adjacent VDD pin (17 V on a 7 V input when VDD = P; 5 V when VDD = v5)",
    "N4": "other pin opens / adjacent shorts (inputs)",
    "N7": "100 nF decoupler short (cmonitor p-n in all; C176 in V2: p-n, or v5-n in V2+F2+v5)",
}


def fmea_rows(out):
    A = out["cases"]["base"]
    B = out["cases"]["allocation B (die FMD on die FIT; package FIT on pins)"]
    tab = {}
    for var in VARS:
        rows = {}
        for src_rows, use in ((A[var]["rows"], ("C2", "C2b", "C3", "C4", "C5", "C6", "N7")),
                              (B[var]["rows"], ("N1", "N2", "N3", "N4"))):
            for r in src_rows:
                g = r["row"]
                if g not in use:
                    continue
                if g == "C2" and r["kind"] == "pin_open" and src_rows is A[var]["rows"]:
                    continue
                e = rows.setdefault(g, {"fit_all": 0.0, "fit_dormant": 0.0, "max_thresholds": 0, "masked_FIT_thr": 0.0,
                                        "statuses": set()})
                e["fit_all"] += r["fit"]
                if r["k"]:
                    e["fit_dormant"] += r["fit"]
                    e["max_thresholds"] = max(e["max_thresholds"], sum(1 for v in r["k"].values() if v > 0) or len(r["k"]))
                e["masked_FIT_thr"] += r["fit"] * sum(r["k"].values())
                e["statuses"].add(r["status"].split(" (")[0].split(":")[0])
        for g, e in rows.items():
            dorm = e["fit_dormant"] > 0
            S = S_OF(e["max_thresholds"]) if dorm else 3
            O = O_of(e["fit_dormant"] if dorm else e["fit_all"])
            D = 9 if dorm else 1
            st = "announced" if not dorm else ("dormant" if e["fit_dormant"] >= e["fit_all"] - 1e-12 else "mixed")
            rows[g] = {"what": ROWDEF.get(g, g), "FIT_per_rail_all": r3(e["fit_all"]), "FIT_per_rail_dormant": r3(e["fit_dormant"]),
                       "max_thresholds_masked": e["max_thresholds"], "masked_FIT_thresholds": r3(e["masked_FIT_thr"]),
                       "S": S, "O": O, "D": D, "RPN": S * O * D, "status": st}
        tab[var] = dict(sorted(rows.items()))
    return tab


def proof_tests(case):
    """Share of the dormant front-end masking (FIT x thresholds, allocation B) that each test would reveal.
    B8 (force MON_GOOD_HA / HB low) acts downstream of every monitor: it reveals none of these.  A per-tap forcing test
    (drive each tap past its threshold through a pad) reveals faults in the comparator, its pins and the tap caps,
    not divider opens or drift.  An LS 'raise the rail' test (ground the TPS7A47 3P2V pin: 17.0 -> 20.2 V) reveals
    every LS span-OV mask, dividers included, and nothing else."""
    out = {}
    for var in VARS:
        rows = case[var]["rows"]
        tot = sum(r["fit"] * sum(r["k"].values()) for r in rows)
        tap = sum(r["fit"] * sum(r["k"].values()) for r in rows
                  if r["kind"] in ("die", "pin_open", "pin_short", "cap_short"))
        span_ov = sum(r["fit"] * r["k"].get("span OV", 0.0) for r in rows)
        out[var] = {"dormant_FIT_thresholds_per_rail": r3(tot), "B8_veto_test": 0.0,
                    "per_tap_forcing_test": r3(tap / tot if tot else 0.0),
                    "LS_rail_raise_test_share_of_LS_rail": r3(span_ov / tot if tot else 0.0)}
    return out


def report(out):
    L = ["# Candidate-B FMEA metric (generated by scripts/fmea_metric.py -> candidate_b.py)", "",
         "RWL in FIT x rails (c24 section 4). Front-end modes count thresholds/4 rail-equivalents, 3 rails. "
         "Chain = c24 P2H heartbeat rows, identical in V0 / V1 / V2.", "",
         "| case | " + " | ".join(f"{v} total" for v in VARS) + " | " + " | ".join(f"{v} front end" for v in VARS) + " | chain (all) |",
         "|---|" + "---:|" * (2 * len(VARS) + 1)]
    for c, r in out["cases"].items():
        L.append(f"| {c} | " + " | ".join(str(r[v]['total_RWL']) for v in VARS) + " | "
                 + " | ".join(str(r[v]['frontend_RWL']) for v in VARS) + f" | {r['V0']['chain_RWL']} |")
    L += ["", "## Per-threshold masking FIT (3 rails) and whole-rail front-end masks", "",
          "| case | variant | neg UV (shoot-through) | neg OV | span UV | span OV (gate overstress) | whole-rail masks |", "|---|---|---:|---:|---:|---:|---:|"]
    for c in ("base", "allocation B (die FMD on die FIT; package FIT on pins)", "worst (k_u 1, k_o 0.5, passives x5, allocation B)"):
        for var in VARS:
            pt = out["cases"][c][var]["per_threshold_FIT"]
            L.append(f"| {c} | {var} | {pt['neg UV']} | {pt['neg OV']} | {pt['span UV']} | {pt['span OV']} | "
                     f"{out['cases'][c][var]['FIT_whole_rail_masks']} |")
    L += ["", "## FMEA rows (per rail): S / O / D / RPN by the c24 section 3 scales", "",
          "| row | what | " + " | ".join(f"{v} FIT dormant / all | {v} S-O-D RPN" for v in VARS) + " |",
          "|---|---|" + "---|---|" * len(VARS)]
    keys = sorted(set().union(*(out["fmea_rows"][v].keys() for v in VARS)))
    for g in keys:
        cells = []
        for var in VARS:
            e = out["fmea_rows"][var].get(g)
            cells += (["-", "-"] if not e else [f"{e['FIT_per_rail_dormant']} / {e['FIT_per_rail_all']}",
                                                f"{e['S']}-{e['O']}-{e['D']} {e['RPN']} ({e['status']})"])
        L.append(f"| {g} | {ROWDEF.get(g, g)} | " + " | ".join(cells) + " |")
    L += ["", "## Proof-test coverage of dormant front-end masking (allocation B)", "",
          "| variant | dormant FIT x thresholds / rail | B8 veto test | per-tap forcing test | LS rail-raise test (LS rail) |", "|---|---:|---:|---:|---:|"]
    for var, e in out["proof_tests"].items():
        L.append(f"| {var} | {e['dormant_FIT_thresholds_per_rail']} | {e['B8_veto_test']} | {e['per_tap_forcing_test']} | "
                 f"{e['LS_rail_raise_test_share_of_LS_rail']} |")
    for c in ("base", "allocation B (die FMD on die FIT; package FIT on pins)"):
        for var in VARS:
            L += ["", f"## Rows, {c}, {var}", "", "| row | mode | FIT | masked (k) | status |", "|---|---|---:|---|---|"]
            for r in out["cases"][c][var]["rows"]:
                L.append(f"| {r['row']} | {r['mode']} | {r['fit']} | {', '.join(f'{t} {v:g}' for t, v in r['k'].items()) or '-'} | {r['status']} |")
    open(os.path.join(RES, "fmea_b_metric.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:60]))
