#!/usr/bin/env python3
"""S6-CMTI: common-mode dv/dt that each isolation barrier actually sees during a hard switch-node edge.

Rerun:  python3 -I cm_barrier.py            (needs ngspice on PATH; writes only ../results/ and a temp dir)

Topology: the committed round-3 conducted-EMI transfer deck
  validation-results/07-conducted-emi/round3/scripts/emi_topology.cir  (read, sha256 recorded)
turned into a transient deck. Every element of that deck is kept; this script only
  * replaces the AC unit sources by one hard edge on leg A (SW_A - HV_RET ramp at the S4 slew; SW_B static),
    i.e. no opposed-leg cancellation (worst case: S4 is a single-leg event);
  * re-values the FET tab capacitance for the as-decided 2.0 mm AlN tile stack (DECISIONS 2026-10-08 M11)
    and keeps round 3's 42 pF silicone-pad value as the high sensitivity;
  * adds the paths round 3 left out that couple SW_A to PE/SELV (T1 CST3015 interwinding C, unspecified)
    and optional extras (Y-cap lead ESL, a separately bonded heatsink, HOT-SELV board/isolator capacitance);
  * runs the rectifier in both states: conducting pair (mains crest, round 3) and all four diodes blocking
    (idle bus held at peak / restart: the case where the Y capacitors reach HV_RET only through junction C).

Barrier reference nets (elec/src, frozen netlist): SELV_GND = PE on this board (r_fe 0 ohm, power_stage_120v.ato:696);
  U9 / U32 / U4: HOT side on HV_RET / LEG_RET / OCP_KELVIN_P (bus return, 1 mOhm shunt apart) -> v(bus_n) - v(pe)
  U36 VOL628A:   L_FILT / N_FILT (line side)                                              -> v(line_f|neut_f) - v(pe)
  U43 / U44:     N_HA = SW_A / N_HB = SW_B vs N_LS                                         -> the switch-node edge itself
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
R3 = PS / "validation-results/07-conducted-emi/round3/scripts/emi_topology.cir"

V_EDGE = 287.62          # V, bus at the s47 OVP band top (ledger 'Barrier peak' stress) = S4 swing
EPS0 = 8.854e-12

# ---- FET tab to PE-bonded spreader bar through the decided stack (DECISIONS.md 2026-10-08, M11):
# 2.032 mm lapped AlN plate (Valley AlN-110 / Almath), Electrolube HTCP20S compound both faces.
# TO-247 exposed drain-tab metal 200-300 mm^2 (body 15.9 x 20.96 mm less the moulded rim and hole); AlN eps_r 8.6-8.9.
TAB_AREA_MM2 = (200.0, 300.0)
ALN_EPS = 8.9
ALN_T = 2.032e-3
C_TAB_ALN = tuple(EPS0 * ALN_EPS * a * 1e-6 / ALN_T for a in TAB_AREA_MM2)   # ~7.8 / 11.6 pF
C_TAB_NOM = 12e-12       # AlN high end + ~0.4 pF fringe, rounded up
C_TAB_HI = 42e-12        # round-3 silicone-pad scenario (SIL-PAD 400/K10 32-52 pF): the stack it replaced


def r3_deck() -> str:
    return R3.read_text()


def transient_deck(p: dict, slew_v_per_ns: float, workdir: Path, step: str = "5p") -> str:
    """Round-3 deck -> transient single-edge deck with the parameter set p."""
    d = r3_deck()
    # strip analysis / save lines and the AC leg sources; keep every passive element
    d = re.sub(r"(?m)^\.ac .*$", "", d)
    d = re.sub(r"(?m)^\.save .*$", "", d)
    d = re.sub(r"(?m)^\.end\s*$", "", d)
    assert d.count("VlegA sw_a bus_n DC 0 AC {EXC_A}") == 1 and d.count("VlegB sw_b bus_n DC 0 AC {EXC_B}") == 1
    tr = V_EDGE / slew_v_per_ns * 1e-9
    d = d.replace("VlegA sw_a bus_n DC 0 AC {EXC_A}",
                  f"VlegA sw_a bus_n PWL(0 0 2n 0 {2e-9 + tr:.6e} {V_EDGE} 400n {V_EDGE})")
    d = d.replace("VlegB sw_b bus_n DC 0 AC {EXC_B}", "VlegB sw_b bus_n DC 0")
    # parameter overrides on the round-3 .param lines
    for key in ("CTABA", "CTABB", "CTABH", "CCOILA", "CCOILB", "CBRJ"):
        if key in p:
            d, n = re.subn(rf"(?m)^(\.param .*\b{key}=)([^\s]+)", lambda m: m[1] + f"{p[key]:.6e}", d)
            assert n == 1, key
    # rectifier state: 'cond' keeps round 3's conducting crest pair; 'block' removes the two 0.05 ohm diode paths
    if p["rect"] == "block":
        for ln in ("RbrLH line_f bus_p 0.05", "RbrNL neut_f bus_n 0.05"):
            assert d.count(ln) == 1, ln
            d = d.replace(ln, "* (blocking) " + ln)
        # DC paths so the operating point exists (1 Gohm leakage, no effect at ns)
        d += "Rleak1 line_f bus_p 1G\nRleak2 neut_f bus_n 1G\n"
    # Y-capacitor lead + trace ESL (round 3 has none)
    if p.get("LY", 0) > 0:
        for a, node in (("CyL line_f pe {CY}", "line_f"), ("CyN neut_f pe {CY}", "neut_f")):
            assert d.count(a) == 1, a
            tag = "yl" if node == "line_f" else "yn"
            d = d.replace(a, f"Ly{tag} {node} {tag}_m {p['LY']:.6e}\nC{tag} {tag}_m pe {{CY}}")
    # heatsink bonded on its own wire (spreader-bar ear -> chassis) instead of straight onto the board PE node
    if p.get("LHS", 0) > 0:
        for a in ("CtabQ2 bus_p pe {CTABH}", "CtabQ5 bus_p pe {CTABH}", "VtabSenseA tab_a pe 0", "VtabSenseB tab_b pe 0"):
            assert d.count(a) == 1, a
            d = d.replace(a, a.replace(" pe ", " hs "))
        d += f"Lhs hs 0 {p['LHS']:.6e}\nRhs hs 0 1k\n"
    # T1 CST3015 primary (SW_A) to SELV secondary: interwinding C, not specified by Coilcraft
    if p.get("CWW", 0) > 0:
        d += f"Cww sw_a pe {p['CWW']:.6e}\n"
    # HOT-to-SELV capacitance that holds HV_RET to PE (board planes across the 8 mm floor, isolator CIO)
    if p.get("CHS", 0) > 0:
        d += f"Chot bus_n pe {p['CHS']:.6e}\n"
    # fix (b) candidate: a local Y1 capacitor across the HOT->SELV floor at the U9 / U32 / U4 cluster, with its ESL
    if p.get("CYLOC", 0) > 0:
        d += f"Lyloc bus_n yloc_m {p.get('LYLOC', 3e-9):.6e}\nCyloc yloc_m pe {p['CYLOC']:.6e}\n"
    out = workdir / "w.txt"
    d += ("\n.options method=gear reltol=1e-4 abstol=1e-9 vntol=1e-6\n"
          f".tran {step} 60n 0 {step}\n"
          ".control\nrun\n"
          f"wrdata {out} v(sw_a)-v(bus_n) v(bus_n)-v(pe) v(bus_p)-v(pe) v(line_f)-v(pe) v(neut_f)-v(pe)\n"
          "quit\n.endc\n.end\n")
    return d


def run_once(p: dict, slew: float, keep: Path | None = None, step: str = "5p") -> dict:
    with tempfile.TemporaryDirectory(prefix="s6cm-") as td:
        w = Path(td)
        deck = transient_deck(p, slew, w, step)
        (w / "d.cir").write_text(deck)
        (w / ".spiceinit").write_text("set ngbehavior=psa\n")
        pr = subprocess.run(["ngspice", "-b", "d.cir"], cwd=w, capture_output=True, text=True, timeout=600)
        if keep:
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copy(w / "d.cir", keep / "deck.cir")
        a = np.loadtxt(w / "w.txt")
    t = a[:, 0]
    cols = {"sw": a[:, 1], "bus_n": a[:, 3], "bus_p": a[:, 5], "line_f": a[:, 7], "neut_f": a[:, 9]}
    tu = np.arange(t[0], t[-1], 5e-12)          # uniform 5 ps grid
    r = {}
    for k, v in cols.items():
        vu = np.interp(tu, t, v)
        dv = np.gradient(vu, tu) * 1e-9                       # V/ns, instantaneous
        n1 = int(round(1e-9 / 5e-12))
        chord = (vu[n1:] - vu[:-n1]) / 1.0                    # V per 1 ns window
        r[k] = dict(dvdt_inst_max=float(np.max(np.abs(dv))), dvdt_1ns_max=float(np.max(np.abs(chord))),
                    v_pk=float(np.max(np.abs(vu))), v_end=float(vu[-1]))
    # validity: a passive network driven by a 287.6 V edge cannot hold a node at > 3x the edge; ngspice occasionally
    # diverges (one 90 V/ns blocking case did, 1e11 V). Such a run is rejected, never reported.
    r["ok"] = pr.returncode == 0 and all(r[k]["v_pk"] < 3 * V_EDGE for k in cols)
    r["step"] = step
    return r


def run(p: dict, slew: float, keep: Path | None = None) -> dict:
    r = run_once(p, slew, keep)
    if not r["ok"]:
        r = run_once(p, slew, keep, step="2p")       # retry at a finer fixed step
    if not r["ok"]:
        raise SystemExit(f"numerical failure at 5 ps and 2 ps: {p} {slew}")
    return r


def cases():
    base = dict(CTABA=C_TAB_NOM, CTABB=C_TAB_NOM, CTABH=C_TAB_NOM, CCOILA=12.5e-12, CCOILB=12.5e-12,
                CBRJ=85e-12, rect="cond", LY=0.0, LHS=0.0, CWW=0.0, CHS=0.0)
    yield "nominal_cond", dict(base)
    yield "nominal_block", dict(base, rect="block")
    # one-at-a-time sensitivities on the blocking state (the worse state)
    yield "block_tab42", dict(base, rect="block", CTABA=C_TAB_HI, CTABB=C_TAB_HI, CTABH=C_TAB_HI)
    yield "block_tabA42_only", dict(base, rect="block", CTABA=C_TAB_HI)
    yield "block_coil100_allA", dict(base, rect="block", CCOILA=100e-12, CCOILB=0.0)
    yield "block_cbrj20", dict(base, rect="block", CBRJ=20e-12)
    yield "block_cww20", dict(base, rect="block", CWW=20e-12)
    yield "block_ly20", dict(base, rect="block", LY=20e-9)
    yield "block_lhs150", dict(base, rect="block", LHS=150e-9)
    yield "block_chs5", dict(base, rect="block", CHS=5e-12)
    yield "cond_ly20_lhs150", dict(base, LY=20e-9, LHS=150e-9)
    # stacked pessimistic corner: every SW_A->PE coupling at its high value, every HV_RET->PE holding path at its low
    yield "block_STACKED_WORST", dict(base, rect="block", CTABA=C_TAB_HI, CTABB=C_TAB_NOM, CTABH=C_TAB_NOM,
                                      CCOILA=100e-12, CCOILB=0.0, CBRJ=20e-12, CWW=20e-12, LY=20e-9, LHS=150e-9)
    yield "cond_STACKED_WORST", dict(base, CTABA=C_TAB_HI, CTABB=C_TAB_NOM, CTABH=C_TAB_NOM,
                                     CCOILA=100e-12, CCOILB=0.0, CBRJ=20e-12, CWW=20e-12, LY=20e-9, LHS=150e-9)
    # the same stacks on the as-decided AlN stack (every tab 12 pF): only the assumed coil / CT / inductance terms high
    stk = dict(CCOILA=100e-12, CCOILB=0.0, CBRJ=20e-12, CWW=20e-12, LY=20e-9, LHS=150e-9)
    yield "block_STACKED_ALN", dict(base, rect="block", **stk)
    yield "cond_STACKED_ALN", dict(base, **stk)
    # fix (b): 1 nF Y1 (3 nH mounted) from HV_RET to SELV_GND at the isolator cluster, on the two stacked corners
    for nm, extra in (("block_STACKED_WORST", dict(rect="block", CTABA=C_TAB_HI, **stk)),
                      ("cond_STACKED_WORST", dict(CTABA=C_TAB_HI, **stk)),
                      ("block_STACKED_ALN", dict(rect="block", **stk)), ("nominal_block", dict(rect="block"))):
        for cy in (1e-9, 2.2e-9):
            yield f"{nm}+Yloc{cy*1e9:g}n", dict(base, **extra, CYLOC=cy, LYLOC=3e-9)


def main():
    import sys
    RES.mkdir(parents=True, exist_ok=True)
    slews = [float(x) for x in sys.argv[1:]] or [49.7, 68.16, 89.997, 106.21]
    rows = []
    for (name, p), s in itertools.product(list(cases()), slews):
        r = run(p, s, keep=RES / "cm_decks" / f"{name}_{s:g}" if s == slews[0] else None)
        row = dict(case=name, slew_sw=s, rect=p["rect"], ok=r["ok"], params={k: v for k, v in p.items()})
        for k in ("sw", "bus_n", "line_f", "neut_f", "bus_p"):
            row[k] = r[k]
        row["ratio_bus_n_1ns"] = r["bus_n"]["dvdt_1ns_max"] / s
        rows.append(row)
        print(f"{name:22s} sw {s:6.1f} V/ns  -> HV_RET-PE inst {r['bus_n']['dvdt_inst_max']:6.2f} / 1ns {r['bus_n']['dvdt_1ns_max']:6.2f} V/ns,"
              f" pk {r['bus_n']['v_pk']:6.1f} V | L_FILT-PE 1ns {r['line_f']['dvdt_1ns_max']:6.2f} N_FILT-PE 1ns {r['neut_f']['dvdt_1ns_max']:6.2f}"
              f" | sw check inst {r['sw']['dvdt_inst_max']:6.1f} step {r['step']}")
    out = dict(source_deck=str(R3), source_sha256=hashlib.sha256(R3.read_bytes()).hexdigest(), v_edge=V_EDGE,
               c_tab_aln_range_pF=[c * 1e12 for c in C_TAB_ALN], c_tab_nom_pF=C_TAB_NOM * 1e12, c_tab_hi_pF=C_TAB_HI * 1e12,
               script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), rows=rows)
    (RES / "cm_barrier.json").write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", RES / "cm_barrier.json")


if __name__ == "__main__":
    main()
