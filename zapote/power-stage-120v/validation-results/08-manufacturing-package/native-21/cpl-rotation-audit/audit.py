#!/usr/bin/env python3
"""Offline CPL rotation audit for native-21 (JLCPCB assembly).

    python3 -I audit.py            # regenerates audit.json, audit.csv, cpl-jlcpcb.corrected*.csv, renders/

Question per placed line: if JLC rotates its package model for this LCSC number by the CPL rotation,
does the part end up the way KiCad has it on the board (pin 1 on the right pad)?

Two independent sources, both committed under sources/ so the run needs no network and no board file:

  1. JLC rotation-offset database (matthewlai/JLCKicadTools cpl_rotations_db.csv, the table the
     Bouni/kicad-jlcpcb-tools plugin also ships).  JLC rotation = (KiCad rotation + offset) mod 360,
     the LAST matching pattern wins, patterns are re.match()ed against the footprint name.
  2. The LCSC/EasyEDA footprint for the LCSC number (JLC places its own package model, which has the
     EasyEDA footprint's orientation at rotation 0).  The KiCad pad layout at rotation 0 is fitted onto
     the EasyEDA pad layout by pad number (or by pin function for polarised two-pad parts); the fitted
     angle theta is the offset: JLC rotation = KiCad rotation + theta.

Classes:
  OK             KiCad rotation is what JLC needs (both sources agree, or no rule and the footprints match).
  CORRECTED      the offset is non-zero and both sources agree on it.  Applied in cpl-jlcpcb.corrected.csv.
  NEEDS-PREVIEW  the sources disagree, one is missing, the footprints do not match, or polarity cannot be
                 established offline.  Left unchanged in the corrected file; the proposed value is the best guess.
  A disagreement is settled for an LCSC number listed in sources/pin-evidence.json: the datasheet confirms that the
  EasyEDA pin numbering is the datasheet's and that KiCad pad n is datasheet pin n, so a unique EasyEDA pad-number
  fit is the part JLC places, and the DB rule (a per-footprint-name heuristic) is overridden: CORRECTED.
  Stage 49: a two-lead THT non-polar part with no EasyEDA footprint (the B32643B bank) is settled by a pin-evidence
  entry with "non_polar_tht": the datasheet gives no polarity and its lead spacing equals the KiCad pad spacing, so the
  leads enter only pads 1 / 2 and rotations k and k + 180 place the same part: OK at the KiCad rotation.
  Stage 51: on a dual-pitch footprint (two pad-2 holes, the bank's 22.5 / 27.5 mm) the pad-2 hole at the part's lead
  spacing is the one compared. Stage 52: the CPL centre check uses the same hole: pad 1 plus the pad-2 hole at the BOM
  MPN's lead spacing, from bom_cpl_jlc.py's DUAL_PITCH table (read from its source, the one copy). At s51 the fitted
  27.5 mm part's centre equalled the all-pads box by coincidence; the 22.5 mm part's does not.
Lines JLC does not place (consigned / hand-assembled, no LCSC number) are listed as EXCLUDED, not classed.

Tool controls are asserted at the end of every run (see CONTROLS and selftest()).
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAB = HERE.parent / "fab"
SRC = HERE / "sources"
THETAS = (0, 90, 180, 270)
FIT_OK_RMS = 0.6      # mm: best fit must be this good to be conclusive
FIT_SEP = 0.35        # mm: the next-best angle must be this much worse, else the fit is ambiguous


# ----------------------------------------------------------------------------- geometry
def rot_screen(p, th_deg):
    """Rotate a point CCW as seen on screen, y axis pointing down (KiCad file and EasyEDA coordinates)."""
    t = math.radians(th_deg)
    c, s = math.cos(t), math.sin(t)
    return (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)


def by_num(pads):
    """pad number -> mean (x, y); pads without a number (mechanical holes) are dropped."""
    acc = {}
    for p in pads:
        if p.get("num", "") != "":
            acc.setdefault(p["num"], []).append((p["x"], p["y"]))
    return {n: (sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for n, v in acc.items()}


def fit(kmap, emap, ee_to_k=None):
    """rms (mm) of the EasyEDA pad layout rotated by theta onto the KiCad layout, theta in 0/90/180/270."""
    pairs = []
    for en, ep in emap.items():
        kn = (ee_to_k or {}).get(en, en) if ee_to_k is not None else en
        if kn in kmap:
            pairs.append((kmap[kn], ep))
    if len(pairs) < 2:
        return None
    kc = (sum(a[0] for a, _ in pairs) / len(pairs), sum(a[1] for a, _ in pairs) / len(pairs))
    ec = (sum(b[0] for _, b in pairs) / len(pairs), sum(b[1] for _, b in pairs) / len(pairs))
    out = {}
    for th in THETAS:
        sq = 0.0
        for a, b in pairs:
            r = rot_screen((b[0] - ec[0], b[1] - ec[1]), th)
            sq += (r[0] - (a[0] - kc[0])) ** 2 + (r[1] - (a[1] - kc[1])) ** 2
        out[th] = math.sqrt(sq / len(pairs))
    return {"rms": out, "n": len(pairs)}


def compass(v):
    """Direction of a vector (y down) in words."""
    x, y = v
    if math.hypot(x, y) < 1e-6:
        return "centre"
    a = math.degrees(math.atan2(-y, x)) % 360
    names = ["right", "up-right", "up", "up-left", "left", "down-left", "down", "down-right"]
    return names[int(((a + 22.5) % 360) // 45)]


# ----------------------------------------------------------------------------- polarity
DIODE_K = {"K", "C", "CATHODE", "KATHODE", "-"}
DIODE_A = {"A", "ANODE", "+"}
CAP_P = {"+", "POS", "P", "PLUS"}
CAP_N = {"-", "N", "NEG", "MINUS"}


def kicad_functions(fpname, pads):
    """Pad-number -> function for polarised two-pad KiCad library footprints (KiCad library convention:
    D_SOD-*: pad 1 cathode; CP_Elec_*: pad 1 positive).  None if the footprint is not a known polar one."""
    nums = {p["num"] for p in pads if p["num"]}
    if nums != {"1", "2"}:
        return None
    if fpname.startswith("D_SOD") or fpname.startswith("D_SMA") or fpname.startswith("D_SMB"):
        return {"1": "K", "2": "A"}
    if fpname.startswith("CP_Elec") or fpname.startswith("CP_EIA"):
        return {"1": "+", "2": "-"}
    return None


def ee_functions(ee, kind):
    """EasyEDA pad number -> function via the LCSC symbol pin names; None if the names do not say."""
    names = {}
    for p in ee.get("pins", []):
        names[p["num"]] = p["name"].strip().upper()
    if len(names) != 2:
        return None
    pos, neg = (DIODE_K, DIODE_A) if kind == "D" else (CAP_P, CAP_N)
    out = {}
    for n, nm in names.items():
        if nm in pos:
            out[n] = "K" if kind == "D" else "+"
        elif nm in neg:
            out[n] = "A" if kind == "D" else "-"
    return out if len(out) == 2 and len(set(out.values())) == 2 else None


# ----------------------------------------------------------------------------- DB
def load_db(path):
    rules = []
    with open(path, newline="") as f:
        rd = csv.reader(f, skipinitialspace=True)
        next(rd)
        for row in rd:
            if row:
                rules.append((row[0], int(float(row[1]))))
    return rules


def db_lookup(rules, fpname):
    """Last matching rule wins.  Project footprints named SOIC16W_... (no hyphen) escape the library
    pattern ^SOIC- although they are the same gull-wing family, so the lookup also tries the hyphenated
    spelling and reports that as an alias match."""
    def run(name):
        hit = None
        for pat, off in rules:
            if re.match(pat, name):
                hit = (pat, off)
        return hit
    hit = run(fpname)
    if hit is None:
        alias = re.sub(r"^SOIC(\d+W?)_", r"SOIC-\1_", fpname)
        if alias != fpname:
            hit = run(alias)
            if hit:
                hit = (hit[0] + f" (via alias {alias})", hit[1])
    return hit


# ----------------------------------------------------------------------------- core classifier
def evaluate(kfp, fpname, ee, rules, ref, kind_override=None, evidence=None):
    """Return a dict describing the EasyEDA fit, the DB rule and the proposed offset set.  Pure function of
    the footprints so selftest() can drive it with synthetic input."""
    kpads = by_num(kfp["pads"])
    res = {"db": db_lookup(rules, fpname), "theta": None, "rms": None, "method": None, "note": ""}
    if ee is None or "error" in ee or not ee.get("pads"):
        res["note"] = "no EasyEDA footprint for this LCSC number"
        npt = (evidence or {}).get("non_polar_tht")
        if npt:
            # stage 49: two through-hole leads, no polarity (datasheet), lead spacing = KiCad pad spacing.
            # stage 51: a dual-pitch footprint carries more than one pad-2 hole (the bank: 22.5 mm and 27.5 mm); the
            # part's two leads enter pad 1 and the pad-2 hole at its lead spacing, so that hole is the one compared
            k1 = kpads.get("1")
            h2 = [(q["x"], q["y"]) for q in kfp["pads"] if q.get("num") == "2"]
            tht = len(kpads) == 2 and all(q.get("type") == "thru_hole" for q in kfp["pads"] if q.get("num"))
            k2 = min(h2, key=lambda q: abs(math.hypot(q[0] - k1[0], q[1] - k1[1]) - npt["lead_spacing_mm"])) \
                if (k1 and h2) else None
            if tht and k1 and k2:
                sep = math.hypot(k2[0] - k1[0], k2[1] - k1[1])
                if abs(sep - npt["lead_spacing_mm"]) <= npt["tolerance_mm"]:
                    res.update(method="THT non-polar (datasheet)", theta=[0, 180], rms=round(abs(sep - npt["lead_spacing_mm"]), 3),
                               pin_evidence=evidence["source"],
                               note=f"KiCad pad spacing {sep:.2f} mm = datasheet lead spacing {npt['lead_spacing_mm']} "
                                    f"+- {npt['tolerance_mm']} mm, no polarity")
                    return res
                res["note"] += f"; non-polar evidence does not match (pad spacing {sep:.2f} mm)"
            else:
                res["note"] += "; non-polar evidence needs two through-hole pads 1 / 2"
        return res
    epads = by_num(ee["pads"])
    res["ee_package"] = ee.get("package")
    kind = kind_override or re.match(r"[A-Z]+", ref).group(0)
    kfun = kicad_functions(fpname, kfp["pads"]) if kind in ("D", "C") else None
    two_pad = len(kpads) == 2 and len(epads) == 2

    if two_pad and kfun:                                # polarised: match by function
        efun = ee_functions(ee, "D" if kind == "D" else "C")
        names = [p["name"].strip() for p in ee.get("pins", [])]
        if efun is None and names and all(n.isdigit() for n in names):
            # the LCSC symbol only says "1"/"2": fall back to the datasheet pin number, which the KiCad
            # library footprint also uses (pad 1 = cathode / plus).  Weaker than a named pin.
            f = fit(kpads, epads)
            res["method"] = "pad number (symbol pins unnamed; datasheet pin 1 assumed = KiCad pad 1)"
        elif efun is None:
            res["note"] = "polarised part but the LCSC symbol pin names do not identify the polarity"
            res["method"] = "polarity-unknown"
            return res
        else:
            inv = {v: k for k, v in kfun.items()}
            ee_to_k = {en: inv[fn] for en, fn in efun.items()}
            f = fit(kpads, epads, ee_to_k)
            res["method"] = "function (symbol pin names K/A or +/-)"
            res["fn"] = {"kicad": kfun, "ee": efun}
    elif two_pad and kind in ("R", "C", "L", "F", "FB"):  # non-polar two-pad: axis only, 180-degree symmetric
        k1, k2 = kpads.get("1"), kpads.get("2")
        e1, e2 = epads.get("1"), epads.get("2")
        if None in (k1, k2, e1, e2):
            res["note"] = "two-pad part without pads 1/2"
            return res
        ak = math.degrees(math.atan2(-(k2[1] - k1[1]), k2[0] - k1[0]))
        ae = math.degrees(math.atan2(-(e2[1] - e1[1]), e2[0] - e1[0]))
        th0 = round(((ak - ae) % 180) / 90.0) * 90 % 180
        sep = math.hypot(k2[0] - k1[0], k2[1] - k1[1]), math.hypot(e2[0] - e1[0], e2[1] - e1[1])
        res.update(method="axis (non-polar)", theta=sorted({th0, (th0 + 180) % 360}),
                   rms=abs(sep[0] - sep[1]), note=f"pad spacing KiCad {sep[0]:.2f} mm vs EasyEDA {sep[1]:.2f} mm")
        res["spacing_mismatch"] = abs(sep[0] - sep[1]) > 0.8
        return res
    else:
        f = fit(kpads, epads)
        res["method"] = "pad number"
    if f is None:
        res["note"] = "fewer than two pad numbers in common"
        return res
    rms = f["rms"]
    best = min(rms, key=rms.get)
    second = sorted(rms.values())[1]
    res["n_common"] = f["n"]
    res["rms_by_theta"] = {str(t): round(v, 3) for t, v in rms.items()}
    res["rms"] = rms[best]
    res["pads_k"], res["pads_ee"] = len(kpads), len(epads)
    if rms[best] <= FIT_OK_RMS and second - rms[best] >= FIT_SEP:
        res["theta"] = [best]
        if evidence and res["method"] == "pad number":
            ee_names = {p["num"]: p["name"].strip().upper() for p in ee.get("pins", [])}
            # an evidence entry may declare how the EasyEDA symbol abbreviates the datasheet pin names (stage 47:
            # C2156518's symbol says C / A for the SNOS455H Cathode / Anode); only the names it lists are mapped
            alias = {k.upper(): v.upper() for k, v in (evidence.get("ee_name_alias") or {}).items()}
            ee_names = {n: alias.get(v, v) for n, v in ee_names.items()}
            ds = {n: f.upper() for n, f in evidence["datasheet_pins"].items()}
            if ee_names == ds and evidence.get("kicad_pad_is_datasheet_pin") and set(ds) == set(kpads):
                res["pin_evidence"] = evidence["source"]
            else:
                res["note"] = (f"pin evidence does not confirm the numbering (EasyEDA {ee_names}, datasheet {ds}, "
                               f"KiCad pads {sorted(kpads)})")
    else:
        res["note"] = (f"pad layouts do not match well enough (best rms {rms[best]:.2f} mm at {best} deg, "
                       f"next {second:.2f} mm)")
    return res


def decide(k, ev, kind, fpname, passive_std):
    """-> (class, proposed JLC rotation, reason)."""
    db = ev["db"]
    dboff = db[1] if db else None
    th = ev["theta"]
    if th is None:
        if kind in ("R", "C") and passive_std and (db is None):
            if (ev.get("method") or "").startswith("polarity"):
                return "NEEDS-PREVIEW", k, ev["note"]
            return "OK", k, ("standard two-pad chip footprint, no JLC offset rule; EasyEDA footprint not "
                             "available offline, JLC chip models are 0 deg = pads along X like KiCad")
        if db:
            cand = (k + dboff) % 360
            return ("NEEDS-PREVIEW", cand,
                    f"only the JLC rotation DB speaks (rule {db[0]!r} offset {dboff:+d}); {ev['note']}")
        return "NEEDS-PREVIEW", k, f"no DB rule and {ev['note'] or 'no usable EasyEDA fit'}"
    P = {(k + t) % 360 for t in th}
    if ev.get("method") == "THT non-polar (datasheet)":
        return ("OK", k, f"two-lead THT, no polarity and no EasyEDA footprint: {ev['note']}; the leads fit only pads 1 / 2, "
                         f"so rot {k} and {(k + 180) % 360} are the same part (sources/pin-evidence.json: "
                         f"{ev['pin_evidence'][:80]}...)")
    if ev.get("spacing_mismatch"):
        return "NEEDS-PREVIEW", k, f"EasyEDA pad spacing differs from the KiCad footprint ({ev['note']})"
    if k in P:
        if dboff in (None, 0) or ((k + dboff) % 360) in P:
            return "OK", k, ("EasyEDA footprint fits the KiCad footprint unrotated"
                             + (f"; DB rule {db[0]!r} offset {dboff:+d} is a no-op for this symmetric part"
                                if dboff not in (None, 0) else ""))
        cand = (k + dboff) % 360
        return ("NEEDS-PREVIEW", k,
                f"CONFLICT: the EasyEDA footprint fits the KiCad one at offset 0 but DB rule {db[0]!r} says "
                f"{dboff:+d} (-> rot {cand}); proposed value keeps the KiCad rotation, check both in the preview")
    prop = sorted(P)[0] if len(P) == 1 else None
    if dboff is not None and ((k + dboff) % 360) in P:
        return ("CORRECTED", (k + dboff) % 360,
                f"EasyEDA footprint fit needs {sorted(th)} deg and DB rule {db[0]!r} gives {dboff:+d}: agree")
    if ev.get("pin_evidence") and len(P) == 1:
        return ("CORRECTED", sorted(P)[0],
                f"EasyEDA footprint fit needs offset {sorted(th)} deg, unique; pin numbering confirmed by the datasheet "
                f"(sources/pin-evidence.json: {ev['pin_evidence'][:80]}...)"
                + (f"; DB rule {db[0]!r} {dboff:+d} overridden" if dboff is not None else ""))
    if dboff is None:
        return ("NEEDS-PREVIEW", sorted(P)[0],
                f"EasyEDA footprint fit needs offset {sorted(th)} deg but no DB rule covers {fpname!r}")
    return ("NEEDS-PREVIEW", sorted(P)[0],
            f"CONFLICT: EasyEDA fit needs offset {sorted(th)} deg (-> rot {sorted(P)[0]}), DB rule {db[0]!r} "
            f"says {dboff:+d} (-> rot {(k + dboff) % 360}); proposed value is the EasyEDA one, check both in the preview")


# ----------------------------------------------------------------------------- io
def expand_bom(path):
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            for ref in [x.strip() for x in r["Designator"].split(",")]:
                out[ref] = r
    return out


def dual_pitch_table():
    """bom_cpl_jlc.py's DUAL_PITCH {footprint: {mpn: lead spacing mm}}, read from its source (it imports pcbnew)."""
    tree = ast.parse((HERE.parent / "scripts/bom_cpl_jlc.py").read_text())
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "DUAL_PITCH" for t in n.targets):
            return ast.literal_eval(n.value)
    raise KeyError("DUAL_PITCH not in bom_cpl_jlc.py")


