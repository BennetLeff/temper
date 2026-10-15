"""Surrogate-probe fidelity vs C1: heat capacity and the dry tau63 it would show, per disc option.

The survey gates C1's tau63 computed from the fitted h_c (fit.py), so the surrogate does
not need C1's heat capacity; this script states how close each option is and what tau63
the surrogate itself will show at C1's modelled worst contact (h 888) and nominal (1300).
Run: python surrogate.py -> surrogate.json
"""
import json
import sys
from math import pi
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import screen  # noqa: E402

C1 = screen.CANDS["C1"]
BOND_C = 2.0e6 * 1.8e-3 * 2.0e-3 * 0.10e-3          # 0.10 mm bondline, cartridge_budget.py
OPTIONS = {   # rho kg/m3, cp J/kgK, d mm, t mm
    "A: Si3N4 0.32 mm, laser-cut Ø8 (C1-exact)": (3250, 690, 8.0, 0.32),
    "B: 99.6 % alumina 0.254 mm, polished, laser-cut Ø8": (3870, 880, 8.0, 0.254),
    "C: 96 % alumina 0.25 mm, as-fired, laser-cut Ø8 (rougher face)": (3720, 880, 8.0, 0.25),
    "B-lean: 99.6 % alumina 0.254 mm, polished, cored Ø8 from one substrate": (3870, 880, 8.0, 0.254),
}
A_CONTACT = pi * (7.6e-3 / 2) ** 2


def tau(c_cap, h):
    return c_cap / (h * A_CONTACT + C1["G_LEAK"]) + screen.es.C_EL / C1["G_BOND"]


rows = {}
for k, (rho, cp, d, t) in OPTIONS.items():
    m = rho * pi * (d / 2e3) ** 2 * t / 1e3
    c = 1.1 * m * cp + BOND_C
    rows[k] = {"disc_mass_mg": round(m * 1e6, 1), "C_cap_mJ_K": round(c * 1e3, 2),
               "vs_C1_pct": round(100 * (c / (C1["C_CAP"] + BOND_C) - 1), 1),
               "tau63_surrogate_s_h888": round(tau(c, 888.0), 3), "tau63_surrogate_s_h1300": round(tau(c, 1300.0), 3)}
out = {"scope": __doc__.strip(), "C1_C_cap_mJ_K": round((C1["C_CAP"] + BOND_C) * 1e3, 2),
       "C1_tau63_s": {"h888": round(screen.tau63(C1, 888.0), 3), "h1300": round(screen.tau63(C1, 1300.0), 3)},
       "options": rows}
(HERE / "surrogate.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out["C1_C_cap_mJ_K"]), json.dumps(out["C1_tau63_s"]))
for k, v in rows.items():
    print(k, v)
