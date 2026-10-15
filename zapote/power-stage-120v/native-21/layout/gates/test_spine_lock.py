#!/usr/bin/env python3
"""Controls for spine_lock.py (the SELV-spine lock, selv_spine_lock.json).

    python3 -I native-21/layout/gates/test_spine_lock.py

Every case mutates the locked baseline (the s32 export) and states the verdict expected in each mode (default = a lane
that does not own the spine; selv = the SELV-side lane). Last, a real-data control: the s31 board must fail, because
stage 32 changed the spine (vias 0.85 -> 0.6 mm, the hsb_good hop B.Cu -> In2).
"""
import copy
import gzip
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("spine_lock", HERE / "spine_lock.py")
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)

lock = json.loads(sl.LOCK.read_text())
base = sl.load(sl.ROOT / lock["baseline"])["primitives"]
fails = 0


def first(pred):
    return next(i for i, p in enumerate(base) if pred(p))


def inside(xy, m=0.0):
    x0, y0, x1, y1 = lock["region"]
    return x0 + m <= xy[0] <= x1 - m and y0 + m <= xy[1] <= y1 - m


def mutated(fn):
    prims = copy.deepcopy(base)
    fn(prims)
    return prims


def case(name, prims, want_default, want_selv):
    global fails
    got = (sl.check(base, prims, lock)["pass"], sl.check(base, prims, lock, "selv")["pass"])
    ok = got == (want_default, want_selv)
    print("ok  " if ok else "FAIL", f"{name}: pass default / selv = {got}, want {(want_default, want_selv)}")
    fails += not ok


def nudge(i, dx=0.01):
    def f(prims):
        prims[i]["end"] = [prims[i]["end"][0] + dx, prims[i]["end"][1]]
    return f


case("unchanged", copy.deepcopy(base), True, True)

i = first(lambda p: p["kind"] == "track" and p["net"] == "pwm_ha" and inside(p["start"]) and inside(p["end"]))
case("contract net (pwm_ha) track end moved 10 um in the region", mutated(nudge(i)), False, False)

i = first(lambda p: p["kind"] == "track" and p["net"] == "ct_s2" and inside(p["start"]) and inside(p["end"]))
case("SELV-internal net (ct_s2) track moved in the region", mutated(nudge(i)), False, True)

i = first(lambda p: p["kind"] == "track" and p["net"] == "pwm_ha" and p["start"][1] < 120 and p["end"][1] < 120)
case("contract net track moved outside the region (LS end)", mutated(nudge(i, 0.5)), True, True)

i = first(lambda p: p["kind"] == "via" and p["net"] == "permit" and inside(p["centre"]))
case("contract via resized 0.6 -> 0.5", mutated(lambda pr: pr[i].update(diameter_mm=0.5)), False, False)

case("other net (sw_b) routed through the region",
     mutated(lambda pr: pr.append({"kind": "track", "net": "sw_b", "layer": "B.Cu", "start": [20.0, 150.0],
                                    "end": [40.0, 150.0], "width_mm": 0.25})), False, True)

i = first(lambda p: p["kind"] == "pad" and p["ref"] == "C47.1")
assert not inside(p := base[i]["centre"]), p
case("frozen ref C47 (outside the region) moved", mutated(lambda pr: pr[i].update(centre=[p[0] + 0.1, p[1]])), False, False)

i = first(lambda p: p["kind"] == "pad" and p["ref"].startswith("TP") and inside(p["centre"]))
case("test point in the region renamed", mutated(lambda pr: pr[i].update(ref="TP99.1")), False, True)


def hole(side):
    def f(prims):
        z = next(p for p in prims if p["kind"] == "zone" and p["net"] == "selv_gnd" and p["layer"] == "In2.Cu"
                 and sl.Polygon(p["shell"]).buffer(0).intersection(sl.box(*lock["region"])).area > 100)
        poly = sl.Polygon(z["shell"], z.get("holes") or []).buffer(0)
        c = next(pt for pt in (sl.Point(x, y) for x in range(40, 100, 2) for y in range(140, 170, 2))
                 if poly.contains(pt.buffer(side)))
        h = c.buffer(side / 2, cap_style=3)
        z["holes"] = (z.get("holes") or []) + [list(h.exterior.coords)]
    return f


case("selv_gnd In2 fill: 2 x 2 mm void in the region", mutated(hole(2.0)), False, False)
case("selv_gnd In2 fill: 0.5 x 0.5 mm void (under the 0.5 mm2 tolerance)", mutated(hole(0.5)), True, True)

s31 = sl.load(sl.ROOT / "native-21/verification/native21s31-all-copper.json.gz")["primitives"]
case("real data: the s31 board (before stage 32's spine edits)", s31, False, False)

print("PASS" if not fails else f"FAIL ({fails})")
raise SystemExit(1 if fails else 0)
