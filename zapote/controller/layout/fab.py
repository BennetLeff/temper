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


# JLC places its library footprint at the CPL rotation, so the CPL carries KiCad's rotation plus the offset
# between the two footprints. Offsets below are the CORRECTED lines of evidence/fab-loose-ends/cpl-rotation
# (audit.py: the JLCKicadTools rotation DB and the EasyEDA pad geometry agree), keyed by LCSC code because one
# KiCad footprint (SOT-23-5) needs different offsets for different parts. NEEDS-PREVIEW parts are NOT here:
# they stay at KiCad's rotation and are listed in fab-notes.md for the owner's JLC preview.
CPL_ROTATION_OFFSET = {
    "C1517414": 270,  # OPA2388IDR, SOIC-8
    "C398355": 270,   # TLV9062IDR, SOIC-8
    "C56997": 270,    # MCP3202-CI/SN, SOIC-8
    "C465732": 270,   # TCA9555PWR, TSSOP-24
    "C7668": 270,     # SN74LVC244APWR, TSSOP-20
    "C70285": 180,    # SN74LVC1G74DCUR, VSSOP-8
    "C7719": 270,     # TPS3823-33DBVR, SOT-23-5
    "C398358": 270,   # TLV9061IDBVR, SOT-23-5
    "C546857": 270,   # 74HC30PW,118, TSSOP-14
    "C133541": 270,   # SN74LVC14ADR, SOIC-14
    "C89608": 270,    # MAX31865AAP+, SSOP-20
    "C2836319": 270,  # SRV05-4, SOT-23-6
    "C350561": 270,   # SN74LVC74APWR, TSSOP-14 (C44 audit: geometry and DB agree)
}


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
    rotated = []
    board_only = []
    for fp in sorted(b.GetFootprints(), key=lambda f: natural(f.GetReference())):
        ref = fp.GetReference()
        mpn = fp.GetFieldText("MPN") if fp.HasField("MPN") else fp.GetValue()
        # C41: copper-only lands (the TC2050 debug pads) are neither bought nor placed
        if fp.IsExcludedFromBOM() or fp.IsExcludedFromPosFiles() or (parts.get(mpn) or {}).get("board_only"):
            board_only.append(ref)
            continue
        pads = list(fp.Pads())
        # C48: the footprint's own type decides, not the presence of a plated hole. The WROOM module (U4)
        # is an SMD footprint whose ground pad carries 12 plated thermal vias; it is reflowed, not hand-soldered
        tht = bool(fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE)
        lib = fp.GetFPID().GetLibItemName().wx_str()
        lines[(mpn, lib, "THT" if tht else "SMD")].append(ref)
        x0 = min(p.GetBoundingBox().GetLeft() for p in pads)
        x1 = max(p.GetBoundingBox().GetRight() for p in pads)
        y0 = min(p.GetBoundingBox().GetTop() for p in pads)
        y1 = max(p.GetBoundingBox().GetBottom() for p in pads)
        cx, cy = mm((x0 + x1) // 2), mm((y0 + y1) // 2)
        off = CPL_ROTATION_OFFSET.get((parts.get(mpn) or {}).get("lcsc"), 0)
        if off:
            rotated.append(ref)
        cpl.append([ref, f"{cx:.3f}mm", f"{-cy:.3f}mm", "Bottom" if fp.IsFlipped() else "Top",
                    f"{(fp.GetOrientationDegrees() + off) % 360:g}", "THT" if tht else "SMD"])
    def stock(mpn):
        rec = parts.get(mpn, {})
        for k in ("jlc_stock_2026_10_15", "jlc_stock_2026_10_12", "jlc_stock_2026_10_08", "lcsc_stock_2026_10_10"):
            if k in rec:
                return rec[k]
        return None
    missing = []
    with (FAB / "bom-jlcpcb.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Manufacturer Part Number", "Mount",
                    "JLC stock (latest check)"])
        for (mpn, lib, mount), refs in sorted(lines.items(), key=lambda kv: natural(kv[1][0])):
            p = parts.get(mpn)
            if p is None or not p.get("lcsc"):
                missing.append(mpn)
            s = stock(mpn)
            w.writerow([mpn, ",".join(sorted(refs, key=natural)), lib, (p or {}).get("lcsc", ""), mpn, mount,
                        "" if s is None else s])
    with (FAB / "cpl-jlcpcb.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Mount"])
        w.writerows(cpl)
    zero_stock = sorted({mpn for (mpn, _, _), _r in lines.items() if stock(mpn) == 0})
    low_stock = sorted({mpn for (mpn, _, _), refs in lines.items()
                        if stock(mpn) is not None and 0 < stock(mpn) < 10 * len(refs)})
    bb = b.GetBoardEdgesBoundingBox()
    drc_path = UNIT / "evidence/drc.json"
    status = "unknown (run the DRC first)"
    if drc_path.exists():
        d_ = json.loads(drc_path.read_text())
        errs = sum(1 for v in d_["violations"] if v["severity"] == "error")
        opens = len(d_["unconnected_items"])
        status = (f"DRC errors {errs}, unconnected {opens}, schematic parity {len(d_['schematic_parity'])}"
                  + (" -- **candidate, not released** (ordering is the owner's decision)"
                     if errs == 0 and opens == 0 and not d_["schematic_parity"]
                     else " -- **NOT FOR ORDER: the board is not fully routed or not DRC-clean**"))
    audit_csv = UNIT / "evidence/fab-loose-ends/cpl-rotation/audit.csv"
    by_code = defaultdict(list)
    if audit_csv.exists():
        for r in csv.DictReader(audit_csv.open()):
            if r["class"] == "NEEDS-PREVIEW":
                by_code[(r["lcsc"], r["mpn"], r["kicad_footprint"])].append(r["ref"])
    preview = "\n".join(f"  - {c} {m} ({f}): {', '.join(sorted(rs, key=natural))}"
                        for (c, m, f), rs in sorted(by_code.items())) or "  - none"
    notes = f"""# Controller fabrication notes (generated by layout/fab.py)

- **Board status:** {status} (evidence/drc.json).

- **Board:** {mm(bb.GetWidth()) - 0.1:.1f} x {mm(bb.GetHeight()) - 0.1:.1f} mm, 4 layers, 1.6 mm, JLC04161H-7628
  (F.Cu 1 oz signal / In1.Cu 0.5 oz selv_gnd plane / In2.Cu 0.5 oz v3v3 pour + signals / B.Cu 1 oz signal),
  HASL lead-free, green mask, white silk. Six 4.0 mm holes (R30 snap-in supports) are milled from Edge.Cuts (no plating, no copper).
- **Coordinates:** Gerbers/drill in KiCad's plot frame. World (appliance) mm: X = kx - {world.OX:g},
  Y = {world.OY:g} - ky = {world.OY:g} + (Gerber Y). Board lower-left corner = world ({world.BOARD[0]:g}, {world.BOARD[1]:g}) = Gerber (20, -96).
- **Assembly:** all parts on the top side. BOM lines {len(lines)}, placements {len(cpl)}
  ({sum(1 for c in cpl if c[5] == 'THT')} THT). CPL rotations are KiCad's plus the audited JLC offset
  (`CPL_ROTATION_OFFSET` in layout/fab.py; evidence/fab-loose-ends/cpl-rotation): {len(rotated)} lines corrected
  ({', '.join(sorted(rotated, key=natural))}).
- **NEEDS-PREVIEW (owner checks these in JLC's placement preview before paying; one designator per LCSC code
  is enough, the rest of the code follows; the CPL carries KiCad's rotation for them):**
{preview}
- **LCSC numbers:** from bom/controller-parts.json; missing: {missing or 'none'}.
- **Consign / stock:** stock 0 (latest JLC check per part: 2026-10-08, C35 swaps 2026-10-12, C37-C41 parts
  2026-10-15): {zero_stock or 'none'} -- consign these or use JLC global sourcing; stock below 10x the
  quantity: {low_stock or 'none'} (DECISIONS open item 7). RG2012V-431-W-T1 (Rref) is consigned by decision
  C37: the sensor-r3 CR-2 accuracy budget needs its 0.05 % / 5 ppm/K.
- **Sourcing swaps (DECISIONS C35/C36):** R53 RT0603BRD0716K5L (C728584), U22 74HC30PW,118 (C546857),
  R31 RT0603BRD078K06L (C861587), J13 code C160315 (same MPN), U14 AD8436ARQZ-R7 (C495329). The C35 Rref
  swap (RT0805BRD07430RL) is reverted by C37.
- **Board-only lands (not on the BOM or CPL):** {', '.join(board_only) or 'none'} (J11: Tag-Connect TC2050-IDC-NL
  debug/programming pads, DECISIONS C41; nothing is fitted).
- **U14 is the AD8436 A grade (ARQZ), not the B grade:** its larger initial gain error is removed by the
  COMMISSIONING step-1 trim; the converter's worst case is -1.5 to +0.8 %, inside the +/-3 % criterion.
  Production direction (DECISIONS C35): delete U14, U15 and the buffers and compute tank RMS from the CT_MON ADC1 path.
- **U4** is the ESP32-S3-WROOM-1U-N8 (enclosure R33): the 150 mm U.FL coax and the chip-antenna board are
  separate items, not on this board's BOM.
"""
    (FAB / "fab-notes.md").write_text(notes)
    print(json.dumps({"bom_lines": len(lines), "placements": len(cpl), "missing_lcsc": missing,
                      "gerbers": sorted(p.name for p in g.iterdir())}, indent=1))
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