DUAL_PITCH = dual_pitch_table()


def pad_bbox_centre(kfp, mpn=None):
    """Same centre the CPL generator used (pad bounding boxes, KiCad centroid, review M9)."""
    th = kfp["rot"]
    xs, ys = [], []
    pads = kfp["pads"]
    # stage 52: a dual-pitch footprint is centred on pad 1 and the pad-2 hole at the fitted part's lead spacing
    # (bom_cpl_jlc.py centroid; KeyError for a part the footprint does not carry)
    fpn = kfp["lib"].split(":")[-1]
    if fpn in DUAL_PITCH:
        sp = DUAL_PITCH[fpn][mpn]
        p1 = next(p for p in pads if p["num"] == "1")
        dist = lambda p: math.hypot(p["x"] - p1["x"], p["y"] - p1["y"])
        p2 = min((p for p in pads if p["num"] == "2"), key=lambda p: abs(dist(p) - sp))
        assert abs(dist(p2) - sp) < 0.05, (fpn, mpn, dist(p2), sp)
        pads = [p1, p2]
    # bom_cpl_jlc.py centroid (stage 17): an all-SMD part with paste-free pads is centred on its pasted pads (R5's CSS2H
    # Kelvin fingers). Stage 35: extract_kicad.py stores a custom pad's true copper box, so the rule is needed here too.
    pasted = [p for p in pads if {"F.Paste", "B.Paste"} & set(p.get("layers", []))]
    if pasted and len(pasted) < len(pads) and all(p["type"] == "smd" for p in pads):
        pads = pasted
    for p in pads:
        x, y = rot_screen((p["x"], p["y"]), th)
        a = (p.get("ang", 0.0) + th) % 180
        w, h = (p["w"], p["h"]) if abs(a) < 1e-6 else (p["h"], p["w"]) if abs(a - 90) < 1e-6 else (max(p["w"], p["h"]),) * 2
        xs += [kfp["x"] + x - w / 2, kfp["x"] + x + w / 2]
        ys += [kfp["y"] + y - h / 2, kfp["y"] + y + h / 2]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def num(s):
    return float(s.replace("mm", ""))


