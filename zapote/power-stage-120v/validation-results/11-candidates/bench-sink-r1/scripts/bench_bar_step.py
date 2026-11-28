#!/usr/bin/env python3
"""Bench clamp bar (JLCCNC, 6061-T6): build123d solid and STEP, every number from bench_params.py.

    ~/.local/share/temper/cadenv/bin/python -I scripts/bench_bar_step.py      (from bench-sink-r1/)
      -> fab/clamp-bar/bench-clamp-bar-r1.step

Part frame (mm): X = u along the bar from its left end (board x BAR x0), Y = v up from its lower edge (board z BAR z0),
Z through the thickness. Z = 0 is the back face; Z = t is face A, the sink-facing face that seats on the two spacers and
that the four spring pockets open into (bench_cad.py section B: the pocket floor sits at Y_BAR + POCKET_DEPTH).
No BR1 driver slot: jlc-mech-r1 section 2, option (a); the owner cuts it after measuring BR1's seat height.

Before it builds anything, the script checks every feature it derives from bench_params.py against the clamp-bar rows of
results/drill-table.md (written by bench_cad.py) and exits 1 on any disagreement instead of picking one.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402

OUT_DIR = STUDY / "fab" / "clamp-bar"
STEP_PATH = OUT_DIR / "bench-clamp-bar-r1.step"
TABLE_TOL = 0.005          # drill-table.md prints 2 decimals

L = P.BAR["x"][1] - P.BAR["x"][0]
H = P.BAR["h"]
T = P.BAR["t"]
FACE_A_Z = T               # pockets open into face A


def features():
    """[(name, kind, u, v, diameter, depth or None for through)] in the part frame, from bench_params only."""
    x0, z0 = P.BAR["x"][0], P.BAR["z"][0]
    out = [(f"pocket {r}", "pocket", x - x0, P.SPRING_Z - z0, P.SPRING["hole"], P.POCKET_DEPTH) for r, x in P.FET_X.items()]
    out += [(f"end hole {i}", "through", x - x0, P.BAR_SCREW_Z - z0, P.BAR_HOLE_D, None) for i, x in enumerate(P.BAR_SCREW_X, 1)]
    return out


def drill_table_bar():
    """The clamp-bar rows of results/drill-table.md: {name: (u, v, size, how)} plus the stated cut length."""
    text = (STUDY / "results" / "drill-table.md").read_text()
    m = re.search(r"Clamp bar: 6061 3/8 x 1 in, cut ([0-9.]+) mm", text)
    if not m:
        raise SystemExit("drill-table.md: no clamp-bar header")
    rows = {}
    section = text[m.end():].split("| cut part |")[0]
    for line in section.splitlines():
        c = [s.strip() for s in line.strip().strip("|").split("|")]
        if len(c) == 5 and re.fullmatch(r"[0-9.]+", c[1] or "x"):
            rows[c[0]] = (float(c[1]), float(c[2]), float(c[3]), c[4])
    return float(m.group(1)), rows


def cross_check():
    """Return a list of disagreements between bench_params.py and drill-table.md (empty when they agree)."""
    errs = []
    cut, rows = drill_table_bar()
    if abs(cut - L) > 0.05:
        errs.append(f"bar length: params {L:.3f}, drill table {cut}")
    for name, kind, u, v, d, depth in features():
        if name not in rows:
            errs.append(f"{name}: in bench_params.py, not in drill-table.md")
            continue
        tu, tv, td, how = rows.pop(name)
        for what, a, b in (("u", u, tu), ("v", v, tv), ("dia", d, td)):
            if abs(a - b) > TABLE_TOL:
                errs.append(f"{name} {what}: params {a:.3f}, drill table {b:.3f}")
        if kind == "pocket":
            m = re.search(r"([0-9.]+) deep", how)
            if not m or abs(float(m.group(1)) - depth) > TABLE_TOL or "flat-bottom" not in how:
                errs.append(f"{name}: drill table '{how}' is not a {depth} deep flat-bottom pocket")
        elif "through" not in how:
            errs.append(f"{name}: drill table '{how}' is not a through hole")
    rest = [n for n in rows if n != "BR1 driver slot"]       # the slot is left off by design (option a)
    if rest:
        errs.append(f"drill-table.md rows with no bench_params feature: {rest}")
    if "BR1 driver slot" not in rows:
        errs.append("drill-table.md has no BR1 driver slot row (expected one, left off this part by design)")
    # stock: 3/8 x 1 in flat bar
    if abs(T - 0.375 * 25.4) > 1e-6 or abs(H - 1.0 * 25.4) > 1e-6:
        errs.append(f"bar section {T} x {H} is not 3/8 x 1 in")
    return errs


def build():
    import build123d as bd

    part = bd.Box(L, H, T, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    for name, kind, u, v, d, depth in features():
        if kind == "pocket":
            # flat-bottom cylinder from face A down to Z = T - depth (no drill point, sharp floor corner)
            cut = bd.Cylinder(d / 2, depth, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
            part -= bd.Pos(u, v, FACE_A_Z) * cut
        else:
            cut = bd.Cylinder(d / 2, T + 2.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
            part -= bd.Pos(u, v, T / 2) * cut
    return part


def main():
    errs = cross_check()
    if errs:
        print("bench_params.py and results/drill-table.md DISAGREE; not building:")
        print("\n".join(f"  - {e}" for e in errs))
        return 1
    print(f"cross-check: {len(features())} features agree with results/drill-table.md (BR1 driver slot left off, option a)")
    import build123d as bd

    part = build()
    part.label = "bench-clamp-bar-r1"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bd.export_step(part, str(STEP_PATH))
    # fixed header timestamp, so an unchanged part re-exports to the same bytes (and the README's sha256 stays valid)
    s = STEP_PATH.read_text()
    s = re.sub(r"(FILE_NAME\('[^']*',')[0-9T:-]+'", r"\g<1>2026-11-28T00:00:00'", s, count=1)
    STEP_PATH.write_text(s)
    v_expect = L * H * T - sum(math.pi * (d / 2) ** 2 * (depth if depth else T) for _, _, _, _, d, depth in features())
    print(f"solid volume {part.volume:.3f} mm3 (analytic {v_expect:.3f}); mass {part.volume * 2.70e-3:.1f} g at 2.70 g/cm3")
    print(f"wrote {STEP_PATH.relative_to(STUDY)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
