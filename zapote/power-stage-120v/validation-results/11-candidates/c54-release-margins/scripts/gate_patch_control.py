#!/usr/bin/env python3
"""Control for results/b3-gate.patch (needs the gitignored b3-ratings/runs/ s53 run files and the `patch` tool).

    python3 -I scripts/gate_patch_control.py [--tmp DIR]

C1  The patched gate on the unchanged run files (R_on MPN 25121WF680JT4E) reproduces the committed margins.json rows
    and release metric exactly (the patch is a no-op for the fitted part).
C2  The patched gate on the same run files with R10/R12/R18/R20 relabelled PS122WF680JT4E (the BOM swap: same 68 ohm,
    same footprint, so heat file, copper and solves are unchanged) gives the R_on terminal margins and release margin
    that release_margins.py predicts (results/margins-c54.json).
C3  An unlisted 2512 MPN stops the patched gate.
Writes results/gate-patch-control.json."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
PS = HERE.parents[3]
B3R = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"
CASES = {"c17.5_h10": 61.0, "c22_h10": 55.0, "c28_h10": 55.0}
R_ON = ("R10", "R12", "R18", "R20")


def load_patched(tmp: Path):
    src = tmp / "b3_ratings_gate.py"
    shutil.copy(B3R / "b3_ratings_gate.py", src)
    patch = (STUDY / "results/b3-gate.patch").read_text()
    # the patch carries PS-relative paths; apply it to the lone copy
    subprocess.run(["patch", "-s", str(src)], input=patch, text=True, check=True)
    spec = importlib.util.spec_from_file_location("b3_gate_patched", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.path.insert(0, str(B3R))
    import b3_ratings_gate as orig                        # the committed gate: its BOM path is the real one
    mod.bom_mpns = lambda path=None: orig.bom_mpns()      # the copy's BOM_CSV default points outside PS
    return mod


def runs_copy(tmp: Path, mpn: str | None):
    d = tmp / f"runs_{mpn or 'fitted'}"
    d.mkdir()
    for c in CASES:
        for m in ("p0p25", "p0p5"):
            r = json.loads((B3R / "runs" / f"{c}_{m}.json").read_text())
            if mpn:
                for p in r["parts"]:
                    if p["ref"] in R_ON:
                        p["mpn"] = mpn
            (d / f"{c}_{m}.json").write_text(json.dumps(r))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmp")
    a = ap.parse_args()
    committed = json.loads((B3R / "margins.json").read_text())
    pred = json.loads((STUDY / "results/margins-c54.json").read_text())
    with tempfile.TemporaryDirectory(dir=a.tmp) as t:
        tmp = Path(t)
        g = load_patched(tmp)
        cases = ",".join(f"{c}@{b:g}" for c, b in CASES.items())
        out = {}
        r1 = g.run(runs_copy(tmp, None), cases)
        same = all(r1["cases"][c] == committed["cases"][c] for c in CASES) and r1["metrics"] == committed["metrics"]
        out["C1_fitted_reproduces_margins_json"] = same
        r2 = g.run(runs_copy(tmp, "PS122WF680JT4E"), cases)
        c2 = {}
        for c in CASES:
            for ref in R_ON:
                row = next(r for r in r2["cases"][c] if r["item"].startswith(f"{ref}: 2512 terminal"))
                c2[f"{c} {ref}"] = {"gate_margin_k": row["margin_k"], "gate_limit_c": row["limit_c"],
                                    "predicted_margin_k": pred["r_on"][c][ref]["parts"]["PS122WF680JT4E"]["margin_k"]}
        out["C2_rows"] = c2
        out["C2_rows_match"] = all(v["gate_margin_k"] == v["predicted_margin_k"] for v in c2.values())
        out["C2_release_margin_K"] = r2["metrics"]["b3_release_margin_K"]
        out["C2_release_worst"] = r2["metrics"]["release_worst_gated"]
        out["C2_release_matches_prediction"] = (r2["metrics"]["b3_release_margin_K"]
                                                == pred["release_after"]["b3_release_margin_K_after"])
        out["C2_ratchet_rated_part_margin_K"] = r2["metrics"]["b3_rated_part_margin_K"]
        out["C2_ratchet_worst"] = r2["metrics"]["worst_gated"]
        out["C2_pass"] = r2["pass"]
        try:
            g.run(runs_copy(tmp, "RC2512FK-0768RL"), cases)
            out["C3_unlisted_mpn_stops"] = False
        except SystemExit as e:
            out["C3_unlisted_mpn_stops"] = "no rating for 2512 gate resistor" in str(e)
    ok = out["C1_fitted_reproduces_margins_json"] and out["C2_rows_match"] and out["C2_release_matches_prediction"] \
        and out["C3_unlisted_mpn_stops"]
    out["PASS"] = ok
    (STUDY / "results/gate-patch-control.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "C2_rows"}, indent=1))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
