#!/usr/bin/env python3
"""Uncapped, geometric measurement of POURED-COPPER pair-clearance violations.

Why not kicad-cli
-----------------
``clearance`` saturates at ``EXTENDED_ERROR_LIMIT = 499`` and
``shorting_items`` at ``ERROR_LIMIT = 199``
(docs/evidence/2026-08-12-dru-rule-precedence.md sec 4). Any headline number
from ``kicad-cli pcb drc`` on this board is a floor, not a count. #1111's
partitioned protocol works on the committed board but
docs/evidence/2026-08-12-router-safety-clearances.md sec 2.1 measured that it
does not transfer to a board carrying freshly-poured copper: a ``.kicad_dru``
holding nothing but ``(constraint clearance (min 0mm))`` already reports 501,
so the subtrahend is itself capped.

This script therefore measures directly from the geometry, uncapped and exact,
against the same table ``kicad-cli`` is judged by
(``packages/temper-placer/configs/pair_clearance.generated.yaml``, emitted by
``scripts/generate_kicad_dru.py`` from the rules it just wrote -- see
docs/evidence/2026-08-12-router-safety-clearances.md sec 1.4 for why that
table and not ``netclass_rules.yaml``'s ``class_pairs``).

Scope
-----
Every reported pair has **at least one zone filled polygon on one side** --
that is what "attributable to poured copper" means here, and it is the only
population this task's change can move. Pairs of two non-zone items
(track/via/pad against track/via/pad) are #1112's population and are not
counted. Both are measured on the same layer; different layers cannot violate
a clearance constraint.

The board must be **zone-filled** first. An emitted zone carries only an
outline; the copper is the ``filled_polygon`` KiCad computes:

    kicad-cli pcb drc --refill-zones --save-board -o /dev/null board.kicad_pcb

Pads are excluded, and that is a measured decision, not a convenience
--------------------------------------------------------------------
Two independent reasons, both established against this board:

1. **kicad-cli does not test zone-to-pad clearance at all.** A ``.kicad_dru``
   containing only ``(rule (condition "A.Type == 'Zone' && B.Type == 'Pad'")
   (constraint clearance (min 20mm)))`` reports **zero** violations on a board
   carrying 128 filled zone polygons and 793 netted pads, while the same probe
   with ``B.Type == 'Track'`` at 0.5mm reports 19. Every partner kicad-cli
   pairs with a zone is a Track or a Via.
2. **A pad's per-layer copper is not reconstructible from the board file.**
   Nearly every through-hole pad here carries ``(remove_unused_layers yes)``,
   so on a layer where the pad has no connection KiCad keeps only the hole.
   Measured on R11 pad 2 (``size 2.4``, ``drill 1.2``): the ac_l pour sits
   5.4005mm from the full 2.4mm pad outline and exactly 6.0005mm -- the rule
   figure -- from the 1.2mm hole. Counting the full outline manufactures a
   0.6mm deficit that does not exist. Deciding which layers are "used"
   requires KiCad's own connectivity pass.

``--include-pads`` re-enables them for inspection; the numbers this document
quotes do not use it.

Cross-validation
----------------
On the pairs kicad-cli does report, this script agrees with it to **0.0004mm**
(``A.NetName == 'ac_l'`` at 8mm: kicad 6.1422 / this 6.1426, kicad 6.5287 /
this 6.5287, kicad 6.0005 / this 6.0005).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

# --------------------------------------------------------------------------
# S-expression reader (whole file, once)
# --------------------------------------------------------------------------


def parse_sexpr(text: str):
    """Parse a KiCad s-expression file into nested lists of str/list."""
    tokens: list = []
    stack: list[list] = [tokens]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "(":
            new: list = []
            stack[-1].append(new)
            stack.append(new)
            i += 1
        elif c == ")":
            stack.pop()
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j])
                    j += 1
            stack[-1].append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            stack[-1].append(text[i:j])
            i = j
    return tokens[0]


def find(node, tag):
    for child in node:
        if isinstance(child, list) and child and child[0] == tag:
            return child
    return None


def find_all(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def fnum(x) -> float:
    return float(x)


# --------------------------------------------------------------------------
# Copper items
# --------------------------------------------------------------------------


@dataclass
class Item:
    geom: object
    net: str
    layer: str
    kind: str  # "zone" | "track" | "via" | "pad"
    ref: str = ""


def _rotate(px, py, cx, cy, deg):
    if not deg:
        return px, py
    a = math.radians(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def _pad_geom(pad, fx, fy, frot):
    at = find(pad, "at")
    px, py = fnum(at[1]), fnum(at[2])
    prot = fnum(at[3]) if len(at) > 3 else 0.0
    # Footprint-local -> board coordinates. KiCad stores the footprint
    # rotation as a counter-clockwise angle in a Y-down frame, which is why
    # the local offset is rotated by -frot here (same convention the repo's
    # own rotation-sign fix, #479, settled on).
    ax, ay = _rotate(fx + px, fy + py, fx, fy, -frot)
    shape = pad[3]
    size = find(pad, "size")
    if size is None:
        return None
    w, h = fnum(size[1]), fnum(size[2])
    # A pad's stored `at` angle is ABSOLUTE in the .kicad_pcb, not relative to
    # its footprint (an 0603 at footprint rotation -90 stores its pads at 270,
    # not at 0). Subtracting the footprint rotation here would rotate every
    # non-square pad on a rotated part by twice its angle.
    total_rot = prot
    if shape == "circle":
        return Point(ax, ay).buffer(w / 2.0, quad_segs=16)
    if shape == "oval":
        r = min(w, h) / 2.0
        if w >= h:
            seg = LineString([(ax - (w / 2 - r), ay), (ax + (w / 2 - r), ay)])
        else:
            seg = LineString([(ax, ay - (h / 2 - r)), (ax, ay + (h / 2 - r))])
        geom = seg.buffer(r, quad_segs=16)
    else:
        rect = Polygon(
            [
                (ax - w / 2, ay - h / 2),
                (ax + w / 2, ay - h / 2),
                (ax + w / 2, ay + h / 2),
                (ax - w / 2, ay + h / 2),
            ]
        )
        rratio = find(pad, "roundrect_rratio")
        if shape == "roundrect" and rratio is not None:
            # Exact, not the bounding rectangle: an over-approximated corner
            # is a fabricated fraction of a millimetre in a measurement whose
            # whole point is fractions of a millimetre.
            r = fnum(rratio[1]) * min(w, h)
            if r > 0:
                geom = rect.buffer(-r, join_style=2).buffer(r, quad_segs=16)
            else:
                geom = rect
        else:  # rect, trapezoid, custom -> bounding rectangle (over-approx)
            geom = rect
    if total_rot:
        from shapely import affinity

        geom = affinity.rotate(geom, -total_rot, origin=(ax, ay))
    return geom


COPPER_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


def _net_table(root) -> dict[str, str]:
    """``{net_number: net_name}`` for the pre-KiCad-10 numbered net table.

    KiCad 10 (``version 20260206``) dropped the numbered table and references
    nets by name everywhere, so this is empty on a board kicad-cli has
    re-saved and populated on the repo's own emitted boards. Both are handled.
    """
    table: dict[str, str] = {}
    for net in find_all(root, "net"):
        if len(net) > 2:
            table[str(net[1])] = str(net[2])
    return table


def _net_of(node, table: dict[str, str]) -> str:
    """Resolve an item's net name across both file-format generations."""
    named = find(node, "net_name")
    if named is not None and len(named) > 1:
        return str(named[1])
    net = find(node, "net")
    if net is None or len(net) < 2:
        return ""
    if len(net) > 2:
        return str(net[2])
    token = str(net[1])
    return table.get(token, "" if token.isdigit() else token)


