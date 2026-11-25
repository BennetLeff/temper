#!/usr/bin/env python3
"""Does the 1.5 -> 1.8 mm FET hole make the copper into the drain pins worse?

    python3 -I scripts/fet_hole_current.py OLD.kicad_pcb NEW.kicad_pcb     -> fet-hole-current.json; exit 1 on any check

The neck is read from shoot-through-f1/s57_necks_hole.json (necks_hole_terminal.py: 2.052 mm; s21_necks.py says 2.561 because it
buffers the terminal 1 mm). Only the drain pins Q2.2 / Q3.2 / Q5.2 / Q6.2 carry that current; the other pads are checked for
the land and ring only.
  ring    (pad short side - hole) / 2, nominal and at JLC's largest finished hole (+0.13)
  entry   pi x d / 2: the near half of the barrel, the least copper that can carry the current into it on one layer
Checks: entry at the new hole's smallest finish (d - 0.08) >= the neck, ring >= 0.25 mm at the largest finish (audit.rs's rule)
and >= 0.254 mm nominal (JLC PTH), and an unchanged pad. It bounds the barrel entry; it does not say the neck itself is safe
(ratio 0.637, DECISIONS 88)."""
import json, math, re, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent.parent
NECKS = HERE.parents[1] / "02-protection-timing/shoot-through-f1/s57_necks_hole.json"
NECK = min(s["best_single_layer"]["neck_mm"] for s in json.loads(NECKS.read_text())["segments"]
           if s["to"] in ("Q2.2", "Q5.2", "Q3.2", "Q6.2"))
RING_NOM, RING_WORST = 0.254, 0.25  # JLC PTH nominal; audit.rs stage57 at the largest hole


def fet_pads(board, ref):
    t = pathlib.Path(board).read_text()
    i = t.index('"Reference" "%s"' % ref)
    b = t[t.rfind("\n\t(footprint ", 0, i):t.find("\n\t(footprint ", i)]
    out = {}
    for n, size, drill in re.findall(r'\(pad "(\d)" thru_hole \w+\s+\(at [-\d. ]+\)\s+\(size ([\d. ]+)\)\s+\(drill ([\d.]+)\)', b):
        out[n] = (tuple(float(v) for v in size.split()), float(drill))
    return out


def ok(old_size, size, drill, drain):
    ring = size == old_size and (min(size) - drill) / 2 >= RING_NOM - 1e-9 and (min(size) - drill - 0.13) / 2 >= RING_WORST - 1e-9
    return ring and (not drain or math.pi * (drill - 0.08) / 2 >= NECK)


rows, bad = [], 0
for ref in ("Q2", "Q3", "Q5", "Q6"):
    a, b = fet_pads(sys.argv[1], ref), fet_pads(sys.argv[2], ref)
    assert sorted(a) == sorted(b) == ["1", "2", "3"], (ref, a, b)
    for n in sorted(b):
        (s0, d0), (s1, d1) = a[n], b[n]
        good = ok(s0, s1, d1, n == "2")
        bad += not good
        rows.append({"pad": f"{ref}.{n}", "drain": n == "2", "size": s1, "drill_old": d0, "drill_new": d1, "entry_old": round(math.pi * d0 / 2, 3),
                     "entry_new": round(math.pi * d1 / 2, 3), "ring_nominal": round((min(s1) - d1) / 2, 3),
                     "ring_worst_hole": round((min(s1) - d1 - 0.13) / 2, 3), "ok": good})
# controls: a 1.3 mm hole fails the drain entry, a 2.1 mm hole fails the ring
assert not ok((2.5, 4.5), (2.5, 4.5), 1.3, True) and not ok((2.5, 4.5), (2.5, 4.5), 2.1, False)
pathlib.Path(HERE / "fet-hole-current.json").write_text(json.dumps({"neck_mm": NECK, "rows": rows}, indent=1) + "\n")
for r in rows:
    print(r)
print("RESULT", "FAIL" if bad else "PASS")
sys.exit(1 if bad else 0)
