#!/usr/bin/env python3
"""Does the 1.5 -> 1.8 mm FET hole make the 0.993 fuse-neck row (Q2.2 / Q5.2) worse? shoot-through-f1 fills each terminal's hole
(f1_containment.py TERM_BUF: "pad land (hole filled)"), so s21_necks.py cannot answer it: s57_necks.json equals s56's.

    python3 -I scripts/fet_hole_current.py OLD.kicad_pcb NEW.kicad_pcb     -> fet-hole-current.json; exit 1 on any check

Measured from the pads of Q2 / Q3 / Q5 / Q6 in both boards:
  ring      (pad short side - hole) / 2, nominal and at JLC's finished hole + 0.13
  entry     pi x d / 2: the near half of the barrel, the least copper that can carry the current into it on one layer
Checks: entry of the new hole >= the 2.561 mm neck (so the pad, not the barrel, still limits), ring >= 0.254 mm (JLC PTH), and
the pad size is unchanged (so the 2.561 mm neck and the pad-to-pad clearance are unchanged)."""
import json, math, re, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent.parent
NECK = 2.561      # shoot-through-f1 s57_necks.json, BR1 + -> Q2 / Q5 drain
RING_MIN = 0.254  # JLC PTH annular ring (the rule is on the nominal ring)


def fet_pads(board, ref):
    t = pathlib.Path(board).read_text()
    i = t.index('"Reference" "%s"' % ref)
    b = t[t.rfind("\n\t(footprint ", 0, i):t.find("\n\t(footprint ", i)]
    out = {}
    for n, size, drill in re.findall(r'\(pad "(\d)" thru_hole \w+\s+\(at [-\d. ]+\)\s+\(size ([\d. ]+)\)\s+\(drill ([\d.]+)\)', b):
        out[n] = (tuple(float(v) for v in size.split()), float(drill))
    return out


def ok(old_size, size, drill):
    return size == old_size and (min(size) - drill) / 2 >= RING_MIN - 1e-9 and math.pi * drill / 2 >= NECK


rows, bad = [], 0
for ref in ("Q2", "Q3", "Q5", "Q6"):
    a, b = fet_pads(sys.argv[1], ref), fet_pads(sys.argv[2], ref)
    assert sorted(a) == sorted(b) == ["1", "2", "3"], (ref, a, b)
    for n in sorted(b):
        (s0, d0), (s1, d1) = a[n], b[n]
        good = ok(s0, s1, d1)
        bad += not good
        rows.append({"pad": f"{ref}.{n}", "size": s1, "drill_old": d0, "drill_new": d1, "entry_old": round(math.pi * d0 / 2, 3),
                     "entry_new": round(math.pi * d1 / 2, 3), "ring_nominal": round((min(s1) - d1) / 2, 3),
                     "ring_worst_hole": round((min(s1) - d1 - 0.13) / 2, 3), "ok": good})
# controls: the old 1.5 hole fails the entry check, a 2.0 hole fails the ring check
assert not ok((2.5, 4.5), (2.5, 4.5), 1.5) and not ok((2.5, 4.5), (2.5, 4.5), 2.1)
pathlib.Path(HERE / "fet-hole-current.json").write_text(json.dumps({"neck_mm": NECK, "rows": rows}, indent=1) + "\n")
for r in rows:
    print(r)
print("RESULT", "FAIL" if bad else "PASS")
sys.exit(1 if bad else 0)
