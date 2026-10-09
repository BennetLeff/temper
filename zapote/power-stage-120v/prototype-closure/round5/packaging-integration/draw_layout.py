"""Dimensioned assembly index derived from the candidate's actual placement records."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
p = json.loads((OUT / "installation-coordinates.json").read_text())
s = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1250" height="760" viewBox="0 0 1250 760">',
    '<rect width="1250" height="760" fill="#f5f3ed"/>',
    '<g font-family="Arial,sans-serif" fill="#123b42">',
    '<text x="35" y="36" font-size="24">Temper / nine-board installation candidate</text>',
    '<text x="35" y="62" font-size="14">Native PCB geometry • R4 housing preserved • final native captures pinned; thermal, wiring and insulation qualification remain</text>',
    '<text x="40" y="95" font-size="18">Pod: front view, 500 W × 500 H × 220 D</text>',
    '<rect x="40" y="115" width="500" height="500" fill="#e6e7e1" stroke="#123b42" stroke-width="2"/>',
    '<text x="650" y="95" font-size="18">R4: top view, X±185 / Y0–440</text>',
    '<rect x="650" y="115" width="370" height="440" fill="#e6e7e1" stroke="#123b42" stroke-width="2"/>',
]
# Retained locations are labeled context, not fabricated detail.
s += [
    '<rect x="724.5" y="277" width="240" height="160" fill="#d2d5d0" stroke="#75817c"/>',
    '<text x="770" y="335" font-size="13">Native19 power PCB / Rz180</text>',
    '<rect x="695" y="447" width="110" height="80" fill="#d8cabc" stroke="#75817c"/>',
    '<text x="710" y="478" font-size="12">D22 below</text>',
]
for i, k in enumerate(["K1", "K2", "KB", "KPA*", "KPB*"]):
    x = 80 + 65 * i
    s += [
        f'<rect x="{x}" y="430" width="45" height="85" fill="#a7babd" stroke="#44676b"/>',
        f'<text x="{x + 4}" y="525" font-size="12">{k}</text>',
    ]
s += [
    '<rect x="110" y="149.5" width="182" height="120.5" fill="#d7a175" stroke="#815237"/>',
    '<text x="145" y="205" font-size="13">2 × HS400</text>',
]
for name, r in p.items():
    a = r["bounds_mm"]
    x0, y0, z0, x1, y1, z1 = a
    if r["space"] == "pod":
        x, y, w, h = 40 + x0, 615 - z1, x1 - x0, z1 - z0
    else:
        x, y, w, h = 835 + x0, 115 + y0, x1 - x0, y1 - y0
    fill = "#91bdac" if name != "central" else "#b5d7ca"
    s += [
        f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{fill}" fill-opacity=".82" stroke="#1b6355"/>',
        f'<text x="{x + 3:.3f}" y="{y + 14:.3f}" font-size="12">{name.upper()}</text>',
    ]
    for m in r["mounts"]:
        a, b, c = m["substrate_underside_world"]
        cx, cy = (40 + a, 615 - c) if r["space"] == "pod" else (835 + a, 115 + b)
        s.append(f'<circle cx="{cx}" cy="{cy}" r="2" fill="#173e40"/>')
s += [
    '<text x="40" y="650" font-size="14">Central panel comes out before contactor service.</text>',
    '<text x="40" y="675" font-size="14">* KPA/KPB = additive proposal, not frozen circuit.</text>',
    '<text x="650" y="600" font-size="14">Catch sensor faces inward; OUT sits over D22.</text>',
    '<text x="650" y="625" font-size="14">BUS/TANK guarded routes modeled; electrical qualification remains.</text>',
    '<text x="650" y="650" font-size="14">Black dots = transformed native mounting centers.</text>',
    '<text x="35" y="725" font-size="13">Drawing index only; inspect STEP plus interference receipt. Body fit does not close lead routing, safety or manufacture.</text>',
    "</g></svg>",
]
(OUT / "installation-layout.svg").write_text("\n".join(s) + "\n")
