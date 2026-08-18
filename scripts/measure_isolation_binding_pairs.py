#!/usr/bin/env python3
"""Measure the *binding* HV<->SELV pad pair inside each isolation-bridging part.

Evidence tool for docs/evidence/2026-08-18-isolation-part-binding-pad-pairs.md.
Read-only: it never writes pcb/temper.kicad_pcb.

For C6/K1/T1/T2/U6 it enumerates every intra-footprint pad pair and reports,
per pair, the EXACT copper-edge distance, both nets' declared domains, both
nets' board-enforced netclasses, whether both pads actually carry copper, and
the governing creepage rule from the generated DRU.

Three deliberate choices, each of which changed the answer:

  * Distances come from ``temper_placer.core.pad_geometry.pad_pair_distance``
    (the temper-geometry Rust kernel), not from pad centres. Centre-to-centre
    over-reports by half the sum of the two pads' extents -- 7.57 mm on T1's
    widest cross pair alone.

  * Distances are computed in the FOOTPRINT LOCAL frame. A footprint placement
    is a rigid motion, so intra-package distances are invariant to it; working
    locally removes any dependence on the board transform. Note KiCad stores a
    pad's ``at`` angle ABSOLUTELY (footprint rotation already folded in) --
    verified here by T1 (fp rot 90 -> pad angle 90) and T2 (fp rot 0 -> pad
    angle 0) sharing one library footprint whose own pads declare no angle --
    so the local pad rotation is ``stored_angle - footprint_rotation``.

  * Pad LAYERS are checked. K1's contact pads 13/14 are ``F.Fab``-only (the
    G4A-1A-E's #250 Faston tabs have no PCB land); a pad-pair scan that ignores
    layers reports an 8.000 mm coil<->contact creepage path that does not exist
    in copper.

Usage:
    env -u CONDA_PREFIX .venv/bin/python scripts/measure_isolation_binding_pairs.py .

pcb/temper.kicad_dru must have been generated first (it is gitignored) or the
creepage columns are meaningless -- see scripts/generate_kicad_dru.py.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import yaml

from temper_placer.core.pad_geometry import pad_pair_distance

ROOT = Path(sys.argv[1])
PCB = ROOT / "pcb" / "temper.kicad_pcb"
PRO = ROOT / "pcb" / "temper.kicad_pro"
TARGETS = ["C6", "K1", "T1", "T2", "U6"]

# ---------------------------------------------------------------- sexpr parse
def tokenize(s):
    i, n, out = 0, len(s), []
    while i < n:
        c = s[i]
        if c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n:
                if s[j] == "\\":
                    buf.append(s[j + 1])
                    j += 2
                elif s[j] == '"':
                    break
                else:
                    buf.append(s[j])
                    j += 1
            out.append(("STR", "".join(buf)))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in "()\"":
                j += 1
            out.append(("SYM", s[i:j]))
            i = j
    return out

def parse(tokens):
    stack = [[]]
    for t in tokens:
        if t == "(":
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif t == ")":
            stack.pop()
        else:
            stack[-1].append(t)
    return stack[0][0]

def head(node):
    return node[0][1] if isinstance(node, list) and node and isinstance(node[0], tuple) else None

def kids(node, name):
    return [c for c in node if isinstance(c, list) and head(c) == name]

def v(tok):
    return tok[1] if isinstance(tok, tuple) else tok

root = parse(tokenize(PCB.read_text()))

# ------------------------------------------------------------- netclass model
pro = json.loads(PRO.read_text())
ASSIGN = pro["net_settings"]["netclass_assignments"]
PATTERNS = pro["net_settings"].get("netclass_patterns", [])

def netclass(net: str) -> str:
    if net in ASSIGN and ASSIGN[net]:
        return ASSIGN[net]
    for p in PATTERNS:
        if p.get("pattern") == net:
            return p["netclass"]
    return "Default"

# --------------------------------------------------------------- DRU creepage
# Transcribed from the generated pcb/temper.kicad_dru, in file order.
# KiCad: last matching rule wins for a given constraint type.
RULES = [
    ("HighVoltageTank functional creepage", "HighVoltageTank",
     lambda b: b in {"HighVoltage", "HighVoltageTank", "HighVoltageSignal"}, 10.0),
    ("AC Mains to LV", "ACMains",
     lambda b: b not in {"ACMains", "HighVoltage", "HighVoltageTank", "HighVoltageSignal", "GateDriveHV"}, 12.6),
    ("HighVoltageIsolated to LV", "HighVoltageIsolated",
     lambda b: b not in {"HighVoltageIsolated", "HighVoltage", "HighVoltageTank", "HighVoltageSignal", "ACMains", "GateDriveHV"}, 12.6),
    ("HV to LV", "HighVoltage",
     lambda b: b not in {"HighVoltage", "HighVoltageTank", "HighVoltageSignal", "ACMains", "GateDriveHV", "HighVoltageIsolated"}, 12.6),
    ("HighVoltageTank to LV", "HighVoltageTank",
     lambda b: b not in {"HighVoltageTank", "HighVoltage", "HighVoltageSignal", "ACMains", "GateDriveHV", "HighVoltageIsolated"}, 12.6),
    ("HighVoltageSignal to LV", "HighVoltageSignal",
     lambda b: b not in {"HighVoltageSignal", "HighVoltage", "HighVoltageTank", "ACMains", "GateDriveHV", "HighVoltageIsolated"}, 12.6),
]

def creepage_req(ca: str, cb: str):
    """Governing creepage min for a netclass pair; (rule_name, mm) or None."""
    gov = None
    for name, a, bpred, mm in RULES:
        if (ca == a and bpred(cb)) or (cb == a and bpred(ca)):
            gov = (name, mm)          # later rule overrides earlier
    return gov

# ------------------------------------------------------------ domain manifest
man = yaml.safe_load((ROOT / "elec" / "domain_manifest.yaml").read_text())
HV_NETS = set(man["domains"]["HV"]["nets"])
SELV_NETS = set(man["domains"]["SELV"]["nets"])

def domain(net: str) -> str:
    if net in HV_NETS:
        return "HV"
    if net in SELV_NETS:
        return "SELV"
    return "UNDECLARED"

def has_copper(layers) -> bool:
    return any(layer == "*.Cu" or layer.endswith(".Cu") for layer in layers)

# ------------------------------------------------------------------- footprints
out = {}
for fp in kids(root, "footprint"):
    ref = None
    for prop in kids(fp, "property"):
        if len(prop) >= 3 and v(prop[1]) == "Reference":
            ref = v(prop[2])
    if ref not in TARGETS:
        continue
    lib = v(fp[1])
    fat = kids(fp, "at")[0]
    frot = float(v(fat[3])) if len(fat) > 3 else 0.0
    pads = []
    for pad in kids(fp, "pad"):
        num = v(pad[1])
        ptype = v(pad[2])
        shape = v(pad[3])
        pat = kids(pad, "at")[0]
        px, py = float(v(pat[1])), float(v(pat[2]))
        abs_rot = float(v(pat[3])) if len(pat) > 3 else 0.0
        local_rot = (abs_rot - frot) % 360.0
        sz = kids(pad, "size")[0]
        w, h = float(v(sz[1])), float(v(sz[2]))
        nets = kids(pad, "net")
        net = v(nets[0][2]) if nets and len(nets[0]) > 2 else ""
        lay = kids(pad, "layers")
        layers = [v(x) for x in lay[0][1:]] if lay else []
        rr = kids(pad, "roundrect_rratio")
        ratio = float(v(rr[0][1])) if rr else 0.25
        pads.append({"num": num, "type": ptype, "shape": shape, "x": px,
                     "y": py, "rot": local_rot, "w": w, "h": h, "net": net,
                     "layers": layers, "ratio": ratio,
                     "copper": has_copper(layers)})
    out[ref] = {"lib": lib, "frot": frot, "pads": pads}

for ref in TARGETS:
    f = out[ref]
    print("=" * 100)
    lib = f["lib"]
    frot = f["frot"]
    print(f"{ref}   {lib}   (footprint rotation {frot:g} deg; all distances computed "
          f"in the footprint local frame -- rigid motion, rotation-invariant)")
    print("-" * 100)
    hdr = ("pad", "shape", "size(mm)", "local(x,y)", "rot", "copper", "net",
           "netclass", "domain")
    print(f"{hdr[0]:<5}{hdr[1]:<11}{hdr[2]:<14}{hdr[3]:<20}{hdr[4]:<5}"
          f"{hdr[5]:<8}{hdr[6]:<32}{hdr[7]:<22}{hdr[8]}")
    for p in f["pads"]:
        num = p["num"] or "(none)"
        pw, ph, px, py = p["w"], p["h"], p["x"], p["y"]
        size = f"{pw:g}x{ph:g}"
        pos = f"({px:g}, {py:g})"
        shape, rot = p["shape"], p["rot"]
        if not p["net"] and p["type"] == "np_thru_hole":
            print(f"{num:<5}{shape:<11}{size:<14}{pos:<20}{rot:<5g}"
                  f"{'NPTH':<8}{'(no net)':<32}{'-':<22}-")
            continue
        cu = "YES" if p["copper"] else "NO"
        net, ncls, dom = p["net"], netclass(p["net"]), domain(p["net"])
        print(f"{num:<5}{shape:<11}{size:<14}{pos:<20}{rot:<5g}"
              f"{cu:<8}{net:<32}{ncls:<22}{dom}")
    print()
    live = [p for p in f["pads"] if p["net"]]
    rows = []
    for a, b in itertools.combinations(live, 2):
        d = pad_pair_distance(
            (a["w"], a["h"], a["shape"], a["x"], a["y"], math.radians(a["rot"]), a["ratio"]),
            (b["w"], b["h"], b["shape"], b["x"], b["y"], math.radians(b["rot"]), b["ratio"]),
        )
        ca, cb = netclass(a["net"]), netclass(b["net"])
        req = creepage_req(ca, cb)
        both_cu = a["copper"] and b["copper"]
        rows.append((d, a, b, ca, cb, req, both_cu))
    rows.sort(key=lambda r: r[0])
    ph = ("pads", "dist(mm)", "domains", "netclasses", "copper", "req(mm)",
          "deficit", "rule")
    print(f"  {ph[0]:<10}{ph[1]:<11}{ph[2]:<18}{ph[3]:<46}{ph[4]:<8}"
          f"{ph[5]:<9}{ph[6]:<10}{ph[7]}")
    for d, a, b, ca, cb, req, both_cu in rows:
        pair = a["num"] + "/" + b["num"]
        dom = domain(a["net"]) + "<->" + domain(b["net"])
        ncs = ca + "<->" + cb
        rq = f"{req[1]:.1f}" if req else "-"
        if req and req[1] > d:
            defi = f"{req[1] - d:+.4f}"
        else:
            defi = "ok" if req else "-"
        cu = "both" if both_cu else "NO-CU"
        rule = req[0] if req else "(none)"
        print(f"  {pair:<10}{d:<11.4f}{dom:<18}{ncs:<46}{cu:<8}"
              f"{rq:<9}{defi:<10}{rule}")
    print()
