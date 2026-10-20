"""Coil-eye field sweep for the sensor-r3 cartridge, over coil variants (not just the R36 coil).

Uses study 06's axisymmetric solver read-only (temper-r32-studies/06-emi-strayfield/{study,fem_axi}.py).
Per variant: wind N turns for a 70 uH free-air coil (L scales as N^2), drive 28 A rms, and report the peak B
on the sensor axis at the spring top (Z95) and the capillary (Z105), then scale the committed G7 field screen
(cad/field-screen.json: spring 0.0471 W and wave spring 1.479 W at 100 kHz / 20 mT, pair pickup 0.0766 mV at
60 kHz with dBz/dz 0.293 T/m) to that field. Heating scales with (f B)^2, pickup with f dBz/dz.

Variants other than "R36" use ASSUMED coil radii (the RCA 12A3 coil has not been measured).
Run: <cadenv python> field_sweep.py  -> field-sweep.json
"""
import json, math, sys
from pathlib import Path
import numpy as np

sys.dont_write_bytecode = True
S06 = Path(__file__).resolve().parents[2] / "temper-r32-studies/06-emi-strayfield"
sys.path.insert(0, str(S06))
import study  # noqa: E402
from fem_axi import Model  # noqa: E402

I_PK = 28.0 * math.sqrt(2)
L_TARGET = 70e-6
REF = {"f": 100e3, "B": 20e-3, "spring_W": 0.04709890115929788, "wave_W": 1.479215192249908,
       "pair_f": 60e3, "pair_g": 0.293, "pair_mV": 0.0766}
G_SPRING = 0.00417           # W/K, cad/field-screen.json
PAN = {"none": None, "steel_mu100": ("steel_pan", 100.0), "steel_mu5": ("steel_pan", 5.0), "alu": ("Al1100", 1.0)}
COILS = {"R36 (21.9 t, r22-116)": (0.022, 0.116), "narrow (assumed r20-90)": (0.020, 0.090),
         "wide-eye (assumed r30-110)": (0.030, 0.110)}


def build(ri, ro, ferrite, pan, turns):
    m = Model(study.R_GRID, study.Z_GRID)
    if ferrite:
        fm = m.box(ri + 0.003, ro + 0.002, 0.0935, 0.0975)
        p = np.minimum(1.0, 8 * 0.020 / (2 * np.pi * m.RC))
        m.mur[fm] = (1 + p * (study.MU_FERRITE - 1))[fm]
    m.add_conductor("base", 0.0, 0.221, 0.008, 0.011, study.SIG["Al5052"])
    m.add_conductor("roof_ring", 0.158, 0.221, 0.102, 0.105, study.SIG["Al5052"])
    if pan:
        name, mu = pan
        m.add_conductor("pan", 0.0, 0.110, 0.110, 0.112, study.SIG[name], mu)
    m.set_coil(ri, ro, 0.0985, 0.1025, turns, I_PK)
    return m


def at(m, r, z):
    Br, Bz = m.B_at(np.array([r]), np.array([z]))
    return abs(Br[0]), abs(Bz[0])


rows = []
for cname, (ri, ro) in COILS.items():
    for ferrite in (True, False):
        m1 = build(ri, ro, ferrite, None, 1)
        L1 = m1.solve(40e3)["L"]
        N = math.sqrt(L_TARGET / L1)
        for pname, pan in PAN.items():
            for f in (40e3, 60e3, 100e3):
                m = build(ri, ro, ferrite, pan, N)
                res = m.solve(f)
                _, bz95 = at(m, 0.0, 0.095)
                _, bz105 = at(m, 0.0, 0.105)
                br, _ = at(m, 0.0015, 0.1055)
                B = max(bz95, bz105)
                g = abs(bz105 - bz95) / 10e-3
                sc = (f * B) ** 2 / (REF["f"] * REF["B"]) ** 2
                dT = REF["spring_W"] * sc / G_SPRING
                rows.append(dict(coil=cname, ferrite=ferrite, pan=pname, f_kHz=f / 1e3, turns=round(N, 2),
                                 L_loaded_uH=round(res["L"] * 1e6, 1), B_spring_mT=round(bz95 * 1e3, 3),
                                 B_capillary_mT=round(bz105 * 1e3, 3), dBz_dz_T_per_m=round(g, 3),
                                 spring_W=REF["spring_W"] * sc, spring_dT_K=round(dT, 3),
                                 wave_spring_W=REF["wave_W"] * sc,
                                 pair_pickup_mV=round(REF["pair_mV"] * (f * g) / (REF["pair_f"] * REF["pair_g"]), 4)))
        print(cname, "ferrite" if ferrite else "air", "N", round(N, 2), flush=True)
Path(__file__).with_name("field-sweep.json").write_text(json.dumps(rows, indent=1))
w = max(rows, key=lambda r: r["spring_dT_K"]); p = max(rows, key=lambda r: r["pair_pickup_mV"])
print("worst spring:", w); print("worst pickup:", p)
