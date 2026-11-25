"""Device decks for the c55 trade.

Every deck is the committed as-built switching deck (c25 F6.cir + c33 board switch-node C + c25 probes + device-study
gate-charge meas), built through the gate-network study's `build_deck()` (split R_on / PMEG + R_off branch, Cgs and
diode measurements), so every device sees the same board, matrices, driver model and screens.

Device kinds
  'gn'   : a config understood by gn.build_deck() itself (CFD7 vendor model, the C8 600 V vendor model as the CM8
           proxy B, the CFD7-029 'CM8W' proxy A), plus an optional diode transit time 'tt' (gn's own mechanism).
  'wrap' : a vendor model (SiC MOSFET, RC-IGBT, GaN) inside a wrapper subckt `<NAME>_W drain gate source` that exposes
           the nodes the deck measures: dd (die drain), s (die source), g (die gate), ldrd (package side of a 100 uohm
           drain sense resistor; die drain current = (v(ldrd)-v(dd))/RDPX). The wrapper text is written per model in
           `wrappers.py`, from the vendor file, with its sha256 asserted.
Driver levels: the deck's 2EDR8259 output model drives +VDRV / -1.6 V (F6). 'vdrv' / 'voff' change them (SiC, IGBT);
the -1.6 V literal in the two B-source drivers becomes the parameter VOFFP (default -1.6, so CoolMOS decks are
byte-for-byte the gn decks apart from the added energy measures).
Energy: generic die heat = integral of v(dd,s) * i_drain over the device-study window (TW0..TW1) for both dies; it needs
no vendor-internal heat channels, so it works for every model. Control in c10: against the device study's vendor
heat-channel energy on the CFD7.
"""
from __future__ import annotations

import re

from common import G, H

RSENSE = 1e-4

GENERIC_ENERGY = """
* ---- c55: generic die heat (v(dd,s) x die drain current), both dies, over the device-study window
.meas tran eg_hs INTEG par('(v(xqh.dd)-v(xqh.s))*(v(xqh.ldrd)-v(xqh.dd))/RDPX') from={TW0} to={TW1}
.meas tran eg_ls INTEG par('(v(xql.dd)-v(xql.s))*(v(xql.ldrd)-v(xql.dd))/RDPX') from={TW0} to={TW1}
.meas tran pg_hs_end FIND par('(v(xqh.dd)-v(xqh.s))*(v(xqh.ldrd)-v(xqh.dd))/RDPX') AT={TW1-5n}
.meas tran pg_ls_end FIND par('(v(xql.dd)-v(xql.s))*(v(xql.ldrd)-v(xql.dd))/RDPX') AT={TW1-5n}
.meas tran pg_hs_start FIND par('(v(xqh.dd)-v(xqh.s))*(v(xqh.ldrd)-v(xqh.dd))/RDPX') AT={TW0}
.meas tran pg_ls_start FIND par('(v(xql.dd)-v(xql.s))*(v(xql.ldrd)-v(xql.dd))/RDPX') AT={TW0}
"""

DRV_LIT = ("Bgl gdl s_ls I={(v(gdl,s_ls)-(-1.6))*", "Bgh gdh sw I={(v(gdh,sw)-(-1.6))*")


def build(dev: dict, long: bool = False, energy_vendor: bool = False, energy_generic: bool = False) -> str:
    """dev: {'kind': 'gn'|'wrap', 'ron', 'roff', 'cgs', 'topo', ['model'|'wrapper'], ['tt'], ['vdrv', 'voff']}"""
    topo = dev.get("topo", "split")
    if dev["kind"] == "gn":
        cfg = dict(model=dev["model"], topo=topo, ron=dev["ron"], roff=dev["roff"], cgs=dev["cgs"])
        if dev.get("tt"):
            cfg["tt"] = dev["tt"]
        deck = G.build_deck(cfg, energy=energy_vendor, long=long)
    else:
        cfg = dict(model="IPW65R018CFD7_L1", topo=topo, ron=dev["ron"], roff=dev["roff"], cgs=dev["cgs"])
        deck = G.build_deck(cfg, energy=False, long=long)
        name, text, rdp = dev["wrapper"]
        assert deck.count("IPW65R018CFD7_L1") == 2, deck.count("IPW65R018CFD7_L1")
        deck = deck.replace("IPW65R018CFD7_L1", name)
        deck = deck.replace(".include IFX_CFD7_650V.lib", ".include IFX_CFD7_650V.lib\n" + text, 1)
        old = re.search(r"RDPX=[0-9.eE+-]+", deck).group(0)
        assert deck.count(old) == 1
        deck = deck.replace(old, f"RDPX={rdp}")
    for lit in DRV_LIT:
        assert deck.count(lit) == 1, lit
        deck = deck.replace(lit, lit.replace("(-1.6)", "(VOFFP)"))
    assert deck.count(".include params.inc") == 1
    deck = deck.replace(".include params.inc", ".param VOFFP=-1.6\n.include params.inc\n.param TJDECK={TJ}", 1)
    if energy_generic:
        # only on energy-grid decks: par() measures become B-sources in ngspice and move switching rows slightly
        # (c00 K6: up to 0.46 V die VDS / 0.17 V/ns), so the decision-grid decks stay the gn decks
        deck = deck.replace("\n.end", "\n" + GENERIC_ENERGY + ".end")
    assert deck.count("\n.end") == 1
    return deck


def params_extra(dev: dict) -> dict:
    """Extra .params for run_case (driver levels)."""
    p = {}
    if "vdrv" in dev:
        p["VDRV"] = str(dev["vdrv"])
    if "voff" in dev:
        p["VOFFP"] = str(dev["voff"])
    if "csnub" in dev:
        p["CSNUB"] = str(dev["csnub"])
    return p
