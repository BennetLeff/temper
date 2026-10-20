#!/usr/bin/env python3
"""Stage 54, J1 neutral feed (c54-j1-thermal fix (b), OPEN-ITEMS S21).

    python3 -I validation-results/11-candidates/c54-board/scripts/edit54_j1.py COPPER.json [--out OUT.json]

Adds an ac_n_in F.Cu strip mirroring the B.Cu edge strip that feeds J1.2 (x 283.6-289.4, y 3.5-26.5), landed on
J1.2's F.Cu pad (282.62-285.62 x 7.7-10.7), and 8 stitch vias (0.6/0.3) tying it to the B.Cu strip. The F.Cu there
holds only J1.2 on the s53 export. Idempotent: a second run changes nothing.
"""
import argparse
import json
from pathlib import Path

NAME = "ac_n_in J1.2 F.Cu feed (s54)"
ZONE = {"net": "ac_n_in", "layer": "F.Cu", "priority": 1, "name": NAME,
        "outline": [[283.6, 3.5], [289.4, 3.5], [289.4, 26.5], [283.6, 26.5]], "holes": []}
VIAS = [{"net": "ac_n_in", "at": [x, y], "size": 0.6, "drill": 0.3}
        for x in (286.5, 288.4) for y in (13.0, 16.5, 20.0, 23.5)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("copper")
    ap.add_argument("--out")
    a = ap.parse_args()
    c = json.loads(Path(a.copper).read_text())
    if not any(z["name"] == NAME for z in c["zones"]):
        c["zones"].append(ZONE)
    have = {(tuple(v["at"]), v["net"]) for v in c["vias"]}
    c["vias"] += [v for v in VIAS if (tuple(v["at"]), v["net"]) not in have]
    Path(a.out or a.copper).write_text(json.dumps(c, indent=1) + "\n")
    print(f"zones {len(c['zones'])} vias {len(c['vias'])}")


if __name__ == "__main__":
    main()
