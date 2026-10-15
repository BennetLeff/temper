#!/usr/bin/env python3
"""Controls for track_cleanup21.py (stage 37, the post-route geometry cleanup) on synthetic boards.

    python3 native-21/layout/test_track_cleanup21.py

1. Each of the four fixes on its own: a free fold-back, a fold-back whose tip is a via (duplicate overlap), a 45 deg
   acute corner (-> 3 x 135), a right angle (-> 2 x 135), an any-angle segment (-> octilinear dogleg).
2. Every edit keeps the net's connectivity: the pad / via / fill partition, floating groups and dangling ends are
   compared before and after on every case (track_cleanup21.Board.partition), and the endpoints at pads stay.
3. Skips: a dogleg with an other-net pad on both sides is refused for clearance (the segment stays); a mitre whose
   tip is overlapped by a third track's end (KiCad joins it there) is refused for connectivity; a corner on res_a
   (RES_A creepage copper) is never touched; a mitre near an other-net pad falls back to a smaller legal chamfer.
4. A barrier case: a SELV any-angle segment 8.6 mm from HOT copper takes the dogleg away from it, never towards it.
5. Idempotence: a second run on every result applies nothing.
"""
import copy
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import track_cleanup21 as tc  # noqa: E402

fails = 0


def check(ok, what, detail=""):
    global fails
    fails += not ok
    print("ok  " if ok else "FAIL", what, "" if ok else detail)


def sq(x, y, h):
    return [[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h]]


def board(tracks, pads=(), vias=(), fills=(), zones=()):
    """A 100 x 100 mm board: pads (ref.pad, net, x, y, half-size) on F.Cu, vias, other-net fills (net, layer, shell)."""
    pl, prims = [], []
    for name, net, x, y, h in pads:
        ref, pad = name.split(".")
        pl.append({"ref": ref, "pad": pad, "net": net, "x": x, "y": y, "box": [x - h, y - h, x + h, y + h],
                   "tht": False, "npth": False, "fc": [x, y]})
        prims.append({"kind": "pad", "ref": name, "net": net, "layer": "F.Cu", "centre": [x, y], "shell": sq(x, y, h),
                      "holes": []})
    for net, layer, shell in fills:
        prims.append({"kind": "zone", "net": net, "layer": layer, "shell": shell, "holes": []})
    copper = {"zones": list(zones), "tracks": copy.deepcopy(list(tracks)),
              "vias": [{"net": n, "at": [x, y], "size": 0.6, "drill": 0.3} for n, x, y in vias], "escapes": []}
    export = {"outline": {"shell": [[0, 0], [100, 0], [100, 100], [0, 100]], "holes": []}, "primitives": prims}
    b = tc.Board(copper, export, pl)
    b._export, b._pads = export, pl     # for the idempotence re-run
    return b


def T(net, pts, w=0.25, layer="F.Cu"):
    return {"net": net, "layer": layer, "width": w, "points": pts}


def geo(b):
    return tc.track_geometry.measure(tc.prims_of(b))


def angles(b, net, layer="F.Cu"):
    out = []
    for v, inc in b.vertices(net, layer).items():
        if len(inc) == 2:
            (t1, j1, n1), (t2, j2, n2) = inc
            out.append(round(tc.angle_at(b.xy(b.tracks[t1]["points"][j1]), b.xy(b.tracks[t1]["points"][n1]),
                                         b.xy(b.tracks[t2]["points"][n2])), 1))
    return sorted(out)


def run_case(name, b, nets):
    parts = {n: b.partition(n) for n in nets}
    before = geo(b)
    applied, skipped = tc.run(b)
    b._part.clear()
    after = geo(b)
    for n in nets:
        check(b.partition(n) == parts[n], f"{name}: connectivity of {n} unchanged", (parts[n], b.partition(n)))
    again = tc.Board(b.copper, b._export, b._pads)
    a2, _ = tc.run(again)
    check(sum(a2.values()) == 0, f"{name}: a second run applies nothing", dict(a2))
    return before, after, applied, skipped


