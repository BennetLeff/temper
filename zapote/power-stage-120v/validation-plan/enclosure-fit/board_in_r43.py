#!/usr/bin/env python3
"""Populated native-21 board in the CURRENT enclosure (R43), real mounting pose, exact solids.

    uv run --offline --no-project --with cadquery-ocp python board_in_r43.py BOARD.step COURTYARDS.json ENVELOPES.json \
        r43-catalog-bboxes.json R43_DIR OUT.json

Stage 53 (s52 footprint/3D review item 23). The chain's old FIT line ran board_in_enclosure.py in its default
`mirror-legacy` pose against the R4 catalog; DECISIONS 2026-10-09 calls that pose a reflection that no board can take.
This check uses:
  * pose (a) as built from R31 on: world = (x - 141, 236 - y, 26 + z), board-local KiCad frame. On the STEP's own
    axes (y up = -KiCad y, z up from the board bottom) that is a pure translation (-141, +236, +26);
  * the frozen R43 solids (r43_catalog_snapshot.py; every part file's sha256 is checked against the snapshot);
  * the lead-trim assembly rule (ASSEMBLY.md, DECISIONS 2026-10-09: THT leads cut to <= 2.5 mm below the board):
    board solids are cut at board-local z = -2.5 mm;
  * a 1.0 mm gap (fit_gate.GAP). An AABB pre-filter picks candidate pairs; each is then measured solid to solid
    (BRepExtrema_DistShapeShape), because the R43 brackets are L-shaped and their boxes span empty space over the
    board (the PS3 bracket's box reaches down to the base floor outboard of the board, the fascia's spans the front);
  * model-less parts (ENVELOPES.json: courtyard x datasheet height) as boxes.
Skipped as obstacles: the harness group (cable AABBs), *_ENVELOPE allocations, the board slab item, and the P4
U-wrapper, whose inner box (less its 1.27 mm wall) is the interior every board solid must stay inside.

Intended interfaces (INTERFACES below) are parts designed to touch a board part: mating plugs, the coil lugs on J2 / J5,
the heatsink stack on the TO-247 row and BR1, and the standoffs / top screws on the board at the mounting holes. They are
listed by name and board reference and are not hits; every other pair under the gap is, and the exit status is 1.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

X0, Y0, ZB = -141.0, 236.0, 26.0
GAP = 1.0
LEAD_TRIM = 2.5
WALL = 1.27
SHELL = "enclosure_P4_U_wrapper"
# (catalog name regex, board reference regex, why the two touch by design)
INTERFACES = [
    (r"^electronics_native21_J3_mate$", r"^(J3|BOARD)$", "TCO loop plug mated in J3 (seated on the board face)"),
    (r"^electronics_native21_J4_mate$", r"^(J4|BOARD)$", "controller harness plug mated in J4 (seated on the board face)"),
    (r"^electronics_native21_J11_mate$", r"^(J11|BOARD)$", "PS3 mains plug mated in J11 (seated on the board face)"),
    (r"^electronics_coil_lug_J2$", r"^J2$", "coil lead lug bolted to J2"),
    (r"^electronics_coil_lug_J5$", r"^J5$", "coil lead lug bolted to J5"),
    (r"^electronics_sink_", r"^(Q2|Q3|Q5|Q6|BR1|BOARD)$",
     "heatsink stack (AlN tiles, gap pad, FR-4 strip, comb) clamps the TO-247 row and BR1 at the board's rear edge"),
    (r"^electronics_native21_(standoff|top_screw)_H\d+$", r"^(BOARD|H\d+)$", "standoff / top screw at a mounting hole"),
]


def read_solids(path):
    r = STEPControl_Reader()
    if r.ReadFile(str(path)) != 1:
        raise SystemExit(f"cannot read {path}")
    r.TransferRoots()
    ex = TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    out = []
    while ex.More():
        out.append(TopoDS.Solid(ex.Current()))
        ex.Next()
    return out


def bbox(shape):
    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b)
    lo, hi = b.CornerMin(), b.CornerMax()
    return [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()]


def moved(shape, dx, dy, dz):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def near(a, b, gap):
    return a[0] < b[3] + gap and a[3] > b[0] - gap and a[1] < b[4] + gap and a[4] > b[1] - gap and \
        a[2] < b[5] + gap and a[5] > b[2] - gap


def main():
    step, crt_p, env_p, snap_p, r43, out_p = sys.argv[1:7]
    expect = json.load(open(sys.argv[sys.argv.index("--expect") + 1]))["hits"] if "--expect" in sys.argv else []
    crt = json.load(open(crt_p))
    env = json.load(open(env_p))
    snap = json.load(open(snap_p))
    r43 = Path(r43)
    shell = [x for x in snap["items"] if x["name"] == SHELL]
    if len(shell) != 1:
        raise SystemExit(f"shell {SHELL} not found once in {snap_p}")
    sh = shell[0]["bbox"]
    interior = [sh[0] + WALL, sh[1] + WALL, sh[2] + WALL, sh[3] - WALL, sh[4] - WALL, sh[5] - WALL]
    items = [x for x in snap["items"] if x["group"] != "harness" and not x["name"].endswith("_ENVELOPE")
             and x["name"] not in (SHELL, "electronics_native21_board")]

    def owner(lb):
        """Board ref of a board-local box: the smallest courtyard holding its plan centre ('BOARD' for the slab)."""
        if lb[5] - lb[2] < 2 and (lb[3] - lb[0]) * (lb[4] - lb[1]) > 30000:
            return "BOARD"
        cx, cy = (lb[0] + lb[3]) / 2, (lb[1] + lb[4]) / 2
        best = None
        for r, (x0, y0, x1, y1) in crt.items():
            if x0 - 0.5 <= cx <= x1 + 0.5 and y0 - 0.5 <= cy <= y1 + 0.5:
                a = (x1 - x0) * (y1 - y0)
                if best is None or a < best[1]:
                    best = (r, a)
        return best[0] if best else None

    # board solids, lead tails cut at the trim rule, posed
    cut_box = BRepPrimAPI_MakeBox(gp_Pnt(-1e4, -1e4, -1e3), gp_Pnt(1e4, 1e4, -LEAD_TRIM)).Shape()
    bodies = []
    for s in read_solids(step):
        b0 = bbox(s)
        if b0[2] < -LEAD_TRIM - 1e-6:
            s = BRepAlgoAPI_Cut(s, cut_box).Shape()
        w = moved(s, X0, Y0, ZB)
        wb = bbox(w)
        local = [wb[0] - X0, Y0 - wb[4], wb[2] - ZB, wb[3] - X0, Y0 - wb[1], wb[5] - ZB]
        bodies.append({"ref": owner(local), "shape": w, "world": wb, "local": local})
    for r, h in env.items():          # model-less parts: courtyard x datasheet height (board top 1.6 mm)
        x0, y0, x1, y1 = crt[r]
        lo, hi = gp_Pnt(x0 + X0, Y0 - y1, ZB + 1.6), gp_Pnt(x1 + X0, Y0 - y0, ZB + 1.6 + h)
        w = BRepPrimAPI_MakeBox(lo, hi).Shape()
        bodies.append({"ref": r, "shape": w, "world": bbox(w), "local": [x0, y0, 1.6, x1, y1, 1.6 + h], "envelope": True})
    parts, checked = {}, 0
    hits, interfaces, outside = [], [], []
    for b in bodies:
        wb = b["world"]
        if not (interior[0] <= wb[0] and wb[3] <= interior[3] and interior[1] <= wb[1] and wb[4] <= interior[4]
                and interior[2] <= wb[2] and wb[5] <= interior[5]):
            outside.append({"ref": b["ref"], "world": [round(v, 2) for v in wb]})
        for it in items:
            if not near(wb, it["bbox"], GAP):
                continue
            why = next((w for pn, pr, w in INTERFACES if re.search(pn, it["name"]) and b["ref"] and re.search(pr, b["ref"])),
                       None)
            if why:
                interfaces.append({"ref": b["ref"], "part": it["name"], "why": why})
                continue
            if it["name"] not in parts:
                f = r43 / it["file"]
                if hashlib.sha256(f.read_bytes()).hexdigest() != it["sha256"]:
                    raise SystemExit(f"{f}: sha256 differs from the snapshot")
                parts[it["name"]] = read_solids(f)
            d = min(BRepExtrema_DistShapeShape(b["shape"], ps).Value() for ps in parts[it["name"]])
            checked += 1
            if d < GAP:
                hits.append({"ref": b["ref"], "part": it["name"], "distance_mm": round(d, 3),
                             "local": [round(v, 2) for v in b["local"]], "world": [round(v, 2) for v in wb]})
    res = {"step_sha256": hashlib.sha256(Path(step).read_bytes()).hexdigest(), "revision": snap["revision"],
           "catalog_sha256": snap["source_sha256"], "pose": "translate (x - 141, 236 - y, 26 + z)", "gap_mm": GAP,
           "lead_trim_mm": LEAD_TRIM, "bodies": len(bodies), "exact_pairs_checked": checked,
           "interfaces": sorted({(i["ref"], i["part"], i["why"]) for i in interfaces}),
           "outside_interior": outside, "hits": hits}
    # known hits (r43-expected-hits.json, each with its reason) are a ratchet, as pin_absmax_expected.json: a hit not
    # listed, or a listed one now closer than recorded, fails; a listed one that no longer hits is stale and fails too
    key = {(e["ref"], e["part"]): e for e in expect}
    new = [h for h in hits if (h["ref"], h["part"]) not in key]
    worse = [h for h in hits if (h["ref"], h["part"]) in key and h["distance_mm"] < key[(h["ref"], h["part"])]["distance_mm"] - 0.01]
    stale = sorted(set(key) - {(h["ref"], h["part"]) for h in hits})
    res.update(new_hits=new, worse_hits=worse, stale_expected=[list(k) for k in stale])
    Path(out_p).write_text(json.dumps(res, indent=1) + "\n")
    print(f"R43 FIT bodies {len(bodies)} exact {checked} hits {len(hits)} (new {len(new)}, worse {len(worse)}, "
          f"stale {len(stale)}) outside {len(outside)} interfaces {len(res['interfaces'])}")
    for h in hits:
        print("  HIT", "known" if (h["ref"], h["part"]) in key else "NEW", h["ref"], h["part"], h["distance_mm"], h["local"])
    sys.exit(1 if new or worse or stale or outside else 0)


main()
