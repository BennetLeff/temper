#!/usr/bin/env python3
"""Small geometry guard for the locally drawn TI DRB0008A land pattern."""
from pathlib import Path
import re

MOD = Path(__file__).parent / "TPS3431_DRB0008A.pretty" / (
    "TPS3431_DRB0008A_VSON-8-1EP_3x3mm_P0.65mm_EP1.75x1.5mm.kicad_mod"
)
text = MOD.read_text()
rows = re.findall(
    r'\(pad "(\d+)" smd roundrect \(at ([\d.-]+) ([\d.-]+)\) '
    r'\(size ([\d.]+) ([\d.]+)\)', text
)
expected = [
    ("1", -1.4, -0.975), ("2", -1.4, -0.325),
    ("3", -1.4, 0.325), ("4", -1.4, 0.975),
    ("5", 1.4, 0.975), ("6", 1.4, 0.325),
    ("7", 1.4, -0.325), ("8", 1.4, -0.975),
]
assert len(rows) == 8, f"expected eight perimeter lands, got {len(rows)}"
for actual, (number, x, y) in zip(rows, expected):
    assert actual[0] == number, (actual, number)
    assert abs(float(actual[1]) - x) < 1e-9 and abs(float(actual[2]) - y) < 1e-9, actual
    assert (float(actual[3]), float(actual[4])) == (0.6, 0.31), actual
thermal = re.search(r'\(pad "9" smd rect \(at 0 0\) \(size ([\d.]+) ([\d.]+)\)', text)
assert thermal and (float(thermal[1]), float(thermal[2])) == (1.75, 1.5)
paste = re.findall(r'\(pad "" smd rect .*?\(size ([\d.]+) ([\d.]+)\) \(layers "F.Paste"\)', text)
assert len(paste) == 4 and all((float(w), float(h)) == (0.725, 0.725) for w, h in paste)
assert abs(4 * 0.725 * 0.725 / (1.75 * 1.5) - 0.799) < 0.002
print("PASS: eight 0.60 x 0.31 mm lands, 0.65 mm pitch, 1.75 x 1.50 mm EP, 4-way 80% paste split")
