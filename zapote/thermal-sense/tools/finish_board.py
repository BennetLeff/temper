"""Apply authored field visibility and label positions through native KiCad."""

import hashlib
import json
from pathlib import Path

import pcbnew

repo = Path(__file__).resolve().parents[3]
path = repo / "zapote/thermal-sense/candidate/section.kicad_pcb"
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(path), None)
before = hashlib.sha256(path.read_bytes()).hexdigest()
labels = {
    "heatsink_probe": (6, 17),
    "coil_probe": (6, 35),
    "host": (91, 23),
    "hs_fixed": (15, 5),
    "hs_top": (27, 10),
    "hs_bottom": (23, 16.5),
    "hs_hyst": (32, 3),
    "hs_comp": (36, 16),
    "hs_filter": (15, 18),
    "hs_bypass": (41, 7),
    "coil_fixed": (15, 23),
    "coil_top": (27, 28),
    "coil_bottom": (23, 34.5),
    "coil_hyst": (32, 21),
    "coil_comp": (36, 34),
    "coil_filter": (15, 36),
    "coil_bypass": (41, 25),
    "hs_open_comp": (55, 16),
    "coil_open_comp": (55, 34),
    "hs_or": (75, 16),
    "coil_or": (75, 34),
    "hs_open_bypass": (60, 17.5),
    "coil_open_bypass": (60, 35.5),
    "hs_or_bypass": (80, 7),
    "coil_or_bypass": (80, 25),
    "open_top": (67, 16),
    "open_bottom": (67, 24),
}
for fp in board.GetFootprints():
    for field in fp.GetFields():
        field.SetVisible(False)
    ref = fp.Reference()
    ref.SetVisible(True)
    ref.SetLayer(pcbnew.F_SilkS)
    ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    ref.SetPosition(
        pcbnew.VECTOR2I(*[pcbnew.FromMM(x) for x in labels[fp.GetFieldText("SourceInstance")]])
    )
    ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.9), pcbnew.FromMM(0.9)))
    ref.SetTextThickness(pcbnew.FromMM(0.12))
for text, xy, size in [
    ("THERMAL SENSE / Rev B", (50, 42), 1.1),
    ("HS NTC", (12, 20), 0.8),
    ("COIL NTC", (12, 38), 0.8),
    ("3V3", (83.5, 6), 0.8),
    ("GND", (83.5, 8.5), 0.8),
    ("HS FAULT", (83.5, 11), 0.8),
    ("COIL FAULT", (83.5, 13.5), 0.8),
    ("HS MON", (83.5, 16), 0.8),
    ("COIL MON", (83.5, 18.5), 0.8),
]:
    existing = [
        item
        for item in board.GetDrawings()
        if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() == text
    ]
    if len(existing) > 1:
        raise ValueError(f"duplicate authored label: {text}")
    item = existing[0] if existing else pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(pcbnew.F_SilkS)
    item.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(x) for x in xy]))
    item.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    item.SetTextThickness(pcbnew.FromMM(0.12))
    if not existing:
        board.Add(item)
io.SaveBoard(str(path), board)
(repo / "zapote/thermal-sense/evidence/board-labels-revb.json").write_text(
    json.dumps(
        {
            "before_sha256": before,
            "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "labels": labels,
            "scope": "fields and labels only",
        },
        indent=2,
    )
    + "\n"
)
