#!/usr/bin/env python3
"""CPL rotation audit for zapote/controller/fab/cpl-jlcpcb.csv (read-only on every input).

Two independent sources are compared for every placed line:
  A. JLC rotation-offset DB  (JLCKicadTools cpl_rotations_db.csv, the DB that Bouni/kicad-jlcpcb-tools
     "Download correction data" is built on): first regex match on the KiCad footprint name gives an offset d,
     JLC rotation = (KiCad rotation + d) mod 360.
  B. Geometry: the public EasyEDA/LCSC footprint of the BOM's LCSC part (easyeda_pads.json, pad number -> x,y) is
     rotated in 90-degree steps until its numbered pads land on the KiCad footprint's numbered pads. That step c is
     the offset JLC needs, because JLC places the LCSC library footprint at the CPL rotation.
Classes: OK / CORRECTED / NEEDS-PREVIEW (rules in README.md).  Outputs: audit.json audit.csv
cpl-jlcpcb.proposed.csv png/*.png.  usage: audit.py --db <cpl_rotations_db.csv>
"""
import argparse, csv, hashlib, json, math, pathlib, re, collections
import sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kicad_pads  # same-directory helper (explicit path because the script runs with python -I)
CTRL = HERE.parents[2]
CPL = CTRL / "fab" / "cpl-jlcpcb.csv"
BOM = CTRL / "fab" / "bom-jlcpcb.csv"
PCB = CTRL / "pcb" / "controller.kicad_pcb"


def load_db(path):
    rules = []
    for ln, row in enumerate(csv.reader(open(path, encoding="utf-8-sig"))):
        row = [c.strip() for c in row]
        if ln == 0 or not row or not row[0]:
            continue
        rules.append({"pattern": row[0], "rot": int(float(row[1])), "dx": row[2] if len(row) > 2 else "0",
                      "dy": row[3] if len(row) > 3 else "0", "line": ln + 1})
    return rules


def db_lookup(rules, fpname):
    for r in rules:
        if re.search(r["pattern"], fpname):
            return r
    return None