def load_items(board_path: Path) -> tuple[list[Item], dict[str, str]]:
    root = parse_sexpr(board_path.read_text(encoding="utf-8"))
    net_by_num = _net_table(root)

    items: list[Item] = []

    for seg in find_all(root, "segment"):
        start, end = find(seg, "start"), find(seg, "end")
        width = fnum(find(seg, "width")[1])
        layer = find(seg, "layer")[1]
        net = _net_of(seg, net_by_num)
        line = LineString([(fnum(start[1]), fnum(start[2])), (fnum(end[1]), fnum(end[2]))])
        items.append(Item(line.buffer(width / 2.0, quad_segs=8), net, layer, "track"))

    for via in find_all(root, "via"):
        at = find(via, "at")
        size = fnum(find(via, "size")[1])
        net = _net_of(via, net_by_num)
        layers = find(via, "layers")
        geom = Point(fnum(at[1]), fnum(at[2])).buffer(size / 2.0, quad_segs=16)
        # A through via occupies every copper layer between its endpoints; the
        # boards here only ever emit F.Cu/B.Cu vias, so span every copper layer.
        spanned = COPPER_LAYERS if layers is None else COPPER_LAYERS
        for layer in spanned:
            items.append(Item(geom, net, layer, "via"))

    for fp in find_all(root, "footprint"):
        at = find(fp, "at")
        fx, fy = fnum(at[1]), fnum(at[2])
        frot = fnum(at[3]) if len(at) > 3 else 0.0
        ref = ""
        for prop in find_all(fp, "property"):
            if len(prop) > 2 and prop[1] == "Reference":
                ref = prop[2]
        for pad in find_all(fp, "pad"):
            net = _net_of(pad, net_by_num)
            if not net:
                continue
            geom = _pad_geom(pad, fx, fy, frot)
            if geom is None or geom.is_empty:
                continue
            layers_node = find(pad, "layers")
            pad_layers = [str(x) for x in layers_node[1:]] if layers_node else []
            resolved = set()
            for lay in pad_layers:
                if lay == "*.Cu":
                    resolved.update(COPPER_LAYERS)
                elif lay in COPPER_LAYERS:
                    resolved.add(lay)
            for lay in sorted(resolved):
                items.append(Item(geom, net, lay, "pad", ref))

    for zone in find_all(root, "zone"):
        net = _net_of(zone, net_by_num)
        layer_node = find(zone, "layer") or find(zone, "layers")
        zone_layers = [str(x) for x in layer_node[1:]] if layer_node else []
        for fp in find_all(zone, "filled_polygon"):
            lay_node = find(fp, "layer")
            lay = lay_node[1] if lay_node is not None else (zone_layers[0] if zone_layers else "")
            pts = find(fp, "pts")
            if pts is None:
                continue
            coords = [(fnum(p[1]), fnum(p[2])) for p in find_all(pts, "xy")]
            if len(coords) < 3:
                continue
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            items.append(Item(poly, net, lay, "zone"))

    return items, net_by_num


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("board", type=Path)
    ap.add_argument("--label", default="")
    ap.add_argument(
        "--include-pads",
        action="store_true",
        help="include zone<->pad pairs (over-counts; see the module docstring)",
    )
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root, for the netclass SSOT and the generated pair table",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(args.repo / "packages" / "temper-placer" / "src"))
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES
    from temper_placer.router_v6.zone_pour_clearance import load_zone_pour_clearance_table

    # The requirement is read from the generated ZONE-world table, which
    # resolves each pair exactly as KiCad does: the last matching
    # pcb/temper.kicad_dru rule, or pcb/temper.kicad_pro's netclass clearance
    # where no rule matches. No figure here comes from netclass_rules.yaml's
    # class_pairs -- see zone_pour_clearance.py's module docstring for why
    # measuring against those would manufacture violations.
    table = load_zone_pour_clearance_table(
        args.repo / "packages" / "temper-placer" / "configs" / "zone_pour_clearance.generated.yaml"
    )

    def net_class(net: str) -> str:
        return TEMPER_NET_ASSIGNMENTS.get(net, "Default") or "Default"

    def required(net_a: str, net_b: str, other_type: str) -> float:
        return table.required(net_class(net_a), net_class(net_b), other_type)

    items, _ = load_items(args.board)
    by_layer: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        if it.kind == "pad" and not args.include_pads:
            continue
        if it.layer in COPPER_LAYERS and it.net:
            by_layer[it.layer].append(it)

    # Largest requirement in play bounds the neighbourhood query.
    max_required = max(max(table.values.values(), default=6.0), 6.0)

    violations = []
    seen: set[tuple] = set()
    for layer, layer_items in sorted(by_layer.items()):
        zones = [it for it in layer_items if it.kind == "zone"]
        if not zones:
            continue
        tree = STRtree([it.geom for it in layer_items])
        for zi, zone in enumerate(zones):
            for idx in tree.query(zone.geom.buffer(max_required)):
                other = layer_items[idx]
                if other.net == zone.net:
                    continue
                if other is zone:
                    continue
                key = (layer, zone.net, other.net, id(zone.geom), id(other.geom))
                if key in seen:
                    continue
                seen.add(key)
                other_type = {"track": "Track", "via": "Via", "pad": "Pad", "zone": "Zone"}[
                    other.kind
                ]
                req = required(zone.net, other.net, other_type)
                overlap = zone.geom.intersects(other.geom)
                dist = 0.0 if overlap else zone.geom.distance(other.geom)
                if dist < req - 1e-6:
                    centroid = zone.geom.centroid
                    violations.append(
                        {
                            "layer": layer,
                            "net_a": zone.net,
                            "net_b": other.net,
                            "class_a": net_class(zone.net),
                            "class_b": net_class(other.net),
                            "kind_a": "zone",
                            "kind_b": other.kind,
                            "ref_b": other.ref,
                            "required_mm": round(req, 4),
                            "actual_mm": round(dist, 4),
                            "deficit_mm": round(req - dist, 4),
                            "overlap": overlap,
                            "x_mm": round(centroid.x, 3),
                            "y_mm": round(centroid.y, 3),
                            "zone_index": zi,
                        }
                    )

    safety = [
        v
        for v in violations
        if getattr(TEMPER_NET_CLASSES.get(v["class_a"]), "safety_category", "LV") in ("HV", "AC")
        or getattr(TEMPER_NET_CLASSES.get(v["class_b"]), "safety_category", "LV") in ("HV", "AC")
    ]
    by_pair: dict[tuple[str, str], int] = defaultdict(int)
    for v in violations:
        by_pair[tuple(sorted((v["class_a"], v["class_b"])))] += 1

    summary = {
        "label": args.label,
        "includes_pads": args.include_pads,
        "board": str(args.board),
        "zone_filled_polygons": sum(1 for it in items if it.kind == "zone"),
        "poured_copper_violations": len(violations),
        "safety_governed": len(safety),
        "distinct_net_pairs": len({(v["net_a"], v["net_b"]) for v in violations}),
        "by_class_pair": {f"{a}|{b}": n for (a, b), n in sorted(by_pair.items())},
        "worst": sorted(violations, key=lambda v: -v["deficit_mm"])[:15],
    }
    print(json.dumps(summary, indent=2))

    if args.csv:
        with args.csv.open("w", newline="") as fh:
            w = csv.DictWriter(
                fh, fieldnames=list(violations[0].keys()) if violations else ["none"]
            )
            w.writeheader()
            w.writerows(violations)
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
