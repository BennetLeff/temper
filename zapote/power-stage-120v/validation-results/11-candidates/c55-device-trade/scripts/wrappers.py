"""Vendor models (outside git, C55_DL) placed in the deck as XQH / XQL with the nodes the deck measures:
dd (die drain), s (die source), g (die gate), ldrd (package side of the drain resistance; die drain current =
(v(ldrd) - v(dd)) / RDPX). Each vendor file is sha256-checked before use (URLs in ../README.md, Datasheets / models).

  IPW65R018CM8   Infineon 650 V CoolMOS 8 library v01_00 (2025-05-07), IPW65R018CM8_L1 used as published; its node names
                 are those of the CFD7 L1 model (dd, g, s, ldrd, Rdp 74.4 uohm). Diode transit time 'tt' (fpar19, vendor
                 25 ns) changes the recovery charge, as the gate-network study did for C8 600 V (c05_qrr.py calibrates it).
  IMW65R026M2H   Infineon CoolSiC 650 V G2 library v1380, IMW65R026M2H_L1 copied with two edits that do not change the
                 circuit: node d1 renamed ldrd, and the die's internal gate resistance RGint (2.905 ohm at fpar127 5,
                 datasheet RG,int 2.9 ohm p.6) moved outside node g into the package Rg, so v(g, s) is the channel gate.
  IHW40N65R5/R6  Infineon TRENCHSTOP 5 RC-H5 / RC-H6 L1 behavioural models (C G E), wrapped with the CFD7 L1 package
                 drain and gate inductances (1.88 / 8.32 nH, 10 ohm damped) and a 100 uohm drain sense; the model's own
                 emitter inductance stays inside it. The model's internal gate resistance is inside node g (not exposed).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from common import DL

LIBS = {
    "cm8_650": (DL / "cm8/c8_650/IFX_C8_650V.lib", "b9d1c19ea90cf886d758b46b732951d925464b147f0294e1e91439a77998345f"),
    "sic_g2": (DL / "IMW65R026M2H/model/infineon-coolsic-mosfet-650-v-g2-spice-simulationmodels-v1380-en.lib",
               "60a00c18"),
    "rc_h5": (next((DL / "IHW40N65R5/model_l1").glob("*/model/IGBT_650V_TRENCHSTOP5_R5_L1.lib"), Path("missing")),
              "b54e89a2"),
    "rc_h6": (next((DL / "IHW40N65R6/model_l1").glob("*/model/IGBT_650V_TRENCHSTOP5_R6_L1.lib"), Path("missing")),
              "35c3b421"),
}


def lib_text(key: str) -> str:
    p, want = LIBS[key]
    b = p.read_bytes()
    h = hashlib.sha256(b).hexdigest()
    assert h.startswith(want), (key, h)
    return b.decode("latin-1").replace("\r\n", "\n").replace("\r", "\n")


CLEAN = DL / "_c55_clean"          # ngspice-compatible copies (outside git, rebuilt from the vendor file every run)


def clean_copy(key: str, edits) -> Path:
    """Vendor lib with only the listed literal substitutions (dialect fixes for ngspice), written outside git."""
    t = lib_text(key)
    for a, b, n_min in edits:
        n = t.count(a)
        assert n >= n_min, (key, a, n)
        t = t.replace(a, b)
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = CLEAN / f"{key}.lib"
    out.write_text(t, encoding="latin-1")
    return out


def sub(text: str, name: str) -> str:
    m = re.search(rf"^\.SUBCKT {re.escape(name)}\b.*?^\.ENDS", text, re.S | re.M | re.I)
    assert m, name
    return m.group(0)


def _cm8(tt=None):
    t = lib_text("cm8_650")
    tech = sub(t, "cool_C8_650_var")
    if tt:
        assert tech.count(".PARAM  fpar19=25e-9") == 1
        tech = tech.replace(".PARAM  fpar19=25e-9", f".PARAM  fpar19={tt}")
    return "IPW65R018CM8_L1", tech + "\n" + sub(t, "IPW65R018CM8_L1") + "\n", 7.44e-05


def _sic_g2():
    t = lib_text("sic_g2")
    die = sub(t, "SiCMOS_650V_gen2")
    assert die.count("RGint\tgg\tgi\t{fpar3}") == 1
    die = die.replace(".SUBCKT SiCMOS_650V_gen2", ".SUBCKT SiCMOS_650V_gen2_C55").replace(
        "RGint\tgg\tgi\t{fpar3}", "RGint\tgg\tgi\t1e-6")
    dev = sub(t, "IMW65R026M2H_L1")
    for a, b in ((".SUBCKT IMW65R026M2H_L1", ".SUBCKT IMW65R026M2H_C55"),
                 ("Rg    g1     g    {Rg}", "Rg    g1     g    {Rg+LIMIT(-1.306*ln(fpar127)+5.0069,0.1,25)}"),
                 ("Ld    drain  d1   {Ld}", "Ld    drain  ldrd   {Ld}"),
                 ("Rd    d1     dd   {Rd}", "Rd    ldrd     dd   {Rd}"),
                 ("Rdcon drain  d1   1.0", "Rdcon drain  ldrd   1.0"),
                 ("SiCMOS_650V_gen2    PARAMS", "SiCMOS_650V_gen2_C55    PARAMS")):
        assert dev.count(a) == 1, a
        dev = dev.replace(a, b)
    # PSpice ARCTAN is ngspice atan, and ngspice's .FUNC takes no '=' (the only dialect edits; one line, line 89)
    p = clean_copy("sic_g2", [(".FUNC VGCHAN(VG) = { 0.6 - 0.8*ARCTAN(", ".FUNC VGCHAN(VG) { 0.6 - 0.8*atan(", 1)])
    return "IMW65R026M2H_C55", f".include {p}\n" + die + "\n" + dev + "\n", 7.67e-05


IGBT_WRAP = """.SUBCKT {name}_C55 drain gate source
L_Ld drain ldrd 1.88n
R_Ld drain ldrd 10
R_Rd dd ldrd 1e-4
L_Lg gate g 8.32n
R_Lg gate g 10
R_Ls s source 1e-6
X1 dd g s {name}_L1
.ENDS
"""


def _igbt(key, name):
    # ngspice cannot evaluate TEMP in a subckt PARAMS default: TJ={TEMP} -> TJ={TJDECK} (= the deck's TJ, devlib)
    clean = clean_copy(key, [("TJ= {TEMP}", "TJ= {TJDECK}", 0), ("TJ={TEMP}", "TJ={TJDECK}", 0)])
    assert "{TEMP}" not in clean.read_text(encoding="latin-1") and "TJDECK" in clean.read_text(encoding="latin-1")
    return f"{name}_C55", f".include {clean}\n" + IGBT_WRAP.format(name=name), 1e-4


DEFAULTS = {"ron": 8.2, "roff": 1.0, "cgs": 1e-9}


def get(name: str) -> dict:
    """Names: cm8_<net>[_ttNN], sic26_<vdrv>_<net>, rch5_<net>, rch6_<net>; <net> = r<R_on>[c<Cgs nF>][s<Csnub nF>]."""
    head, _, tt = name.partition("_tt")
    parts = head.split("_")
    fam = parts[0]
    net = parts[-1]
    m = re.fullmatch(r"r([0-9p]+)(?:c([0-9p]+))?(?:s([0-9p]+))?", net)
    assert m, name
    ron = float(m.group(1).replace("p", "."))
    cgs = float(m.group(2).replace("p", ".")) * 1e-9 if m.group(2) else 1e-9
    d = dict(kind="wrap", ron=ron, roff=1.0, cgs=cgs, topo="split")
    if m.group(3):                      # drain-source snubber per device (deck CSNUB, as built 1 nF C0G)
        d["csnub"] = float(m.group(3).replace("p", ".")) * 1e-9
    if fam == "cm8":
        d["wrapper"] = _cm8(f"{int(tt)}e-9" if tt else None)
    elif fam == "sic26":
        d["wrapper"] = _sic_g2()
        d["vdrv"] = float(parts[1])
    elif fam in ("rch5", "rch6"):
        d["wrapper"] = _igbt("rc_h5" if fam == "rch5" else "rc_h6", "IHW40N65R5" if fam == "rch5" else "IHW40N65R6")
    else:
        raise KeyError(name)
    return d


def identity(name: str) -> dict:
    fam = name.split("_")[0]
    key = {"cm8": "cm8_650", "sic26": "sic_g2", "rch5": "rc_h5", "rch6": "rc_h6"}[fam]
    p = LIBS[key][0]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()}