def rotate(p, c):
    """Rotate point (x,y; y down) counter-clockwise on screen by c degrees."""
    a = math.radians(c)
    x, y = p
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def pad_map(pads):
    g = collections.defaultdict(list)
    for p in pads:
        g[p["num"]].append((p["x"], p["y"]))
    return {n: (sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for n, v in g.items() if n}


def geometry(kpads, epads):
    """Return (best_c, rms_by_c, status)."""
    k = pad_map([p for p in kpads if "x" in p])
    e = pad_map([{"num": p["n"], "x": p["x"], "y": p["y"]} for p in epads if p["layer"] in ("1", "11")])
    common = sorted(set(k) & set(e))
    if len(common) < 2:
        return None, {}, "too few common pad numbers (%d)" % len(common)
    kc = (sum(k[n][0] for n in common) / len(common), sum(k[n][1] for n in common) / len(common))
    ec = (sum(e[n][0] for n in common) / len(common), sum(e[n][1] for n in common) / len(common))
    rms = {}
    for c in (0, 90, 180, 270):
        s = 0.0
        for n in common:
            rx, ry = rotate((e[n][0] - ec[0], e[n][1] - ec[1]), c)
            s += (rx - (k[n][0] - kc[0])) ** 2 + (ry - (k[n][1] - kc[1])) ** 2
        rms[c] = math.sqrt(s / len(common))
    order = sorted(rms, key=rms.get)
    best, second = order[0], order[1]
    if rms[best] > 0.8 and rms[best] > 0.25 * rms[second]:  # absolute fit, or an unambiguous winner when land widths differ
        return None, rms, "no 90-degree rotation matches the numbered pads (best RMS %.2f mm)" % rms[best]
    if rms[second] < rms[best] + 0.25:
        return None, rms, "ambiguous: symmetric pad set (RMS %.2f vs %.2f mm)" % (rms[best], rms[second])
    return best, rms, "ok"


def is_symmetric_nonpolar(ref, fpname, npads):
    return npads == 2 and (re.match(r"^(R|C|L)\d+$", ref) is not None) and not fpname.startswith(("CP_", "D_")) \
        and "Elec" not in fpname


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="downloaded cpl_rotations_db.csv")
    ap.add_argument("--pads", default=str(HERE / "easyeda_pads.json"))
    a = ap.parse_args()
    db_bytes = open(a.db, "rb").read()
    rules = load_db(a.db)
    ee = json.load(open(a.pads))
    fps = kicad_pads.footprints(PCB)
    bom = {}
    for r in csv.DictReader(open(BOM)):
        for d in r["Designator"].split(","):
            bom[d.strip()] = r
    cpl = list(csv.DictReader(open(CPL)))
    recs = []
    for row in cpl:
        ref = row["Designator"]
        rot = float(row["Rotation"]) % 360
        b = bom[ref]
        fp = fps[ref]
        fpname = fp["name"].split(":")[-1]
        dbrule = db_lookup(rules, fpname)
        d = None if dbrule is None else dbrule["rot"] % 360
        e = ee.get(b["LCSC Part #"])
        c, rms, gstat = (None, {}, "no EasyEDA footprint data") if not e else geometry(fp["pads"], e["pads"])
        notes = []
        if abs((fp["rot"] % 360) - rot) > 0.01:
            notes.append("CPL rotation %.1f differs from board footprint rotation %.1f" % (rot, fp["rot"] % 360))
        if fp["layer"] != "F.Cu":
            notes.append("not on top layer")
        sym = is_symmetric_nonpolar(ref, fpname, len(fp["pads"]))
        # ----- classification (rules are restated in README.md)
        tht = row["Mount"] == "THT"
        polarised = fpname.startswith(("CP_", "D_")) or re.match(r"^D\d+$", ref) is not None
        if sym:
            if c in (0, 180, None) and d in (None, 0, 180):
                cls, corr, basis = "OK", 0, "symmetric non-polar two-pad passive: a 180 deg error is harmless (geometry c=%s, DB %s)" % (c, d)
            elif c in (90, 270) and d in (None, c):
                cls, corr, basis = "CORRECTED", c, "pad axis differs by %d deg (geometry%s)" % (c, " and DB" if d == c else " only")
            else:
                cls, corr, basis = "NEEDS-PREVIEW", None, "geometry c=%s vs DB d=%s" % (c, d)
        elif c is not None and d is not None:
            if c == d:
                cls, corr, basis = ("OK", 0, "geometry and DB agree: offset 0") if c == 0 else \
                    ("CORRECTED", c, "geometry and DB agree: offset %d" % c)
            else:
                cls, corr, basis = "NEEDS-PREVIEW", None, "geometry c=%d vs DB d=%d disagree" % (c, d)
        elif c is not None:
            if c == 0 and not polarised:
                cls, corr, basis = "OK", 0, "geometry c=0; no DB rule (single source)"
            else:
                cls, corr, basis = "NEEDS-PREVIEW", None, "single source (geometry c=%d, no DB rule)%s" % (c, "; polarised part" if polarised else "")
        elif d is not None:
            if d == 0 and not polarised:
                cls, corr, basis = "OK", 0, "DB offset 0; no EasyEDA geometry (single source)"
            else:
                cls, corr, basis = "NEEDS-PREVIEW", None, "single source (DB d=%d, %s)" % (d, gstat)
        else:
            cls, corr, basis = "NEEDS-PREVIEW", None, "no DB rule and %s" % gstat
        if tht and cls in ("OK", "CORRECTED") and (c not in (0, None) or d not in (0, None)) and not sym:
            cls, corr, basis = "NEEDS-PREVIEW", None, basis + "; THT line (JLC hand/wave-places THT, preview may not show it)"
        cand = sorted({(rot + x) % 360 for x in (c, d) if x is not None})
        if notes and cls == "OK":
            cls, corr = "NEEDS-PREVIEW", None
        new_rot = rot if corr is None else (rot + corr) % 360
        centroid = None
        kp = [p for p in fp["pads"] if "x" in p]
        if kp:
            centroid = (round(sum(p["x"] for p in kp) / len(kp), 3), round(sum(p["y"] for p in kp) / len(kp), 3))
        recs.append({
            "ref": ref, "mpn": b["Manufacturer Part Number"], "lcsc": b["LCSC Part #"], "kicad_footprint": fpname,
            "mount": row["Mount"], "rot_in": rot, "db_pattern": dbrule and dbrule["pattern"], "db_offset": d,
            "geom_offset": c, "geom_rms_mm": {str(k): round(v, 3) for k, v in rms.items()}, "geom_status": gstat,
            "symmetric_nonpolar": sym, "class": cls, "applied_offset": corr, "rot_proposed": new_rot,
            "basis": basis, "candidate_rotations": cand, "notes": notes, "kicad_pad_centroid_mm": centroid})
    byref0 = {r["ref"]: r for r in recs}
    c0603 = byref0["C2"]  # CL10B103KB8NNNC, C_0603: symmetric passive, must stay untouched
    sot = [r for r in recs if r["kicad_footprint"] == "SOT-23"]
    controls = {
        "0603_noop": {"ref": "C2", "class": c0603["class"], "rot_in": c0603["rot_in"], "rot_proposed": c0603["rot_proposed"],
                      "pass": c0603["class"] == "OK" and c0603["rot_in"] == c0603["rot_proposed"] and c0603["db_offset"] is None},
        "sot23_known_offset": {"refs": [r["ref"] for r in sot], "db_pattern": sot[0]["db_pattern"], "db_offset": sot[0]["db_offset"],
                               "classes": {r["ref"]: r["class"] for r in sot},
                               "pass": all(r["db_offset"] == 270 and r["class"] in ("CORRECTED", "NEEDS-PREVIEW") for r in sot)},
    }
    json.dump({"meta": {"cpl": str(CPL.relative_to(CTRL)), "cpl_lines": len(cpl),
                        "db_sha256": hashlib.sha256(db_bytes).hexdigest(), "db_rules": len(rules),
                        "counts": dict(collections.Counter(r["class"] for r in recs)), "controls": controls},
               "rules_used": sorted({r["db_pattern"] for r in recs if r["db_pattern"]}),
               "lines": recs}, open(HERE / "audit.json", "w"), indent=1)
    with open(HERE / "audit.csv", "w", newline="") as f:
        cols = ["ref", "mpn", "lcsc", "kicad_footprint", "mount", "rot_in", "db_offset", "geom_offset", "class",
                "applied_offset", "rot_proposed", "candidate_rotations", "basis", "kicad_pad_centroid_mm"]
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)
    byref = {r["ref"]: r for r in recs}
    with open(HERE / "cpl-jlcpcb.proposed.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Mount"])
        for row in cpl:
            r = byref[row["Designator"]]
            rotv = r["rot_proposed"]
            w.writerow([row["Designator"], row["Mid X"], row["Mid Y"], row["Layer"],
                        int(rotv) if rotv == int(rotv) else rotv, row["Mount"]])
    print(json.dumps({"counts": dict(collections.Counter(r["class"] for r in recs))}))
    print("controls:", json.dumps({k: v["pass"] for k, v in controls.items()}))
    print("CORRECTED:", ",".join(r["ref"] for r in recs if r["class"] == "CORRECTED"))


if __name__ == "__main__":
    main()