# 1a. free fold-back: R1.1 -> (20, 10) doubles back to (15, 10) -> R2.1
b = board([T("na", ["R1.1", [20, 10]]), T("na", [[20, 10], [15, 10], "R2.1"])],
          pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 15, 15, 0.3)])
bf, af, ap, _ = run_case("free fold-back", b, ["na"])
check(bf["fold_backs"] == 1 and af["fold_backs"] == 0 and af["acute_corners"] == 0, "free fold-back removed", (bf, af))
check(all(math.dist(b.xy(q), (20, 10)) > 1 for t in b.tracks for q in t["points"]), "the dead tip at (20, 10) is gone",
      [t["points"] for t in b.tracks])
check(any(t["points"][0] == "R1.1" or t["points"][-1] == "R1.1" for t in b.tracks)
      and any("R2.1" in t["points"] for t in b.tracks), "pad endpoints kept")

# 1b. fold-back whose tip is a via: the overlapping duplicate goes, the via keeps its track
b = board([T("na", ["R1.1", [20, 10]]), T("na", [[20, 10], [15, 10], "R2.1"]), T("na", [[20, 10], [30, 10]], layer="B.Cu"),
           T("na", [[30, 10], "R3.1"])],
          pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 15, 15, 0.3), ("R3.1", "na", 30, 12, 0.3)],
          vias=[("na", 20, 10), ("na", 30, 10)])
bf, af, ap, _ = run_case("fold-back at a via", b, ["na"])
check(bf["fold_backs"] == 1 and af["fold_backs"] == 0, "via fold-back removed", (bf, af))
check(any(math.dist(b.xy(t["points"][-1]), (20, 10)) < 1e-6 or math.dist(b.xy(t["points"][0]), (20, 10)) < 1e-6
          for t in b.tracks if t["layer"] == "F.Cu"), "a track still reaches the via")

# 1c. acute 45 deg corner (free tip): R1.1 -> (20, 10) -> (12, 18) -> R2.1
b = board([T("na", ["R1.1", [20, 10], [12, 18], "R2.1"])], pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 12, 25, 0.3)])
bf, af, ap, _ = run_case("acute corner", b, ["na"])
check(bf["acute_corners"] == 1 and af["acute_corners"] == 0 and af["right_angle_corners"] == 0, "acute corner opened", (bf, af))
check(min(angles(b, "na")) >= 134.5, "opened into 135 deg bends", angles(b, "na"))

# 1d. right angle: R1.1 -> (20, 10) -> R2.1 at (20, 20)
b = board([T("na", ["R1.1", [20, 10], "R2.1"])], pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 20, 20, 0.3)])
bf, af, ap, _ = run_case("right angle", b, ["na"])
check(bf["right_angle_corners"] == 1 and af["right_angle_corners"] == 0, "right angle mitred", (bf, af))
check(angles(b, "na") == [135.0, 135.0], "two 135 deg bends", angles(b, "na"))
leg = min(math.dist(b.xy(q), (20, 10)) for t in b.tracks for q in t["points"])
check(0.25 <= leg <= 1.5, f"chamfer leg suits the 0.25 mm track ({leg:.2f} mm from the old corner)")

# 1e. any-angle segment R1.1 (10, 10) -> R2.1 (20, 15)
b = board([T("na", ["R1.1", "R2.1"])], pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 20, 15, 0.3)])
bf, af, ap, _ = run_case("any-angle", b, ["na"])
check(bf["any_angle_mm"] > 11 and af["any_angle_mm"] == 0.0, "any-angle snapped to octilinear", (bf, af))
check(angles(b, "na") == [135.0], "one 135 deg bend", angles(b, "na"))

# 3a. dogleg blocked by other-net pads on both sides: stays, clearance reason
b = board([T("na", ["R1.1", "R2.1"])], pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 20, 15, 0.3),
                                             ("X1.1", "nb", 15, 15.35, 0.1), ("X2.1", "nb", 15, 9.65, 0.1)])
