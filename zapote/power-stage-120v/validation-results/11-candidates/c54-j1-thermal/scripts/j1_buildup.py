#!/usr/bin/env python3
"""Reproduce the J1 (Phoenix 1714971) release-case temperature of OPEN-ITEMS S21: bay air -> B3 pad copper -> own rise.

    python3 -I scripts/j1_buildup.py            -> results/j1_buildup.json (+ results/b3_j1_probe_s53.json if the run
                                                   files are present)

Inputs
  * B3 BASIS run files of the s53 board of record (82af7bd9, DECISIONS 75), b3-ratings/runs/c17.5_h10_p0p{25,5}.json
    and c28_h10_*.json (gitignored). When present they are read and their J1 probe rows are written, with each file's
    sha256, to results/b3_j1_probe_s53.json (committed); when absent that extract is used. The committed
    b3-ratings/margins.json carries the same board sha256 (checked).
  * The S21 records in git: temp-ratings-2026-10-15/results.json at 723589bc9 (the s47 board, where 104.6 C comes
    from) and at HEAD (the s52 re-base, 103.1 C).
Estimator (b3_ratings_gate.est, the S21 rule): pad = Q(0.25) + 3 |Q(0.25) - Q(0.5)| + (bay - 50 C) on the J1 pad-copper
probe 'pad_max_cell_c' (mounting layer F.Cu, both pads: the hotter pole); + own rise 23 K x (13.5 / 32)^2 = 4.09 K
(ratings_table.J1_RISE: the p.6 curve's knee, 32 A flat to 82 C on 6 mm2 = 23 K, scaled I^2).
"""
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PS = ROOT.parents[2]                      # zapote/power-stage-120v
B3R = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"
RUNS = B3R / "runs"
EXTRACT = ROOT / "results" / "b3_j1_probe_s53.json"
OUT = ROOT / "results" / "j1_buildup.json"
TR = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15/results.json"
CASES = {"c17.5_h10": 61.0, "c28_h10": 55.0}
TAMB_MODEL_C, K_MESH = 50.0, 3.0
S53_BOARD = "82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27"
OWN_RISE_K = 23.0 * (13.5 / 32.0) ** 2


def extract():
    rows = {}
    for c in CASES:
        rows[c] = {}
        for m in ("p0p25", "p0p5"):
            f = RUNS / f"{c}_{m}.json"
            raw = f.read_bytes()
            r = json.loads(raw)
            p = r["probes"]["J1"]
            rows[c][m] = {"file": f.name, "sha256": hashlib.sha256(raw).hexdigest(), "board_sha256": r["board_sha256"],
                          "bay_c": r["bay_c"], "i_line_a": r["i_line_a"], "i_t_a": r["i_t_a"],
                          "copper_temp_model": r["copper_temp_model"]["model"], **p}
    EXTRACT.write_text(json.dumps(rows, indent=1) + "\n")
    return rows


def git_json(rev, path):
    out = subprocess.run(["git", "-C", str(PS), "show", f"{rev}:zapote/power-stage-120v/{path}"], check=True,
                         capture_output=True).stdout
    return json.loads(out)


def j1_line(d):
    return next(l for l in d["lines"] if l["mpn"] == "1714971")


def main():
    have_runs = all((RUNS / f"{c}_{m}.json").exists() for c in CASES for m in ("p0p25", "p0p5"))
    rows = extract() if have_runs else json.loads(EXTRACT.read_text())
    margins = json.loads((B3R / "margins.json").read_text())
    out = {"own_rise_k_s21": round(OWN_RISE_K, 3), "source_runs": "run files" if have_runs else "committed extract",
           "cases": {}}
    for c, bay in CASES.items():
        a, b = rows[c]["p0p25"], rows[c]["p0p5"]
        for r in (a, b):
            assert r["board_sha256"] == S53_BOARD == margins["board_sha256"][c], "board is not the s53 board of record"
            assert r["bay_c"] == bay and r["i_line_a"] == 13.5 and r["copper_temp_model"] == "hot-iterated"
        q25, q05 = a["pad_max_cell_c"], b["pad_max_cell_c"]
        mesh = K_MESH * abs(q25 - q05)
        pad = q25 + mesh + (bay - TAMB_MODEL_C)
        # per-pad split: pad_mean is the area mean of both pads (equal 3.0 mm pads), pad_max_padmean the hotter pad's
        # mean, so the cooler pad's mean is 2 x mean - hotter (both at model ambient)
        cool = 2 * a["pad_mean_c"] - a["pad_max_padmean_c"]
        out["cases"][c] = {
            "bay_c": bay,
            "b3_pad_max_cell_p0p25_c_at_model_50C": round(q25, 3),
            "b3_pad_max_cell_p0p5_c_at_model_50C": round(q05, 3),
            "pad_rise_over_model_ambient_k": round(q25 - TAMB_MODEL_C, 3),
            "mesh_allowance_k": round(mesh, 3),
            "bay_shift_k": bay - TAMB_MODEL_C,
            "pad_est_c": round(pad, 2),
            "own_rise_k": round(OWN_RISE_K, 2),
            "j1_est_c": round(pad + OWN_RISE_K, 2),
            "margin_to_105_k": round(105.0 - pad - OWN_RISE_K, 2),
            "hot_pad_mean_est_c": round(a["pad_max_padmean_c"] + bay - TAMB_MODEL_C, 2),
            "cool_pad_mean_est_c": round(cool + bay - TAMB_MODEL_C, 2),
            "hot_minus_cool_pad_k": round(a["pad_max_padmean_c"] - cool, 2),
        }
    # the S21 records
    hist = {}
    for name, rev in (("s47 (OPEN-ITEMS S21 text, commit 723589bc9)", "723589bc9"), ("s52 re-base (HEAD)", "HEAD")):
        rel = j1_line(git_json(rev, TR))["release"]
        hist[name] = {"pad_c": rel["pad_c"], "own_rise_k": rel["extra_k"], "est_c": rel["est_c"],
                      "margin_k": rel["margin_k"]}
    out["s21_records"] = hist
    rel = out["cases"]["c17.5_h10"]
    s47 = hist["s47 (OPEN-ITEMS S21 text, commit 723589bc9)"]
    assert abs(s47["pad_c"] + OWN_RISE_K - 104.6) < 0.06, s47
    out["check"] = (f"104.6 C (S21) = s47 pad {s47['pad_c']} + {OWN_RISE_K:.2f} K; on the s53 board of record the same "
                    f"rule gives {rel['j1_est_c']:.2f} C = bay 61 + pad rise {rel['pad_rise_over_model_ambient_k']:.2f} "
                    f"+ mesh {rel['mesh_allowance_k']:.2f} + own {OWN_RISE_K:.2f} K")
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(out["check"])
    for c, v in out["cases"].items():
        print(f"  {c}: pad {v['pad_est_c']} C (hot pad mean {v['hot_pad_mean_est_c']}, cool pad mean "
              f"{v['cool_pad_mean_est_c']}), J1 {v['j1_est_c']} C, margin {v['margin_to_105_k']:+.2f} K")


if __name__ == "__main__":
    main()
