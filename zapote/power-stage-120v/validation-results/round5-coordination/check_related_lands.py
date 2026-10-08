#!/usr/bin/env python3
"""Read native PTH outer lands; no board edits or qualification inference."""
import hashlib
import json
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[4]
BOARDS = {
    "native15_negative_control": "zapote/power-stage-120v/native-15/section.kicad_pcb",
    "native17_positive_control": "zapote/power-stage-120v/native-17/section.kicad_pcb",
    "rtd_current": "zapote/rtd/unit/candidate/section.kicad_pcb",
    "thermal_current": "zapote/thermal-sense/candidate/section.kicad_pcb",
    "current_sense_current": "zapote/current-sense/candidate/section.kicad_pcb",
}


def main():
    results = []
    for label, name in BOARDS.items():
        path = REPO / name
        board = pcbnew.LoadBoard(str(path))
        pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        missing = []
        for pad in pads:
            absent = [side for layer, side in [(pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")]
                      if not pad.FlashLayer(layer)]
            if absent:
                missing.append({"ref": pad.GetParentFootprint().GetReference(),
                                "pad": pad.GetNumber(), "missing": absent})
        results.append({"label": label, "path": name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "pth_pads": len(pads), "missing_outer_land_pads": len(missing),
                        "missing": missing})
    if results[0]["missing_outer_land_pads"] != 88:
        raise RuntimeError("native15 negative control differs from expected 88 missing-land pads")
    if results[1]["pth_pads"] != 116 or results[1]["missing_outer_land_pads"]:
        raise RuntimeError("native17 positive control failed")
    report = {"tool": pcbnew.GetBuildVersion(),
              "evidence_class": "exact structural; FlashLayer census only, not full PCB qualification",
              "boards": results}
    Path(__file__).with_name("related-board-outer-lands.json").write_text(
        json.dumps(report, indent=2) + "\n")
    for row in results:
        print(f"{row['label']}: {row['missing_outer_land_pads']}/{row['pth_pads']} PTH pads missing an outer land")


if __name__ == "__main__":
    main()
