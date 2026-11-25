#!/usr/bin/env python3
"""s56 lands against the maker's drawing, for lines with no JLC geometry (compare_lands.py) and the hand-fitted parts.

    python3 -I drawing_lands.py [BOARD.kicad_pcb]   -> drawing-results.json (board of record s56 when no board is given),
                                                       exit 1 on any FAIL

Pads are read from the committed board of record (board-of-record-s56/section.kicad_pcb). DRAWING holds what was read off
each maker's sheet (2026-11-25, by eye from the rendered page or its text): pad number -> (x, y), and the land size or
drill where the drawing gives one. Position tolerance 0.10 mm (pattern centred). This is a transcription check: it catches
a wrong package or pitch, not a misread drawing, and an independent reader should repeat it before the order."""
import json, math, re, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
PCB = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 and __name__ == "__main__" else HERE.parents[1] / "08-manufacturing-package/native-21/board-of-record-s56/section.kicad_pcb"
TOL = 0.10
# ref: (source, {pad: (x, y)}, {"size": (w, h) | "drill": (lead_min_hole, max)} )
row = lambda x, n, p, y0: {str(i + 1): (x, y0 + i * p) for i in range(n)}
U41 = {str(i + 1): (-4.975, -5.525 + 0.65 * i) for i in range(18)} | {str(36 - i): (4.975, -5.525 + 0.65 * i) for i in range(18)}
DRAWING = {
    "U41": ("RECOM R24C2T25/R Rev. 1-2024 p.12 recommended footprint (sha 2e8133d235cb)", U41, {"size": (1.85, 0.45)}),
    "U42": ("as U41", U41, {"size": (1.85, 0.45)}),
    "T1": ("Coilcraft CST3015 doc 1608-2 rev 09/08/25 p.2 land pattern (sha 0da51f0ee583)",
           {"1": (5.58, -12.65), "2": (-5.58, -12.65), "3": (-6.88, 12.65), "4": (6.88, 12.65)},
           {"size": {"1": (4.8, 9.0), "2": (4.8, 9.0), "3": (3.0, 4.6), "4": (3.0, 4.6)}}),
    "F2": ("Schurter UMT-H p.2 soldering pads (sha bac65726cd08): 10 mm gap, 3.75 x 5.6", {"1": (-6.875, 0), "2": (6.875, 0)},
           {"size": (3.75, 5.6)}),
    "J6": ("Phoenix 1704004 p.7 drilling plan (sha 068a14900fa7): 15.24 mm, hole 1.4", {"1": (0, -7.62), "2": (0, 7.62)},
           {"drill": (1.4, 1.4)}),
    "C1": ("KEMET R46 F3095 (sha 5a3131ce8de7): 22.5 +/-0.4, lead 0.8", {"1": (-11.25, 0), "2": (11.25, 0)}, {"drill": (1.0, 1.4)}),
    "C2": ("as C1", {"1": (-11.25, 0), "2": (11.25, 0)}, {"drill": (1.0, 1.4)}),
    "BR1": ("Diodes GBJ2510 DS21221 rev 11-2 (sha c7d965771158): 10.0, 7.5, 7.5; lead 1.1 x 0.8 max diagonal 1.36",
            {"1": (-13.125, 0), "2": (-3.125, 0), "3": (4.375, 0), "4": (11.875, 0)}, {"drill": (1.4, 2.0)}),
    "R130": ("Vishay AC05 (sha 246742c2396d): lead 0.8 +/-0.03, body 7.5 max, mounted upright: pitch is ours, no drawing",
             {"1": (-2.54, 0), "2": (2.54, 0)}, {"drill": (0.9, 1.3)}),
    "L1": ("TDK B82726S22*3A020 data sheet as transcribed in elec/src/parts.ato (sheet not on disk): 10 mm in a row, 25 mm between, "
           "2 mm pins", {"1": (-5, -12.5), "2": (5, -12.5), "3": (5, 12.5), "4": (-5, 12.5)}, {"drill": (2.2, 2.8)}),
}
_fet = ("Infineon IPW65R018CFD7 Rev. 2.0 PG-TO247-3 (sha c364050a04a4): e 5.44, b 1.00-1.40, c 0.38-0.89, so the lead diagonal is up to "
        "1.66 mm; a round hole must clear it")
for _q in ("Q2", "Q3", "Q5", "Q6"):
    DRAWING[_q] = (_fet, {"1": (-5.45, 0), "2": (0, 0), "3": (5.45, 0)}, {"lead_diag": 1.659})
for _c in ("C21", "C22", "C23", "C151", "C152"):
    DRAWING[_c] = ("TDK MMKP B32643B sheet (sha ab9fdca0b967): 22.5 +/-0.4, lead 0.8 +/-0.05; the fitted H-type sheet is transcribed in parts.ato",
                   {"1": (-11.25, 0), "2": (11.25, 0)}, {"lead_diag": 0.85, "second_hole_at": 27.5})
DRAWING["RV1"] = ("Littelfuse TMOV/iTMOV revised 10/01/19 pp.6-7, 20 mm, 115-420 V row (sha 039bf6182ec4): e 6.5-8.5, lead 0.76-0.86; "
                  "bulk leads are offset e1 1.5-4.0 (FOOTPRINTS.md F4: form lead 2 into line)", {"1": (-3.75, 0), "2": (3.75, 0)}, {"lead_diag": 0.86})
