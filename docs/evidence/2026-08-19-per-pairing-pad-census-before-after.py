#!/usr/bin/env python3
"""Read-only: the class-pair pad-pair census, before and after the per-pairing
creepage change, on one identical placement.

Reproduces section 7 of ``docs/evidence/2026-08-19-mechanism-a-analyze.py``
(commit ``6a6718a21``, branch ``analysis/mechanism-a-zero-copper``) exactly --
same net->class resolution (``netclass_rules.yaml`` via
``DesignRules``), same pad positions (``pin_world_position``), same
centre-to-centre distance, same ``PairCreepageTable.required(a, b)`` lookup --
and runs it TWICE, against two ``pair_creepage.generated.yaml`` projections:
the one ``scripts/generate_kicad_dru.py`` emitted before this change (every
HV-class <-> LV-class pair at 12.6 mm) and the one it emits after (per-class,
derived per pairing).

That doc reported **187** pad pairs closer than their required creepage, over
74 distinct nets, on this exact board (``eb5022510``). This script exists so
the *delta* is measured against that number and not against a
differently-defined one: the repo also carries a 196-pair HV<->SELV
copper-to-copper figure from ``scripts/measure_cross_domain_creepage.py`` and
a 185-187 kicad-cli ``violations_by_type.creepage`` band, and conflating them
would make the before/after meaningless.

CENTRE-TO-CENTRE IS AN UPPER BOUND on the real copper-to-copper gap, so every
count here is a LOWER BOUND on the real violation count -- the same caveat the
original doc states.

Usage::

    python docs/evidence/2026-08-19-per-pairing-pad-census-before-after.py \\
        --before /path/to/pair_creepage.generated.yaml.before

``--before`` defaults to reconstructing the old projection in memory (every
HV-class <-> LV-class pair at 12.6 mm) is NOT offered: reconstructing a
"before" would be a guess. Pass the real file, taken from git::

    git show origin/main:packages/temper-placer/configs/pair_creepage.generated.yaml \\
        > /tmp/pair_creepage.before.yaml
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from pathlib import Path

from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.router_v6.pair_creepage import (
    load_pair_creepage_table,
    net_class_of,
)

REPO = Path(__file__).resolve().parent.parent.parent


def census(table, pads, cls) -> tuple[int, set[str], Counter]:
    pairs = 0
    nets_v: set[str] = set()
    by_class: Counter = Counter()
    for i in range(len(pads)):
        n1, x1, y1 = pads[i]
        for j in range(i + 1, len(pads)):
            n2, x2, y2 = pads[j]
            if n1 == n2:
                continue
            req = table.required(cls[n1], cls[n2])
            if req <= 0:
                continue
            if math.dist((x1, y1), (x2, y2)) < req:
                pairs += 1
                by_class[tuple(sorted((cls[n1], cls[n2])))] += 1
                nets_v |= {n1, n2}
    return pairs, nets_v, by_class


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument(
        "--after",
        type=Path,
        default=REPO / "packages/temper-placer/configs/pair_creepage.generated.yaml",
    )
    ap.add_argument("--board", type=Path, default=REPO / "pcb/temper.kicad_pcb")
    args = ap.parse_args(argv[1:])
    for path in (args.before, args.after, args.board):
        if not path.is_file():
            print(f"ERROR: missing {path}", file=sys.stderr)
            return 2

    design_rules = create_temper_design_rules()
    parsed = parse_kicad_pcb(args.board)
    # WORLD coordinates, via `pin_world_position` -- the same call the
    # original census used. `pin.position` is a LOCAL footprint offset; using
    # it directly would compare pads from different components as if every
    # footprint sat at the origin, and every pair would "violate".
    pads = [
        (pin.net, *pin_world_position(pin, comp))
        for comp in parsed.netlist.components
        for pin in comp.pins
        if pin.net
    ]
    cls = {n: net_class_of(n, design_rules) for n, _, _ in pads}
    print(f"{len(pads)} netted pads on {args.board.name}\n")

    results = {}
    for label, path in (("BEFORE", args.before), ("AFTER", args.after)):
        table = load_pair_creepage_table(path)
        pairs, nets_v, by_class = census(table, pads, cls)
        results[label] = (pairs, nets_v, by_class)
        print(
            f"{label:6} ({path.name}): {pairs} pad pair(s) closer "
            f"centre-to-centre than their required creepage, over "
            f"{len(nets_v)} net(s)"
        )
        for key, count in by_class.most_common():
            print(f"         {key[0]:24} <-> {key[1]:24} {count:5d}")
        print()

    before_pairs, before_nets, before_by = results["BEFORE"]
    after_pairs, after_nets, after_by = results["AFTER"]
    print(
        f"DELTA: {after_pairs - before_pairs:+d} pad pairs "
        f"({before_pairs} -> {after_pairs}), "
        f"{len(after_nets) - len(before_nets):+d} nets "
        f"({len(before_nets)} -> {len(after_nets)})\n"
    )
    print("attribution, per class pair:")
    for key in sorted(set(before_by) | set(after_by)):
        b, a = before_by.get(key, 0), after_by.get(key, 0)
        if a == b:
            continue
        direction = "RAISED" if a > b else "lowered"
        print(f"  {key[0]:24} <-> {key[1]:24} {b:5d} -> {a:5d}  ({direction})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