bf, af, ap, sk = run_case("dogleg blocked", b, ["na", "nb"])
check(af == bf and sum(ap.values()) == 0, "blocked dogleg left as it was", (bf, af))
check(any(w.startswith("clearance") for w in sk.values()), "skipped for clearance", sk)

# 3b. a third track's end overlaps the corner tip (KiCad joins it there): a mitre would cut it off
b = board([T("na", ["R1.1", [20, 10], "R2.1"]), T("na", [[20.05, 10], [30, 10], "R3.1"])],
          pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 20, 20, 0.3), ("R3.1", "na", 30, 15, 0.3)])
bf, af, ap, sk = run_case("overlap-joined tip", b, ["na"])
check(b.tracks[0]["points"] == ["R1.1", [20, 10], "R2.1"], "corner with an overlap-joined track kept", b.tracks[0])
check(sk.get(("right", "F.Cu", ("na", (20, 10))), "").startswith("connect"), "skipped for connectivity", sk)
check(ap[("right", "F.Cu")] == 1, "the other track's own free corner (30, 10) is still mitred", dict(ap))

# 3c. res_a (RES_A creepage copper) is never edited
b = board([T("res_a", ["R1.1", [20, 10], "R2.1"], w=0.4)], pads=[("R1.1", "res_a", 10, 10, 0.3), ("R2.1", "res_a", 20, 20, 0.3)])
bf, af, ap, sk = run_case("res_a locked", b, ["res_a"])
check(af == bf and any("locked" in w for w in sk.values()), "res_a right angle left alone", sk)

# 3d. an other-net pad inside the corner, 0.275 mm from the arms: the largest mitre would hit it, a smaller one fits
b = board([T("na", ["R1.1", [20, 10], "R2.1"])], pads=[("R1.1", "na", 10, 10, 0.3), ("R2.1", "na", 20, 20, 0.3),
                                                       ("X1.1", "nb", 19.525, 10.475, 0.075)])
bf, af, ap, sk = run_case("mitre beside a pad", b, ["na", "nb"])
leg = min(math.dist(b.xy(q), (20, 10)) for t in b.tracks for q in t["points"])
check(af["right_angle_corners"] == 0 and leg < 0.5, f"smaller mitre chosen (leg {leg:.2f} mm)", (af, leg))
pad = tc.box(19.45, 10.4, 19.6, 10.55)
gap = min(tc.seg_shape(p, q, 0.25).distance(pad) for ti in range(len(b.tracks)) for p, q in b.segs(ti))
check(gap >= 0.2 + tc.MARGIN - 1e-6, f"mitre keeps clearance to the pad ({gap:.3f} mm)")

# 4. barrier: v3v3 (SELV) any-angle segment, an sw_a (HOT) pad ~8.5 mm below it; the dogleg towards it would cross 8 mm
b = board([T("v3v3", ["R1.1", "R2.1"])], pads=[("R1.1", "v3v3", 10, 50, 0.3), ("R2.1", "v3v3", 20, 55, 0.3),
                                               ("Q1.1", "sw_a", 15, 62.5, 0.3)])
d0 = b.barrier_dist("v3v3", tc.unary_union([tc.seg_shape(p, q, 0.25) for p, q in b.segs(0)]))
bf, af, ap, sk = run_case("barrier dogleg", b, ["v3v3", "sw_a"])
d1 = b.barrier_dist("v3v3", tc.unary_union([tc.seg_shape(p, q, 0.25) for ti in range(len(b.tracks)) for p, q in b.segs(ti)]))
check(af["any_angle_mm"] == 0.0 and d1 >= d0 - 1e-6, f"dogleg taken away from the HOT pad ({d0:.3f} -> {d1:.3f} mm)")
mid = [b.xy(q) for q in b.tracks[0]["points"]][1]
check(mid[1] < 52.5, f"the bend lies on the far side ({mid})")

print("PASS" if not fails else f"FAIL ({fails})")
raise SystemExit(1 if fails else 0)
