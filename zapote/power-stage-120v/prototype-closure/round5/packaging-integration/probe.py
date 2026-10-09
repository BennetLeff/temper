import json
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE.parents[1] / "round3/packaging"))
from build_proposal import bounds, hits, read_parts  # noqa: E402

OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
base = read_parts(
    ROOT
    / "output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step"
)
print(
    "sensor placeholders", [(k, bounds(v)) for k, v in base.items() if "SENSE" in k or "AMC" in k]
)
placements = {
    "catch": ("cyclic", (103, 348, 78)),
    "bus": ("flat", (77, 290, 14)),
    "tank": ("flat", (-80, 90, 14)),
    "out": ("flat", (-130, 410, 66)),
}
res = {}
for key, (rot, xyz) in placements.items():
    parts = read_parts(OUT / "boards" / f"{key}.step")

    def tf(s, rot=rot, xyz=xyz):
        return (s.rotate((0, 0, 0), (1, 1, 1), 120) if rot == "cyclic" else s).translate(xyz)

    items = {key + "_" + k: tf(v) for k, v in parts.items()}
    res[key] = {
        "bounds": bounds(cq.Compound.makeCompound(list(items.values()))),
        "hits": hits(items, base),
    }
    print(key, res[key])
(OUT / "probe.json").write_text(json.dumps(res, indent=2))
