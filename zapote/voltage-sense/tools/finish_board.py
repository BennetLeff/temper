"""Apply authored field visibility and label positions through native KiCad."""

import json, hashlib
from pathlib import Path
import pcbnew

repo = Path(__file__).resolve().parents[3]
path = repo / "zapote/voltage-sense/candidate/section.kicad_pcb"
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(path), None)
before = hashlib.sha256(path.read_bytes()).hexdigest()
labels = {
    "input": (6, 29),
    "host": (70, 24),
    "r_ovp_top1": (20, 9),
    "r_ovp_top2": (30, 9),
    "r_ovp_top3": (40, 9),
    "r_adc_top1": (20, 25),
    "r_adc_top2": (30, 25),
    "r_adc_top3": (40, 25),
    "r_ovp_bottom": (45, 20),
    "r_hyst": (53, 7),
    "r_adc_bottom": (46, 35),
    "comp": (54, 20),
    "reference": (54, 23),
    "c_adc": (51, 36),
    "c_comp": (59, 10),
    "c_ref_in": (59, 32),
    "c_ref_out": (61, 22),
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
    ("VOLTAGE SENSE / Rev A", (38, 3), 1.2),
    ("BUS+", (6, 12), 0.9),
    ("RETURN", (6, 32), 0.9),
    ("3V3 / RTN / FAULT / MON", (64, 38), 0.8),
    ("NON-ISOLATED", (26, 38), 1),
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
(repo / "zapote/voltage-sense/evidence/board-labels.json").write_text(
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
