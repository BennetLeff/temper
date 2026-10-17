#!/usr/bin/env python3
"""Regression for leg_region_diff.py on native-17 with synthetic edits. Prints PASS or raises.

- identical board: both legs UNCHANGED, exit 0;
- bulk capacitor C5 (far board edge, outside both regions) moved 1 mm: UNCHANGED;
- C38 (leg A's local capacitor) moved 0.5 mm: leg A CHANGED;
- a track deleted near Q3: leg A CHANGED;
- Q2's 3-D model offset raised 3 mm (taller mounting): FET flag, rerun needed;
- stackup thickness edited: stackup flag.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE.parents[3] / "native-17" / "section.kicad_pcb"


def footprint_span(text: str, ref: str) -> tuple[int, int]:
    i = text.index(f'"Reference" "{ref}"')
    s = text.rfind("(footprint ", 0, i)
    depth, j = 0, s
    while True:
        c = text[j]
        depth += c == "("
        depth -= c == ")"
        j += 1
        if depth == 0:
            return s, j


def edit_footprint(text: str, ref: str, fn) -> str:
    s, e = footprint_span(text, ref)
    return text[:s] + fn(text[s:e]) + text[e:]


def shift_at(block: str, dx: float, dy: float) -> str:
    m = re.search(r"\(at ([-\d.]+) ([-\d.]+)", block)
    return block[:m.start()] + f"(at {float(m[1]) + dx:g} {float(m[2]) + dy:g}" + block[m.end():]


def run(new_text: str) -> tuple[int, dict]:
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "new.kicad_pcb"
        p.write_text(new_text)
        out = Path(t) / "out.json"
        rc = subprocess.run([sys.executable, str(HERE / "leg_region_diff.py"), str(BOARD), str(p), "--json", str(out)],
                            capture_output=True, text=True).returncode
        return rc, json.loads(out.read_text())


def main() -> None:
    base = BOARD.read_text()
    rc, r = run(base)
    assert rc == 0 and r["legs"] == {"A": r["legs"]["A"], "B": r["legs"]["B"]} and not r["rerun_needed"], r
    assert {v["verdict"] for v in r["legs"].values()} == {"UNCHANGED"}

    rc, r = run(edit_footprint(base, "C5", lambda b: shift_at(b, 1.0, 0.0)))
    assert rc == 0 and {v["verdict"] for v in r["legs"].values()} == {"UNCHANGED"}, r["legs"]

    rc, r = run(edit_footprint(base, "C38", lambda b: shift_at(b, 0.5, 0.0)))
    assert rc == 2 and r["legs"]["A"]["verdict"] == "CHANGED", r["legs"]["A"]
    assert "pads" in r["legs"]["A"]["differences"] and "footprints" in r["legs"]["A"]["differences"]

    # delete one track that lies inside leg A's region (near Q3's source pad, 143.45, 4.215)
    m = next(m for m in re.finditer(r"\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)", base)
             if 130 < float(m[1]) < 160 and 0 < float(m[2]) < 30)
    s = m.start()
    depth, e = 0, s
    while True:
        depth += base[e] == "("
        depth -= base[e] == ")"
        e += 1
        if depth == 0:
            break
    rc, r = run(base[:s] + base[e:])
    assert rc == 2 and "tracks" in r["legs"]["A"]["differences"], r["legs"]["A"]

    def taller(block: str) -> str:
        mm = re.search(r"\(offset\s*\(xyz ([-\d.]+) ([-\d.]+) ([-\d.]+)\)", block)
        assert mm, "Q2 has no 3-D model offset to edit"
        return block[:mm.start()] + f"(offset (xyz {mm[1]} {mm[2]} {float(mm[3]) + 3:g})" + block[mm.end():]
    rc, r = run(edit_footprint(base, "Q2", taller))
    assert rc == 2 and r["rerun_needed"] and any(f.startswith("Q2: models") for f in r["fet_flags"]), r["fet_flags"]

    th = re.search(r"\(thickness ([\d.]+)\)", base[base.index("(stackup"):])
    i = base.index("(stackup") + th.start()
    rc, r = run(base[:i] + f"(thickness {float(th[1]) + 0.1:g})" + base[i + len(th[0]):])
    assert rc == 2 and r["stackup_changed"], r
    print("PASS test_leg_region_diff: identical, far move, local move, deleted track, FET mounting, stackup")


if __name__ == "__main__":
    main()
