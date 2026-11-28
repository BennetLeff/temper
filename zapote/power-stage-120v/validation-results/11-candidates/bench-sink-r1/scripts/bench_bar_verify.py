#!/usr/bin/env python3
"""Re-import the exported clamp-bar STEP and check it against bench_params.py and results/drill-table.md.

    ~/.local/share/temper/cadenv/bin/python -I scripts/bench_bar_verify.py    (from bench-sink-r1/)
      -> fab/clamp-bar/step-check.md; exits 1 on any FAIL

What is measured on the re-imported B-rep (nothing is taken from the build script's own objects):
  * units (the STEP's length unit is the millimetre), one solid, bounding box, volume against the analytic volume;
  * every cylindrical face: radius, axis direction, axis position (u, v) and its z extent, matched to a feature;
  * every pocket floor: a plane normal to z at face A - depth, bounded by one circle of the pocket radius at the
    pocket centre, area = pi r^2 (a flat bottom, no drill point);
  * no cone, sphere, torus or B-spline face anywhere (no drill points, no fillets);
  * the BR1 driver-slot location is solid metal (the slot is cut later by the owner, jlc-mech-r1 section 2 option a).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402
import bench_bar_step as B  # noqa: E402

TOL = 1e-3          # mm, geometric agreement of the re-imported B-rep
REPORT = B.OUT_DIR / "step-check.md"


def main():
    import build123d as bd
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane

    rows, fails = [], []

    def check(name, measured, expected, ok, note=""):
        rows.append((name, measured, expected, "PASS" if ok else "FAIL", note))
        if not ok:
            fails.append(name)

    errs = B.cross_check()
    check("bench_params.py vs drill-table.md", f"{len(errs)} disagreements", "0", not errs, "; ".join(errs))
    raw = B.STEP_PATH.read_text()
    check("STEP length unit", "MILLI METRE" if "SI_UNIT(.MILLI.,.METRE.)" in raw else "other", "MILLI METRE",
          "SI_UNIT(.MILLI.,.METRE.)" in raw)

    shape = bd.import_step(str(B.STEP_PATH))
    solids = shape.solids()
    check("solids in file", str(len(solids)), "1", len(solids) == 1)
    s = solids[0]
    bb = s.bounding_box()
    exp_bb = (0.0, 0.0, 0.0, B.L, B.H, B.T)
    got_bb = (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)
    check("bounding box min (x, y, z)", "%.4f, %.4f, %.4f" % got_bb[:3], "%.4f, %.4f, %.4f" % exp_bb[:3],
          all(abs(a - b) < TOL for a, b in zip(got_bb[:3], exp_bb[:3])))
    check("bounding box size L x H x t", "%.4f x %.4f x %.4f" % (bb.size.X, bb.size.Y, bb.size.Z),
          "%.4f x %.4f x %.4f" % (B.L, B.H, B.T),
          all(abs(a - b) < TOL for a, b in zip((bb.size.X, bb.size.Y, bb.size.Z), (B.L, B.H, B.T))))
    feats = B.features()
    v_exp = B.L * B.H * B.T - sum(math.pi * (d / 2) ** 2 * (dep if dep else B.T) for *_, d, dep in feats)
    check("volume mm3", f"{s.volume:.3f}", f"{v_exp:.3f}", abs(s.volume - v_exp) < 0.01)

    # classify faces on the re-imported solid
    cyls, planes, other = [], [], []
    for f in s.faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        t = ad.GetType()
        fb = f.bounding_box()
        if t == GeomAbs_Cylinder:
            c = ad.Cylinder()
            loc, ax = c.Location(), c.Axis().Direction()
            cyls.append(dict(r=c.Radius(), x=loc.X(), y=loc.Y(), dir=(ax.X(), ax.Y(), ax.Z()), z=(fb.min.Z, fb.max.Z)))
        elif t == GeomAbs_Plane:
            n = ad.Plane().Axis().Direction()
            planes.append(dict(face=f, n=(n.X(), n.Y(), n.Z()), z=(fb.min.Z, fb.max.Z), bb=fb))
        else:
            other.append(str(t))
    check("faces other than plane / cylinder", str(len(other)), "0", not other, ", ".join(other))
    check("cylindrical faces", str(len(cyls)), str(len(feats)), len(cyls) == len(feats))
    check("planar faces (6 box + 4 floors)", str(len(planes)), "10", len(planes) == 10)

    for name, kind, u, v, d, dep in feats:
        match = [c for c in cyls if abs(c["x"] - u) < TOL and abs(c["y"] - v) < TOL]
        if len(match) != 1:
            check(f"{name}: cylinder at u {u:.3f}, v {v:.3f}", f"{len(match)} found", "1", False)
            continue
        c = match[0]
        axial = abs(abs(c["dir"][2]) - 1.0) < 1e-9
        z_exp = (B.T - dep, B.T) if kind == "pocket" else (0.0, B.T)
        check(f"{name}: centre u, v", f"{c['x']:.4f}, {c['y']:.4f}", f"{u:.4f}, {v:.4f}",
              abs(c["x"] - u) < TOL and abs(c["y"] - v) < TOL)
        check(f"{name}: diameter", f"{2 * c['r']:.4f}", f"{d:.4f}", abs(2 * c["r"] - d) < TOL and axial,
              "axis along z" if axial else "axis NOT along z")
        if kind == "pocket":
            depth = B.T - c["z"][0]
            check(f"{name}: depth from face A", f"{depth:.4f}", f"{dep:.4f} +/- {P.POCKET_DEPTH_TOL}",
                  abs(depth - dep) < TOL and abs(c["z"][1] - B.T) < TOL)
            floor = [p for p in planes if abs(abs(p["n"][2]) - 1) < 1e-9 and abs(p["z"][0] - z_exp[0]) < TOL
                     and abs(p["z"][1] - z_exp[0]) < TOL and abs((p["bb"].min.X + p["bb"].max.X) / 2 - u) < TOL
                     and abs((p["bb"].min.Y + p["bb"].max.Y) / 2 - v) < TOL]
            ok = len(floor) == 1
            if ok:
                f = floor[0]["face"]
                edges = f.edges()
                circ = [e for e in edges if e.geom_type == bd.GeomType.CIRCLE]
                area_exp = math.pi * (d / 2) ** 2
                ok = (len(edges) == 1 and len(circ) == 1 and abs(circ[0].radius - d / 2) < TOL
                      and abs(f.area - area_exp) < 1e-3 and not f.inner_wires())
                check(f"{name}: flat floor at z {z_exp[0]:.3f}", f"plane, 1 circle r {circ[0].radius:.4f}, area {f.area:.3f}",
                      f"plane, 1 circle r {d / 2:.4f}, area {area_exp:.3f}", ok)
            else:
                check(f"{name}: flat floor at z {z_exp[0]:.3f}", f"{len(floor)} found", "1", False)
        else:
            check(f"{name}: through (z extent)", f"{c['z'][0]:.4f} .. {c['z'][1]:.4f}", f"0.0000 .. {B.T:.4f}",
                  abs(c["z"][0]) < TOL and abs(c["z"][1] - B.T) < TOL)

    # the BR1 driver slot is NOT on this part: its centre and both ends are metal
    sl = P.BAR_SLOT
    su = sl["x"] - P.BAR["x"][0]
    pts = [(su, z - P.BAR["z"][0], B.T / 2) for z in (sl["z"][0] + 0.5, sum(sl["z"]) / 2, sl["z"][1] - 0.5)]
    inside = [s.is_inside(bd.Vector(*p)) for p in pts]
    check("BR1 driver slot absent (option a)", f"metal at u {su:.2f}, v {pts[0][1]:.2f}/{pts[1][1]:.2f}/{pts[2][1]:.2f}: {inside}",
          "all True", all(inside))

    floor_t = B.T - P.POCKET_DEPTH
    wall_end = min(min(u - d / 2, B.L - u - d / 2) for _, _, u, _, d, _ in feats)
    wall_edge = min(min(v - d / 2, B.H - v - d / 2) for _, _, _, v, d, _ in feats)
    md = ["# Clamp bar STEP check (scripts/bench_bar_verify.py; do not edit)", "",
          f"File: `{B.STEP_PATH.relative_to(STUDY)}`, re-imported with build123d / OCP. Part frame: x = u from the bar's left end, "
          f"y = v from its lower edge, z = 0 back face, z = {B.T} face A (pockets open here). Geometric tolerance {TOL} mm.", "",
          "| check | measured | expected | verdict | note |", "|---|---|---|---|---|"]
    md += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    md += ["", f"Derived (not checks): pocket floor web {floor_t:.3f} mm; smallest hole-to-end wall {wall_end:.3f} mm; "
           f"smallest hole-to-edge wall {wall_edge:.3f} mm; mass {s.volume * 2.70e-3:.1f} g at 2.70 g/cm3.", "",
           f"**{len(rows) - len(fails)} PASS, {len(fails)} FAIL.**"]
    REPORT.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
