#!/usr/bin/env python3
"""Uncapped, per-pair clearance measurement for a routed board.

WHY NOT kicad-cli
-----------------
`clearance` saturates at EXTENDED_ERROR_LIMIT = 499
(docs/evidence/2026-08-12-dru-rule-precedence.md sec 4), so a headline number
is a floor. That document worked around the cap by partitioning per rule and
subtracting a 0.001mm unconditioned floor's own contribution -- which works on
the COMMITTED board, where the floor fires once.

That protocol does not transfer to a freshly-routed board. Measured here on
this branch's own baseline route: a `.kicad_dru` containing nothing but
`(constraint clearance (min 0mm))` already reports **501** clearance errors
(and `shorting_items` 204). Those are overlapping, not merely close, copper
pairs; they appear inside every partition and cannot be subtracted out,
because the subtrahend is itself capped. So the partitioned kicad-cli protocol
cannot produce an exact count for these boards at all -- reported as a finding,
not worked around.

WHAT THIS DOES INSTEAD
----------------------
Counts violations directly from the routed geometry, uncapped, against the
same per-net-class-PAIR matrix kicad-cli enforces
(`configs/pair_clearance.generated.yaml`, itself derived by evaluating
`pcb/temper.kicad_dru`'s own rules -- see scripts/generate_kicad_dru.py).

SCOPE, stated rather than assumed: **track/via <-> track/via only**. Those are
the items the ROUTER emits and the ones this change governs; 1,053 of the
1,291 distinct violating pairs #1110 catalogued are bare track<->track naming
no component. Pad-involving pairs are excluded because a pad's true copper
outline is not reconstructible from this script's inputs without the footprint
library, and an over-approximated pad polygon would inflate both columns by an
unknown amount. Both columns are measured identically, so the delta is honest;
the absolute number is a track/via subtotal, not the board's whole count.

Same-net pairs are exempt (KiCad exempts them too). Only different-layer-
disjoint pairs are skipped: two items sharing no copper layer cannot violate a
clearance rule.

Usage:
    python docs/evidence/scripts/2026-08-12-router-safety-clearances-measure.py \
        --board routed.kicad_pcb --label baseline --out baseline.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

from temper_placer.router_v6.pair_clearance import (  # noqa: E402
    UNASSIGNED_NETCLASS,
    load_pair_clearance_table,
)

_SEGMENT_RE = re.compile(
    r"\(segment\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)"
    r"\s+\(width ([\d.]+)\)\s+\(layer \"([^\"]+)\"\)(?:\s+\(locked\))?\s+\(net (\d+)\)",
    re.DOTALL,
)
_VIA_RE = re.compile(
    r"\(via\s*(?:\(\w+\)\s*)?\(at ([-\d.]+) ([-\d.]+)\)\s+\(size ([\d.]+)\)"
    r"\s+\(drill ([\d.]+)\)\s+\(layers ([^)]*)\)(?:\s+\([^)]*\))*?\s+\(net (\d+)\)",
    re.DOTALL,
)
_NET_RE = re.compile(r'\(net (\d+) "([^"]*)"\)')


@dataclass(frozen=True)
class Item:
    kind: str  # "track" | "via"
    net: str
    net_class: str
    layers: frozenset[str]
    half_width: float
    geom: object  # shapely centreline / centre point


def parse_board(path: Path, net_class_of: dict[str, str]) -> list[Item]:
    text = path.read_text(encoding="utf-8")
    numbers = {int(n): name for n, name in _NET_RE.findall(text)}
    items: list[Item] = []
    for x1, y1, x2, y2, width, layer, net in _SEGMENT_RE.findall(text):
        name = numbers.get(int(net), "")
        items.append(
            Item(
                kind="track",
                net=name,
                net_class=net_class_of.get(name, UNASSIGNED_NETCLASS),
                layers=frozenset({layer}),
                half_width=float(width) / 2.0,
                geom=LineString([(float(x1), float(y1)), (float(x2), float(y2))]),
            )
        )
    for x, y, size, _drill, layers, net in _VIA_RE.findall(text):
        name = numbers.get(int(net), "")
        items.append(
            Item(
                kind="via",
                net=name,
                net_class=net_class_of.get(name, UNASSIGNED_NETCLASS),
                # A via spans the stackup: it can conflict on any layer.
                layers=frozenset(re.findall(r'"([^"]+)"', layers) or layers.split()),
                half_width=float(size) / 2.0,
                geom=Point(float(x), float(y)),
            )
        )
    return items


def _layers_touch(a: Item, b: Item) -> bool:
    if a.kind == "via" or b.kind == "via":
        return True  # a via passes through every signal layer of the stackup
    return bool(a.layers & b.layers)


def measure(
    board: Path,
    net_class_of: dict[str, str],
    safety_category_of: dict[str, str] | None = None,
) -> dict:
    """Count uncapped pair-clearance violations among tracks and vias.

    ``safety_category_of`` maps net class -> ``netclass_rules.yaml``'s
    ``safety_category``. A violating pair is *safety-governed* when either
    side is HV or AC -- the population the DRU's cross-barrier rules exist
    for, and the one this change targets. The rest are the router's own
    same-domain crowding at the 0.2mm default, which is a congestion problem,
    not a safety one, and is reported separately rather than folded in.
    """
    safety_category_of = safety_category_of or {}
    table = load_pair_clearance_table()
    items = parse_board(board, net_class_of)
    if not items:
        raise SystemExit(f"no segments or vias parsed from {board}")

    max_required = max(table.pairs.values(), default=0.0)
    max_half = max(item.half_width for item in items)
    reach = max_required + 2 * max_half + 1e-6

    tree = STRtree([item.geom for item in items])

    def is_safety(class_a: str, class_b: str) -> bool:
        return any(
            safety_category_of.get(name) in {"HV", "AC"} for name in (class_a, class_b)
        )

    violations = 0
    safety_violations = 0
    safety_pairs: set[tuple[str, str]] = set()
    pairs: set[tuple[str, str]] = set()
    by_class_pair: Counter[tuple[str, str]] = Counter()
    by_net: Counter[str] = Counter()
    worst: list[tuple[float, str, str, float, float]] = []

    for index_a, a in enumerate(items):
        for index_b in tree.query(a.geom.buffer(reach)):
            if index_b <= index_a:
                continue
            b = items[index_b]
            if a.net == b.net or not _layers_touch(a, b):
                continue
            required = table.required(a.net_class, b.net_class)
            actual = a.geom.distance(b.geom) - a.half_width - b.half_width
            if actual < required - 1e-9:
                violations += 1
                pairs.add((a.net, b.net) if a.net < b.net else (b.net, a.net))
                key = (
                    (a.net_class, b.net_class)
                    if a.net_class <= b.net_class
                    else (b.net_class, a.net_class)
                )
                by_class_pair[key] += 1
                by_net[a.net] += 1
                by_net[b.net] += 1
                worst.append((required - actual, a.net, b.net, required, actual))
                if is_safety(a.net_class, b.net_class):
                    safety_violations += 1
                    safety_pairs.add(
                        (a.net, b.net) if a.net < b.net else (b.net, a.net)
                    )

    worst.sort(reverse=True)
    return {
        "board": str(board),
        "items": len(items),
        "tracks": sum(1 for i in items if i.kind == "track"),
        "vias": sum(1 for i in items if i.kind == "via"),
        "violations": violations,
        "distinct_pairs": len(pairs),
        "safety_governed_violations": safety_violations,
        "safety_governed_distinct_pairs": len(safety_pairs),
        "by_class_pair": {f"{a}|{b}": n for (a, b), n in by_class_pair.most_common()},
        "by_net": dict(by_net.most_common(15)),
        "worst_shortfalls": [
            {
                "shortfall_mm": round(s, 4),
                "net_a": na,
                "net_b": nb,
                "required_mm": rq,
                "actual_mm": round(ac, 4),
            }
            for s, na, nb, rq, ac in worst[:10]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--rules",
        type=Path,
        default=REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml",
    )
    args = parser.parse_args()

    from temper_placer.io.netclass_loader import load_netclass_rules

    design_rules = load_netclass_rules(args.rules).design_rules
    net_class_of = dict(design_rules.net_class_assignments)
    safety_category_of = {
        name: getattr(rules, "safety_category", None)
        for name, rules in design_rules.net_classes.items()
    }

    result = measure(args.board, net_class_of, safety_category_of)
    result["label"] = args.label
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
