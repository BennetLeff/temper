#!/usr/bin/env python3
"""DAC-image error (rev_e_spurs mechanism 3) with U5's ideal 284 kHz pole replaced by the simulated
DAC -> SOURCE transfer of each U5 part (validation/stability-full-chain/source_stage.json, u5_parts).

python3 validation/power-spurs/dac_images_u5.py   ->  dac_images_u5.json

The image level, codec anti-alias response and calibrated DUT terms are rev_e_spurs.py's; only the
source pole changes.  The transfer is interpolated in log frequency on source_stage.py's HF grid."""
import json
from pathlib import Path

import numpy as np

import rev_e_spurs as rs

HERE = Path(__file__).resolve().parent
stage = json.loads((HERE.parent / "stability-full-chain/source_stage.json").read_text())["u5_parts"]


def interp(tab):
    keys = sorted(tab, key=float)
    lf = np.log10([float(k) for k in keys])
    mag = np.abs([complex(*tab[k]) for k in keys])
    return lambda x: float(np.interp(np.log10(x), lf, mag))


MODELS = {"ideal pole (rev_e_spurs)": None}
MODELS.update({name: interp(row["dac_to_source"]) for name, row in stage.items()})


def image_error(f, fmod, z, hmag):
    tot = 0.0
    for j in (1, 2):
        for sgn in (-1, 1):
            fk = j * fmod + sgn * f
            src = abs(rs.src_pole(fk) / rs.src_pole(f)) if hmag is None else hmag(fk) / hmag(f)
            level = abs(np.sinc(fk / fmod) / np.sinc(f / fmod)) * src
            _, cal = rs.dut_terms(z, f, fk)
            tot += level * abs(rs.aa(fk) / rs.aa(f)) * abs(cal)
    return tot


out = {}
for dut in ("coil 50 uH + 0.5 ohm", "C 500 nF"):
    for f in (27000.0, 60000.0, 85000.0):
        key = f"{dut}, {f / 1e3:g} kHz"
        out[key] = {m: {k: 100 * image_error(f, fm, rs.DUTS[dut], h) for k, fm in rs.F_MOD.items()}
                    for m, h in MODELS.items()}
        print(f"{key}, calibrated image error % ({' / '.join(rs.F_MOD)}):")
        for m, row in out[key].items():
            print(f"   {m:28s} " + "  ".join(f"{v:7.4f}" for v in row.values()))
(HERE / "dac_images_u5.json").write_text(json.dumps(out, indent=1) + "\n")
