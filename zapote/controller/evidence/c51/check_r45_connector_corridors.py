"""Are C51's new connector positions (ENCLOSURE-HANDOFF "C51 request to R45") free in the enclosure model?

For each proposed connector this builds a vertical prism over its body (footprint + MARGIN on every side) from the
controller's top surface up H_PROBE mm, intersects it with every saved R43 part (exact solids, bbox prefilter), and
reports, per obstruction, the lowest Z the obstruction reaches inside the prism. "Free height" is that lowest Z minus
the board top: how far the mated plug and the cable's first rise can go before they meet something.

Need per connector: mated height + one bend of 3 x OD (the enclosure's harness rule, R19/R31) + one OD.

Run (CAD env, see output/temper-manufacturing-r43/design/r43/HANDOFF.md):
  ~/.local/share/temper/cadenv/bin/python check_r45_connector_corridors.py [--r43 <folder>] [--json out.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build123d as bd

BOARD_TOP = 24.6        # controller top surface since R30 (ENCLOSURE-HANDOFF)
H_PROBE = 30.0          # prism height above the board top
MARGIN = 1.0            # added to each side of the connector body
BEND = 3.0              # minimum bend radius as a multiple of OD (enclosure harness rule)

# name, centre (world X, Y), body X x Y, mated height (None = unread), cable OD, parts this connector replaces or owns
CONNECTORS = [
    # C53: J9 moved from (-31.5, 86) to (43.5, 86), rotated 180 (the food channel sits in the free field in front of it)
    dict(name="J9", part="JST B4B-XH-A", centre=(43.5, 86.0), body=(12.4, 5.75), mated=9.8, od=2.3,
         own=("electronics_controller_J9", "harness_probe_M12_to_controller")),
    # JST ePH.pdf (PDF created 2026-01-27) p.1: top entry "mounting height of 8 mm", width 4.5; header table B = 5.9
    # for 2 circuits; insulation O.D. 0.5-1.5 mm.
    dict(name="J14", part="JST B2B-PH-K-S", centre=(66.0, 86.0), body=(5.9, 4.5), mated=8.0, od=1.5, own=()),
    dict(name="J15", part="JST B5B-XH-A", centre=(104.5, 86.0), body=(14.9, 5.75), mated=9.8, od=3.0, own=()),
]
# The native-21 HOT block J13 was judged against (R43 evidence/ps3/check_ps3_retention.py HOT_BLOCK): X, Y, Z ranges.
HOT_BLOCK = ((65.8, 118.2), (96.4, 123.6), (24.2, 51.7))


def gap_to_hot(c: dict) -> float:
    """Shortest distance from the mated plug body (board top to board top + mated) to HOT_BLOCK."""
    (x, y), (w, d) = c["centre"], c["body"]
    lo = (x - w / 2, y - d / 2, BOARD_TOP)
    hi = (x + w / 2, y + d / 2, BOARD_TOP + (c["mated"] or 0.0))
    g = [max(b[0] - h, l - b[1], 0.0) for (l, h, b) in zip(lo, hi, HOT_BLOCK)]
    return sum(v * v for v in g) ** 0.5


# Negative controls: spots the model is known to occupy. Each must FAIL, or the check is not seeing parts.
CONTROLS = [
    dict(name="ctrl@J13", part="probe", centre=(88.0, 85.65), body=(5.9, 4.5), mated=9.8, od=1.5, own=()),
    dict(name="ctrl@J1", part="probe", centre=(55.0, 84.0), body=(6.0, 4.0), mated=9.8, od=1.5, own=()),
    dict(name="ctrl@J12", part="probe", centre=(126.0, 86.0), body=(5.9, 4.5), mated=9.8, od=1.5, own=()),
]
# Always the controller's own: the allocation envelope of its components (Z24.6-31 over the whole board).
OWN_ALWAYS = ("electronics_SELV_controller_components_ENVELOPE",)


def prism(c: dict) -> bd.Solid:
    (x, y), (w, d) = c["centre"], c["body"]
    hw, hd = w / 2 + MARGIN, d / 2 + MARGIN
    return bd.Solid.make_box(2 * hw, 2 * hd, H_PROBE, bd.Plane((x - hw, y - hd, BOARD_TOP + 0.01)))


def need(c: dict) -> float | None:
    return None if c["mated"] is None else c["mated"] + BEND * c["od"] + c["od"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    here = Path(__file__).resolve()
    ap.add_argument("--r43", type=Path, default=here.parents[5] / "output/temper-manufacturing-r43")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    catalog = json.loads((a.r43 / "catalog.json").read_text())
    for p in catalog:
        if hashlib.sha256((a.r43 / p["file"]).read_bytes()).hexdigest() != p["sha256"]:
            raise SystemExit(f"saved geometry differs from catalog: {p['name']}")
    rows = []
    for c in CONNECTORS + CONTROLS:
        pr = prism(c)
        pb = pr.bounding_box()
        hits = []
        for p in catalog:
            if p["kind"] == "reference":
                continue
            b = p["bbox"]
            if (b[3] <= pb.min.X or b[0] >= pb.max.X or b[4] <= pb.min.Y or b[1] >= pb.max.Y
                    or b[5] <= pb.min.Z or b[2] >= pb.max.Z):
                continue
            zmin, vol = None, 0.0
            for s in bd.import_step(a.r43 / p["file"]).solids():
                o = pr.intersect(s)
                if o is None:
                    continue
                for q in (o if isinstance(o, bd.ShapeList) else [o]):
                    for sol in q.solids():
                        if sol.volume > 1e-3:
                            vol += sol.volume
                            z = sol.bounding_box().min.Z
                            zmin = z if zmin is None else min(zmin, z)
            if zmin is not None:
                own = p["name"] in c["own"] or p["name"] in OWN_ALWAYS
                hits.append(dict(part=p["name"], kind=p["kind"], z_min=round(zmin, 2), overlap_mm3=round(vol, 1), own=own))
        foreign = [h for h in hits if not h["own"]]
        free = min((h["z_min"] for h in foreign), default=BOARD_TOP + H_PROBE) - BOARD_TOP
        n = need(c)
        verdict = "UNREAD (mated height)" if n is None else ("PASS" if free >= n else "FAIL")
        rows.append(dict(connector=c["name"], part=c["part"], centre=c["centre"], body=c["body"], margin=MARGIN,
                         free_height_mm=round(free, 2), plug_to_hot_block_mm=round(gap_to_hot(c), 2), need_mm=None if n is None else round(n, 2), verdict=verdict,
                         obstructions=sorted(hits, key=lambda h: h["z_min"])))
    bad_controls = [r["connector"] for r in rows if r["connector"].startswith("ctrl@") and r["verdict"] != "FAIL"]
    rows_out = [r for r in rows if not r["connector"].startswith("ctrl@")]
    for r in rows:
        print(f"{r['connector']} {r['part']} at {r['centre']}: free {r['free_height_mm']:.1f} mm above the board, "
              f"need {r['need_mm']} -> {r['verdict']}; "
              f"plug body to the J13 HOT block {r['plug_to_hot_block_mm']:.2f} mm")
        for h in r["obstructions"]:
            print(f"    {'own ' if h['own'] else '    '}{h['part']} ({h['kind']}) from Z{h['z_min']:.2f}, {h['overlap_mm3']:.0f} mm3")
    if a.json:
        a.json.write_text(json.dumps(dict(r43=str(a.r43.name), board_top=BOARD_TOP, probe_height=H_PROBE, rows=rows_out,
                                          controls_failed_as_required=not bad_controls), indent=1) + "\n")
    if bad_controls:
        raise SystemExit(f"negative control did not FAIL: {bad_controls}")
    if any(r["verdict"] != "PASS" for r in rows_out):
        raise SystemExit("a proposed connector does not PASS")


if __name__ == "__main__":
    main()
