"""Guard the visible annotation failure observed on native-09."""

import json
import os
import subprocess
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
KICAD_PY = Path(os.environ.get(
    "KICAD_PY",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
))

PROBE = """
import json, pcbnew, sys
b = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(sys.argv[1], None)
mm = pcbnew.ToMM
rows = {}
for f in b.GetFootprints():
    r = f.Reference()
    p = r.GetPosition()
    c = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    x, y = mm(p.x), mm(p.y)
    bounds = (mm(c.GetX()), mm(c.GetY()), mm(c.GetRight()), mm(c.GetBottom()))
    gap = max(bounds[0] - x, 0, x - bounds[2], bounds[1] - y, y - bounds[3])
    rows[f.GetReference()] = {
        'at': [round(x, 3), round(y, 3)],
        'size_mm': mm(r.GetTextHeight()),
        'thickness_mm': mm(r.GetTextThickness()),
        'visible': r.IsVisible(),
        'front_silkscreen': r.GetLayer() == pcbnew.F_SilkS,
        'courtyard_gap_mm': gap,
        'metadata_hidden_near_footprint': all(
            f.GetField(name) and not f.GetField(name).IsVisible()
            and f.GetField(name).GetPosition() == f.GetPosition()
            for name in ('Sheetpath', 'SourceInstance', 'MPN')
        ),
    }
print(json.dumps(rows))
"""


def test_native_15_references_are_visible_legible_and_source_fields_are_hidden():
    if not KICAD_PY.is_file():
        pytest.skip("KiCad pcbnew Python is unavailable")
    result = subprocess.run(
        [str(KICAD_PY), "-c", PROBE, str(UNIT / "native-15/section.kicad_pcb")],
        text=True,
        capture_output=True,
        check=True,
    )
    actual = json.loads(result.stdout)
    expected = json.loads((UNIT / "reference-labels.json").read_text())["references"]
    assert len(actual) == json.loads((UNIT / "build-receipt.json").read_text())["components"]
    assert set(actual) == set(expected)
    for name, row in actual.items():
        assert row["at"] == expected[name]["at"], name
        assert row["visible"] and row["front_silkscreen"], name
        assert row["courtyard_gap_mm"] <= 4.0, name
        assert row["metadata_hidden_near_footprint"], name
        # JLCPCB legend minimum: 1.0 mm text, 0.15 mm stroke.
        assert row["size_mm"] >= 1.0 - 1e-6 and row["thickness_mm"] >= 0.15 - 1e-6, name
