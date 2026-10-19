"""Build-fidelity sensitivity: how much do the errors a home-built former makes move L and R? (supports README D5/D6)

Each case perturbs the R1 winding or the ferrite the way a particular former build would, and re-solves the 2D model
(L, R carry the 3D factors k_free / k_L_pan / k_R_pan as everywhere else).
  - CNC / printed comb former: bundle sits up to 0.3 mm proud of the notch floor; roof 0.2 mm thicker (print tolerance)
  - no-printer former (FR4 roof sheet, pencil marks + spacer cord): each turn's radius off by a random error
    (sigma 0.3 / 0.6 mm, 6 seeds each), or every pitch off by a systematic +/-3 % (spacer cord too thick / thin; the
    section starts at its nominal radius and grows from there)
  - bars glued 2 mm further out (template misplaced), or the bar set 0.5 mm lower (thicker glue line under the roof)
Free-air L at 40 kHz, and loaded L and reflected R on the 430 pan (mu 200, 240 mm) at 40 kHz.
Run: .venv/bin/python model/fidelity.py -> model/results/fidelity.json (~1 min, 8 workers)
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coil_geometry as G  # noqa: E402
import coil_model as CM  # noqa: E402
import materials as M  # noqa: E402

FACT = json.loads((HERE / "results" / "compare_3d.json").read_text())["factors"]


@dataclass(frozen=True)
class RingWinding:
    """A winding given directly by its rings (for perturbed builds); quacks like G.Winding for coil_model."""
    sections: tuple
    ring_list: tuple
    z_c: float = G.Z_WIND_C
    d_bundle: float = G.D_BUNDLE

    def rings(self):
        return list(self.ring_list)


def jittered(w, sigma, seed):
    rng = np.random.default_rng(seed)
    return RingWinding(w.sections, tuple((r + rng.normal(0.0, sigma), wt) for r, wt in w.rings()))


def pitch_scaled(w, k):
    secs = tuple(G.Section(s.r0, s.r0 + (s.r1 - s.r0) * k, s.turns) for s in w.sections)
    return G.Winding(sections=secs, z_c=w.z_c, name=f"pitch x{k}")


def cases():
    w = G.R1
    out = [("nominal", w, {}), ("bundle_z+0.3", G.Winding(w.sections, z_c=G.Z_WIND_C + 0.3), {}),
           ("roof+0.2 (bars 0.2 lower)", w, dict(z_bar=(G.Z_BAR[0] - 0.2, G.Z_BAR[1] - 0.2))),
           ("bars 0.5 lower", w, dict(z_bar=(G.Z_BAR[0] - 0.5, G.Z_BAR[1] - 0.5))),
           ("bars 2 mm further out", w, dict(bar_r=(G.BAR_R[0] + 2.0, G.BAR_R[1] + 2.0))),
           ("pitch +3 %", pitch_scaled(w, 1.03), {}), ("pitch -3 %", pitch_scaled(w, 0.97), {})]
    for sigma in (0.3, 0.6):
        for seed in range(6):
            out.append((f"jitter_sigma{sigma}_seed{seed}", jittered(w, sigma, seed), {}))
    return out


def run(args):
    name, w, kw = args
    free = CM.build(w, **kw).solve(40e3)
    pan = M.pan("ss430", radius_mm=120.0)
    pan["f_grid"] = 40e3
    loaded = CM.build(w, enclosure=True, pan=pan, **kw).solve(40e3)
    return dict(case=name, L_free_uH=free["L"] * 1e6 * FACT["k_free"], L_430_uH=loaded["L"] * 1e6 * FACT["k_L_pan"],
                R_430_ohm=loaded["R"] * FACT["k_R_pan"])


def main():
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(run, cases()))
    nom = rows[0]
    for r in rows:
        r["dL_free_pct"] = 100 * (r["L_free_uH"] / nom["L_free_uH"] - 1)
        r["dL_430_pct"] = 100 * (r["L_430_uH"] / nom["L_430_uH"] - 1)
        r["dR_430_pct"] = 100 * (r["R_430_ohm"] / nom["R_430_ohm"] - 1)
    summ = {}
    for sigma in (0.3, 0.6):
        j = [r for r in rows if r["case"].startswith(f"jitter_sigma{sigma}_")]
        summ[f"jitter_sigma{sigma}"] = {k: dict(min=min(r[k] for r in j), max=max(r[k] for r in j))
                                        for k in ("dL_free_pct", "dL_430_pct", "dR_430_pct")}
    out = dict(note=__doc__, rows=rows, jitter_summary=summ)
    (HERE / "results" / "fidelity.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        print(f"{r['case']:28s} L_free {r['L_free_uH']:6.2f} ({r['dL_free_pct']:+5.2f} %)  L_430 {r['L_430_uH']:6.2f} "
              f"({r['dL_430_pct']:+5.2f} %)  R_430 {r['R_430_ohm']:.3f} ({r['dR_430_pct']:+5.2f} %)")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
