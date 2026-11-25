"""Extract the C49 controller board into one JSON: every footprint (local courtyard, local pads, world pose,
block) and the routed copper (track length per layer and per net, vias).

Read-only. Standard library only.

    python3 -I scripts/extract_c49.py [path/to/controller.kicad_pcb]  -> results/c49-board.json

Input: the C49 board of record, C/pcb/controller.kicad_pcb, sha256 b3af25b8... (C/ORDER.md:24-25).
`kicad_courtyard.py` is a verbatim copy of output/temper-board-shrink-r1/scripts/kicad_courtyard.py.
Blocks: the same atopile-path rules as output/temper-board-shrink-r1/scripts/measure_controller.py
BLOCKS (copied below so this folder runs on its own).

World frame (C/layout/world.py:20-38): X = kx - 58, Y = 110 - ky. Local footprint frame: KiCad's
footprint coordinates (y down), rotation CCW on screen; kicad_courtyard.to_board() maps it.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kicad_courtyard as kc  # noqa: E402

C = Path("/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/controller")
DEFAULT_PCB = C / "pcb/controller.kicad_pcb"
EXPECTED_SHA = "b3af25b892858e0c89624ed72ce207e9e1f25d6429aaed4f7814804229f8b1bb"
OX, OY = 58.0, 110.0

# measure_controller.py BLOCKS (shrink-r1), first match wins
BLOCKS = [
    ("connectors", lambda p, r: r.startswith("J")),
    ("mcu", lambda p, r: p in {"mcu", "c_mcu_bulk", "c_mcu_hf", "c_en", "r_en", "r_dc_pd", "r_cs_oled_pu", "r_cs_exp_pu"}),
    ("buck_3v3", lambda p, r: p in {"u_3v3", "l_3v3", "c_in_bulk", "c_ss_3v3", "c_bst_3v3", "c_in3a", "c_in3b", "c_out3a",
                                    "c_out3b", "c_out3c", "r_en3_top", "r_en3_bot", "r_fb3_top", "r_fb3_bot"}),
    ("blower_buck", lambda p, r: p in {"u_12", "l_12", "c_blw_bulk", "c_ss_12", "c_bst_12", "c_in12a", "c_in12b", "c_in12c",
                                       "c_out12a", "c_out12b", "r_en12_top", "r_en12_bot", "r_fb12_top", "r_fb12_bot",
                                       "r_fan_inj", "c_fan_ctl", "r_fan_pwm_filt", "r_fan_pwm_pd", "q_fan_off",
                                       "r_fan_off_pd", "r_blw_pg_top", "r_blw_pg_bot", "r_tach_pu", "r_tach_series",
                                       "c_tach", "d_tach", "d_merge"}),
    ("rtd", lambda p, r: p.startswith("rtd_pan.")),
    ("thermal_sense", lambda p, r: p.startswith("thermal.")),
    ("interlock", lambda p, r: p.startswith("interlock.") or p in {"u_permit", "c_permit", "r_run_en_pd", "r_permit_pd"}),
    ("trip_glue", lambda p, r: p in {"u_rail", "c_rail", "c_rail_sense", "r_rail_sense", "r_rail_pu", "u_live", "c_live",
                                     "u_rail_inv", "c_rail_inv", "u_rb", "c_rb", "u_runaway", "c_runaway", "c_runaway_th",
                                     "r_runaway_top", "r_runaway_bot", "u_runaway_or", "c_runaway_or", "u_rim_trip",
                                     "c_rim_trip", "r_rim_th_top", "r_rim_th_bot", "c_rim_th"}),
    ("capmode", lambda p, r: p.startswith(("u_cm_", "c_cm_", "r_cm_"))),
    ("rms", lambda p, r: p.startswith(("u_rms", "c_rms", "r_rms", "u_adc", "c_adc", "r_adc", "d_rms"))),
    ("d11_ctmon", lambda p, r: p.startswith(("u_rx", "r_rx", "c_rx", "u_ref", "r_ref", "r_bias_top", "r_bias_bot",
                                             "r_vbus_adc", "c_vbus_adc", "r_ct_mon_def", "r_ct_adc", "c_ct_adc", "u_buf1",
                                             "c_buf1"))),
    ("ntc_afe", lambda p, r: p.startswith(("u_buf2", "c_buf2", "u_buf3", "c_buf3", "r_hs_", "c_hs_", "r_coil_", "c_coil_",
                                           "r_m12", "c_m12", "d_m12", "r_rim_", "c_rim_", "d_rim"))),
    ("j4_if", lambda p, r: p.startswith(("r_pwm_", "rpd_pwm_", "r_ct_zc", "r_line_zc", "r_bias_ser", "r_bias_pd", "c_bias"))),
    ("expander", lambda p, r: p in {"u_io", "c_io", "r_scl_pu", "r_sda_pu"}),
    ("ui_bus", lambda p, r: p.startswith(("u_esd_ui", "c_esd_ui", "rs_ui_", "u_v5", "c_v5", "r_v5"))),
]


def block_of(path, ref):
    for name, rule in BLOCKS:
        if rule(path or "", ref or ""):
            return name
    return "unassigned"


def local_pads(fp, fp_rot):
    out = []
    for pd in kc.kids(fp, "pad"):
        at = kc.kid(pd, "at")
        lx, ly = float(at[1]), float(at[2])
        pabs = float(at[3]) if len(at) > 3 else 0.0
        rel = (pabs - fp_rot) % 180.0
        sz = kc.kid(pd, "size")
        w, h = float(sz[1]), float(sz[2])
        if abs(rel - 90.0) < 1:
            w, h = h, w
        net = kc.kid(pd, "net")
        out.append({"num": pd[1], "kind": pd[2], "net": (net[-1] if net else None),
                    "x": lx, "y": ly, "w": w, "h": h})
    return out


def main(argv):
    pcb = Path(argv[1]) if len(argv) > 1 else DEFAULT_PCB
    sha = hashlib.sha256(pcb.read_bytes()).hexdigest()
    board = kc.load(pcb)
    parts = []
    for fp in kc.kids(board, "footprint"):
        at = kc.kid(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        props = {p[1]: p[2] for p in kc.kids(fp, "property") if len(p) > 2}
        attr = kc.kid(fp, "attr")
        loops, pts, fallback = kc._local_courtyard(fp)
        area = sum(kc.shoelace(l) for l in loops) if loops and not fallback else None
        ref = props.get("Reference")
        path = props.get("SourceInstance")
        parts.append({
            "ref": ref, "path": path, "block": block_of(path, ref), "lib": fp[1].split(":")[-1],
            "mpn": props.get("MPN") or props.get("Value"),
            "tht": "through_hole" in (attr[1:] if attr else []),
            "world": [round(fx - OX, 4), round(OY - fy, 4), rot],
            "crtyd_local": [[[round(x, 4), round(y, 4)] for x, y in l] for l in loops],
            "crtyd_area_mm2": round(area, 4) if area is not None else None,
            "pads_local": local_pads(fp, rot),
        })

    # routed copper
    per_layer = defaultdict(lambda: {"segments": 0, "length_mm": 0.0})
    per_net = defaultdict(float)
    per_net_layer = defaultdict(lambda: defaultdict(float))
    width_hist = defaultdict(float)
    for s in kc.kids(board, "segment"):
        (x1, y1), (x2, y2) = kc.xy(kc.kid(s, "start")), kc.xy(kc.kid(s, "end"))
        L = math.hypot(x2 - x1, y2 - y1)
        lay = kc.kid(s, "layer")[1]
        net = kc.kid(s, "net")[-1]
        w = float(kc.kid(s, "width")[1])
        per_layer[lay]["segments"] += 1
        per_layer[lay]["length_mm"] += L
        per_net[net] += L
        per_net_layer[net][lay] += L
        width_hist[f"{w:g}"] += L
    vias = defaultdict(int)
    for v in kc.kids(board, "via"):
        vias[kc.kid(v, "net")[-1]] += 1
    edge = kc.edge_cuts(board)

    out = {
        "schema": "temper.controller-shrink-c60.c49-board.v1",
        "board_file": str(pcb), "board_sha256": sha, "board_matches_order_md": sha == EXPECTED_SHA,
        "outline_world": [edge["bbox"][0] - OX, OY - edge["bbox"][3], edge["bbox"][2] - OX, OY - edge["bbox"][1]],
        "board_area_mm2": round(edge["outer_area_mm2"], 1),
        "parts": parts,
        "tracks_per_layer": {k: {"segments": v["segments"], "length_mm": round(v["length_mm"], 1)} for k, v in per_layer.items()},
        "track_length_total_mm": round(sum(v["length_mm"] for v in per_layer.values()), 1),
        "track_length_by_width_mm": {k: round(v, 1) for k, v in sorted(width_hist.items(), key=lambda kv: float(kv[0]))},
        "track_length_per_net_mm": {k: round(v, 2) for k, v in sorted(per_net.items())},
        "track_length_per_net_layer_mm": {k: {l: round(x, 2) for l, x in v.items()} for k, v in sorted(per_net_layer.items())},
        "vias_total": sum(vias.values()),
        "vias_per_net": dict(sorted(vias.items())),
    }
    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / "c49-board.json").write_text(json.dumps(out, indent=0))
    print(f"sha match {out['board_matches_order_md']}; {len(parts)} footprints; tracks {out['track_length_total_mm']} mm; "
          f"vias {out['vias_total']}")
    for k, v in sorted(out["tracks_per_layer"].items()):
        print(f"  {k}: {v['segments']} segments, {v['length_mm']} mm")


if __name__ == "__main__":
    main(sys.argv)
