#!/usr/bin/env python3
"""Re-anchor round 17's native-21 closures (ports and bridges) on another board's copper export.

Each closure end names its pad and net in the note ("C38.1 bus_p -> C38.2 hv_ret"). For every end this finds that
pad in the export, checks the net, and moves the end to the pad centre. Ends that did not move are left
bit-identical. Fails if a pad is missing or its net differs. Writes closures-leg{A,B}-<tag>.json and
closures-<tag>-moves.json (every end that moved, old -> new).

    python3 -I closures_for_board.py EXPORT.json.gz TAG
"""
import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R17 = HERE.parents[4] / "validation-results/01-switching-parasitics/round17"
END = re.compile(r"([A-Z]+\d+\.\d+) ([A-Za-z0-9_\-]+)")


def main():
    export, tag = sys.argv[1], sys.argv[2]
    d = json.load(gzip.open(export, "rt"))
    pads = {}
    for p in d["primitives"]:
        if p["kind"] == "pad":
            pads.setdefault(p["ref"], set()).add((p["net"], round(p["centre"][0], 4), round(p["centre"][1], 4)))
    moves = {"board_sha256": d.get("board_sha256"), "export": str(export), "moved": [], "unchanged": 0}
    for leg in "AB":
        src = R17 / f"closures-leg{leg}-n21.json"
        cls = json.loads(src.read_text())
        for c in cls:
            ends = END.findall(c["note"])[:2]
            assert len(ends) == 2, c
            for key, (ref, net) in zip(("a", "b"), ends):
                got = pads.get(ref)
                if not got:
                    raise SystemExit(f"{c['name']}: pad {ref} not in export")
                cen = {(x, y) for n, x, y in got}
                nets = {n for n, x, y in got}
                if nets != {net}:
                    raise SystemExit(f"{c['name']}: pad {ref} is on {sorted(nets)}, closure says {net}")
                assert len(cen) == 1, (ref, cen)
                (x, y), = cen
                old = c[key]
                if abs(old[0] - x) < 0.01 and abs(old[1] - y) < 0.01:
                    moves["unchanged"] += 1
                    continue
                c[key] = [x, y]
                moves["moved"].append({"leg": leg, "closure": c["name"], "end": key, "pad": ref, "net": net,
                                       "old": old, "new": [x, y]})
        (HERE / f"closures-leg{leg}-{tag}.json").write_text(json.dumps(cls, indent=1) + "\n")
    (HERE / f"closures-{tag}-moves.json").write_text(json.dumps(moves, indent=1) + "\n")
    print(tag, d.get("board_sha256", "")[:8], "moved", [(m["leg"], m["closure"], m["pad"], m["old"], m["new"]) for m in moves["moved"]],
          "unchanged", moves["unchanged"])


if __name__ == "__main__":
    main()
