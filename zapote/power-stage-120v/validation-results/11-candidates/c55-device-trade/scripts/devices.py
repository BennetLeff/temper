"""Candidate device configurations (switching decks). Datasheet values for loss / thermal live in device_data.json.

CoolMOS (kind 'gn', the gate-network study's own model handling):
  cfd7_8p2          IPW65R018CFD7, as-built until s41: R_on 8.2 ohm, deck R_off literal, Cgs 1 nF (control)
  cfd7_c39          IPW65R018CFD7 + the adopted candidate-39 network (s42 on): R_on 68 ohm 2512, R_off 1 ohm, Cgs 4.7 nF
  cfd7_r68c6p8      the CM8's selected 68 ohm / 6.8 nF network on the CFD7 (S14 at the CFD7 maximum Qrr)
  *_tt125 / _tt260  same with the CFD7 body-diode transit time 125 / 260 ns (Qrr ~ typical / ~ maximum; gn study, S6)
  c8p_39            IPW65R018CM8 on proxy B (C8 600 V IPW60R016CM8_L1), R_on 39 ohm: DECISIONS 54's CM8 route, kept only
                    to compare with Infineon's 650 V CM8 model, published May 2025 and found by this study
Wrapped vendor models (kind 'wrap', wrappers.py): cm8_r39[_ttNN] (IPW65R018CM8_L1 650 V vendor model), cm8_r68c4p7
(the s42 network unchanged: FET-only swap), sic26_<VDRV>_r<R>, rch5_r<R>, rch6_r<R>.
"""
from __future__ import annotations

from common import sha

ROFF_DECK = 1.34482758621

BASE = {
    "cfd7_8p2": dict(kind="gn", model="IPW65R018CFD7_L1", ron=8.2, roff=ROFF_DECK, cgs=1e-9),
    "cfd7_c39": dict(kind="gn", model="IPW65R018CFD7_L1", ron=68, roff=1.0, cgs=4.7e-9),
    # the CM8's selected network (68 ohm / 6.8 nF) on the CFD7, to see whether it closes S14 at the CFD7 maximum Qrr
    "cfd7_r68c6p8": dict(kind="gn", model="IPW65R018CFD7_L1", ron=68, roff=1.0, cgs=6.8e-9),
    # CM8 proxy B (600 V C8 vendor model), kept only to compare with the 650 V CM8 model (wrappers.py 'cm8_*')
    "c8p_39": dict(kind="gn", model="IPW60R016CM8_L1", ron=39, roff=1.0, cgs=1e-9),
}


def get(name: str) -> dict:
    """'<dev>__q' = the same device on the as-built 8.2 ohm / deck R_off / 1 nF network: the gate-charge basis of the
    B3 heat file (device study: worst S2 gate-loop charge on that network, 382.6 nC for the CFD7)."""
    if name.endswith("__q"):
        d = get(name[:-3])
        d.update(ron=8.2, roff=ROFF_DECK, cgs=1e-9)
        return d
    base, _, tt = name.partition("_tt")
    if base in BASE:
        d = dict(BASE[base])
        if tt:
            d["tt"] = f"{int(tt)}e-9"
        return d
    import wrappers                      # SiC / IGBT / GaN wrapped vendor models
    return wrappers.get(name)


def model_identity(name: str) -> dict:
    from common import G, C8_LIB
    d = get(name)
    if d["kind"] == "gn":
        out = {"IFX_CFD7_650V.lib": sha(G.LIB)}
        if d["model"].startswith("IPW60R016CM8"):
            out["IFX_C8_600V.lib"] = sha(C8_LIB)
        return out
    import wrappers
    return wrappers.identity(name)
