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
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    mm = pcbnew.ToMM

    def mount(ref: str) -> str:
        attrs = fps[ref].GetAttributes()
        if attrs & pcbnew.FP_THROUGH_HOLE:
            return "THT"
        if attrs & pcbnew.FP_SMD:
            return "SMD"
        return "other"

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
            w.writerow([ref, f"{mm(fp.GetPosition().x):.3f}mm", f"{mm(fp.GetPosition().y):.3f}mm",
                        "Bottom" if fp.IsFlipped() else "Top", f"{fp.GetOrientationDegrees():g}", mount(ref)])
    tht = sum(1 for r in fps if mount(r) == "THT")
    print(f"{len(rows)} BOM lines, {len(fps)} placements ({tht} THT, {len(fps) - tht} SMD/other)")


if __name__ == "__main__":
    main()
