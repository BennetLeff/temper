#!/usr/bin/env python3
"""FR-4 pressure pads (JLCPCB bare FR-4, no copper): one Gerber zip per thickness, a 3 x 2 panel of 14 x 16 mm pads.

    ~/.local/share/temper/kikit-venv/bin/python -I scripts/bench_pads_gerber.py     (from bench-sink-r1/)
      -> fab/pads/bench-pads-1.6mm-r1.zip, fab/pads/bench-pads-0.8mm-r1.zip

Needs KiCad 10's pcbnew (the kikit venv inherits KiCad's Python) and KiKit 1.8. Pad size from bench_params.FR4_PAD;
thicknesses are the nominal of bench_params.FR4_T and FR4_THIN_T (1.6 and 0.8, both on JLCPCB's FR-4 list).

Panel (JLCPCB capabilities page, read 2026-11-28; quotes in the README):
  * 6 pads per panel (4 + 2 spares; JLCPCB's minimum order of 5 panels gives 30 per thickness), 3 columns x 2 rows,
    2.0 mm milled gaps ("Panel board spacing: 1.6 or 2 mm"; "Min. Non-Plated Slots: 1.0mm").
  * 5 mm frame on all sides ("Minimum tooling edge width: 3 mm"), so the panel is 60 x 48 mm, far above the
    "3 x 3 mm" minimum board size. No V-cut (its minimum panel is 70 x 70).
  * Each pad hangs on two 5.0 mm tabs, one on each 14 mm edge (to the frame, or to the pad in the other row) ("For breakaway with mouse-bites, the minimum width is 5mm"),
    mouse-bites Ø0.6, 7 per tab (KiKit spaces them evenly: 0.833 mm pitch, 0.233 mm web; recommended 0.5-0.8 mm holes,
    0.2-0.3 mm between them; "Min. Non-plated holes: 0.50mm"), hole centres 0.25 mm inside the pad edge so the break
    stays inside the 14 x 16 outline. The milled corners get a 0.5 mm router radius (KiKit millradius).
  * Layers: Edge.Cuts (outline) and an NPTH Excellon (mouse-bites) carry all the geometry. F.Cu / B.Cu are present and
    EMPTY so the set reads as an ordinary 2-layer board with no copper. F.Mask / B.Mask open the whole of every pad
    (and 0.1 mm past its edge), so both pad faces are bare laminate; mask stays on the frame only. F.SilkS has text on
    the frame only: the panel label and JLC's order-number marker 'JLCJLCJLCJLC', so the order number is not printed
    on a pad face. No paste layers (no assembly).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
KIKIT = str(Path.home() / ".local/share/temper/kikit-venv/bin/kikit")
OUT = STUDY / "fab" / "pads"

PANEL = dict(rows=2, cols=3, space=2.0, frame=5.0, tab_w=5.0, bite_d=0.6, bite_pitch=0.8, bite_offset=0.25,
             mill_r=0.5, mask_over=0.1)
THICKNESSES = {"1.6mm": 1.6, "0.8mm": 0.8}          # JLCPCB FR-4 list values; each must sit inside its bench_params range
assert P.FR4_T[0] < THICKNESSES["1.6mm"] < P.FR4_T[1] and P.FR4_THIN_T[0] < THICKNESSES["0.8mm"] < P.FR4_THIN_T[1]
LAYERS = ["F.Cu", "B.Cu", "F.Mask", "B.Mask", "F.SilkS", "Edge.Cuts"]


def zip_name(tag):
    return OUT / f"bench-pads-{tag}-r1.zip"


def source_board(path, thickness):
    import pcbnew

    b = pcbnew.BOARD()
    b.SetCopperLayerCount(2)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(pcbnew.FromMM(thickness))
    w, h = P.FR4_PAD
    x0, y0 = 100.0, 100.0

    def rect(layer, x1, y1, x2, y2, filled, width=0.1):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        s.SetLayer(layer)
        s.SetFilled(filled)
        s.SetWidth(pcbnew.FromMM(width) if not filled else 0)
        b.Add(s)

    rect(pcbnew.Edge_Cuts, x0, y0, x0 + w, y0 + h, False, 0.1)
    m = PANEL["mask_over"]
    for layer in (pcbnew.F_Mask, pcbnew.B_Mask):
        rect(layer, x0 - m, y0 - m, x0 + w + m, y0 + h + m, True)
    b.Save(str(path))


def panelize(src, dst, tag):
    pn = PANEL
    label = f"BSR1 FR-4 PAD {tag} x{pn['rows'] * pn['cols']} NO CU"
    cmd = [KIKIT, "panelize",
           "--layout", f"grid; rows: {pn['rows']}; cols: {pn['cols']}; space: {pn['space']}mm",
           "--tabs", f"fixed; hcount: 0; vcount: 1; vwidth: {pn['tab_w']}mm; hwidth: {pn['tab_w']}mm",
           "--cuts", f"mousebites; drill: {pn['bite_d']}mm; spacing: {pn['bite_pitch']}mm; offset: {pn['bite_offset']}mm",
           "--framing", f"frame; width: {pn['frame']}mm; space: {pn['space']}mm; cuts: none",
           "--post", f"millradius: {pn['mill_r']}mm",
           "--text", f"simple; text: {label}; anchor: mt; voffset: 2.5mm; width: 1.5mm; height: 1.5mm; thickness: 0.2mm",
           "--text2", "simple; text: JLCJLCJLCJLC; anchor: mb; voffset: -2.5mm; width: 1.2mm; height: 1.2mm; thickness: 0.15mm",
           str(src), str(dst)]
    # KiKit names and orders its mouse-bite holes through set iteration: pin the hash seed so the plot is repeatable
    r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED="0"))
    if r.returncode:
        raise SystemExit(f"kikit failed:\n{r.stdout}\n{r.stderr}")


def canonical_panel(path):
    """Make the panel file canonical before plotting. KiKit adds its mouse-bite footprints in an order that changes from
    run to run, and every item carries a random UUID; pcbnew plots in file order. So: footprints are re-sorted by
    position (in their own slots), and each UUID is replaced by one derived from its item's content."""
    import hashlib
    import re
    import uuid

    text = path.read_text()
    pat = re.compile(r'\(uuid "[0-9a-fA-F-]+"\)')
    parts, items, depth, start, last = [], [], 0, None, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
            if depth == 2:
                start = i
        elif ch == ")":
            if depth == 2 and start is not None:
                parts.append(text[last:start])
                items.append(text[start:i + 1])
                last = i + 1
            depth -= 1
    tail = text[last:]

    def at(item):
        m = re.search(r"\(at ([-0-9.]+) ([-0-9.]+)", item)
        return (float(m.group(2)), float(m.group(1))) if m else (0.0, 0.0)

    fp_slots = [k for k, it in enumerate(items) if it.startswith("(footprint")]
    for k, it in zip(fp_slots, sorted((items[k] for k in fp_slots), key=at)):
        items[k] = it
    seen = {}
    for k, it in enumerate(items):
        seed = hashlib.sha256(pat.sub("(uuid)", re.sub(r'"KiKit_[A-Z]+_[0-9_]+"', '""', it)).encode()).hexdigest()
        seen[seed] = seen.get(seed, 0) + 1
        n = iter(range(10 ** 6))
        items[k] = pat.sub(lambda m: f'(uuid "{uuid.uuid5(uuid.NAMESPACE_OID, f"{seed}/{seen[seed]}/{next(n)}")}")', it)
    path.write_text("".join(p + it for p, it in zip(parts, items)) + tail)