for _j in ("J2", "J5"):
    DRAWING[_j] = ("Wuerth 7466004R rev 001.003 2023-07-03 p.1 recommended land (sha e629b5c54c31): pad dia 8.5, NPTH 5.2", {}, {"ring": (8.5, 5.2)})
for _d in ("D3", "D17"):
    DRAWING[_d] = ("Littelfuse 30KPA P600 (sha 1fe25d7c0973): lead 1.22-1.36 (pitch 12.7 is ours)", {"1": (-6.35, 0), "2": (6.35, 0)}, {"lead_diag": 1.36})
NOT_CHECKED = {"R51 R52 R55 R56": "standard 1206", "R71 R72 R74 R75 R131": "standard 0603", "R132": "standard 0603"}
# clips carry two slots per fuse end: compared as hole pairs at 10.80 mm
CLIP = {"F1": (10.80, ("Littelfuse 125 003 clip, sheet 03/12/13 (sha 58666b2c7e73): 10.80 mm, slots 1.20 x 2.5. The clips' 30.96 mm "
                       "centres: Littelfuse KLDR (sha c51ae8155f39) 38.1 mm long, 12.7 mm ferrules, 10.3 mm: each 11.57 mm clip covers 9.4 mm of ferrule"))}


def pads(ref, t):
    i = t.find('"Reference" "%s"' % ref)
    j = t.rfind("\n\t(footprint ", 0, i)
    b = t[j:t.find("\n\t(footprint ", i)]
    out = []
    for n, at, size, drill in re.findall(r'\(pad "([^"]*)" \w+ \w+\s+\(at ([-\d. ]+)\)\s+\(size ([-\d. ]+)\)(?:\s+\(drill ([^)]*)\))?', b):
        a = [float(v) for v in at.split()]
        out.append((n, a[0], a[1], [float(v) for v in size.split()], drill))
    return out


def check():
    t, rows = PCB.read_text(), []
    for ref, (src, want, ex) in DRAWING.items():
        if "ring" in ex:
            npth = [p for p in pads(ref, t) if p[4] and float(p[4].split()[0]) == ex["ring"][1]]
            block = t[t.rfind("\n\t(footprint ", 0, t.find('"Reference" "%s"' % ref)):]
            block = block[:block.find("\n\t(footprint ", 5)]
            g = re.search(r"\(gr_circle\s+\(center ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)\s+\(width ([-\d.]+)\)", block)
            od = 0.0 if g is None else 2 * math.hypot(float(g[3]) - float(g[1]), float(g[4]) - float(g[2])) + float(g[5])
            ok = len(npth) == 1 and abs(od - ex["ring"][0]) <= TOL
            rows.append({"ref": ref, "verdict": "PASS" if ok else "FAIL", "pad_od_mm": round(od, 3), "why": [] if ok else ["ring"], "source": src})
            continue
        got = [p for p in pads(ref, t) if p[0] in want]
        if "second_hole_at" in ex:      # dual-pitch footprint: the other pad-2 hole stays empty
            x1 = next(p[1] for p in got if p[0] == "1")
            got = [p for p in got if abs(abs(p[1] - x1) - ex["second_hole_at"]) > 0.05]
        why = []
        if {p[0] for p in got} != set(want) or len(got) != len(want):
            rows.append({"ref": ref, "verdict": "FAIL", "why": ["pads differ"], "source": src})
            continue
        cx = [sum(p[k] for p in got) / len(got) for k in (1, 2)]
        wx = [sum(v[k] for v in want.values()) / len(want) for k in (0, 1)]
        worst = max(math.hypot((p[1] - cx[0]) - (want[p[0]][0] - wx[0]), (p[2] - cx[1]) - (want[p[0]][1] - wx[1])) for p in got)
        if worst > TOL:
            why.append("pad centre off by %.3f mm" % worst)
        for p in got:
            sz = ex.get("size")
            sz = sz[p[0]] if isinstance(sz, dict) else sz
            if sz and sorted(p[3]) != sorted(sz):
                why.append("pad %s size %s, drawing %s" % (p[0], p[3], sz))
            if "lead_diag" in ex and float(p[4].split()[0]) < ex["lead_diag"]:
                why.append("pad %s hole %s, maximum lead diagonal %s" % (p[0], p[4], ex["lead_diag"]))
            if "drill" in ex:
                d = float(p[4].split()[0])
                if not ex["drill"][0] - 1e-9 <= d <= ex["drill"][1] + 1e-9:
                    why.append("pad %s drill %s outside %s" % (p[0], d, ex["drill"]))
        rows.append({"ref": ref, "verdict": "FAIL" if why else "PASS", "worst_mm": round(worst, 4), "why": why, "source": src})
    for ref, (pitch, src) in CLIP.items():
        x = sorted(p[1] for p in pads(ref, t) if p[4].startswith("oval"))
        d = [round(x[1] - x[0], 3), round(x[3] - x[2], 3)] if len(x) == 4 else []
        rows.append({"ref": ref, "verdict": "PASS" if d and all(abs(v - pitch) <= TOL for v in d) else "FAIL", "slots_mm": d, "source": src})
    return rows


if __name__ == "__main__":
    r = check()
    (HERE / "drawing-results.json").write_text(json.dumps(r, indent=1) + "\n")
    for k, v in NOT_CHECKED.items():
        print("NOT CHECKED", k, v)
    for x in r:
        print(x["verdict"], x["ref"], x.get("worst_mm", x.get("slots_mm", x.get("pad_od_mm"))), x.get("why", ""))
    sys.exit(any(x["verdict"] == "FAIL" for x in r))
