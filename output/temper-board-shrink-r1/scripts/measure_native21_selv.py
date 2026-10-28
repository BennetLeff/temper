"""Measure native-21's SELV island (stage-53 board of record): size, what sits in it, room left.

Read-only. Inputs: the s53 routed board (review-packet-s53 README: outside git, sha256 82af7bd9...)
and audit.rs SELV_NETS (the same list native-21/layout/domains.py uses). Output:
results/native21-selv.json. Standard library only.

    python3 -I scripts/measure_native21_selv.py [board] [audit.rs]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kicad_courtyard as kc  # noqa: E402

PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
DEFAULT_PCB = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/s53/c53int/section.kicad_pcb")
EXPECTED_SHA = "82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27"


def selv_nets(audit_rs: Path) -> set[str]:
    t = audit_rs.read_text()
    body = t[t.index("const SELV_NETS"):]
    body = body[:body.index("];")]
    body = re.sub(r"//[^\n]*", "", body)            # drop comments before collecting the names
    return set(re.findall(r'"([^"]+)"', body))


def is_selv(net: str, selv: set[str]) -> bool:
    # native-21/layout/domains.py domain(): SELV list plus J4 no-connect stubs and three named nc nets
    return net in selv or net.endswith(("-nc10", "-nc11", "-nc12", "-nc15")) or \
        net in ("line_zc.buffer-nc", "u_bias_flt-nc", "leg_a.driver-nc_7", "leg_b.driver-nc_7")


def main(argv):
    pcb = Path(argv[1]) if len(argv) > 1 else DEFAULT_PCB
    audit = Path(argv[2]) if len(argv) > 2 else PS / "audit.rs"
    sha = hashlib.sha256(pcb.read_bytes()).hexdigest()
    selv = selv_nets(audit)
    board = kc.load(pcb)
    fps = kc.footprints(board)
    edge = kc.edge_cuts(board)
    zs = kc.zones(board)

    cls = {"selv_only": [], "crossing": [], "hot_only": [], "no_net": []}
    for f in fps:
        nets = {p["net"] for p in f["pads"] if p["net"]}
        if not nets:
            cls["no_net"].append(f)
            continue
        s = {n for n in nets if is_selv(n, selv)}
        if s and s == nets:
            cls["selv_only"].append(f)
        elif s:
            cls["crossing"].append(f)
        else:
            cls["hot_only"].append(f)

    # SELV island: the selv_gnd / v3v3 plane zones (outline polygons and filled copper)
    island = {}
    for z in zs:
        if z["net"] in ("selv_gnd", "v3v3") and not z["keepout"]:
            for lay in z["layers"]:
                key = f"{z['net']}@{lay}"
                d = island.setdefault(key, {"outline_mm2": 0.0, "filled_mm2": 0.0, "bbox": None})
                d["outline_mm2"] += z["outline_area_mm2"]
                pts = [p for poly in z["outline"] for p in poly]
                if pts:
                    bb = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
                    d["bbox"] = bb if d["bbox"] is None else [min(d["bbox"][0], bb[0]), min(d["bbox"][1], bb[1]),
                                                              max(d["bbox"][2], bb[2]), max(d["bbox"][3], bb[3])]
            for lay, p in z["filled"]:
                key = f"{z['net']}@{lay}"
                island.setdefault(key, {"outline_mm2": 0.0, "filled_mm2": 0.0, "bbox": None})
                island[key]["filled_mm2"] += kc.shoelace(p)
    island = {k: {"outline_mm2": round(v["outline_mm2"], 1), "filled_mm2": round(v["filled_mm2"], 1),
                  "bbox": [round(x, 1) for x in v["bbox"]] if v["bbox"] else None} for k, v in island.items()}

    def summ(lst):
        return {"count": len(lst), "crtyd_mm2": round(sum(f["crtyd_area_mm2"] for f in lst), 1)}

    selv_crt = sum(f["crtyd_area_mm2"] for f in cls["selv_only"])
    cross_crt = sum(f["crtyd_area_mm2"] for f in cls["crossing"])
    largest_island = max((v["outline_mm2"] for v in island.values()), default=0.0)
    out = {
        "schema": "temper.board-shrink-r1.native21-selv.v1",
        "board_file": str(pcb), "board_sha256": sha, "board_matches_s53_packet": sha == EXPECTED_SHA,
        "selv_net_count": len(selv),
        "outline_bbox_mm": edge["bbox"], "board_area_mm2": round(edge["outer_area_mm2"], 1),
        "placements": len(fps),
        "crtyd_total_mm2": round(sum(f["crtyd_area_mm2"] for f in fps), 1),
        "utilisation_pct": round(100 * sum(f["crtyd_area_mm2"] for f in fps) / edge["outer_area_mm2"], 1),
        "classes": {k: summ(v) for k, v in cls.items()},
        "selv_only_refs": sorted(f["ref"] for f in cls["selv_only"]),
        "crossing_refs": sorted(f["ref"] for f in cls["crossing"]),
        "selv_island_zones": island,
        "selv_island_largest_outline_mm2": round(largest_island, 1),
        "selv_island_occupied_crtyd_mm2_bound": [round(selv_crt, 1), round(selv_crt + cross_crt, 1)],
        "note": "Occupied range: SELV-only courtyards (low) to SELV-only + every crossing part's whole courtyard (high); "
                "a crossing part straddles the 8 mm moat, so only part of it is inside the island.",
    }
    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / "native21-selv.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("board_matches_s53_packet", "board_area_mm2", "placements", "utilisation_pct",
                                          "classes", "selv_island_zones", "selv_island_occupied_crtyd_mm2_bound")}, indent=1))


if __name__ == "__main__":
    main(sys.argv)