def plot(panel, outdir, tag):
    gdir = outdir / "gerber"
    gdir.mkdir()
    env = dict(os.environ, SOURCE_DATE_EPOCH="1795824000")
    r = subprocess.run([KICAD_CLI, "pcb", "export", "gerbers", "--output", str(gdir), "--layers", ",".join(LAYERS),
                        "--no-x2", "--no-netlist", "--subtract-soldermask", str(panel)], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"gerber export failed:\n{r.stdout}\n{r.stderr}")
    r = subprocess.run([KICAD_CLI, "pcb", "export", "drill", "--output", str(gdir) + "/", "--format", "excellon",
                        "--excellon-units", "mm", "--excellon-separate-th", str(panel)], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"drill export failed:\n{r.stdout}\n{r.stderr}")
    return gdir


def deterministic(gdir):
    """Strip run-time dates from the plot files so an unchanged panel rebuilds to the same zip."""
    import re
    for f in sorted(gdir.iterdir()):
        if f.suffix == ".gbrjob" or f.name.endswith("-PTH.drl"):     # job file, and the empty plated-hole file
            f.unlink()
            continue
        t = f.read_text(errors="replace")
        t = re.sub(r"(CreationDate,)[^*\n]*", r"\g<1>2026-11-28T00:00:00+00:00", t)
        t = re.sub(r"(; DRILL file KiCad [0-9.]+) date [^\n]*", r"\1", t)
        t = re.sub(r"(G04 Created by KiCad \(PCBNEW [^)]*\)) date [^*\n]*", r"\1", t)
        f.write_text(t)


def write_zip(gdir, path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gdir.iterdir()):
            zi = zipfile.ZipInfo(f.name, date_time=(2026, 11, 28, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, f.read_bytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for tag, t in THICKNESSES.items():
        work = Path(tempfile.mkdtemp(prefix=f"bsr1-pads-{tag}-"))
        try:
            src = work / "pad.kicad_pcb"
            pan = work / f"bench-pads-{tag}.kicad_pcb"
            source_board(src, t)
            panelize(src, pan, tag)
            canonical_panel(pan)
            gdir = plot(pan, work, tag)
            deterministic(gdir)
            write_zip(gdir, zip_name(tag))
            print(f"{tag}: board thickness {t} mm -> {zip_name(tag).relative_to(STUDY)}: "
                  + ", ".join(sorted(f.name for f in gdir.iterdir())))
            keep = os.environ.get("BSR1_KEEP_PANEL")
            if keep:
                shutil.copy(pan, Path(keep) / pan.name)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
