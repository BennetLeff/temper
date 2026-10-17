#!/usr/bin/env python3
"""Gate-network study for the native-21 bridge (S4 reverse-diode dv/dt, DECISIONS 49 / candidate 39).

Deck = the device-study harness deck (validation-results/01-switching-parasitics/device-study-2026-10-15/scripts/
harness.py, imported read-only: sha-checked c25 F6.cir + c33 board sw-node C + c25 PROBES + gate-loop charge), with:
  * the as-built turn-off branch value (Roffl/Roffh 1.34482758621 ohm literal) and Cgs (1 nF literal) turned into
    parameters ROFF and CGS (defaults = the literals, so the as-built deck is numerically unchanged);
  * topology 'split' (as built: RG in series, PMEG6030EP + ROFF in parallel with RG, anode at the gate side),
    'sym' (turn-off branch deleted: one symmetric resistor RG), or 'short' (diode replaced by 1 uohm: control);
  * diode-current measurements on the commutated (off) device: die drain current from the vendor subckt's
    R_Rd (v(ldrd)-v(dd))/Rdp, chord diF/dt 75->25 % and 50->0 % of |IL|, zero-crossing time, reverse peak;
  * optional ENERGY B-sources (device-study harness, die heat from the vendor heat channels) for the loss subset;
  * device 'CM8W' = IPW65R029CFD7_L1 copied into the deck with Rg,int 3.8 -> 1.0 ohm (IPW65R018CM8 Rev 2.1 p.5
    RG 1 ohm typ): the CM8 proxy with the gate resistance placed inside the package, so split networks see it;
    'CM8RGC' = the device study's own proxy (RG_deck = R_ext + 1.0 - 3.8, 029 model unchanged; symmetric only).

python3 -I gn.py <grid> --cfg <name> [--workers 4]     (configs in configs(); grids in grid())
Outputs: ../sims/<cfg>/<grid>/results.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "sims"   # s6-cmti copy: writes only under the job tmp dir
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
DS = PS / "validation-results/01-switching-parasitics/device-study-2026-10-15"
_spec = importlib.util.spec_from_file_location("ds_harness", DS / "scripts/harness.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)        # read-only reuse; nothing is written by import
d2c, run_d2, Z = H.d2c, H.run_d2, H.Z
LIB = run_d2.KIT / "models/vendor/IFX_CFD7_650V.lib"
PMEG_LIB = run_d2.KIT / "models/vendor/PMEG6030EP.txt"

ROFF_ASBUILT = "1.34482758621"     # deck literal (D6 'off1': 3.9 || 1.345 = 1 ohm); the BOM has 1 ohm (R53/54/57/58)
RDP = {"IPW65R018CFD7_L1": 7.44e-05}
DRIVER = {"nom": d2c.VARIANTS["edr_rg8p2"][:2], "strong": d2c.VARIANTS["edr_rg8p2_strong"][:2],
          "weak": d2c.VARIANTS["edr_rg8p2_weak"][:2]}     # 2EDR8259 Ron_SRC / Ron_SNK typ / min / max (Table 20)


C8LIB = PS / "validation-results/01-switching-parasitics/gate-network-2026-10-15/dl/cm8/c8_600/IFX_C8_600V.lib"  # not needed for CFD7 configs   # Infineon C8 600V library v1336 (public zip, README)
C8LIB_ZIP_SHA = "32050b46b1904af3a6e838503104d9da95d6c7058de3a710f8ce9f6415fb2f69"


def subckt_text(name: str, lib: Path | None = None) -> str:
    t = (lib or (C8LIB if "CM8" in name and name.startswith("IPW60") else LIB)).read_text()
    m = re.search(rf"^\.SUBCKT {name} .*?^\.ENDS", t, re.S | re.M)
    assert m, name
    return m.group(0)


def rdp_of(model: str) -> float:
    s = subckt_text(model, C8LIB if model.startswith("IPW60R016CM8") else LIB)
    return float(re.search(r"Rdp=([0-9.Ee+-]+)", s).group(1))


DIODE_MEAS = """
* ---- gate-network study: commutated-diode current (die drain current, + into drain) and edge measures
.save v(xql.ldrd) v(xqh.ldrd) v(xql.dd) v(xqh.dd) v(g_ls) v(g_hs) v(gdl3) v(gdh3)
.param IABS={abs(IL)+1e-3}
.meas tran ild_min MIN par('(v(xql.ldrd)-v(xql.dd))/RDPX') from={T1} to={T1+DT+0.75u}
.meas tran ild_max MAX par('(v(xql.ldrd)-v(xql.dd))/RDPX') from={T1+DT} to={T1+DT+0.75u}
.meas tran ihd_min MIN par('(v(xqh.ldrd)-v(xqh.dd))/RDPX') from={T1} to={T1+DT+0.75u}
.meas tran ihd_max MAX par('(v(xqh.ldrd)-v(xqh.dd))/RDPX') from={T1+DT} to={T1+DT+0.75u}
.meas tran tl75 WHEN par('(v(xql.ldrd)-v(xql.dd))/RDPX')={-0.75*IABS} RISE=1 TD={T1+DT}
.meas tran tl50 WHEN par('(v(xql.ldrd)-v(xql.dd))/RDPX')={-0.50*IABS} RISE=1 TD={T1+DT}
.meas tran tl25 WHEN par('(v(xql.ldrd)-v(xql.dd))/RDPX')={-0.25*IABS} RISE=1 TD={T1+DT}
.meas tran tl00 WHEN par('(v(xql.ldrd)-v(xql.dd))/RDPX')=0 RISE=1 TD={T1+DT}
.meas tran th75 WHEN par('(v(xqh.ldrd)-v(xqh.dd))/RDPX')={-0.75*IABS} RISE=1 TD={T1+DT}
.meas tran th50 WHEN par('(v(xqh.ldrd)-v(xqh.dd))/RDPX')={-0.50*IABS} RISE=1 TD={T1+DT}
.meas tran th25 WHEN par('(v(xqh.ldrd)-v(xqh.dd))/RDPX')={-0.25*IABS} RISE=1 TD={T1+DT}
.meas tran th00 WHEN par('(v(xqh.ldrd)-v(xqh.dd))/RDPX')=0 RISE=1 TD={T1+DT}
* energy dissipated in the series gate resistors (R_on) and the turn-off branch resistors over the window
.save v(gdl) v(gdh) v(offl) v(offh)
.meas tran e_rgl INTEG par('(v(gdl)-v(gdl3))*(v(gdl)-v(gdl3))/RG') from={T1-20n} to={T1+DT+0.75u}
.meas tran e_rgh INTEG par('(v(gdh)-v(gdh3))*(v(gdh)-v(gdh3))/RG') from={T1-20n} to={T1+DT+0.75u}
* incoming gate (die) reaching 4 V / 10 V after its on command (turn-on delay, plateau exit)
.meas tran tgh4 WHEN par('v(xqh.g)-v(xqh.s)')=4 RISE=1 TD={THS}
.meas tran tgl4 WHEN par('v(xql.g)-v(xql.s)')=4 RISE=1 TD={TLS}
.meas tran tgh10 WHEN par('v(xqh.g)-v(xqh.s)')=10 RISE=1 TD={THS}
.meas tran tgl10 WHEN par('v(xql.g)-v(xql.s)')=10 RISE=1 TD={TLS}
"""

CM8_NOTE = "IPW65R029CFD7_L1 with Rg,int 3.8 -> 1.0 ohm (IPW65R018CM8 Rev 2.1 p.5: RG 1 ohm typ)"


def cm8_wrapper() -> str:
    s = subckt_text("IPW65R029CFD7_L1")
    assert s.count("Rg=3.8") == 1, s[:300]
    return s.replace(".SUBCKT IPW65R029CFD7_L1", ".SUBCKT CM8W_L1").replace("Rg=3.8", "Rg=1.0")


LONG_MEAS = """
* ---- slow-gate check: incoming die gate voltage after its on command (long window)
.meas tran vgh_1u FIND par('v(xqh.g)-v(xqh.s)') AT={THS+1u}
.meas tran vgl_1u FIND par('v(xql.g)-v(xql.s)') AT={TLS+1u}
.meas tran vgh_2u FIND par('v(xqh.g)-v(xqh.s)') AT={THS+2u}
.meas tran vgl_2u FIND par('v(xql.g)-v(xql.s)') AT={TLS+2u}
.meas tran vgh_3u FIND par('v(xqh.g)-v(xqh.s)') AT={THS+3u}
.meas tran vgl_3u FIND par('v(xql.g)-v(xql.s)') AT={TLS+3u}
"""


def build_deck(cfg: dict, energy: bool = False, long: bool = False) -> str:
    model = cfg["model"]
    base_dev = "IPW65R029CFD7_L1" if model in ("CM8W_L1",) else model
    if model == "IPW60R016CM8_L1":
        deck = H.deck_text("IPW65R018CFD7_L1", energy=energy).replace("IPW65R018CFD7_L1", model)
        tech = subckt_text("cool_C8_600_var", C8LIB)
        if cfg.get("tt"):
            # C8 body-diode transit time (dbody TT={fpar19}, vendor 25 ns) for the Qrr sensitivity
            assert tech.count(".PARAM  fpar19=25e-9") == 1
            tech = tech.replace(".PARAM  fpar19=25e-9", f".PARAM  fpar19={cfg['tt']}")
        c8 = tech + "\n" + subckt_text(model, C8LIB)
        deck = deck.replace(".include IFX_CFD7_650V.lib", ".include IFX_CFD7_650V.lib\n" + c8, 1)
    else:
        deck = H.deck_text(base_dev, energy=energy)
    if model == "CM8W_L1":
        deck = deck.replace("IPW65R029CFD7_L1", "CM8W_L1")
        deck = deck.replace(".include IFX_CFD7_650V.lib", ".include IFX_CFD7_650V.lib\n" + cm8_wrapper(), 1)
    if cfg.get("tt"):
        # diode transit-time sensitivity (D-24 method: cool_tech_w3.fpar20 only, 50 ns -> tt), in renamed copies
        assert model in ("IPW65R018CFD7_L1", "IPW60R016CM8_L1")
    if cfg.get("tt") and model == "IPW65R018CFD7_L1":
        tech = subckt_text("cool_tech_w3")
        assert tech.count(".PARAM  fpar20=50e-9") == 1
        tech = tech.replace(".SUBCKT cool_tech_w3 ", ".SUBCKT cool_tech_w3_tt ").replace(
            ".PARAM  fpar20=50e-9", f".PARAM  fpar20={cfg['tt']}")
        dev = subckt_text(model).replace(".SUBCKT IPW65R018CFD7_L1", ".SUBCKT IPW65R018CFD7_TT").replace(
            "cool_tech_w3 PARAMS", "cool_tech_w3_tt PARAMS")
        assert "cool_tech_w3_tt PARAMS" in dev
        deck = deck.replace("IPW65R018CFD7_L1", "IPW65R018CFD7_TT")
        deck = deck.replace(".include IFX_CFD7_650V.lib", ".include IFX_CFD7_650V.lib\n" + tech + "\n" + dev, 1)
    # parameters for the turn-off branch and Cgs (defaults = the deck literals)
    for lit, new in ((f"Roffl offl gdl {ROFF_ASBUILT}", "Roffl offl gdl {ROFF}"),
                     (f"Roffh offh gdh {ROFF_ASBUILT}", "Roffh offh gdh {ROFF}"),
                     ("Cgsl g_ls s_ls 1n", "Cgsl g_ls s_ls {CGS}"), ("Cgsh g_hs sw 1n", "Cgsh g_hs sw {CGS}")):
        assert deck.count(lit) == 1, lit
        deck = deck.replace(lit, new)
    deck = deck.replace(".include params.inc", f".param ROFF={ROFF_ASBUILT} CGS=1n RDPX={rdp_of(base_dev)}\n"
                        ".include params.inc", 1)
    topo = cfg["topo"]
    if topo == "sym":
        for ln in ("XDoffl gdl3 offl PMEG6030EP", "XDoffh gdh3 offh PMEG6030EP", "Roffl offl gdl {ROFF}",
                   "Roffh offh gdh {ROFF}"):
            assert deck.count(ln + "\n") == 1, ln
            deck = deck.replace(ln + "\n", "")
    elif topo == "short":
        deck = deck.replace("XDoffl gdl3 offl PMEG6030EP", "Rdsl gdl3 offl 1u")
        deck = deck.replace("XDoffh gdh3 offh PMEG6030EP", "Rdsh gdh3 offh 1u")
    elif topo == "open":
        # symmetric R by an open diode (1 Gohm): a fallback for 'sym' rows whose t=0 operating point fails
        deck = deck.replace("XDoffl gdl3 offl PMEG6030EP", "Rdsl gdl3 offl 1G")
        deck = deck.replace("XDoffh gdh3 offh PMEG6030EP", "Rdsh gdh3 offh 1G")
    elif topo != "split":
        raise ValueError(topo)
    if cfg.get("cgd"):
        # option (d): external gate-drain (Miller) capacitor at the package pins, drain pin -> gate pin
        deck = deck.replace("Cgsh g_hs sw {CGS}", "Cgsh g_hs sw {CGS}\nCgdh bus g_hs {CGD}\nCgdl d_ls g_ls {CGD}", 1)
        deck = deck.replace(".include params.inc", f".param CGD={cfg['cgd']}\n.include params.inc", 1)
    deck = deck.replace("\n.end", "\n" + DIODE_MEAS + ".end")
    if long:
        # window 0.75 us -> 3.75 us after the on command (tran end and the energy window TW1 only)
        for a, b in ((".tran {TRMAX} {T1+DT+0.8u} 0 {TRMAX}", ".tran {TRMAX} {T1+DT+3.8u} 0 {TRMAX}"),
                     ("TW1={T1+DT+0.75u}", "TW1={T1+DT+3.75u}")):
            assert deck.count(a) == 1, a
            deck = deck.replace(a, b)
        deck = deck.replace("\n.end", "\n" + LONG_MEAS + ".end")
    assert deck.count("\n.end") == 1
    return deck


def configs() -> dict:
    """name -> config. ron = series R (RG, external), roff = turn-off branch R; rgc = RG correction (CM8RGC)."""
    c = {}
    c["asbuilt"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=8.2, roff=float(ROFF_ASBUILT), cgs=1e-9)
    c["asbuilt_bom"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=8.2, roff=1.0, cgs=1e-9)
    for r in (10, 12, 15, 18, 22):
        # option (a) as the device study used it: only R10/R12/R18/R20 change, the 1 ohm + PMEG branch stays
        c[f"rext{r}"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=r, roff=float(ROFF_ASBUILT), cgs=1e-9)
    for r in (10, 12, 15, 18, 22):
        c[f"sym{r}"] = dict(model="IPW65R018CFD7_L1", topo="sym", ron=r, roff=r, cgs=1e-9)
    for ron in (15, 22, 27, 33, 39, 47):
        for roff in (1.0, 4.7, 8.2):
            c[f"split{ron}_{roff:g}".replace(".", "p")] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron,
                                                               roff=roff, cgs=1e-9)
    c["split56_1"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=56, roff=1.0, cgs=1e-9)
    for ron in (39, 47):
        c[f"split{ron}_1_cgs2p2"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron, roff=1.0, cgs=2.2e-9)
    for cg in (2.2, 4.7):
        for ron in (8.2, 22, 33):
            c[f"split{ron:g}_1_cgs{cg:g}".replace(".", "p")] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron,
                                                                   roff=1.0, cgs=cg * 1e-9)
    for cgd in (10, 22, 47):
        for ron in (8.2, 15, 22, 33):
            c[f"split{ron:g}_1_cgd{cgd}".replace(".", "p")] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron,
                                                                  roff=1.0, cgs=1e-9, cgd=cgd * 1e-12)
            c[f"c8_split{ron:g}_1_cgd{cgd}".replace(".", "p")] = dict(model="IPW60R016CM8_L1", topo="split", ron=ron,
                                                                     roff=1.0, cgs=1e-9, cgd=cgd * 1e-12)
    for ron in (68, 82, 100, 120):
        c[f"split{ron}_1"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron, roff=1.0, cgs=1e-9)
    for ron in (39, 47, 56, 68):
        c[f"split{ron}_1_cgs4p7"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron, roff=1.0, cgs=4.7e-9)
    for ron in (56, 68):
        c[f"split{ron}_1_cgs2p2"] = dict(model="IPW65R018CFD7_L1", topo="split", ron=ron, roff=1.0, cgs=2.2e-9)
    for base in ("split56_1", "split68_1", "split82_1", "split100_1", "split120_1", "split39_1_cgs2p2",
                 "split47_1_cgs2p2", "split56_1_cgs2p2", "split68_1_cgs2p2", "split39_1_cgs4p7", "split47_1_cgs4p7",
                 "split56_1_cgs4p7", "split68_1_cgs4p7", "split33_1_cgs4p7", "split22_1_cgs4p7"):
        c[f"{base}_tt125"] = dict(c[base], tt="125e-9")
    c["split39_1_tt50"] = dict(c["split39_1"], tt="50e-9")   # control: renamed copy at the vendor value
    for tt in (125, 260):
        for nm, base in (("asbuilt", "asbuilt"), ("split39_1", "split39_1"), ("split47_1", "split47_1"),
                         ("split33_1_cgs2p2", "split33_1_cgs2p2")):
            c[f"{nm}_tt{tt}"] = dict(c[base], tt=f"{tt}e-9")
    # S6-CMTI addition: the adopted network (68 ohm + Cgs 4.7 nF) and its neighbour at maximum Qrr (TT 260 ns, D-24 map)
    for base in ("split68_1_cgs4p7", "split56_1_cgs4p7", "split100_1"):
        c[f"{base}_tt260"] = dict(c[base], tt="260e-9")
    # control: the 'open' fallback (diode as 1 Gohm) against the deleted branch
    for r in (12, 22):
        c[f"open{r}"] = dict(model="IPW65R018CFD7_L1", topo="open", ron=r, roff=r, cgs=1e-9)
    # controls: split with the diode shorted and R_on = R_off = 2R  ==  sym R
    for r in (12, 22):
        c[f"short{2*r}_{2*r}"] = dict(model="IPW65R018CFD7_L1", topo="short", ron=2 * r, roff=2 * r, cgs=1e-9)
    # CM8 proxy B: Infineon's own C8 technology model, IPW60R016CM8_L1 (600 V C8; datasheet twin of IPW65R018CM8)
    c["c8_asbuilt"] = dict(model="IPW60R016CM8_L1", topo="split", ron=8.2, roff=float(ROFF_ASBUILT), cgs=1e-9)
    for r in (10, 12, 15, 18, 22):
        c[f"c8_sym{r}"] = dict(model="IPW60R016CM8_L1", topo="sym", ron=r, roff=r, cgs=1e-9)
    for ron in (15, 22, 27, 33, 39, 47, 56, 68):
        for roff in (1.0,):
            c[f"c8_split{ron}_{roff:g}".replace(".", "p")] = dict(model="IPW60R016CM8_L1", topo="split", ron=ron,
                                                                  roff=roff, cgs=1e-9)
    # CM8 proxy (029 model, Rg,int 1.0 ohm inside the package)
    c["cm8_asbuilt"] = dict(model="CM8W_L1", topo="split", ron=8.2, roff=1.0, cgs=1e-9)
    for r in (10, 12, 15, 18, 22):
        c[f"cm8_sym{r}"] = dict(model="CM8W_L1", topo="sym", ron=r, roff=r, cgs=1e-9)
    for r in (8.2, 10, 12, 15):
        # the device study's own CM8 proxy: 029 model unchanged, RG_deck = R_ext + 1.0 - 3.8, as-built turn-off branch
        c[f"cm8rgc_rext{r:g}".replace(".", "p")] = dict(model="IPW65R029CFD7_L1", topo="split",
                                                       ron=round(r + 1.0 - 3.8, 3), roff=float(ROFF_ASBUILT),
                                                       cgs=1e-9, note="device-study proxy convention")
    for ron in (15, 22, 27, 33, 39, 47, 56, 68):
        for roff in (1.0,):
            c[f"cm8_split{ron}_{roff:g}".replace(".", "p")] = dict(model="CM8W_L1", topo="split", ron=ron, roff=roff,
                                                                   cgs=1e-9)
    # C8 body-diode TT sensitivity (vendor 25 ns)
    for tt in (60, 80):
        for ron in (27, 39, 47, 56, 68):
            c[f"c8_split{ron}_1_tt{tt}"] = dict(c[f"c8_split{ron}_1"], tt=f"{tt}e-9")
    return c


def run_case(deck: Path, out: Path, cfg: dict, case: str, drv: str, leg: str, temp, vbus, il, d, dt, esl,
             trmax="0.2n") -> dict:
    roh, rol = DRIVER[drv]
    cret, cbus = Z.node_caps()[H.BOARD][leg]
    name = f"{case}_{drv}_{leg}_T{temp}_v{vbus}_i{il}_d{d}_dt{dt}_esl{esl}_s{trmax}"
    p = run_d2.matrix_params(run_d2.read_L(str(d2c.MATRICES[leg])))
    p.update(TJ=str(temp), VBUS=str(vbus), IL=str(il), DIR=str(d), DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n",
             TRMAX=trmax, ROH=str(roh), ROL=str(rol), RG=str(cfg["ron"]),
             CBRD_RET=f"{max(cret, 1e-6)}p", CBRD_BUS=f"{max(cbus, 1e-6)}p")
    if cfg["topo"] != "sym":
        p["ROFF"] = str(cfg["roff"])
    p["CGS"] = str(cfg["cgs"])
    if cfg.get("cgd"):
        p["CGD"] = str(cfg["cgd"])
    keep = out / "runs" / name
    r = run_d2.run(deck, p, keep=keep)
    m = r["meas"]
    row = {"case": case, "drv": drv, "leg": leg, "temp_C": temp, "vbus": vbus, "il": il, "dir": d, "dt_ns": dt,
           "esl_nH": esl, "trmax": trmax}
    inc, off = ("hs", "ls") if d == 0 else ("ls", "hs")
    energy = "e_hs_die" in deck.read_text()
    need = ["vds_ls_die_pk", "vds_hs_die_pk", f"vgs_{off}_off_max", f"vds_{inc}_at_on"] + \
        (["e_hs_die", "e_ls_die"] if energy else [])
    if r["aborted"] or any(k not in m for k in need):
        row["status"] = "aborted" if r["aborted"] else "indeterminate"
        row["missing"] = [k for k in need if k not in m]
        (keep / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
        return row
    shutil.rmtree(keep, ignore_errors=True)
    t1 = 2e-6
    tz = m.get(f"t_{inc}_zvs")
    row.update(status="complete", vds_pk=max(m["vds_ls_die_pk"], m["vds_hs_die_pk"]), off_V=m[f"vgs_{off}_off_max"],
               incoming_V=m[f"vds_{inc}_at_on"],
               vgs_abs=max(abs(m[f"vgs_{s}_die_{e}"]) for s in ("ls", "hs") for e in ("min", "max")),
               t_trans_ns=(tz - t1) * 1e9 if tz is not None else None,
               q_gate_hs_C=m.get("qh_win"), q_gate_ls_C=m.get("ql_win"))
    row["zvs"] = row["incoming_V"] <= 0.05 * vbus
    row["dvsw_abs"] = max(abs(m["dvsw_max"]), abs(m["dvsw_min"])) if "dvsw_max" in m else None
    t2080 = m.get("tr2080") if d == 0 else m.get("tf8020")
    if t2080 and t2080 > 0:
        row["slew2080_Vns"] = 0.6 * vbus / (t2080 * 1e9)
    t1090 = m.get("tr1090") if d == 0 else m.get("tf9010")
    if t1090 and t1090 > 0:
        row["slew1090_Vns"] = 0.8 * vbus / (t1090 * 1e9)
    # commutated diode = the device turned off at T1 (its body diode carries |IL| through the dead time when IL < 0)
    o = "l" if off == "ls" else "h"
    t75, t50, t25, t00 = (m.get(f"t{o}{k}") for k in ("75", "50", "25", "00"))
    ia = abs(il) + 1e-3
    row["i_diode_fwd_A"] = -m.get(f"i{o}d_min") if m.get(f"i{o}d_min") is not None else None
    row["i_rr_pk_A"] = m.get(f"i{o}d_max")
    if t75 and t25 and t25 > t75:
        row["difdt_75_25_Apus"] = 0.5 * ia / ((t25 - t75) * 1e6)
    if t50 and t00 and t00 > t50:
        row["difdt_50_0_Apus"] = 0.5 * ia / ((t00 - t50) * 1e6)
    ton = t1 + dt * 1e-9
    tg4, tg10 = m.get(f"tg{inc[0]}4"), m.get(f"tg{inc[0]}10")
    row["t_on_gate4_ns"] = (tg4 - ton) * 1e9 if tg4 else None
    row["t_on_gate10_ns"] = (tg10 - ton) * 1e9 if tg10 else None
    row["t_zero_cross_ns"] = (t00 - ton) * 1e9 if t00 else None
    row["e_ron_inc_J"] = m.get(f"e_rg{inc[0]}")      # R_on energy of the device turning on (this edge)
    row["e_ron_out_J"] = m.get(f"e_rg{off[0]}")      # R_on energy of the device turning off (this edge)
    q_inc = m.get("qh_win") if inc == "hs" else m.get("ql_win")
    row["q_gate_inc_nC"] = -q_inc * 1e9 if q_inc is not None else None
    for k in ("1u", "2u", "3u"):
        if f"vg{inc[0]}_{k}" in m:
            row[f"vgs_inc_{k}_V"] = m[f"vg{inc[0]}_{k}"]
    if energy:
        tw0 = t1 - 20e-9
        tw1 = t1 + dt * 1e-9 + (3.75e-6 if "vgh_1u" in m else 0.75e-6)
        e_tot = m["e_hs_die"] + m["e_ls_die"]
        p_end = m[f"p_{inc}_end"]
        row.update(e_out_J=m[f"e_{off}_die"], e_in_J=m[f"e_{inc}_die"], e_tot_J=e_tot, p_cond_end_W=p_end,
                   p_cond_start_W=m.get(f"p_{off}_start"),
                   e_extra_J=e_tot - p_end * (tw1 - tw0),
                   # outgoing die heat net of its 20 ns pre-T1 conduction (turn-off loss per edge)
                   e_off_edge_J=m[f"e_{off}_die"] - m[f"p_{off}_start"] * 20e-9)
    return row


def screen(row: dict) -> dict:
    """c25 rules (via the device-study harness) + the dv/dt screens of this study."""
    if row["status"] != "complete":
        return row
    case = row["case"]
    if case in ("S1", "S2", "S4", "S5"):
        H.screen(row, case)
    s = row.get("slew2080_Vns")
    row["pass_dvdt96"] = (s is None) or s <= 96.0
    row["pass_dvdt100"] = (s is None) or s <= 100.0
    if case == "S4":
        row["pass_diode56"] = s is not None and s <= 56.0
        g = row.get("difdt_75_25_Apus")
        row["pass_difdt1040"] = g is not None and g <= 1040.0
    return row


TEMPS_NOM = (27, 100, 150)
CORNERS = [("nom", t) for t in TEMPS_NOM] + [(v, t) for v in ("weak", "strong") for t in (27, 150)]


def grid(name: str):
    """(case, drv, leg, temp, vbus, il, dir, dt, esl[, energy])"""
    js = []
    if name == "s4screen":
        # binding S4 corners on the as-built deck: leg A, 280 V, dir 0 (HS on, LS diode), DT 600 and 340
        # (DT 600 is the worse dead time on the as-built deck: 85.8 vs 84.6 V/ns; committed edge rows)
        for drv, t in CORNERS:
            for leg in "AB":
                for dt in (600,):
                    for esl in (10, 1.06):
                        js.append(("S4", drv, leg, t, 280, -20, 0, dt, esl))
                        js.append(("S4", drv, leg, t, 280, -20, 1, dt, esl))
        return js
    if name == "s4b":
        # the binding S4 set on the full grid: leg A, HS turning on (LS diode), 170/198/280 V, every driver/temperature
        # corner, both ESL, DT 600 (the as-built full grid's worst rows are leg A, dir 0, at 198 or 280 V)
        for drv, t in CORNERS:
            for vb in (170, 198, 280):
                for esl in (10, 1.06):
                    js.append(("S4", drv, "A", t, vb, -20, 0, 600, esl))
        return js
    if name == "full":
        for drv, t in CORNERS:
            for leg in "AB":
                for d in (0, 1):
                    for vb in (198, 280):
                        js.append(("S1", drv, leg, t, vb, 37, d, 340, 10))
                        if drv == "nom":
                            js.append(("S1", drv, leg, t, vb, 37, d, 408, 10))
                    for esl in (10, 1.06):
                        js.append(("S2", drv, leg, t, 280, 71, d, 340, esl))
                        for vb in (170, 198, 280):
                            for dt in (340, 600):
                                js.append(("S4", drv, leg, t, vb, -20, d, dt, esl))
                            js.append(("S5", drv, leg, t, vb, 0, d, 340, esl))
        return js
    if name == "loss":
        # die heat per edge (vendor heat channels): S1 ZVS turn-off at 10/20/37 A and S4 hard turn-on
        for leg in "AB":
            for t in (100, 150):
                for d in (0, 1):
                    for il in (10, 20, 37):
                        js.append(("S1", "nom", leg, t, 198, il, d, 408, 10, True))
                    js.append(("S4", "nom", leg, t, 280, -20, d, 408, 10, True))
                    js.append(("S4", "nom", leg, t, 198, -20, d, 408, 10, True))
        return js
    if name == "slowgate":
        # long window (3.75 us after the on command): conduction penalty of a slow turn-on in ZVS operation
        for leg in "AB":
            for t in (100, 150):
                for d in (0, 1):
                    for il in (20, 37):
                        js.append(("S1", "nom", leg, t, 198, il, d, 408, 10, True))
        return js
    if name == "repro":
        # committed device-study rows (as-built edge + edge2): all S4/S5, S2, S1 at DT 340/408 nominal
        rows = []
        for mode in ("edge", "edge2"):
            R = json.loads((DS / f"sims/IPW65R018CFD7_L1/{mode}/results.json").read_text())["rows"]
            rows += [r for r in R if r["status"] == "complete" and r["variant"] == "edr_rg8p2" and
                     (r["case"] in ("S4", "S2", "S5") or (r["case"] == "S1" and r["dt_ns"] in (340, 408)))
                     and r["temp_C"] in (27, 150)]
            rows += [r for r in R if r["status"] == "complete" and r["case"] == "S4" and r["vbus"] == 280 and
                     r["leg"] == "A" and r["dir"] == 0 and r["temp_C"] == 150]
        seen, out = set(), []
        for r in rows:
            k = (r["case"], r["variant"], r["leg"], r["temp_C"], r["vbus"], r["il"], r["dir"], r["dt_ns"], r["esl_nH"])
            if k not in seen:
                seen.add(k)
                drv = {"edr_rg8p2": "nom", "edr_rg8p2_weak": "weak", "edr_rg8p2_strong": "strong"}[r["variant"]]
                out.append(((r["case"], drv, r["leg"], r["temp_C"], r["vbus"], r["il"], r["dir"], r["dt_ns"],
                             r["esl_nH"]), r))
        return out
    if name == "erepro":
        # committed device-study energy rows (as-built, DT 569, Tj 150, leg A): a few points
        R = json.loads((DS / "sims/IPW65R018CFD7_L1/energy/results.json").read_text())["rows"]
        want = [r for r in R if r["status"] == "complete" and r["leg"] == "A" and r["temp_C"] == 150 and
                r["vbus"] in (100, 198) and r["il"] in (10, 30)]
        return [(("E", "nom", r["leg"], r["temp_C"], r["vbus"], r["il"], r["dir"], r["dt_ns"], 10, True), r)
                for r in want]
    raise ValueError(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grid")
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fix", action="store_true", help="re-run only the non-complete rows of an existing results.json")
    a = ap.parse_args()
    cfg = configs()[a.cfg]
    out = OUT / a.cfg / a.grid
    out.mkdir(parents=True, exist_ok=True)
    jobs = grid(a.grid)
    ref = None
    if a.grid in ("repro", "erepro"):
        ref = [r for _, r in jobs]
        jobs = [j for j, _ in jobs]
    if a.limit:
        jobs = jobs[:a.limit]
    decks = {}
    for en in (False, True):
        p = out / ("deck_energy.cir" if en else "deck.cir")
        p.write_text(build_deck(cfg, energy=en, long=(a.grid == "slowgate")))
        decks[en] = p

    if cfg["topo"] == "sym":
        # fallback for rows whose t=0 operating point fails: the same symmetric network with the diode as 1 Gohm
        cfg_open = dict(cfg, topo="open")
        for en in (False, True):
            p = out / ("deck_open_energy.cir" if en else "deck_open.cir")
            p.write_text(build_deck(cfg_open, energy=en, long=(a.grid == "slowgate")))
            decks[("open", en)] = p

    def go(j):
        case, drv, leg, t, vb, il, d, dt, esl, *en = j
        en = bool(en and en[0])
        r = run_case(decks[en], out, cfg, case, drv, leg, t, vb, il, d, dt, esl)
        if r["status"] != "complete":
            r = run_case(decks[en], out / "retry", cfg, case, drv, leg, t, vb, il, d, dt, esl, trmax="0.1n")
        if r["status"] != "complete" and cfg["topo"] == "sym":
            r = run_case(decks[("open", en)], out / "retry_open", cfg_open, case, drv, leg, t, vb, il, d, dt, esl)
            r["fallback"] = "diode branch as 1 Gohm (open)"
        return screen(r)

    prev = out / "results.json"
    if a.fix and prev.is_file():
        old = json.loads(prev.read_text())
        rows = old["rows"]
        bad = [i for i, r in enumerate(rows) if r["status"] != "complete"]
        with ThreadPoolExecutor(a.workers) as ex:
            new = list(ex.map(go, [jobs[i] for i in bad]))
        for i, r in zip(bad, new):
            rows[i] = r
    else:
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(go, jobs))
    res = {"cfg_name": a.cfg, "cfg": cfg, "grid": a.grid,
           "identity": {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for p in (decks[False], decks[True], Path(__file__), DS / "scripts/harness.py", LIB, PMEG_LIB,
                                  d2c.MATRICES["A"], d2c.MATRICES["B"], Z.REF_DECK) if Path(p).is_file()},
           "rows": rows}
    if ref is not None:
        res["reference"] = ref[:len(rows)]
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    bad = sum(r["status"] != "complete" for r in rows)
    print(a.cfg, a.grid, f"{len(rows) - bad}/{len(rows)} complete")


if __name__ == "__main__":
    main()
