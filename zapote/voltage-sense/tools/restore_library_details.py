"""Restore library pad rotations/unused-layer policy and metadata after generation.

Pad centres, nets and routed copper are preserved. Native KiCad supplies the
rotation; no independent trigonometry is used. This corrects generation loss,
not the library definition used by DRC.
"""

import json, hashlib
from pathlib import Path
import pcbnew

repo = Path(__file__).resolve().parents[3]
base = repo / "zapote/voltage-sense/candidate"
p = base / "section.kicad_pcb"
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(p), None)
before = hashlib.sha256(p.read_bytes()).hexdigest()
changes = []
for fp in board.GetFootprints():
    nickname = fp.GetFPID().GetLibNickname()
    name = fp.GetFPID().GetLibItemName()
    original = io.FootprintLoad(
        str(base / "candidate-libs" / f"{nickname}.pretty"), str(name), False, None
    )
    original.SetOrientation(fp.GetOrientation())
    original.SetPosition(fp.GetPosition())
    pads = {pad.GetNumber(): pad for pad in original.Pads()}
    for pad in fp.Pads():
        expected = pads[pad.GetNumber()]
        if pad.GetPosition() != expected.GetPosition():
            raise ValueError("pad centre differs from source library")
        changes.append(
            {
                "ref": fp.GetReference(),
                "pad": pad.GetNumber(),
                "angle_before": pad.GetOrientationDegrees(),
                "angle_after": expected.GetOrientationDegrees(),
                "remove_unconnected_before": pad.GetRemoveUnconnected(),
                "remove_unconnected_after": expected.GetRemoveUnconnected(),
            }
        )
        pad.SetOrientation(expected.GetOrientation())
        pad.SetRemoveUnconnected(expected.GetRemoveUnconnected())
        pad.SetKeepTopBottom(expected.GetKeepTopBottom())
    for field in original.GetFields():
        if field.GetName().startswith("KiLib_"):
            fp.SetField(field.GetName(), field.GetText())
            next(f for f in fp.GetFields() if f.GetName() == field.GetName()).SetVisible(False)
    # Make authored reference labels visible in fabricated silkscreen.
    fp.Reference().SetLayer(pcbnew.F_SilkS)
io.SaveBoard(str(p), board)
(repo / "zapote/voltage-sense/evidence/library-restoration.json").write_text(
    json.dumps(
        {
            "before_sha256": before,
            "after_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "pad_changes": changes,
        },
        indent=2,
    )
    + "\n"
)
