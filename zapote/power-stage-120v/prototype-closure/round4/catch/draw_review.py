"""Generate a dimensioned review sheet from the declared interface and routed paths."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round4/catch"


def main() -> None:
    d = json.loads((HERE / "interface.json").read_text())
    routes = json.loads((OUT / "route-geometry.json").read_text())["routes"]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1400" viewBox="0 0 1400 1400"><rect width="1400" height="1400" fill="white"/><style>text{font-family:Arial,sans-serif;fill:#142839}.label{font-size:18px}.small{font-size:15px}.head{font-size:28px;font-weight:bold}</style>'
    ]

    def text(x, y, s, cls="label"):
        svg.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(s)}</text>')

    text(35, 42, "TEMPER CATCH CARRIER — R4 ENGINEERING REVIEW", "head")
    text(
        35,
        70,
        "Dimensions in mm. World coordinates; diagram is not a fabrication drawing. All interfaces below remain conditional.",
    )

    def rect(x, y, w, h, fill, stroke="#405565"):
        svg.append(
            f'<rect x="{55 + (x + 140) * 2.25}" y="{130 + (y - 180) * 2.25}" width="{w * 2.25}" height="{h * 2.25}" fill="{fill}" fill-opacity="0.35" stroke="{stroke}"/>'
        )

    rect(-110.5, 162, 240, 160, "#cccccc")
    rect(-99.75, 199.6, 42, 33, "#3c4a59")
    rect(15.5, 328.5, 111, 99, "#b7e4c7")
    rect(17, 342, 107, 76.5, "#b9b9b9")
    rect(25, 355, 57.5, 45, "#74b1ed")
    rect(25, 369, 80, 34, "#ffe39a")
    sensor = d["sense_card"]
    sx, sy, _ = sensor["origin_mm"]
    sw, sh, _ = sensor["max_size_mm"]
    rect(sx, sy, sw, sh, "#df9af2")
    for r, color in zip(routes, ["#be2e30", "#17499b", "#c46f00"], strict=True):
        points = " ".join(
            f"{55 + (x + 140) * 2.25:.2f},{130 + (y - 180) * 2.25:.2f}"
            for x, y, z in r["sampled_centerline_mm"]
        )
        svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="4"/>')
    text(55, 105, "TOP — routing projected in XY; Z variation is in STEP")
    text(190, 255, "C5 obstruction", "small")
    text(
        55,
        725,
        "Native stud locations: J8 (−97.5,192.5), J10 (−63.5,192.5); stud top Z35.",
        "small",
    )
    text(55, 750, "Carrier XY 111 × 99; origin (15.5,328.5). Body support deck Z40..41.5.", "small")
    text(55, 775, "CC1 57.5 × 45 × 30 at (25,355,45); four leads on 52.5 × 20.3 grid.", "small")
    text(55, 800, "Bleed 80 × 34 × 1.6 at (25,369,81); VR37 bodies top Z87.1.", "small")
    text(
        55, 825, "Guard top Z80.5 front / Z90.5 rear. Capacitor pin carrier 65 × 36 × 1.6.", "small"
    )
    text(55, 850, "Base Ø3.4 holes: (23,334), (118,334), (23,424), (118,424).", "small")
    text(780, 115, "WIRE CROSS-SECTION / ROUTE")
    svg.append(
        '<circle cx="835" cy="180" r="39.37" fill="#e0e4e9" stroke="#334"/><circle cx="835" cy="180" r="20.47" fill="#c88945" stroke="#633"/>'
    )
    text(890, 165, "Max insulation OD 3.937", "small")
    text(890, 191, "Copper 3.29 mm² (stranded)", "small")
    text(780, 240, "22 mm true bend radius; supplier minimum 19.685.", "small")
    text(780, 267, "Paired-saddle centers: X−116/Z73 and X−110/Z78.", "small")
    text(780, 294, "Local center spacing √61 = 7.810; OD gap 3.873.", "small")
    text(780, 321, "Routes separate at C5 and holder; not a uniform pair.", "small")
    y = 365
    for r in routes:
        text(780, y, f"{r['name']}: {r['length_mm']:.3f} mm", "small")
        y += 27
    text(780, y + 12, "No extracted full-loop inductance. Terminal joints omitted.", "small")
    text(780, 505, "SERVICE / RELEASE HOLDS")
    for i, s in enumerate(
        [
            "US141 moved forward 6; DIN ends Y426.",
            "Opening projection begins Y324.5 and crosses hood.",
            "Remove discharged-unit rear hood/front carrier panels.",
            "Supplier terminal coordinates/sideways mounting open.",
            "Diode spreader is CATCH_P, never PE.",
            "Sense card is an unrouted 60×35 reservation.",
            "Lug support and wire minimum OD do not fully match.",
            "Insulation, fuse arc and hot-pulse tests are unqualified.",
        ]
    ):
        text(780, 540 + i * 29, s, "small")
    text(
        35,
        935,
        "READ WITH: README.md, carrier-checks.json, internal-checks.json, native KiCad DRC/ERC and manifest.json.",
    )
    text(
        35,
        966,
        "Only the passive bleed PCB is natively routed. The diode/capacitor assembly and sensor require the recorded interface closures.",
    )
    svg.append("</svg>")
    (OUT / "catch-dimensioned-review.svg").write_text("\n".join(svg) + "\n")


if __name__ == "__main__":
    main()
