# provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
# Measurements taken at this commit (barrier 20.0mm configuration) and at
# fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (barrier 12.6mm configuration),
# working tree clean in both. See
# docs/evidence/2026-08-19-per-pairing-placement-routed.md
"""Static, placement-level count of pads sitting inside a FOREIGN pad's
required creepage halo.

This is the placement-side counterpart of the router-level
"FREED_then_BLOCKED_by_foreign_creepage_halo" census in
`2026-08-19-mechanism-a-analyze.py` section 5. It needs no route: it asks,
of the placement alone, how many pads are closer to a foreign-net pad than
the pair creepage that net-class pair requires.

Why both: the router-level number depends on which nets the router happened
to decline on that run (the denominator moves), so it cannot by itself
separate "the placement freed pads" from "the router declined different
nets". This one is a pure function of the placement and the creepage table,
so the same two placements can be compared under the SAME table.

Distance is centre-to-centre, which is an UPPER bound on the real copper gap,
so every count here is a LOWER bound on the true violation count -- the same
caveat `2026-08-19-per-pairing-pad-census-before-after.py` carries.

Read-only.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from math import hypot
from pathlib import Path

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.router_v6.pair_creepage import default_creepage_table, net_class_of


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    rules = load_netclass_rules(
        args.repo / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    ).design_rules
    tbl = default_creepage_table()
    pcb = parse_kicad_pcb_v6(args.board)

    pads = [(pin.net, *pin_world_position(pin, comp))
            for comp in pcb.components for pin in comp.pins if pin.net]
    cls = {n: net_class_of(n, rules) for n, _, _ in pads}

    viol_pairs = 0
    by_class_pair: Counter = Counter()
    nets_violating: set[str] = set()
    pads_inside: set[tuple] = set()

    for i in range(len(pads)):
        n1, x1, y1 = pads[i]
        for j in range(i + 1, len(pads)):
            n2, x2, y2 = pads[j]
            if n1 == n2:
                continue
            req = tbl.required(cls[n1], cls[n2])
            if req <= 0.0:
                continue
            if hypot(x2 - x1, y2 - y1) < req:
                viol_pairs += 1
                key = " <-> ".join(sorted((cls[n1], cls[n2])))
                by_class_pair[key] += 1
                nets_violating.add(n1)
                nets_violating.add(n2)
                pads_inside.add((n1, round(x1, 4), round(y1, 4)))
                pads_inside.add((n2, round(x2, 4), round(y2, 4)))

    out = {
        "label": args.label,
        "board": str(args.board),
        "pads_total": len(pads),
        "violating_pad_pairs": viol_pairs,
        "nets_involved": len(nets_violating),
        "pads_inside_a_foreign_halo": len(pads_inside),
        "by_class_pair": dict(by_class_pair.most_common()),
    }

    print(f"=== {args.label or args.board} ===")
    print(f"pads                              {out['pads_total']}")
    print(f"pad pairs closer than required    {out['violating_pad_pairs']}")
    print(f"nets involved                     {out['nets_involved']}")
    print(f"pads inside a FOREIGN creepage halo {out['pads_inside_a_foreign_halo']}"
          f"/{out['pads_total']}")
    for k, v in by_class_pair.most_common():
        print(f"  {k:44s} {v}")

    if args.json_out:
        args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