def norm(a):
    return int(round(a)) % 360


def pin1_text(kfp, ee, theta, k):
    kp = by_num(kfp["pads"])
    c = None
    if kp:
        c = (sum(v[0] for v in kp.values()) / len(kp), sum(v[1] for v in kp.values()) / len(kp))
    s = ""
    if c and "1" in kp:
        v = rot_screen((kp["1"][0] - c[0], kp["1"][1] - c[1]), k)
        s = f"KiCad pad 1 at ({v[0]:+.2f},{v[1]:+.2f}) mm = {compass(v)} of centre at board rotation {k}"
    if ee and ee.get("pads") and theta is not None:
        ep = by_num(ee["pads"])
        if ep and "1" in ep:
            ec = (sum(v[0] for v in ep.values()) / len(ep), sum(v[1] for v in ep.values()) / len(ep))
            e1 = (ep["1"][0] - ec[0], ep["1"][1] - ec[1])
            s += f"; EasyEDA pad 1 {compass(e1)} of centre at JLC rot 0"
    return s


# ----------------------------------------------------------------------------- render
def render(path, ref, kfp, ee, k, old, new, lcsc, cls, fpname, alt=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=80)
    kp = by_num(kfp["pads"])
    c = (sum(v[0] for v in kp.values()) / len(kp), sum(v[1] for v in kp.values()) / len(kp)) if kp else (0, 0)
    lim = 1.0
    # KiCad pads as placed on the board (rotation old)
    for p in kfp["pads"]:
        if p["num"] == "":
            continue
        x, y = rot_screen((p["x"] - c[0], p["y"] - c[1]), old)
        a = (p.get("ang", 0.0) + old) % 180
        w, h = (p["w"], p["h"]) if abs(a) < 1e-6 else (p["h"], p["w"])
        is1 = p["num"] == "1"
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="#d33" if is1 else "#bbb", ec="k", lw=0.6, alpha=0.8))
        ax.text(x, y, p["num"], ha="center", va="center", fontsize=6)
        lim = max(lim, abs(x) + w, abs(y) + h)
    # EasyEDA/JLC package placed at the proposed JLC rotation: dashed outlines, pin 1 blue
    if ee and ee.get("pads"):
        ep = by_num(ee["pads"])
        ec = (sum(v[0] for v in ep.values()) / len(ep), sum(v[1] for v in ep.values()) / len(ep))
        for p in ee["pads"]:
            if p["num"] == "":
                continue
            x, y = rot_screen((p["x"] - ec[0], p["y"] - ec[1]), new)
            a = (p.get("rot", 0.0) + new) % 180
            w, h = (p["w"], p["h"]) if abs(a) < 1e-6 else (p["h"], p["w"])
            is1 = p["num"] == "1"
            ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="none", ec="#06c" if is1 else "#777",
                                   lw=1.6 if is1 else 0.8, ls="--"))
            lim = max(lim, abs(x) + w, abs(y) + h)
    if alt is not None and alt != new and ee and ee.get("pads"):     # the DB's competing rotation: pad 1 only, green
        ep = by_num(ee["pads"])
        ec = (sum(v[0] for v in ep.values()) / len(ep), sum(v[1] for v in ep.values()) / len(ep))
        for p in ee["pads"]:
            if p["num"] == "1":
                x, y = rot_screen((p["x"] - ec[0], p["y"] - ec[1]), alt)
                a = (p.get("rot", 0.0) + alt) % 180
                w, h = (p["w"], p["h"]) if abs(a) < 1e-6 else (p["h"], p["w"])
                ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="none", ec="#2a2", lw=1.6, ls=":"))
                lim = max(lim, abs(x) + w, abs(y) + h)
    ax.set_xlim(-lim * 1.1, lim * 1.1)
    ax.set_ylim(lim * 1.1, -lim * 1.1)   # y down, like the board view
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.set_title(f"{ref}  {lcsc}  [{cls}]\n{fpname}\nKiCad rot {old} -> JLC rot {new}", fontsize=8)
    ax.text(0.01, 0.01, "solid: KiCad pads on the board, pad 1 red\ndashed: EasyEDA/JLC package at the proposed "
            "rotation, pad 1 blue", transform=ax.transAxes, fontsize=5.5, va="bottom")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ----------------------------------------------------------------------------- controls
