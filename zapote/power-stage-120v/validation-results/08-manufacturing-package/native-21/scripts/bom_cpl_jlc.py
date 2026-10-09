#!/usr/bin/env python3
"""Write JLCPCB-format BOM and CPL files for a native board.

    KICAD_PY scripts/bom_cpl_jlc.py <board.kicad_pcb> <frozen/default.csv> <fab-dir>

BOM columns: Comment, Designator, Footprint, LCSC Part #, Manufacturer
Part Number, Mount, Assembly. The source BOM (frozen/default.csv) carries
manufacturer part numbers in its "LCSC" column; none of them is an LCSC
catalogue number, so "LCSC Part #" is left empty and every line is marked
for sourcing: assembly by JLCPCB needs an LCSC number chosen and checked
per line, otherwise the part is consigned or hand-assembled.

CPL columns: Designator, Mid X, Mid Y, Layer, Rotation, from KiCad's
footprint positions (board Y downward, mm). JLCPCB's rotation convention
differs from KiCad's for some packages; check each rotation against JLCPCB's
placement preview once LCSC parts are chosen.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]


def main() -> None:
    board_path, bom_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    board = pcbnew.LoadBoard(str(board_path))
    # board-only parts (test points, fiducials, mounting holes) are excluded from the BOM and CPL by design
    fps = {fp.GetReference(): fp for fp in board.GetFootprints() if not fp.IsExcludedFromBOM()}
    mm = pcbnew.ToMM

    def mount(ref: str) -> str:
        attrs = fps[ref].GetAttributes()
        if attrs & pcbnew.FP_THROUGH_HOLE:
            return "THT"
        if attrs & pcbnew.FP_SMD:
            return "SMD"
        pads = list(fps[ref].Pads())          # attribute unset (T1): decide from the pads themselves
        if pads and all(pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for pd in pads):
            return "SMD"
        if any(pd.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for pd in pads):
            return "THT"
        return "other"

    def centroid(fp):
        """Part centre for the CPL: centre of the pads' bounding box (review M9). KiCad's origin is
        pin 1 on most THT footprints, up to 25 mm from the body centre."""
        boxes = [pd.GetBoundingBox() for pd in fp.Pads()]
        if not boxes:
            return mm(fp.GetPosition().x), mm(fp.GetPosition().y)
        x0 = min(b.GetX() for b in boxes); x1 = max(b.GetRight() for b in boxes)
        y0 = min(b.GetY() for b in boxes); y1 = max(b.GetBottom() for b in boxes)
        return mm((x0 + x1) // 2), mm((y0 + y1) // 2)

    rows, seen = [], set()
    with bom_path.open() as f:
        for line in csv.DictReader(f):
            refs = [r.strip() for r in line["Designator"].split(",")]
            seen.update(refs)
            kinds = {mount(r) for r in refs}
            if len(kinds) != 1:
                raise ValueError(f"mixed mount types in one BOM line: {refs}")
            rows.append({"Comment": line["Comment"], "Designator": ",".join(refs),
                         "Footprint": line["Footprint"].split(":")[-1], "LCSC Part #": "",
                         "Manufacturer Part Number": line["LCSC"], "Mount": kinds.pop(),
                         "Assembly": "LCSC number to be sourced, or consigned/hand-assembled"})
    missing = sorted(set(fps) - seen)
    if missing:
        raise ValueError(f"board footprints absent from BOM: {missing}")
    with (out / "bom-jlcpcb.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (out / "cpl-jlcpcb.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Mount"])
        for ref in sorted(fps, key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):] or 0))):
            fp = fps[ref]
            cx, cy = centroid(fp)
            w.writerow([ref, f"{cx:.3f}mm", f"{cy:.3f}mm",
                        "Bottom" if fp.IsFlipped() else "Top", f"{fp.GetOrientationDegrees():g}", mount(ref)])
    tht = sum(1 for r in fps if mount(r) == "THT")
    print(f"{len(rows)} BOM lines, {len(fps)} placements ({tht} THT, {len(fps) - tht} SMD/other)")


if __name__ == "__main__":
    main()
