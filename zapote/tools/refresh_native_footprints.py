"""Reinstantiate exact native library footprints while preserving source identities and pad centres.

The source skeleton loses native pad/text rotation and metadata on some library
formats. Load each original candidate library with KiCad, place it with KiCad,
and require identical pad centres before retaining copper. Never derive the
library from an edited board.
"""

import argparse
import hashlib
import json
from pathlib import Path

import pcbnew

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--board", type=Path, required=True)
parser.add_argument("--libraries", type=Path, required=True)
parser.add_argument("--receipt", type=Path, required=True)
args = parser.parse_args()
p = args.board.resolve()
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(p), None)
before = hashlib.sha256(p.read_bytes()).hexdigest()
record = []
uuid_replacements = {}
for old in list(board.GetFootprints()):
    if old.GetLayer() != pcbnew.F_Cu:
        raise ValueError("only front-side footprint refresh is supported")
    fpid = old.GetFPID()
    lib = args.libraries.resolve() / f"{fpid.GetLibNickname()}.pretty"
    fp = io.FootprintLoad(str(lib), str(fpid.GetLibItemName()), False, None)
    fp.SetFPID(fpid)
    fp.SetPosition(old.GetPosition())
    fp.SetOrientation(old.GetOrientation())
    old_pads = list(old.Pads())
    new_pads = list(fp.Pads())
    # GetPosition() is already in board/world coordinates after placement and
    # orientation.  Number alone is insufficient for relays and other
    # multi-pad packages with repeated physical numbers; NPTH uses "".
    def key(q):
        pos = q.GetPosition()
        return (str(q.GetNumber()), int(pos.x), int(pos.y))

    old_keys = [key(q) for q in old_pads]
    new_keys = [key(q) for q in new_pads]
    if len(set(old_keys)) != len(old_keys):
        raise ValueError("saved footprint has coincident duplicate pad centres")
    if len(set(new_keys)) != len(new_keys):
        raise ValueError("native library has coincident duplicate pad centres")
    old_by_key = dict(zip(old_keys, old_pads))
    new_by_key = dict(zip(new_keys, new_pads))
    if set(old_by_key) != set(new_by_key):
        raise ValueError("pad census differs by number/world centre; routing must be redone")
    for k, q in new_by_key.items():
        prior = old_by_key[k]
        if q.GetPosition() != prior.GetPosition():
            raise ValueError("pad centre differs; routing must be redone")
        # KiCad's Python binding exposes KIID read-only.  Record the mapping
        # and apply it to the serialized board after the native replacement.
        uuid_replacements[q.m_Uuid.AsString()] = prior.m_Uuid.AsString()
        if q.GetNumber() != "" and prior.GetNet():
            q.SetNet(prior.GetNet())
    fp.SetPath(old.GetPath())
    uuid_replacements[fp.m_Uuid.AsString()] = old.m_Uuid.AsString()
    fp.SetReference(old.GetReference())
    fp.SetValue(old.GetValue())
    for f in old.GetFields():
        if f.GetName() not in ["Reference", "Value"]:
            fp.SetField(f.GetName(), f.GetText())
    for f in fp.GetFields():
        f.SetVisible(False)
    ref = fp.Reference()
    ref.SetVisible(True)
    ref.SetLayer(old.Reference().GetLayer())
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
data = p.read_bytes()
for i, (new_uuid, old_uuid) in enumerate(uuid_replacements.items()):
    marker = f"00000000-0000-0000-0000-{i:012d}"
    data = data.replace(new_uuid.encode(), marker.encode())
    data = data.replace(marker.encode(), old_uuid.encode())
p.write_bytes(data)
args.receipt.write_text(
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
