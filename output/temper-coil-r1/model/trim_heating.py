"""What the tune move costs in pan heating: R1 with the outer section trimmed (or the spare turn kept), on the 430 pan
(mu 200, 240 mm) and cast iron (mu 100), 40 kHz. Loaded L, reflected R and the rim share (heat at r >= 92 mm).
Feeds the tune rule in BUILD-AND-MEASURE.md (how far the outer section may be trimmed). R43's "keep >= 6 outer turns" came
from study 09; this checks it on the R1 layout.
Run: .venv/bin/python model/trim_heating.py -> model/results/trim_heating.json (~30 s)
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coil_geometry as G  # noqa: E402
import coil_model as CM  # noqa: E402
import materials as M  # noqa: E402

FACT = json.loads((HERE / "results" / "compare_3d.json").read_text())["factors"]
FREE = json.loads((HERE / "results" / "free_air.json").read_text())["candidates"]
STATES = {"R1_plus_spare": 1.0, "R1": 0.0, "R1_trim-0.5": -0.5, "R1_trim-1": -1.0, "R1_trim-1.5": -1.5, "R1_trim-2": -2.0}


def winding(delta):
    return G.with_spare(G.R1, delta) if delta > 0 else (G.trimmed(G.R1, -delta) if delta < 0 else G.R1)


def run(args):
    key, cls = args
    w = winding(STATES[key])
    pan = M.pan(cls, radius_mm=120.0)
    pan["f_grid"] = 40e3
    m = CM.build(w, enclosure=True, pan=pan)
    r = m.solve(40e3)
    prof = CM.pan_profile(m)
    return dict(state=key, outer_turns=w.sections[1].turns, pan=cls, L_free_uH=FREE[key]["L_free_uH"],
                L_loaded_uH=r["L"] * 1e6 * FACT["k_L_pan"], R_refl_ohm=r["R"] * FACT["k_R_pan"],
                rim_share=sum(p["share"] for p in prof if p["r_mm"][0] >= 92),
                centre_share=sum(p["share"] for p in prof if p["r_mm"][1] <= 55))


def main():
    jobs = [(k, c) for k in STATES for c in ("ss430", "cast_iron")]
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(run, jobs))
    (HERE / "results" / "trim_heating.json").write_text(json.dumps(dict(note=__doc__, rows=rows), indent=1) + "\n")
    for r in rows:
        print(f"{r['state']:14s} out {r['outer_turns']:.2f} {r['pan']:9s} L_free {r['L_free_uH']:5.1f} L_loaded {r['L_loaded_uH']:5.1f} "
              f"R {r['R_refl_ohm']:.2f} rim {r['rim_share'] * 100:4.1f} % centre {r['centre_share'] * 100:4.1f} %")


if __name__ == "__main__":
    main()
