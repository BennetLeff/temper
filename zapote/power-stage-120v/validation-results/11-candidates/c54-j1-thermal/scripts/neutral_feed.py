#!/usr/bin/env python3
"""Where the J1 hot pole's copper heat comes from: the task-04 DC fields of ac_l_in and ac_n_in on the s53 board.

    python3 -I scripts/neutral_feed.py      -> results/neutral_feed.json

Inputs: round5-native21/outputs/ac_{l,n}_main-p0125-pl18.json (committed: path resistance, barrel hop heat) and the
matching -heat.npz nodal Joule maps (gitignored; when present the strip / near-pad sums are recomputed, otherwise the
committed results/neutral_feed.json is kept). All at 15 A, 20 C copper (the task-04 drive); 13.5 A scales by
(13.5/15)^2. Needs numpy only when the npz files are read.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PS = ROOT.parents[2]
OUTD = PS / "validation-results/04-board-current-thermal/round5-native21/outputs"
OUT = ROOT / "results" / "neutral_feed.json"
S53_BOARD = "82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27"
J1 = {"ac_l_main": (274.6, 9.2), "ac_n_main": (284.12, 9.2)}
STRIP = (283.5, 289.5, 3.4, 26.6)         # the ac_n_in B.Cu edge strip (copper.json zone 'ac_n_in J1-RV1-C1-L1')


def main():
    out = {"drive_a": 15.0, "scale_to_13p5A": (13.5 / 15.0) ** 2, "nets": {}}
    have_npz = all((OUTD / f"{n}-p0125-pl18-heat.npz").exists() for n in J1)
    if have_npz:
        import numpy as np
    for n, (x0, y0) in J1.items():
        d = json.loads((OUTD / f"{n}-p0125-pl18.json").read_text())
        assert d["board_sha256"] == S53_BOARD
        j1_barrel = sum(h["joule_w"] for h in d["barrel_hop_heat"]
                        if abs(h["xy_mm"][0] - x0) < 0.01 and abs(h["xy_mm"][1] - y0) < 0.01)
        row = {"net": d["net"], "source_pad": d["source_pad"], "sink_pad": d["sink_pad"], "r_mohm": round(d["r_ohm"] * 1e3, 4),
               "loss_w": round(d["loss_w"], 4), "j1_barrel_hop_w": round(j1_barrel, 4),
               "max_a_per_mm": {k: round(v["amps_per_mm"], 3) for k, v in d["layer_max_a_per_mm"].items()
                                if v["amps_per_mm"] > 1e-6}}
        if have_npz:
            z = np.load(OUTD / f"{n}-p0125-pl18-heat.npz")
            near, strip = {}, 0.0
            for r in (3, 6, 10, 20):
                s = 0.0
                for L in ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu"):
                    xx, yy = np.meshgrid(z[L + "_x_mm"], z[L + "_y_mm"], indexing="ij")
                    s += float(z[L + "_joule_w"][np.hypot(xx - x0, yy - y0) < r].sum())
                near[f"r{r}mm"] = round(s, 4)
            xx, yy = np.meshgrid(z["B_Cu_x_mm"], z["B_Cu_y_mm"], indexing="ij")
            m = (xx >= STRIP[0]) & (xx <= STRIP[1]) & (yy >= STRIP[2]) & (yy <= STRIP[3])
            strip = float(z["B_Cu_joule_w"][m].sum())
            row.update(sheet_joule_within_w=near, edge_strip_joule_w=round(strip, 4))
        out["nets"][n] = row
    if not have_npz:
        old = json.loads(OUT.read_text())
        for n in J1:
            for k in ("sheet_joule_within_w", "edge_strip_joule_w"):
                out["nets"][n][k] = old["nets"][n][k]
    nn = out["nets"]["ac_n_main"]
    local = nn["edge_strip_joule_w"] + nn["j1_barrel_hop_w"]
    # mirrored F.Cu strip: the strip's sheet heat halves (two equal sheets in parallel); at J1.2 the current enters the
    # F.Cu half directly and only the B.Cu half takes the barrel hop: hop heat x (1/2)^2
    after = 0.5 * nn["edge_strip_joule_w"] + 0.25 * nn["j1_barrel_hop_w"]
    out["neutral_local_heat"] = {"now_w_15A": round(local, 4), "mirrored_w_15A": round(after, 4),
                                 "reduction": round(1 - after / local, 3),
                                 "now_w_13p5A": round(local * out["scale_to_13p5A"], 4),
                                 "line_side_total_w_13p5A": round(out["nets"]["ac_l_main"]["loss_w"] * out["scale_to_13p5A"], 4),
                                 "r_ratio_n_over_l": round(nn["r_mohm"] / out["nets"]["ac_l_main"]["r_mohm"], 2)}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["neutral_local_heat"]))


if __name__ == "__main__":
    main()
