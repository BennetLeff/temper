"""Native pcbnew oracle for proposed underside sense-wire takeoffs."""

import hashlib
import json
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
p = ROOT / "zapote/power-stage-120v/native-19/section.kicad_pcb"
b = pcbnew.LoadBoard(str(p))
data = []
for fp in b.GetFootprints():
    for pad in fp.Pads():
        if (fp.GetReference(), pad.GetNumber()) in [
            ("C5", "1"),
            ("C5", "3"),
            ("C21", "1"),
            ("C21", "2"),
        ]:
            x = pcbnew.ToMM(pad.GetPosition().x)
            y = pcbnew.ToMM(pad.GetPosition().y)
            data.append(
                {
                    "ref": fp.GetReference(),
                    "pin": pad.GetNumber(),
                    "net": pad.GetNetname(),
                    "native_xy_mm": [x, y],
                    "world_pad_bottom_mm": [129.5 - x, y + 162, 30.387],
                    "drill_mm": [
                        pcbnew.ToMM(pad.GetDrillSize().x),
                        pcbnew.ToMM(pad.GetDrillSize().y),
                    ],
                    "size_mm": [pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)],
                }
            )
assert len(data) == 4
(
    ROOT / "output/temper-prototype-closure/round5/packaging-integration/native-pickoffs.json"
).write_text(
    json.dumps(
        {
            "source": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "datum": "Proper Rz180 native19 candidate mapping; underside solder joints are not present in capacitor STEP models",
            "pickoffs": data,
        },
        indent=2,
    )
    + "\n"
)
