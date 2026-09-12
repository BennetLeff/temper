"""Reinstantiate exact native library footprints while preserving source identities and pad centres.

The source skeleton loses native pad/text rotation and metadata on some library
formats. Load each original candidate library with KiCad, place it with KiCad,
and require identical pad centres before retaining copper. Never derive the
library from an edited board.
"""

from pathlib import Path
import hashlib, json
import pcbnew

base = Path(__file__).resolve().parents[1]
p = base / "candidate/section.kicad_pcb"
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(p), None)
before = hashlib.sha256(p.read_bytes()).hexdigest()
record = []
for old in list(board.GetFootprints()):
    fpid = old.GetFPID()
    lib = base / "candidate/candidate-libs" / f"{fpid.GetLibNickname()}.pretty"
    fp = io.FootprintLoad(str(lib), str(fpid.GetLibItemName()), False, None)
    fp.SetFPID(fpid)
    fp.SetPosition(old.GetPosition())
    fp.SetOrientation(old.GetOrientation())
    pads = {q.GetNumber(): q for q in old.Pads()}
    for q in fp.Pads():
        prior = pads[q.GetNumber()]
        if q.GetPosition() != prior.GetPosition():
            raise ValueError("pad centre differs; routing must be redone")
        q.SetNet(prior.GetNet())
    fp.SetPath(old.GetPath())
    fp.SetReference(old.GetReference())
    fp.SetValue(old.GetValue())
    for f in old.GetFields():
        if f.GetName() not in ["Reference", "Value"]:
            fp.SetField(f.GetName(), f.GetText())
    for f in fp.GetFields():
        f.SetVisible(False)
    ref = fp.Reference()
    ref.SetVisible(True)
    ref.SetLayer(pcbnew.F_SilkS)
    ref.SetTextAngle(old.Reference().GetTextAngle())
    ref.SetPosition(old.Reference().GetPosition())
    ref.SetTextSize(old.Reference().GetTextSize())
    ref.SetTextThickness(old.Reference().GetTextThickness())
    record.append(
        {
            "reference": fp.GetReference(),
            "library_sha256": hashlib.sha256(
                (lib / f"{fpid.GetLibItemName()}.kicad_mod").read_bytes()
            ).hexdigest(),
            "pad_centres_preserved": True,
        }
    )
    board.Remove(old)
    board.Add(fp)
io.SaveBoard(str(p), board)
(base / "evidence/native-library-refresh.json").write_text(
    json.dumps(
        {
            "before_sha256": before,
            "after_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "footprints": record,
        },
        indent=2,
    )
    + "\n"
)
