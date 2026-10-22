"""R1 coil parts substituted into the frozen R43 enclosure: interference screen and clearances.

Method (the same as R43's src/check_integration.py --all-pairs, restricted to the pairs the substitution touches):
  - R43's catalog.json and saved STEP parts, every file's sha256 checked against the catalog (read-only);
  - the R43 parts sensor_coil_former, sensor_coil_litz_winding, harness_coil_lead_to_J2/J5, electronics_coil_lug_J2/J5
    and sensor_coil_winding_NTC are replaced in memory by the R1 parts from r1_parts.py;
  - every pair (replaced part, any other non-reference part) and (replaced, replaced) whose bounding boxes overlap is
    intersected solid by solid; a positive volume > 1e-4 mm3 is a hit. A hit is dispositioned with R43's own
    expected-interference row for that pair (subsystem-metadata.json, same vocabulary and volume limit); anything else is
    REVIEW_REQUIRED and is dispositioned by hand in DISPOSITIONS below (same vocabulary), with the reason;
  - clearances: exact minimum distance (OCCT) from each replaced part to every part within 3 mm of its box; pairs under
    1.0 mm are listed, and the glass-underside gaps are reported for the comb top, winding top and both leads.
Configurations: former CNC / print x winding R1 / with the spare turn (the leads follow the winding's outer end).
Run: .venv/bin/python -B fit/screen_r1_in_r43.py  -> fit/results/r1-in-r43-screen.json  (several minutes)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build123d as bd  # noqa: E402

import lug as LUG  # noqa: E402
import r1_parts as R  # noqa: E402

ROOT = R.R43
OUT = HERE / "results" / "r1-in-r43-screen.json"
REPLACED = ("sensor_coil_former", "sensor_coil_litz_winding", "harness_coil_lead_to_J2", "harness_coil_lead_to_J5",
            "electronics_coil_lug_J2", "electronics_coil_lug_J5", "sensor_coil_winding_NTC")
GAP = 1.0
# Exact distance is skipped where the parts touch by design (OCCT's extrema on the swept spiral against the comb runs for
# many minutes): the winding (its gaps are reported analytically from the stack), and the former on the carrier top and
# round the bars. Intersection volume is still computed for every pair.
NO_DISTANCE = {"sensor_coil_litz_winding"}
NO_DISTANCE_PAIRS = {frozenset(p) for p in (("sensor_coil_former", "sensor_coil_ferrite_bars"),
                                             ("sensor_coil_former", "sensor_coil_routed_insulating_carrier"))}
# Hits outside R43's own allowances, dispositioned by hand (filled from the first run's output; vocabulary as R43).
DISPOSITIONS = {
    **{frozenset((f"harness_coil_lead_to_{n}", "sensor_coil_litz_winding")): dict(
        disposition="DOCUMENTED_CONDUCTOR_CONTINUITY", maximum_accepted_reporting_mm3=40.0,
        reason="the lead is the winding's own Litz continuing out; the overlap is the 3.55 mm sleeved lead's start cap over the 2.29 mm bundle end (R43's 15 mm3 was for a 2.4 mm lead on a 2.4 mm bundle)")
       for n in ("J2", "J5")},
    frozenset(("harness_coil_lead_to_J2", "electronics_coil_lug_J2")): dict(
        disposition="DOCUMENTED_UNVERIFIED_CABLE_ENTRY", maximum_accepted_reporting_mm3=130.0,
        reason="the sleeved lead runs inside the lug's PVDF heat-shrink for its last 10 mm and enters the barrel (R43's 60 mm3 limit was for a bare lead into a barrel, no shrink)"),
    frozenset(("harness_coil_lead_to_J5", "electronics_coil_lug_J5")): dict(
        disposition="DOCUMENTED_UNVERIFIED_CABLE_ENTRY", maximum_accepted_reporting_mm3=130.0,
        reason="the sleeved lead runs inside the lug's PVDF heat-shrink for its last 10 mm and enters the barrel (R43's 60 mm3 limit was for a bare lead into a barrel, no shrink)"),
}


def bbox(s):
    b = s.bounding_box()
    return [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z]


def overlap(a, b, pad=0.0):
    return all(a[i] < b[i + 3] + pad and b[i] < a[i + 3] + pad for i in range(3))


def solids_of(shape):
    return [(s, bbox(s)) for s in shape.solids()]


def inter_volume(sa, sb):
    tot = 0.0
    for a, ab in sa:
        for b, bb in sb:
            if not overlap(ab, bb):
                continue
            o = a.intersect(b)
            if o is not None:
                tot += sum(x.volume for x in o) if isinstance(o, bd.ShapeList) else o.volume
    return tot


def distance(sa, sb, pad):
    d = math.inf
    for a, ab in sa:
        for b, bb in sb:
            if overlap(ab, bb, pad):
                d = min(d, a.distance_to(b))
    return d


def main():
    t0 = time.time()
    catalog = json.loads((ROOT / "catalog.json").read_text())
    for p in catalog:
        if hashlib.sha256((ROOT / p["file"]).read_bytes()).hexdigest() != p["sha256"]:
            raise SystemExit(f"R43 saved geometry differs from its catalog: {p['name']}")
    meta = json.loads((ROOT / "evidence/subsystem-metadata.json").read_text())
    expected = {frozenset(r["pair"]): r for sec in meta.values() for r in sec.get("expected_interferences", [])}
    others = [p for p in catalog if p["kind"] != "reference" and p["name"] not in REPLACED]
    cache = {}

    def other_solids(p):
        if p["name"] not in cache:
            cache[p["name"]] = solids_of(bd.import_step(ROOT / p["file"]))
        return cache[p["name"]]

    # ---- R1 parts per variant
    parts = {}
    f_cnc, f_info = R.former_world("cnc")
    f_pr, _ = R.former_world("print")
    parts[("sensor_coil_former", "cnc")] = f_cnc
    parts[("sensor_coil_former", "print")] = f_pr
    parts[("sensor_coil_winding_NTC", "-")] = R.ntc_bead(f_info)
    winfo, linfo = {}, {}
    for st in ("R1", "spare"):
        w, wi = R.winding(st)
        parts[("sensor_coil_litz_winding", st)] = w
        winfo[st] = wi
        for n, pts in R.lead_points(st).items():
            s, li = R.lead(pts, LUG.BEND_RULE_MM, n)
            parts[(f"harness_coil_lead_to_{n}", st)] = s
            linfo[f"{n}_{st}"] = {k: v for k, v in li.items() if k != "points"}
    for n in ("J2", "J5"):
        parts[(f"electronics_coil_lug_{n}", "-")] = LUG.lug_solid(n)
    psol = {k: solids_of(v) for k, v in parts.items()}
    pbox = {k: bbox(v) for k, v in parts.items()}
    print(f"parts built {time.time() - t0:.0f} s", flush=True)

    pair_cache = {}

    def check(ka, sa, ba, kb, sb, bb):
        key = (ka, kb)
        if key in pair_cache:
            return pair_cache[key]
        t = time.time()
        vol = inter_volume(sa, sb) if overlap(ba, bb) else 0.0
        skip = ka[0] in NO_DISTANCE or kb[0] in NO_DISTANCE or kb[1] in NO_DISTANCE or frozenset((ka[0], kb[1])) in NO_DISTANCE_PAIRS
        d = 0.0 if vol > 1e-4 else (math.nan if skip else (distance(sa, sb, GAP) if overlap(ba, bb, GAP) else math.inf))
        pair_cache[key] = (vol, d)
        if time.time() - t > 5:
            print(f"   slow pair {ka} {kb}: {time.time() - t:.0f} s", flush=True)
        return vol, d

    configs = [("cnc", "R1"), ("cnc", "spare"), ("print", "R1"), ("print", "spare")]
    results = []
    for fv, st in configs:
        sel = {"sensor_coil_former": ("sensor_coil_former", fv), "sensor_coil_litz_winding": ("sensor_coil_litz_winding", st),
               "harness_coil_lead_to_J2": ("harness_coil_lead_to_J2", st), "harness_coil_lead_to_J5": ("harness_coil_lead_to_J5", st),
               "electronics_coil_lug_J2": ("electronics_coil_lug_J2", "-"), "electronics_coil_lug_J5": ("electronics_coil_lug_J5", "-"),
               "sensor_coil_winding_NTC": ("sensor_coil_winding_NTC", "-")}
        hits, close, pairs = [], [], 0
        names = list(sel)
        for i, na in enumerate(names):
            ka = sel[na]
            targets = [(p["name"], ("R43", p["name"]), None, p["bbox"], p) for p in others]
            targets += [(nb, sel[nb], None, pbox[sel[nb]], None) for nb in names[i + 1:]]
            for nb, kb, _, bb, p in targets:
                if not overlap(pbox[ka], bb, GAP):
                    continue
                sb = psol[kb] if p is None else other_solids(p)
                vol, d = check(ka, psol[ka], pbox[ka], kb, sb, bb)
                pairs += 1
                if vol > 1e-4:
                    h = dict(a=na, b=nb, volume_mm3=round(vol, 4), disposition="REVIEW_REQUIRED")
                    allow = expected.get(frozenset((na, nb)))
                    hand = DISPOSITIONS.get(frozenset((na, nb)))
                    if allow and vol <= allow["maximum_accepted_reporting_mm3"]:
                        h.update(disposition=allow["disposition"], basis="R43 " + allow["reason"],
                                 limit_mm3=allow["maximum_accepted_reporting_mm3"])
                    elif hand and vol <= hand["maximum_accepted_reporting_mm3"]:
                        h.update(disposition=hand["disposition"], basis="R1 fit: " + hand["reason"],
                                 limit_mm3=hand["maximum_accepted_reporting_mm3"])
                    elif allow:
                        h["note"] = f"over R43's limit {allow['maximum_accepted_reporting_mm3']} mm3 ({allow['disposition']})"
                    hits.append(h)
                elif d < GAP:
                    close.append(dict(a=na, b=nb, distance_mm=round(d, 3)))
        unresolved = [h for h in hits if h["disposition"] == "REVIEW_REQUIRED"]
        results.append(dict(former=fv, winding=st, pairs_checked=pairs, hits=hits, under_1mm=close,
                            unresolved=len(unresolved)))
        print(f"{fv}/{st}: pairs {pairs}, hits {len(hits)}, unresolved {len(unresolved)}, under 1 mm {len(close)} "
              f"({time.time() - t0:.0f} s)", flush=True)
        for h in hits:
            print("   HIT", h["a"], h["b"], h["volume_mm3"], h["disposition"], h.get("note", ""), flush=True)
        for c in close:
            print("   NEAR", c["a"], c["b"], c["distance_mm"], flush=True)

    # ---- glass and the stack
    glass = next(p for p in others if p["name"] == "enclosure_glass_350x340x4_sensor_bore")
    gs = other_solids(glass)
    gl = {}
    for k in [("sensor_coil_former", "cnc"), ("sensor_coil_former", "print"), ("sensor_coil_litz_winding", "R1"),
              ("sensor_coil_litz_winding", "spare"), ("harness_coil_lead_to_J5", "R1"), ("harness_coil_lead_to_J2", "R1")]:
        # the glass underside is the plane Z106 over the whole coil (its bore is at the centre, r < 22): top-to-plane gap
        gl[f"{k[0]}/{k[1]}"] = dict(top_z=round(pbox[k][5], 3), gap_to_glass_underside_mm=round(R.Z_GLASS - pbox[k][5], 3))
    stack = dict(roof_top_z=R.Z_ROOF_TOP, bundle_mm=R.BUNDLE, winding_centre_z=R.Z_WIND, winding_top_z=R.Z_WIND_TOP,
                 comb_top_z=R.Z_COMB_TOP, glass_underside_z=R.Z_GLASS, pan_base_z=110.0,
                 comb_top_to_glass_mm=round(R.Z_GLASS - R.Z_COMB_TOP, 3), winding_top_to_glass_mm=round(R.Z_GLASS - R.Z_WIND_TOP, 3),
                 winding_centre_to_pan_mm=round(110.0 - R.Z_WIND, 3), em_model_winding_centre_z=R.G.Z_WIND_C,
                 em_model_centre_to_pan_mm=round(110.0 - R.G.Z_WIND_C, 3),
                 crossing_lead_centre_z=round(R.Z_CROSS, 3), crossing_lead_top_z=round(R.Z_CROSS + R.LEAD_OD / 2, 3),
                 crossing_lead_top_to_glass_mm=round(R.Z_GLASS - R.Z_CROSS - R.LEAD_OD / 2, 3), lead_od_mm=R.LEAD_OD)
    res = dict(about=__doc__.strip(), r43_root=str(ROOT), r43_catalog_sha256=hashlib.sha256((ROOT / "catalog.json").read_bytes()).hexdigest(),
               build123d=bd.__version__, replaced=list(REPLACED), lug=LUG.SUMMARY, sleeve=LUG.SLEEVE, bend_rule=LUG.BEND_RULE,
               winding=winfo, leads=linfo, former_info={k: v for k, v in f_info.items() if k != "ntc"} | dict(
                   ntc=dict(last_inner_turn_r=f_info["ntc"]["last_inner_turn_r"], bead_centre_r=f_info["ntc"]["bead_centre_r"])),
               configs=results, glass=gl, stack=stack, runtime_s=round(time.time() - t0))
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    for k in ("sensor_coil_former/cnc", "sensor_coil_litz_winding/R1", "harness_coil_lead_to_J5/R1"):
        print(k, gl[k])
    print(json.dumps(stack))
    if any(r["unresolved"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
