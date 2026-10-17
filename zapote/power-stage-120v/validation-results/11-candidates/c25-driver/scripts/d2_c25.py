#!/usr/bin/env python3
"""Candidate 25 (UCC21550 -> Infineon 2EDR8259H/X): D2 switching transient with the new driver.

Local ngspice only (the remote FEM box is needed only to *extract* inductance matrices, D1;
this study reuses the committed native-21 matrices, so nothing remote is needed).

Deck = the as-built native-21 deck used by round17/d2 `f6_legs.py --diode pmeg --vneg -1.6`
(D-13 F6.cir + D-14 itl4 + Nexperia PMEG6030EP + -1.6 V off level), checked byte-for-byte
against the committed `results/f6-vneg-m1p6-legA21-s9b2/F6.cir` (sha256 55a2058f...).
Matrices: legA21-h0-s9b2-n21 / legB21-h0-s9b2-n21 (latest native-21 pair in round17/d2).

The driver is the deck's output-resistance approximation; the variants only change ROH, ROL
and the series gate resistor RG through params.inc (the deck defaults are overridden there).
Two dv/dt probes are appended (B-sources with ddt(), measurement only) so the switch-node
edge rate can be compared between drivers.

    python3 -B d2_c25.py repro            # reproduce two committed as-built cases
    python3 -B d2_c25.py edge  [--workers 8]   # driver variants at 443 ns: dv/dt + screens
    python3 -B d2_c25.py dtband [--workers 8]  # 2EDR (Rg 8.2) over a widened dead-time band

Writes ../results/<mode>/{results.json,summary.json,summary.md}. Run directories are deleted
after parsing (disk budget); aborted runs keep their run.log.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
C25 = HERE.parent
POWER = C25.parents[2]
D2 = POWER / "validation-results/01-switching-parasitics/round17/d2"
D13 = D2.parent / "delegation" / "out-D13"
sys.path.insert(0, str(D2))
import run_d2  # noqa: E402  (read-only reuse: matrix reader, ngspice runner)

PMEG = run_d2.KIT / "models" / "vendor" / "PMEG6030EP.txt"
REF_DECK = D2 / "results" / "f6-vneg-m1p6-legA21-s9b2" / "F6.cir"
REF_SHA = "55a2058f05c366b046ea1d1b2e8b8d0101f81ffeb5a0ed23cde5c8348e3fc342"
MATRICES = {"A": D2 / "legA21-h0-s9b2-n21.matrix.txt", "B": D2 / "legB21-h0-s9b2-n21.matrix.txt"}
SCREEN = {r["temp_C"]: r["model_screen_V"] for r in json.loads((D13 / "results-threshold.json").read_text())}

# Driver variants: (ROH, ROL, RG). Sources: TI SLUSE89C 5.8 p.10 (ROH 5, ROL 0.55 typ) and 7.3.4
# (pull-up NMOS boost 1.47 ohm // 5 = 1.136 ohm, D-2's sensitivity); Infineon 2EDR8259H Rev 1.7
# Table 20 p.15 (Ron_SRC 0.6/0.95/1.5, Ron_SNK 0.24/0.39/0.62 ohm, min/typ/max).
VARIANTS = {
    "ucc_asbuilt": (5.0, 0.55, 3.9),
    "ucc_boost": (1.136012, 0.55, 3.9),
    "edr_rg3p9": (0.95, 0.39, 3.9),
    "edr_rg8p2": (0.95, 0.39, 8.2),
    "edr_rg8p2_strong": (0.6, 0.24, 8.2),
    "edr_rg8p2_weak": (1.5, 0.62, 8.2),
}

PROBES = """
* ---- c25 dv/dt probes (measurement only; V/ns)
Bdvsw dvsw 0 V={ddt(v(sw))*1e-9}
Bdvls dvls 0 V={ddt(v(xql.dd)-v(xql.s))*1e-9}
Bdvhs dvhs 0 V={ddt(v(xqh.dd)-v(xqh.s))*1e-9}
.meas tran dvsw_max MAX v(dvsw) from={T1} to={T1+DT+0.75u}
.meas tran dvsw_min MIN v(dvsw) from={T1} to={T1+DT+0.75u}
.meas tran dvls_max MAX v(dvls) from={T1} to={T1+DT+0.75u}
.meas tran dvls_min MIN v(dvls) from={T1} to={T1+DT+0.75u}
.meas tran dvhs_max MAX v(dvhs) from={T1} to={T1+DT+0.75u}
.meas tran dvhs_min MIN v(dvhs) from={T1} to={T1+DT+0.75u}
* 20-80 % switch-node edge time (board node sw vs leg return), first crossing after T1
.meas tran tr2080 TRIG v(sw) VAL={0.2*VBUS} RISE=1 TD={T1} TARG v(sw) VAL={0.8*VBUS} RISE=1 TD={T1}
.meas tran tf8020 TRIG v(sw) VAL={0.8*VBUS} FALL=1 TD={T1} TARG v(sw) VAL={0.2*VBUS} FALL=1 TD={T1}
.meas tran tr1090 TRIG v(sw) VAL={0.1*VBUS} RISE=1 TD={T1} TARG v(sw) VAL={0.9*VBUS} RISE=1 TD={T1}
.meas tran tf9010 TRIG v(sw) VAL={0.9*VBUS} FALL=1 TD={T1} TARG v(sw) VAL={0.1*VBUS} FALL=1 TD={T1}
"""


def asbuilt_deck() -> str:
    """Rebuild f6_legs.py's deck (--diode pmeg --vneg -1.6) and check it against the committed one."""
    deck = (D13 / "decks" / "F6.cir").read_text()
    deck = deck.replace(".include params.inc", ".include params.inc\n.options itl4=100000", 1)
    old = ".model D6D D(Is=1u N=1 Rs=0.05 Cjo=20p Tt=0)\nDoffl gdl3 offl D6D"
    assert old in deck and "Doffh gdh3 offh D6D" in deck
    deck = deck.replace(old, f".include {PMEG}\nXDoffl gdl3 offl PMEG6030EP")
    deck = deck.replace("Doffh gdh3 offh D6D", "XDoffh gdh3 offh PMEG6030EP")
    assert deck.count("-(-2))") == 2
    deck = deck.replace("-(-2))", "-(-1.6))")
    sha = hashlib.sha256(deck.encode()).hexdigest()
    if sha != REF_SHA or deck != REF_DECK.read_text():
        raise SystemExit(f"as-built deck mismatch: {sha}")
    return deck


