"""Apply authored interlock label positions through native KiCad; no routing search."""

import hashlib
import json
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
BOARD = ROOT / "zapote/interlock/candidate/section.kicad_pcb"
b = pcbnew.LoadBoard(str(BOARD))
before = hashlib.sha256(BOARD.read_bytes()).hexdigest()
labels = {
    "J1": (8, 10),
    "J2": (92, 27.8),
    "U1": (31, 18.5),
    "U2": (31, 36.5),
    "U3": (49, 20.5),
    "U4": (66, 39),
    "U5": (66, 12),
    "U6": (49, 40),
    "R1": (18, 15.3),
    "R2": (18, 19.3),
    "R3": (18, 23.3),
    "R4": (18, 27.3),
    "R5": (18, 31.3),
    "R6": (18, 35.3),
    "R7": (18, 39.3),
    "R8": (38, 51),
    "R9": (58, 7),
    "R10": (45, 53),
    "R11": (78, 43),
    "C1": (36.5, 19.6),
    "C2": (36.5, 40.8),
    "C3": (55, 21.6),
    "C4": (70, 37),
    "C5": (70, 16),
    "C6": (53, 40.2),
}
for fp in b.GetFootprints():
    for field in fp.GetFields():
        field.SetVisible(False)
    ref = fp.Reference()
    ref.SetVisible(True)
    ref.SetLayer(pcbnew.F_SilkS)
    ref.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in labels[fp.GetReference()]]))
    ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.9), pcbnew.FromMM(0.9)))
    ref.SetTextThickness(pcbnew.FromMM(0.12))
for text, xy, size in [
    ("SAFETY INTERLOCK / Rev A", (48, 4), 1.3),
    ("FAULT INPUTS", (9, 7), 0.8),
    ("HOST / PERMIT", (90, 26), 0.8),
    ("J1: 1 GND  2 OCP  3 OVP  4 HS  5 COIL  6 RTD  7 RUNAWAY  8 AUX", (50, 59), 0.85),
    ("J2: 1 3V3  2 GND  3 WDI  4 RESET_N  5 LIVE  6 PERMIT  7 FAULT  8 WDT_N", (50, 61.5), 0.85),
]:
    matches = [i for i in b.GetDrawings() if isinstance(i, pcbnew.PCB_TEXT) and i.GetText() == text]
    if len(matches) > 1:
        raise ValueError("duplicate board label")
    t = matches[0] if matches else pcbnew.PCB_TEXT(b)
    t.SetText(text)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in xy]))
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    t.SetTextThickness(pcbnew.FromMM(0.12))
    if not matches:
        b.Add(t)
pcbnew.SaveBoard(str(BOARD), b)
(ROOT / "zapote/interlock/evidence/board-labels.json").write_text(
    json.dumps(
        {
            "scope": "authored field visibility and label geometry only",
            "before_sha256": before,
            "after_sha256": hashlib.sha256(BOARD.read_bytes()).hexdigest(),
            "labels": labels,
        },
        indent=2,
    )
    + "\n"
)
