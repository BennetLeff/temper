#!/usr/bin/env python3
"""OPEN-ITEMS S18 lane summary: PS2's B3 row and what the body-to-air path moved, from the run files and two margins files.

    python3 -I scripts/summarize.py RUNS BASE_RUNS BASE_MARGINS NEW_MARGINS [SENS_DIR:LABEL ...] > results/ps2-summary.json

RUNS: the new BASIS run files (run_basis.py --runs). BASE_RUNS: the s47 run files (pins-only PS2). BASE_MARGINS: the s47 margins.json (pins-only PS2, the committed
basis). NEW_MARGINS: run_basis.py --out of the same board with the S18 model. SENS_DIR:LABEL: extra run dirs (one case
each, gated with the matching margins file DIR/margins.json) reported as sensitivities. Reads JSON only.
"""
import json
import sys
from pathlib import Path

runs, base_runs, base_f, new_f = (Path(a) for a in sys.argv[1:5])
base, new = json.loads(base_f.read_text()), json.loads(new_f.read_text())


def ps2_row(m, c):
    return next((r for r in m["cases"][c] if r["item"].startswith("PS2:")), None)


out = {"board_sha256": sorted(set(new["board_sha256"].values())), "cases": {}, "metrics": {}, "row_deltas": {}}
for k in ("b3_release_margin_K", "release_worst_gated", "b3_laminate_margin_K", "b3_rated_part_margin_K",
          "b3_advisory_margin_K", "worst_gated"):
    out["metrics"][k] = {"s47_pins_only": base["metrics"].get(k), "s18_body_air": new["metrics"].get(k)}
out["pass"] = {"s47_pins_only": base["pass"], "s18_body_air": new["pass"]}
for c, rows in new["cases"].items():
    bay = new["basis"]["cases"][c]["bay_c"]
    r25 = json.loads((runs / f"{c}_p0p25.json").read_text())
    r05 = json.loads((runs / f"{c}_p0p5.json").read_text())
    b25 = json.loads((base_runs / f"{c}_p0p25.json").read_text())
    p = {m: next(q for q in r["parts"] if q["ref"] == "PS2") for m, r in (("0.25", r25), ("0.5", r05))}
    row = ps2_row(new, c)
    shift = bay - 50.0
    out["cases"][c] = {
        "bay_c": bay, "role": new["basis"]["cases"][c]["role"],
        "gated_row": row,
        "mesh_0p25": {k: (round(v + shift, 2) if k.endswith("_c") and isinstance(v, float) else v)
                      for k, v in p["0.25"].items() if k in ("loss_w", "pins_w", "body_air_w", "g_air_w_k", "g_pins_w_k",
                                                               "case_c", "pad_mean_c", "pad_max_cell_c", "env_upper_c",
                                                               "board_under_body_c", "board_ring_c", "local_air_rule_c")},
        "mesh_0p5": {k: (round(v + shift, 2) if k.endswith("_c") and isinstance(v, float) else v)
                     for k, v in p["0.5"].items() if k in ("pins_w", "body_air_w", "case_c", "pad_max_cell_c",
                                                             "board_ring_c")},
        "pins_only_s47_0p25": {
            k: round(v + shift, 2) for k, v in next(q for q in b25["parts"] if q["ref"] == "PS2").items()
            if k in ("pad_mean_c", "pad_max_cell_c", "tj_c")},
        "balance_rel": [r25["balance"]["balance_rel"], r05["balance"]["balance_rel"]],
    }
    # every row common to both margins files: how far it moved
    old = {r["item"]: r for r in base["cases"].get(c, [])}
    d = {r["item"]: round(r["margin_k"] - old[r["item"]]["margin_k"], 2) for r in rows if r["item"] in old}
    moved = {k: v for k, v in d.items() if v != 0}
    out["row_deltas"][c] = {"rows_compared": len(d), "rows_moved": len(moved),
                            "max_abs_move_k": max((abs(v) for v in d.values()), default=0.0),
                            "moved": dict(sorted(moved.items(), key=lambda t: -abs(t[1]))[:12]),
                            "new_rows": [r["item"] for r in rows if r["item"] not in old],
                            "dropped_rows": [k for k in old if k not in {r["item"] for r in rows}]}
out["sensitivities"] = {}
for arg in sys.argv[5:]:
    d, _, label = arg.partition(":")
    m = json.loads((Path(d) / "margins.json").read_text())
    c = next(iter(m["cases"]))
    r25 = json.loads((Path(d) / f"{c}_p0p25.json").read_text())
    bay = m["basis"]["cases"][c]["bay_c"]
    p = next(q for q in r25["parts"] if q["ref"] == "PS2")
    out["sensitivities"][label] = {"case": c, "sens": r25.get("sens"), "ps2_row": ps2_row(m, c),
                                   "release_margin_k": m["metrics"].get("b3_release_margin_K"),
                                   "release_worst": m["metrics"].get("release_worst_gated"),
                                   "pins_w_0p25": p.get("pins_w"), "case_c_0p25": None if "case_c" not in p
                                   else round(p["case_c"] + bay - 50.0, 2)}
print(json.dumps(out, indent=1))
