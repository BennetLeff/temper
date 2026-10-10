#!/usr/bin/env python3
"""Write the JLCPCB fabrication + assembly package for the routed controller board.

    KICAD_PY layout/fab.py            (from zapote/controller)  -> fab/

fab/gerbers/      Gerber X2 for the 4 copper layers, masks, paste, silk, Edge.Cuts; Excellon PTH/NPTH
                  drill files + drill map; job file
fab/controller-gerbers.zip   the same, zipped for upload
fab/bom-jlcpcb.csv           Comment, Designator, Footprint, LCSC Part #, Manufacturer, MPN, Mount
fab/cpl-jlcpcb.csv           Designator, Mid X, Mid Y, Layer, Rotation (Gerber coordinates: X = kx,
                             Y = -ky, mm; part centre = pads' bounding-box centre)
fab/assembly-top.pdf         assembly drawing: F.Fab outlines and reference designators, silk, outline
fab/fab-notes.md             stack-up, finish and ordering notes (generated)
LCSC numbers come from bom/controller-parts.json by MPN (the frozen BOM CSV carries MPNs only).
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(HERE))
import world  # noqa: E402

CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
BOARD = UNIT / "pcb/controller.kicad_pcb"
FAB = UNIT / "fab"
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts"


def run(*args):
    r = subprocess.run([CLI, *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"kicad-cli {' '.join(args[:3])} failed: {r.stderr[-800:]}")
    return r.stdout


def natural(ref):
    p = ref.rstrip("0123456789")
    return (p, int(ref[len(p):] or 0))


def main():
    if FAB.exists():
        shutil.rmtree(FAB)
    g = FAB / "gerbers"
    g.mkdir(parents=True)
    run("pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask", "--use-drill-file-origin",
        "-o", str(g), str(BOARD))
    run("pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm", "--excellon-separate-th",
        "--generate-map", "--map-format", "gerberx2", "--drill-origin", "plot", "-o", str(g) + "/", str(BOARD))
    with zipfile.ZipFile(FAB / "controller-gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(g.iterdir()):
            z.write(f, f.name)
    run("pcb", "export", "pdf", "--layers", "F.Fab,Edge.Cuts,F.Silkscreen", "--mode-single", "--black-and-white",
        "--include-border-title", "-o", str(FAB / "assembly-top.pdf"), str(BOARD))

    parts = json.loads((UNIT / "bom/controller-parts.json").read_text())["parts"]
    b = pcbnew.LoadBoard(str(BOARD))
    mm = pcbnew.ToMM
    lines = defaultdict(list)
    cpl = []
    for fp in sorted(b.GetFootprints(), key=lambda f: natural(f.GetReference())):
        ref = fp.GetReference()
        mpn = fp.GetFieldText("MPN") if fp.HasField("MPN") else fp.GetValue()
        pads = list(fp.Pads())
        tht = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in pads)
        lib = fp.GetFPID().GetLibItemName().wx_str()
        lines[(mpn, lib, "THT" if tht else "SMD")].append(ref)
        x0 = min(p.GetBoundingBox().GetLeft() for p in pads)
        x1 = max(p.GetBoundingBox().GetRight() for p in pads)
        y0 = min(p.GetBoundingBox().GetTop() for p in pads)
        y1 = max(p.GetBoundingBox().GetBottom() for p in pads)
        cx, cy = mm((x0 + x1) // 2), mm((y0 + y1) // 2)
        cpl.append([ref, f"{cx:.3f}mm", f"{-cy:.3f}mm", "Bottom" if fp.IsFlipped() else "Top",
                    f"{fp.GetOrientationDegrees() % 360:g}", "THT" if tht else "SMD"])
    missing = []
    with (FAB / "bom-jlcpcb.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Manufacturer Part Number", "Mount",
                    "JLC stock 2026-10-08"])
        for (mpn, lib, mount), refs in sorted(lines.items(), key=lambda kv: natural(kv[1][0])):
            p = parts.get(mpn)
            if p is None or not p.get("lcsc"):
                missing.append(mpn)
            w.writerow([mpn, ",".join(sorted(refs, key=natural)), lib, (p or {}).get("lcsc", ""), mpn, mount,
                        (p or {}).get("jlc_stock_2026_10_08", "")])
    with (FAB / "cpl-jlcpcb.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Mount"])
        w.writerows(cpl)
    zero_stock = sorted({mpn for (mpn, _, _), _r in lines.items()
                         if parts.get(mpn, {}).get("jlc_stock_2026_10_08", 1) in (0,)})
    low_stock = sorted({mpn for (mpn, _, _), refs in lines.items()
                        if 0 < parts.get(mpn, {}).get("jlc_stock_2026_10_08", 10**9) < 10 * len(refs)})
    bb = b.GetBoardEdgesBoundingBox()
    drc_path = UNIT / "evidence/drc.json"
    status = "unknown (run the DRC first)"
    if drc_path.exists():
        d_ = json.loads(drc_path.read_text())
        errs = sum(1 for v in d_["violations"] if v["severity"] == "error")
        opens = len(d_["unconnected_items"])
        status = (f"DRC errors {errs}, unconnected {opens}, schematic parity {len(d_['schematic_parity'])}"
                  + ("" if errs == 0 and opens == 0 else " -- **NOT FOR ORDER: the board is not fully routed**"))
    notes = f"""# Controller fabrication notes (generated by layout/fab.py)

- **Board status:** {status} (evidence/drc.json).

- **Board:** {mm(bb.GetWidth()) - 0.1:.1f} x {mm(bb.GetHeight()) - 0.1:.1f} mm, 4 layers, 1.6 mm, JLC04161H-7628
  (F.Cu 1 oz signal / In1.Cu 0.5 oz selv_gnd plane / In2.Cu 0.5 oz v3v3 pour + signals / B.Cu 1 oz signal),
  HASL lead-free, green mask, white silk. Six 4.0 mm holes (R30 snap-in supports) are milled from Edge.Cuts (no plating, no copper).
- **Coordinates:** Gerbers/drill in KiCad's plot frame. World (appliance) mm: X = kx - {world.OX:g},
  Y = {world.OY:g} - ky = {world.OY:g} + (Gerber Y). Board lower-left corner = world ({world.BOARD[0]:g}, {world.BOARD[1]:g}) = Gerber (20, -96).
- **Assembly:** all parts on the top side. BOM lines {len(lines)}, placements {len(cpl)}
  ({sum(1 for c in cpl if c[5] == 'THT')} THT). CPL rotations are KiCad's; check each package in JLC's
  placement preview (JLC's zero orientation differs for some footprints).
- **LCSC numbers:** from bom/controller-parts.json; missing: {missing or 'none'}.
- **Consign / stock:** JLC stock 0 on 2026-10-08: {zero_stock or 'none'}; stock below 10x the quantity:
  {low_stock or 'none'} (DECISIONS open item 7).
- **J11** (debug header) may be left unfitted in production.
"""
    (FAB / "fab-notes.md").write_text(notes)
    print(json.dumps({"bom_lines": len(lines), "placements": len(cpl), "missing_lcsc": missing,
                      "gerbers": sorted(p.name for p in g.iterdir())}, indent=1))
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
