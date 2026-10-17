#!/usr/bin/env python3
"""DECISIONS 39 adoption item 3: the committed stage-19b conducted-EMI model on another board's copper.

Runs the UNMODIFIED `07-conducted-emi/s19b/emi_s19b.py` (imported, not copied) with three module attributes
redirected, so the committed s19b results stay untouched:
  * COPPER     -> the board's copper-dump.json (switch-node pours, F.Cu / B.Cu);
  * HERE       -> --out (results.json and inputs/copper-dump-s19b-summary.json land there);
  * fringe_cap_per_mm(-1.6) -> fringe_cap_per_mm(-B), B = --b-depth-mm, the B.Cu pour depth below the F.Cu pour
    (s19b hard-codes 1.6 mm). Optional --fringe-h sets the 2-D Laplace grid (s19b default 0.5 mm).
Everything else (receiver network, sources, scenarios, controls and their asserts) is the s19b model as committed.

    python3 -I emi_board.py --copper DUMP --b-depth-mm 1.658 --tag s33 --out DIR [--fringe-h 0.5]

Writes DIR/results.json (the s19b schema), DIR/inputs/copper-dump-s19b-summary.json (its board_sha256 key is
rewritten to the copper dump's sha256, see provenance) and DIR/provenance.json, and prints emi_min_margin_dB with
scorecard.py's definition (min margin_dB over scenarios.nominal).
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PS = HERE.parents[4]  # zapote/power-stage-120v
S19B = PS / "validation-results/07-conducted-emi/s19b/emi_s19b.py"


def margins(o):
    """scorecard.py's walk: every margin_dB under the object."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "margin_dB" and isinstance(v, (int, float)):
                yield v
            else:
                yield from margins(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copper", required=True)
    ap.add_argument("--b-depth-mm", type=float, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fringe-h", type=float, default=0.5)
    a = ap.parse_args()
    copper = Path(a.copper).resolve()
    assert copper.exists(), copper
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    sys.argv = [str(S19B), "--no-plots"]  # the module reads --quick / --no-plots from argv
    spec = importlib.util.spec_from_file_location("emi_s19b", S19B)
    m = importlib.util.module_from_spec(spec)
    sys.modules["emi_s19b"] = m
    spec.loader.exec_module(m)

    m.COPPER = copper
    m.HERE = out
    orig = m.fringe_cap_per_mm
    calls = []

    def fringe(z_pour_mm, h=0.5):
        z = -a.b_depth_mm if abs(z_pour_mm + 1.6) < 1e-12 else z_pour_mm
        v = orig(z, h=a.fringe_h)
        calls.append({"z_requested_mm": z_pour_mm, "z_used_mm": z, "h_mm": a.fringe_h,
                      "z_on_grid_mm": -30.0 + a.fringe_h * round((z + 30.0) / a.fringe_h), "F_per_mm": v})
        return v

    m.fringe_cap_per_mm = fringe
    m.main()

    summ_p = out / "inputs/copper-dump-s19b-summary.json"
    summ = json.loads(summ_p.read_text())
    sha = hashlib.sha256(copper.read_bytes()).hexdigest()
    summ["board_sha256"] = sha
    summ["board_sha256_note"] = "sha256 of the copper dump this summary was taken from (emi_board.py; s19b's own key is its board file's)"
    summ_p.write_text(json.dumps(summ, indent=1) + "\n")

    res = json.loads((out / "results.json").read_text())
    ms = list(margins(res.get("scenarios", {}).get("nominal", {})))
    emi_min = round(min(ms), 1)
    prov = {"tag": a.tag, "copper_dump": str(copper), "copper_dump_sha256": sha, "b_depth_mm": a.b_depth_mm,
            "fringe_h_mm": a.fringe_h, "fringe_calls": calls, "model": "07-conducted-emi/s19b/emi_s19b.py (unmodified)",
            "emi_min_margin_dB": emi_min, "emi_min_margin_dB_unrounded": min(ms),
            "definition": "scorecard.py: min margin_dB over results.json scenarios.nominal"}
    (out / "provenance.json").write_text(json.dumps(prov, indent=1) + "\n")
    print(f"{a.tag}: emi_min_margin_dB {emi_min} ({min(ms):.3f}); B depth {a.b_depth_mm} mm, fringe h {a.fringe_h} mm")


if __name__ == "__main__":
    main()