def selftest(rules):
    """Synthetic checks of the geometry engine and the sign convention (no board data involved)."""
    # KiCad-style SOT-23-5 (pin 1 top-left), EasyEDA-style copy rotated by -theta so that theta is the answer.
    kpads = [{"num": "1", "x": -1.1375, "y": -0.95}, {"num": "2", "x": -1.1375, "y": 0.0},
             {"num": "3", "x": -1.1375, "y": 0.95}, {"num": "4", "x": 1.1375, "y": 0.95},
             {"num": "5", "x": 1.1375, "y": -0.95}]
    for theta in THETAS:
        epads = []
        for p in kpads:
            x, y = rot_screen((p["x"], p["y"]), -theta)       # rot_screen(e, theta) == k
            epads.append({"num": p["num"], "x": x, "y": y, "w": 1, "h": 1})
        ev = evaluate({"pads": kpads}, "SOT-23-5", {"pads": epads, "pins": []}, [], "U1")
        assert ev["theta"] == [theta], (theta, ev)
    # 0603 resistor: horizontal in both, and vertical EasyEDA footprint => 90
    r = [{"num": "1", "x": -0.8, "y": 0}, {"num": "2", "x": 0.8, "y": 0}]
    assert evaluate({"pads": r}, "R_0603_1608Metric", {"pads": r}, [], "R1")["theta"] == [0, 180]
    rv = [{"num": "1", "x": 0, "y": -0.8}, {"num": "2", "x": 0, "y": 0.8}]
    assert evaluate({"pads": r}, "R_0603_1608Metric", {"pads": rv}, [], "R1")["theta"] == [90, 270]
    # polarised diode: EasyEDA pad 1 = anode on the left, KiCad pad 1 = cathode on the left => 180
    d_k = [{"num": "1", "x": -1.65, "y": 0}, {"num": "2", "x": 1.65, "y": 0}]
    d_e = [{"num": "1", "x": -1.5, "y": 0}, {"num": "2", "x": 1.5, "y": 0}]
    ev = evaluate({"pads": d_k}, "D_SOD-123", {"pads": d_e, "pins": [{"num": "1", "name": "A"}, {"num": "2", "name": "K"}]},
                  [], "D1")
    assert ev["theta"] == [180], ev
    ev = evaluate({"pads": d_k}, "D_SOD-123", {"pads": d_e, "pins": [{"num": "1", "name": "K"}, {"num": "2", "name": "A"}]},
                  [], "D1")
    assert ev["theta"] == [0], ev
    # DB semantics: last match wins, re.match anchored at the start
    assert db_lookup(rules, "SOT-23")[1] == -90 and db_lookup(rules, "SOT-23-5")[1] == -90
    assert db_lookup(rules, "SOIC-8_3.9x4.9mm_P1.27mm")[1] == 270
    assert db_lookup(rules, "R_0603_1608Metric") is None
    # pin evidence: a SOT-23-3 whose EasyEDA footprint is the KiCad one turned 180 deg, DB rule -90
    k3 = [{"num": "1", "x": -0.9375, "y": -0.95}, {"num": "2", "x": -0.9375, "y": 0.95}, {"num": "3", "x": 0.9375, "y": 0.0}]
    e3 = [{"num": p["num"], "x": -p["x"], "y": -p["y"], "w": 1, "h": 1} for p in k3]
    pins = [{"num": "1", "name": "CATHODE"}, {"num": "2", "name": "REF"}, {"num": "3", "name": "ANODE"}]
    good = {"datasheet_pins": {"1": "CATHODE", "2": "REF", "3": "ANODE"}, "kicad_pad_is_datasheet_pin": True, "source": "t"}
    ev = evaluate({"pads": k3}, "SOT-23", {"pads": e3, "pins": pins}, rules, "U1", evidence=good)
    assert ev["theta"] == [180] and ev.get("pin_evidence"), ev
    assert decide(0, ev, "U", "SOT-23", False)[:2] == ("CORRECTED", 180)
    bad = dict(good, datasheet_pins={"1": "REF", "2": "CATHODE", "3": "ANODE"})    # TL432 numbering: must not settle
    ev = evaluate({"pads": k3}, "SOT-23", {"pads": e3, "pins": pins}, rules, "U1", evidence=bad)
    assert not ev.get("pin_evidence") and decide(0, ev, "U", "SOT-23", False)[0] == "NEEDS-PREVIEW", ev
    ev = evaluate({"pads": k3}, "SOT-23", {"pads": e3, "pins": pins}, rules, "U1")    # no evidence: unchanged
    assert decide(0, ev, "U", "SOT-23", False)[0] == "NEEDS-PREVIEW"
    # stage 47: an abbreviated EasyEDA symbol (C / A / NC) settles only through the entry's declared alias
    pins_ab = [{"num": "1", "name": "C"}, {"num": "2", "name": "A"}, {"num": "3", "name": "NC"}]
    ds_full = {"datasheet_pins": {"1": "CATHODE", "2": "ANODE", "3": "NC"}, "kicad_pad_is_datasheet_pin": True, "source": "t"}
    ev = evaluate({"pads": k3}, "SOT-23", {"pads": e3, "pins": pins_ab}, rules, "U1", evidence=ds_full)
    assert not ev.get("pin_evidence"), ev
    ev = evaluate({"pads": k3}, "SOT-23", {"pads": e3, "pins": pins_ab}, rules, "U1",
                  evidence=dict(ds_full, ee_name_alias={"C": "CATHODE", "A": "ANODE"}))
    assert ev.get("pin_evidence") and decide(0, ev, "U", "SOT-23", False)[:2] == ("CORRECTED", 180), ev
    ev = evaluate({"pads": k3}, "SOT-23", {"pads": e3, "pins": pins_ab}, rules, "U1",     # alias swapped: must not settle
                  evidence=dict(ds_full, ee_name_alias={"C": "ANODE", "A": "CATHODE"}))
    assert not ev.get("pin_evidence"), ev
    # stage 49: a two-lead THT non-polar part without an EasyEDA footprint settles only on matching lead spacing
    t2 = [{"num": "1", "x": 0.0, "y": 0.0, "type": "thru_hole"}, {"num": "2", "x": 22.5, "y": 0.0, "type": "thru_hole"}]
    npe = {"non_polar_tht": {"lead_spacing_mm": 22.5, "tolerance_mm": 0.4}, "source": "t"}
    ev = evaluate({"pads": t2}, "TDK_B32643B_P22.5_W14.5_L26.5_Radial", None, rules, "C21", evidence=npe)
    assert ev["theta"] == [0, 180] and decide(0, ev, "C", "TDK_B32643B", False)[:2] == ("OK", 0), ev
    ev = evaluate({"pads": t2}, "X", None, rules, "C21",
                  evidence={"non_polar_tht": {"lead_spacing_mm": 27.5, "tolerance_mm": 0.4}, "source": "t"})
    assert ev["theta"] is None and decide(0, ev, "C", "X", False)[0] == "NEEDS-PREVIEW", ev
    # stage 51: the dual-pitch bank footprint (pad 2 at 22.5 and 27.5 mm) settles on either part's lead spacing
    t3 = t2 + [{"num": "2", "x": 27.5, "y": 0.0, "type": "thru_hole"}]
    for sp in (22.5, 27.5):
        ev = evaluate({"pads": t3}, "Bank_Film_DualPitch_P22.5_P27.5_Radial", None, rules, "C21",
                      evidence={"non_polar_tht": {"lead_spacing_mm": sp, "tolerance_mm": 0.5}, "source": "t"})
        assert ev["theta"] == [0, 180] and ev["rms"] == 0.0, ev
    # stage 52: the CPL centre on the dual-pitch footprint follows the fitted part's hole (22.5 mm: 11.25; 27.5: 13.75)
    k3 = {"lib": "temper:Bank_Film_DualPitch_P22.5_P27.5_Radial", "rot": 0.0, "x": 0.0, "y": 0.0,
          "pads": [dict(q, w=2.4, h=2.4) for q in t3]}
    assert abs(pad_bbox_centre(k3, "B32643H8104J000")[0] - 11.25) < 1e-9, pad_bbox_centre(k3, "B32643H8104J000")
    assert abs(pad_bbox_centre(k3, "MMK104J3DF1KN208G2")[0] - 13.75) < 1e-9
    try:
        pad_bbox_centre(k3, "UNKNOWN")
        raise AssertionError("an MPN the dual-pitch footprint does not carry must raise")
    except KeyError:
        pass
    ev = evaluate({"pads": t3}, "X", None, rules, "C21",
                  evidence={"non_polar_tht": {"lead_spacing_mm": 25.0, "tolerance_mm": 0.5}, "source": "t"})
    assert ev["theta"] is None, ev
    smd = [dict(q, type="smd") for q in t2]
    ev = evaluate({"pads": smd}, "X", None, rules, "C21", evidence=npe)
    assert ev["theta"] is None, ev
    print("selftest: ok")


