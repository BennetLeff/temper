"""Engineer review packet, intentionally distinct from a fabrication drawing."""

import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/packaging-integration"
W, H = landscape(A3)
STYLE = ParagraphStyle(
    "body", fontName="Helvetica", fontSize=11, leading=15, textColor=colors.HexColor("#152334")
)
SMALL = ParagraphStyle("small", parent=STYLE, fontSize=9, leading=12)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def para(c, text, x, y, width, style=STYLE):
    p = Paragraph(text, style)
    _, height = p.wrap(width, 900)
    p.drawOn(c, x, y - height)
    return y - height - 12


def title(c, page, t, status):
    c.setFillColor(colors.HexColor("#142b42"))
    c.setFont("Helvetica-Bold", 23)
    c.drawString(42, H - 45, t)
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#8b3a25"))
    c.drawString(42, H - 67, status)
    c.setFillColor(colors.HexColor("#526273"))
    c.setFont("Helvetica", 9)
    c.drawString(
        42,
        23,
        "Temper | Internal installation candidate | mm | Not a fabrication or powered-build release",
    )
    c.drawRightString(W - 42, 23, f"{page} / 4")


def table(c, rows, x, y, widths):
    data = [[Paragraph(str(v), SMALL) for v in row] for row in rows]
    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8ef")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#8b9dad")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, colors.HexColor("#d2dce4")),
            ]
        )
    )
    _, hh = t.wrap(1000, 1000)
    t.drawOn(c, x, y - hh)
    return y - hh - 18


