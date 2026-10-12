#!/usr/bin/env python3
"""Render a PNG for every CORRECTED / NEEDS-PREVIEW CPL line from audit.json.

Left panel = what the submitted CPL asks JLC to do (library footprint placed at the CPL rotation) against the
KiCad pads on the board; further panels = each candidate rotation (DB / geometry / applied).  Grey squares = KiCad
pads at the board rotation, pad 1 outlined red; blue rings = JLC/EasyEDA library pads with their numbers, pad 1 is the
red star.  A candidate is right when blue rings sit on the grey pads with the red star on the red-outlined pad.
usage: render_pngs.py   (needs matplotlib; reads audit.json, easyeda_pads.json and the board read-only)
"""
import json, pathlib, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit, kicad_pads


def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def main():
    A = json.load(open(HERE / "audit.json"))
    ee = json.load(open(HERE / "easyeda_pads.json"))
    fps = kicad_pads.footprints(audit.PCB)
    out = HERE / "png"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    n = 0
    for r in A["lines"]:
        if r["class"] == "OK":
            continue
        fp = fps[r["ref"]]
        kp = [p for p in fp["pads"] if "x" in p]
        R = r["rot_in"]
        e = ee.get(r["lcsc"])
        epads = audit.pad_map([{"num": p["n"], "x": p["x"], "y": p["y"]} for p in e["pads"] if p["layer"] in ("1", "11")]) if e else {}
        kmap = audit.pad_map(kp)
        common = sorted(set(kmap) & set(epads))
        kc = centroid([kmap[k] for k in (common or kmap)])
        ec = centroid([epads[k] for k in common]) if common else (0, 0)
        panels = [("as submitted: JLC rot %g" % R, R)]
        for lab, off in (("DB", r["db_offset"]), ("geometry", r["geom_offset"])):
            if off is not None:
                panels.append(("%s offset %d: JLC rot %g" % (lab, off, (R + off) % 360), (R + off) % 360))
        seen, uniq = set(), []
        for lab, J in panels:
            if J not in seen:
                seen.add(J)
                uniq.append((lab, J))
        panels = uniq[:3]
        fig, axs = plt.subplots(1, len(panels), figsize=(3.6 * len(panels), 3.9), dpi=70)
        if len(panels) == 1:
            axs = [axs]
        ext = max([abs(c) for p in kp for c in audit.rotate((p["x"] - kc[0], p["y"] - kc[1]), R)] + [1.0]) + 1.2
        for ax, (lab, J) in zip(axs, panels):
            for p in kp:
                x, y = audit.rotate((p["x"] - kc[0], p["y"] - kc[1]), R)
                w, h = p.get("w", 1), p.get("h", 1)
                if int(R) % 180 == 90:
                    w, h = h, w
                is1 = p["num"] == "1"
                ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="#bbbbbb", ec="#d00000" if is1 else "#888888",
                                       lw=2.4 if is1 else 0.6, zorder=1))
            for num, pt in epads.items():
                x, y = audit.rotate((pt[0] - ec[0], pt[1] - ec[1]), J)
                ax.add_patch(Circle((x, y), 0.22, fc="none", ec="#1a5fb4", lw=1.2, zorder=3))
                if num == "1":
                    ax.plot([x], [y], marker="*", ms=14, color="#d00000", zorder=4)
                ax.text(x, y - 0.32, num, ha="center", va="bottom", fontsize=6, color="#1a5fb4", zorder=5)
            ax.set_xlim(-ext, ext)
            ax.set_ylim(ext, -ext)  # y down like the board
            ax.set_aspect("equal")
            ax.set_title(lab, fontsize=8)
            ax.set_xticks([])
            ax.set_yticks([])
        if not epads:
            axs[0].text(0, ext * 0.8, "no EasyEDA footprint data", ha="center", fontsize=7, color="#a00000")
        fig.suptitle("%s  %s  %s  [%s]  CPL rot %g, candidates %s\n%s" % (
            r["ref"], r["mpn"], r["kicad_footprint"], r["class"], R, r["candidate_rotations"], r["basis"][:110]), fontsize=7)
        fig.tight_layout(rect=(0, 0, 1, 0.9))
        fig.savefig(out / ("%s_%s.png" % (r["ref"], r["class"])))
        plt.close(fig)
        n += 1
    print(n, "PNGs ->", out)


if __name__ == "__main__":
    main()