# expected outcome of two real, unambiguous lines (checked after the run)
CONTROLS = {
    # 0603 resistor, KiCad 0: JLC chip resistors are 0 deg = pads along X, no DB rule -> no-op
    "R7": {"class": "OK", "delta": 0},
    # SOT-23-6 (TPS3700, C33002): DB "^SOT-23" -90 and the LCSC footprint fit both give -90
    "U14": {"class": "CORRECTED", "delta": -90},
    # SOIC-14 (LM2901BIDR C22427890 since stage 46; LM339BIDR C22416291 before, the same EasyEDA pads): DB "^SOIC-"
    # 270 and the LCSC footprint fit both give 270
    "U29": {"class": "CORRECTED", "delta": -90},
    # SOT-23-3 (TL431BQDBZR C190245 since stage 46; TL431BIDBZR C41283 before): EasyEDA fit 180, DB "^SOT-23" -90;
    # settled by the TI SLVS543S p.4 pinout
    "U17": {"class": "CORRECTED", "delta": -180},
    # SOT-23-3 (LM4050AEM3-2.5/NOPB C2156518 since stage 47; LM4040A25IDBZR C9421 before, the same DBZ pinout and
    # EasyEDA pad arrangement): EasyEDA fit 180, DB "^SOT-23" -90; settled by the TI SNOS455H p.3 pinout
    "U5": {"class": "CORRECTED", "delta": -180},
    # SOT-23-5 (TPS70950QDBVRQ1 C485909 since stage 48; TPS70950DBVR C96028 before, the same DBV pinout and EasyEDA pad
    # arrangement at a 2.2 mm column pitch): EasyEDA fit 180, DB "^SOT-23" -90; settled by the TI SLVSCE6D p.3 pinout
    "U3": {"class": "CORRECTED", "delta": -180},
}


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()

    rules = load_db(SRC / "cpl_rotations_db.csv")
    selftest(rules)
    kfps = json.loads((SRC / "kicad-footprints.json").read_text())
    ees = json.loads((SRC / "easyeda-footprints.json").read_text())
    pin_ev = json.loads((SRC / "pin-evidence.json").read_text())["parts"]
    bom = expand_bom(FAB / "bom-jlcpcb.csv")
    cpl = list(csv.DictReader(open(FAB / "cpl-jlcpcb.csv", newline="")))

    rows, excluded, centre_err = [], [], 0.0
    for line in cpl:
        ref = line["Designator"]
        kfp = kfps[ref]
        b = bom[ref]
        # the board dump must be the board the CPL was written from
        cx, cy = pad_bbox_centre(kfp, b.get("Manufacturer Part Number"))
        centre_err = max(centre_err, abs(cx - num(line["Mid X"])), abs(cy - num(line["Mid Y"])))
        assert abs(kfp["rot"] - float(line["Rotation"])) < 1e-6, ref
        k = norm(float(line["Rotation"]))
        fpname = kfp["lib"].split(":")[-1]
        lcsc = b["LCSC Part #"]
        placed = bool(lcsc) and b["Assembly"].startswith("JLC")
        if not placed:
            excluded.append({"designator": ref, "footprint": fpname, "mount": line["Mount"],
                             "lcsc": lcsc, "kicad_rot": k, "reason": b["Assembly"]})
            continue
        assert line["Layer"] == "Top", f"{ref}: bottom side not handled"
        ee = ees.get(lcsc)
        kind = re.match(r"[A-Z]+", ref).group(0)
        ev = evaluate(kfp, fpname, ee, rules, ref, evidence=pin_ev.get(lcsc))
        passive_std = bool(re.match(r"(R|C|L)_(0201|0402|0603|0805|1206|1210|2512)_", fpname)) and kind in ("R", "C")
        cls, prop, reason = decide(k, ev, kind, fpname, passive_std)
        th = ev["theta"]
        rows.append({
            "designator": ref, "footprint": fpname, "lcsc": lcsc, "mount": line["Mount"],
            "kicad_rot": k, "proposed_jlc_rot": prop, "class": cls,
            "db_rule": ev["db"][0] if ev["db"] else "", "db_offset": ev["db"][1] if ev["db"] else "",
            "easyeda_package": (ee or {}).get("package", ""),
            "easyeda_offset": "/".join(str(t) for t in th) if th else "",
            "easyeda_rot": "/".join(str((k + t) % 360) for t in th) if th else "",
            "db_rot": (k + ev["db"][1]) % 360 if ev["db"] else "",
            "fit_method": ev.get("method") or "", "fit_rms_mm": round(ev["rms"], 3) if ev.get("rms") is not None else "",
            "pin1_evidence": pin1_text(kfp, ee, th, k), "reason": reason,
        })
    assert centre_err < 0.01, f"board dump does not reproduce the CPL centres (max err {centre_err:.4f} mm)"

    # ---- controls
    byref = {r["designator"]: r for r in rows}
    ctl = {}
    for ref, exp in CONTROLS.items():
        r = byref[ref]
        got = {"class": r["class"], "delta": (r["proposed_jlc_rot"] - r["kicad_rot"] + 180) % 360 - 180}
        ctl[ref] = {"expected": exp, "got": got, "pass": got == exp}
    ok = all(c["pass"] for c in ctl.values())
    print("controls:", {k: v["pass"] for k, v in ctl.items()})
    assert ok, f"control failure: {json.dumps(ctl, indent=1)}"

    # ---- outputs
    counts = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    fields = list(rows[0])
    with open(HERE / "audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    corr = {r["designator"]: r["proposed_jlc_rot"] for r in rows if r["class"] == "CORRECTED"}
    ys = [num(l["Mid Y"]) for l in cpl]
    meta = {
        "lines_in_cpl": len(cpl), "lines_placed_by_jlc": len(rows), "lines_excluded_not_placed": len(excluded),
        "counts": counts, "controls": ctl, "board_dump_vs_cpl_max_centre_error_mm": round(centre_err, 4),
        "cpl_mid_y_range_mm": [min(ys), max(ys)],
        "sources": {"rotation_db": "matthewlai/JLCKicadTools cpl_rotations_db.csv @500a9fff5998edb23f9bc36920a6f8f598f4ff67",
                    "easyeda": "JLCEDA/EasyEDA Official Library public component API (https://easyeda.com, https://lceda.cn)",
                    "board": "zapote/power-stage-120v/native-21/section.kicad_pcb (untracked) dumped to sources/kicad-footprints.json"},
    }
    (HERE / "audit.json").write_text(json.dumps({"meta": meta, "lines": rows, "excluded": excluded}, indent=1) + "\n")

    for name, flip in (("cpl-jlcpcb.corrected.csv", False), ("cpl-jlcpcb.corrected-ynegated.csv", True)):
        with open(HERE / name, "w", newline="") as f:
            w = csv.writer(f, lineterminator="\r\n")
            w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Mount"])
            for line in cpl:
                rot = corr.get(line["Designator"], None)
                y = line["Mid Y"]
                if flip and not y.startswith("-"):
                    y = "-" + y
                w.writerow([line["Designator"], line["Mid X"], y, line["Layer"],
                            line["Rotation"] if rot is None else rot, line["Mount"]])

    if not args.no_render:
        rd = HERE / "renders"
        rd.mkdir(exist_ok=True)
        for old in rd.glob("*.png"):
            old.unlink()
        for r in rows:
            if r["class"] in ("CORRECTED", "NEEDS-PREVIEW"):
                ref = r["designator"]
                render(rd / f"{r['class']}_{ref}.png", ref, kfps[ref], ees.get(r["lcsc"]), r["kicad_rot"],
                       r["kicad_rot"], r["proposed_jlc_rot"], r["lcsc"], r["class"], r["footprint"],
                       alt=r["db_rot"] if r["db_rot"] != "" else None)
    print(json.dumps(counts), "excluded:", len(excluded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