def main():
    cap = json.loads((OUT / "native-capture.json").read_text())
    route_data = json.loads((OUT / "harness-probe.json").read_text())
    power_data = json.loads((OUT / "rigid-power-installation.json").read_text())
    guide_xy = ", ".join(
        f"({r['floor_hole_xy_d_mm'][0]:g},{r['floor_hole_xy_d_mm'][1]:g})"
        for r in route_data["candidate_changes"].values()
        if "floor_hole_xy_d_mm" in r
    )
    cooling_xy = ", ".join(
        f"({r['center_xy'][0]:g},{r['center_xy'][1]:g}) d{r['diameter']:g}"
        for r in power_data["new_cooling_floor_holes"]
    )
    verified = OUT / "installation-verification.json"
    current = (
        verified.exists()
        and json.loads(verified.read_text()).get("native_capture_sha256")
        == sha(OUT / "native-capture.json")
        and json.loads(verified.read_text()).get("status") == "PASS"
    )
    current = current and all(sha(ROOT / item["source"]) == item["sha256"] for item in cap.values())
    if current:
        verification = json.loads(verified.read_text())
        current = verification["support_receipt_sha256"] == sha(
            OUT / "support-receipt.json"
        ) and verification["harness_receipt_sha256"] == sha(OUT / "harness-receipt.json")
    status = (
        "MATCHING NATIVE CHECKPOINT - NOMINAL GEOMETRY VERIFIED; QUALIFICATION HOLDS REMAIN"
        if current
        else "CHECKPOINT ONLY - FINAL MERGED RECEIPT PENDING"
    )
    orientation = json.loads((OUT / "power-orientation-verification.json").read_text())
    if orientation["status"] != "PASS_ACTUAL_RIGID_POWER_GEOMETRY":
        status = "REFLECTED_BASELINE_NOT_MANUFACTURING_GEOMETRY - POWER BOARD REQUIRES RIGID PLACEMENT ECO"
    c = canvas.Canvas(str(OUT / "temper-installation-review.pdf"), pagesize=(W, H))
    c.setTitle("Temper support and guarded sense harness - engineering review candidate")
    title(c, 1, "Installation overview", status)
    image = OUT / "support-harness-installation.png"
    iw, ih = 1440, 1050
    scale = min((W - 84) / iw, (H - 120) / ih)
    c.drawImage(str(image), (W - iw * scale) / 2, 49, width=iw * scale, height=ih * scale)
    c.showPage()
    title(c, 2, "Pod and cooker board placement", status)
    image = OUT / "installation-layout.png"
    iw, ih = 1250, 760
    scale = min((W - 84) / iw, (H - 130) / ih)
    c.drawImage(str(image), (W - iw * scale) / 2, 55, width=iw * scale, height=ih * scale)
    c.showPage()
    title(c, 3, "Attachment patterns and assembly sequence", status)
    y = H - 94
    y = para(
        c,
        "Use the <b>candidate-drilled-floor.step</b> from the same receipt as the routed assembly. Fabricate a new candidate floor: restore the 8 obsolete cooling bores, then cut 14 cooling/PE and 12 support/guide holes. Preserve unrelated vents, folds, feet and mounts. Historical floor and housing files are unchanged.",
        42,
        y,
        W - 84,
    )
    rows = [
        ["Interface", "Coordinates / geometry", "Fastener stack / installation"],
        [
            "Revised cooling / new floor",
            cooling_xy,
            "Use matching cooling interface and floor-drilling-manifest.json. Existing shifted holes must not become unplanned slots.",
        ],
        [
            "Catch paired-wire saddle",
            "Post axes: (135.5,285), (135.5,295); base Z68-70. Closure axes (124.5,289.5), (124.5,294.5).",
            "One machined PEEK lower guide/base. Diameter6.2 wells admit the checked diameter4 driver envelope before wire installation; 6mm rail engagement. Two M2x8 closure screws and one right locating dowel. Guide only; not axial restraint.",
        ],
        [
            "Front tray / stepped guard",
            "Floor XY: (-86,26), (131,26), (-86,70), (131,80); four diameter 3.4 holes",
            "M3x8 from below; 0.5 shim, 1.5 tray, blind-threaded PEEK posts. Separate M3x6 top screws. Rear-left post moved from Y79 to 70.",
        ],
        [
            "OUT frame",
            "Floor XY: (-133,316), (-126,316), (-76.5,316), (-69.5,316); four diameter 3.4 holes",
            "M3x6 into machined bracket feet. Uprights Y328-331 avoid PE and filter. Two M3x5 frame screws at (-128,335), (-73,335).",
        ],
        [
            "Guide blocks",
            "Floor XY: " + guide_xy + "; four diameter 3.4 holes",
            "BUS side: M3x10, 2.2 spacer and local duct-floor hole. Other blocks: M3x8. Two M2x8 joining screws per split block.",
        ],
        [
            "Catch sensor / removable guard",
            "Guard screw axes: (Y391,Z46), (Y351,Z46), (Y351,Z75); diameter 2.9 clearance",
            "M2.5x12 from X121 toward -X through guard, rail, 3 mm spacer, PCB and PEEK nut. Unplug both card interfaces before guard removal.",
        ],
        [
            "Supervisor carrier",
            "Four frame posts: X29/306, Z34/248; Y82-200; diameter 12 x118",
            "M4x10 each end. Central board uses four actual NPTHs and 15 mm insulating spacers. Remove carrier to service contactors.",
        ],
        [
            "CT / LINE / PRE carriers",
            "CT outer posts: X469, Z129/166; bridges at Z130/148. LINE/PRE: X387/453,Z361/468",
            "CT bridges: M3; rear voltage carrier: 8 mm spacers with M3x18 through bolts. Exact NPTH patterns are in support-patterns.json.",
        ],
    ]
    y = table(c, rows, 42, y, [185, 360, W - 84 - 545])
    y = para(
        c,
        "<b>OUT is an independent support.</b> The revised board underside is Z75, tray Z69.5-71, frame top Z69.5 and downstand bottom Z63.5. Three M2.5x12 board screws capture the frame, tray, 4 mm standoffs and PCB. The filter cover carries no board load. Rejected rear/side supports and the 0.25 mm slot are not approved alternatives.",
        42,
        y,
        W - 84,
    )
    y = para(
        c,
        "<b>Assembly order:</b> inspect and bond the unpowered base; install and set cooling clamps before obstructing C5/PS1/PS2 parts, with glass/coil/hood roof removed; install OUT bracket feet; fit the candidate hood notches and seals; fit frame/trays; fit PCB spacers and boards; install pre-threaded grommets and guide tubes; terminate and restrain wires; inspect fasteners and insulation; close guards. Removal requires isolated power and verified discharge. A harness must not be pulled by removing its carrier.",
        42,
        y,
        W - 84,
    )
    y = para(
        c,
        "<b>Materials:</b> PEEK fasteners/supports and 6061-T6 frame members are candidates. Exact grades, torque, thread creep, harness loads and PE continuity still require qualification. Metal frame joints are not automatically protective bonds. The PDF is an installation index; native CAD and matching receipts define geometry.",
        42,
        y,
        W - 84,
    )
    c.showPage()
    title(c, 4, "Evidence, limits and engineer review targets", status)
    y = H - 94
    rows = [
        ["Established digitally", "Still required before a powered prototype"],
        [
            "Inherited reflection rejected; actual native19 solids now checked for a proper Rz180 placement",
            "Read the matching orientation and cooling receipts. Revised cooling/retention/catch routes replace the reflected baseline; terminal processes, electrical insulation, forces and hot measurements remain required.",
        ],
        [
            "Actual nine native board exports, mounting holes and connector working volumes; hash-identified source chain",
            "Freeze the native board revision and repeat the full chain after any geometry/model change. Resolve all electrical/DRC release holds separately.",
        ],
        [
            "Four R32 guide paths from native C5/C21 pads to BUS/TANK cards, custom wall ports, grommets and bolted blocks",
            "Design/verify formed solder tails, insulation boots and capacitor lead projections. Qualify axial grip and hot sag between supports. Long sensing leads require transfer-function, common-mode/EMI and transient tests.",
        ],
        [
            "OUT minimum measured separation: 1.0 mm to PE/filter/carrier; 1.5 mm frame-to-filter cover",
            "Confirm proposed <=0.60 mm adverse mechanical stack and loaded/hot displacement. These are mechanical distances, not insulation acceptance.",
        ],
        [
            "31 material/service check groups; intentional threaded joints and conductor continuation contacts are separately bounded and reported",
            "Dedicated sink-to-cradle braid and locking stacks are modeled. Qualify braid/termination, bond resistance and fault withstand, plus insulation, accessibility and hot containment against actual voltages/environment.",
        ],
    ]
    y = table(c, rows, 42, y, [520, W - 84 - 520])
    h = json.loads((OUT / "harness-probe.json").read_text())
    lengths = ", ".join(f"{k} {v['length_mm']:.1f} mm" for k, v in h["routes"].items())
    y = para(
        c,
        "<b>Wire candidate:</b> Alpha 392240, 22 AWG silicone, maximum OD 2.8956 mm. Its published 10xOD bend requirement is 28.956 mm; the modeled inside jacket radius is 30.5522 mm. Guide tube candidate: OD5 / ID3.3 mm, material/shape stability unqualified. Jacket path lengths: "
        + lengths
        + ".",
        42,
        y,
        W - 84,
    )
    y = para(
        c,
        "<b>Primary sources:</b> alphawire.com/products/wire/hook-up-wire/premium/392240; iportal.se.com/Contents/docs/SQD-LC1D18BD.PDF; talema.com/wp-content/uploads/datasheets/AC-1005.pdf; Accu SIP-M2.5-10-PEEK and SIP-M3-6-PEEK dimensional pages. Wire DC rating does not by itself accept high-frequency tank voltage.",
        42,
        y,
        W - 84,
        SMALL,
    )
    y = para(
        c,
        "<b>Identity of this packet</b> - compare full digests, not filename alone.",
        42,
        y,
        W - 84,
    )
    entries = [("Central PCB", cap["central"]["sha256"]), ("PRE PCB", cap["pre"]["sha256"])]
    for name in [
        "r4-supported-routed-candidate.step",
        "pod-supported-integration-candidate.step",
        "candidate-drilled-floor.step",
    ]:
        p = OUT / name
        if p.exists():
            entries.append((name, sha(p)))
    for label, digest in entries:
        y = para(
            c,
            f'<b>{label}</b><br/><font face="Courier" size="9">{digest}</font>',
            42,
            y,
            W - 84,
            SMALL,
        )
    c.save()
    print("Wrote temper-installation-review.pdf; current native chain:", current)


if __name__ == "__main__":
    main()