def write_decks(out: Path) -> dict[str, Path]:
    base = asbuilt_deck()
    probed = base.replace("\n.end", "\n" + PROBES + ".end")
    assert probed != base
    out.mkdir(parents=True, exist_ok=True)
    (out / "F6.cir").write_text(base)
    (out / "F6probe.cir").write_text(probed)
    return {"plain": out / "F6.cir", "probe": out / "F6probe.cir"}


def one(job, decks, out: Path, deck_key="probe"):
    variant, leg, temp, (case, vbus, il, dt), d, esl = job
    roh, rol, rg = VARIANTS[variant]
    name = f"{variant}_{leg}_T{temp}_{case}_v{vbus}_i{il}_d{d}_dt{dt}_esl{esl}"
    p = run_d2.matrix_params(run_d2.read_L(str(MATRICES[leg])))
    p.update(TJ=str(temp), VBUS=str(vbus), IL=str(il), DIR=str(d), DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n",
             TRMAX="0.2n")
    if variant != "ucc_asbuilt" or deck_key == "probe":
        p.update(ROH=str(roh), ROL=str(rol), RG=str(rg))
    keep = out / "runs" / name
    r = run_d2.run(decks[deck_key], p, keep=keep)
    m = r["meas"]
    off, inc = ("ls", "hs") if d == 0 else ("hs", "ls")
    need = ["vds_ls_die_pk", "vds_hs_die_pk", f"vgs_{off}_off_max", f"vds_{inc}_at_on"] + \
           [f"vgs_{s}_die_{e}" for s in ("ls", "hs") for e in ("min", "max")]
    row = {"variant": variant, "leg": leg, "temp_C": temp, "case": case, "vbus": vbus, "il": il, "dir": d,
           "dt_ns": dt, "esl_nH": esl}
    # the opposite-direction edge measures (tf8020 on a rising case, ...) fail by design; ignore those
    failed = [f for f in r["failed"] if not any(t in f for t in ("tr2080", "tf8020", "tr1090", "tf9010"))]
    if r["aborted"] or failed or any(k not in m for k in need):
        row["status"] = "indeterminate"
        (keep / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
        return row
    shutil.rmtree(keep, ignore_errors=True)
    vds = max(m["vds_ls_die_pk"], m["vds_hs_die_pk"])
    offv = m[f"vgs_{off}_off_max"]
    vgs = max(abs(m[f"vgs_{s}_die_{e}"]) for s in ("ls", "hs") for e in ("min", "max"))
    lim = 585 if case == "S2" else 520
    row.update(status="complete", vds_pk=vds, off_V=offv, vgs_abs=vgs, incoming_V=m[f"vds_{inc}_at_on"],
               vgs_off_at_partner=m.get(f"vgs_{off}_at_partner"),
               pass_vds=vds <= lim, pass_vgs=vgs <= 30, pass_3V=offv < 3.0, pass_1p9=offv < 1.9,
               pass_model=offv < SCREEN[temp], zvs=m[f"vds_{inc}_at_on"] <= 0.05 * vbus)
    if "dvsw_max" in m:
        row.update(dvsw_abs=max(abs(m["dvsw_max"]), abs(m["dvsw_min"])),
                   dvdie_abs=max(abs(m[k]) for k in ("dvls_max", "dvls_min", "dvhs_max", "dvhs_min")))
    # edge rate: DIR=0 is a rising switch node (HS turns on), DIR=1 falling (LS turns on)
    t2080 = m.get("tr2080") if d == 0 else m.get("tf8020")
    t1090 = m.get("tr1090") if d == 0 else m.get("tf9010")
    if t2080 and t2080 > 0:
        row["slew2080_Vns"] = 0.6 * vbus / (t2080 * 1e9)
    if t1090 and t1090 > 0:
        row["slew1090_Vns"] = 0.8 * vbus / (t1090 * 1e9)
    row["pass"] = row["pass_vds"] and row["pass_vgs"] and row["pass_3V"] and row["pass_model"] and \
        (row["zvs"] if case == "S1" else True)
    row["pass_hot"] = row["pass"] and row["pass_1p9"]
    return row


def pts(case_names, dts):
    out = []
    for dt in dts:
        if "S1" in case_names:
            out += [("S1", v, 37, dt) for v in (198, 280)]
        if "S2" in case_names:
            out += [("S2", 280, 71, dt)]
        if "S4" in case_names:
            out += [("S4", v, -20, dt) for v in (170, 198, 280)]
        if "S5" in case_names:
            out += [("S5", v, 0, dt) for v in (170, 198, 280)]
    return out


def summarize(rows, keys, out: Path, title: str):
    groups = {}
    for r in rows:
        k = tuple(r[x] for x in keys)
        groups.setdefault(k, []).append(r)
    lines = [f"# {title}", "", "| " + " | ".join(keys) + " | complete | pass | pass incl. 1.9 V | max off-gate V | "
             "max die VDS V | ZVS (S1) | max inst. dv/dt sw V/ns | max inst. dv/dt die V/ns | max 20-80 % slew V/ns | max 10-90 % slew V/ns |",
             "|" + " --- |" * (len(keys) + 10)]
    summ = {}
    for k in sorted(groups, key=lambda t: tuple(str(x) for x in t)):
        g = groups[k]
        c = [r for r in g if r["status"] == "complete"]
        s1 = [r for r in c if r["case"] == "S1"]
        s = {"cases": len(g), "complete": len(c), "pass": sum(r["pass"] for r in c),
             "pass_hot": sum(r["pass_hot"] for r in c),
             "max_off_V": round(max((r["off_V"] for r in c), default=float("nan")), 3),
             "max_vds_V": round(max((r["vds_pk"] for r in c), default=float("nan")), 1),
             "zvs": f"{sum(r['zvs'] for r in s1)}/{len(s1)}" if s1 else "-",
             "max_dvsw": round(max((r.get("dvsw_abs", float("nan")) for r in c), default=float("nan")), 1),
             "max_dvdie": round(max((r.get("dvdie_abs", float("nan")) for r in c), default=float("nan")), 1),
             "max_slew2080": round(max((r.get("slew2080_Vns", 0.0) for r in c), default=float("nan")), 1),
             "max_slew1090": round(max((r.get("slew1090_Vns", 0.0) for r in c), default=float("nan")), 1)}
        summ["|".join(map(str, k))] = s
        lines.append("| " + " | ".join(map(str, k)) + f" | {s['complete']}/{s['cases']} | {s['pass']} | {s['pass_hot']} | "
                     f"{s['max_off_V']} | {s['max_vds_V']} | {s['zvs']} | {s['max_dvsw']} | {s['max_dvdie']} | "
                     f"{s['max_slew2080']} | {s['max_slew1090']} |")
    (out / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def identity(out: Path, extra: dict):
    files = [*MATRICES.values(), out / "F6.cir", out / "F6probe.cir", Path(__file__), D2 / "run_d2.py", PMEG,
             run_d2.KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"]
    return {"files": {str(p.relative_to(POWER)) if p.is_relative_to(POWER) else str(p):
                      hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "variants": VARIANTS, "model_screen_V": SCREEN, **extra}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["repro", "edge", "dtband"])
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    out = C25 / "results" / a.mode
    decks = write_decks(out)
    if a.mode == "repro":
        # committed: f6-vneg-m1p6-legA21-s9b2 A_T100_S1_v198 d0 dt443 esl10 and an S4 row
        ref = json.loads((D2 / "results/f6-vneg-m1p6-legA21-s9b2/results.json").read_text())
        want = [r for r in ref if (r["temp_C"], r["case"], r["vbus"], r["dir"], r["dt_ns"], r["esl_nH"]) in
                {(100, "S1", 198, 0, 443, 10), (27, "S4", 170, 0, 391, 1.06)}]
        rows = []
        for w in want:
            job = ("ucc_asbuilt", "A", w["temp_C"], (w["case"], w["vbus"], w["il"], w["dt_ns"]), w["dir"], w["esl_nH"])
            for key in ("plain", "probe"):
                r = one(job, decks, out / key, key)
                rows.append({"deck": key, "committed_off_V": w["off_V"], "committed_vds_pk": w["vds_pk"], **r})
        (out / "results.json").write_text(json.dumps(rows, indent=1) + "\n")
        for r in rows:
            print(r["deck"], r["case"], "off", r["off_V"], "vs", r["committed_off_V"], "vds", r["vds_pk"], "vs",
                  r["committed_vds_pk"], "dvsw", r.get("dvsw_abs"), "slew2080", r.get("slew2080_Vns"),
                  "slew1090", r.get("slew1090_Vns"))
        return
    if a.mode == "edge":
        jobs = list(itertools.product(VARIANTS, "AB", (27, 150), pts(("S1", "S2", "S4", "S5"), (443,)), (0, 1),
                                      (1.06, 10)))
        keys = ("variant", "case")
        extra = {"mode": "edge", "dt_ns": 443, "temps": [27, 150]}
    else:
        dts = (340, 364, 391, 408, 443, 500, 530, 562, 600)
        jobs = list(itertools.product(("edr_rg8p2",), "AB", (27, 100, 150), pts(("S1", "S2", "S4", "S5"), dts),
                                      (0, 1), (1.06, 10)))
        # weak/strong output corners at the band edges, 150 C (weakest off-hold) and 27 C
        jobs += list(itertools.product(("edr_rg8p2_weak", "edr_rg8p2_strong"), "AB", (27, 150),
                                       pts(("S1", "S2", "S4", "S5"), (340, 364, 562, 600)), (0, 1), (1.06, 10)))
        keys = ("variant", "case", "dt_ns")
        extra = {"mode": "dtband", "dts": dts}
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(lambda j: one(j, decks, out), jobs))
    (out / "results.json").write_text(json.dumps(rows, indent=1) + "\n")
    (out / "identity.json").write_text(json.dumps(identity(out, extra), indent=1) + "\n")
    summarize(rows, keys, out, f"c25 D2 {a.mode}")


if __name__ == "__main__":
    main()
