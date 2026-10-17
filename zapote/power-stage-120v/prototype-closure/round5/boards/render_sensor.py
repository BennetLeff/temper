"""Render conventional KiCad symbols from the reviewed sensor pin table."""

from __future__ import annotations

import csv
import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
DST = HERE / "native/catch-sensor"


def uid(s):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-round5-boards/" + s))


def q(s):
    return json.dumps(str(s))


def definition(lib, name):
    s = (LIB / (lib + ".kicad_sym")).read_text()
    i = s.index('\n\t(symbol "' + name + '"') + 2
    depth = 0
    quoted = False
    escape = False
    for j in range(i, len(s)):
        c = s[j]
        if c == '"' and not escape:
            quoted = not quoted
        if not quoted:
            if c == "(":
                depth += 1
            if c == ")":
                depth -= 1
        if depth == 0:
            break
        escape = c == "\\" and not escape
    return s[i : j + 1]


def pins(raw):
    out = {}
    for t in re.split(r"\(pin (?!_names|_numbers)", raw)[1:]:
        p = re.search(r"\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)", t)
        n = re.search(r'\(number "(.*?)"', t)
        if p and n:
            out[n[1]] = tuple(map(float, p.groups()))
    return out


def main(sensor="catch"):
    global DST
    DST = HERE / "native" / (sensor + "-sensor")
    count = {"catch": 8, "bus": 8, "line": 4, "pre": 4, "out": 4, "tank": 12}[sensor]
    channel = {
        "catch": "VCATCH",
        "bus": "VBUS",
        "line": "VLINE",
        "pre": "VPRE",
        "out": "VOUT",
        "tank": "VTANK",
    }[sensor]
    parts = defaultdict(list)
    for r in csv.DictReader((HERE / (sensor + "-pins.tsv")).open(), delimiter="\t"):
        parts[r["reference"]].append(r)
    raw = {
        name: definition(lib, name)
        for lib, name in [
            ("Device", "R_Small_US"),
            ("Device", "C"),
            ("Isolator_Analog", "AMC3330"),
            ("Connector_Generic", "Conn_01x02"),
            ("Connector_Generic", "Conn_01x06"),
            ("power", "PWR_FLAG"),
        ]
    }
    raw["AMC3330"] = raw["AMC3330"].replace(
        "(pin output line\n\t\t\t\t(at 17.78 0 180)",
        "(pin open_collector line\n\t\t\t\t(at 17.78 0 180)",
    )
    objects = []
    coords = {}
    serial = [0]

    def wire(a, b):
        if a == b:
            return
        serial[0] += 1
        objects.append(
            f'(wire(pts(xy {a[0]} {a[1]})(xy {b[0]} {b[1]}))(stroke(width 0)(type default))(uuid "{uid("w" + str(serial[0]))}"))'
        )

    def label(net, xy, angle=0):
        serial[0] += 1
        objects.append(
            f'(global_label {q(net)}(shape bidirectional)(at {xy[0]} {xy[1]} {angle})(effects(font(size 1.016 1.016))(justify left))(uuid "{uid("l" + str(serial[0]))}"))'
        )

    positions = {
        **{
            f"R{i}": (30.48 + ({4: 35.56, 8: 17.78, 12: 12.7}[count]) * (i - 1), 86.36, 90)
            for i in range(1, count + 1)
        },
        f"R{count + 1}": (185.42, 105.41, 0),
        "C1": (198.12, 105.41, 0),
        "U1": (226.06, 81.28, 0),
        f"R{count + 2}": (289.56, 69.85, 0),
        "J1": (30.48, 45.72, 0),
        "J2": (340.36, 83.82, 0),
        "C2": (292.1, 137.16, 0),
        "C3": (309.88, 137.16, 0),
        "C4": (109.22, 137.16, 0),
        "C5": (127, 137.16, 0),
        "C6": (345.44, 137.16, 0),
        "C7": (180.34, 137.16, 0),
        "C8": (198.12, 137.16, 0),
    }
    for ref, rows in parts.items():
        name = (
            "R_Small_US"
            if ref[0] == "R"
            else "C"
            if ref[0] == "C"
            else "AMC3330"
            if ref[0] == "U"
            else "Conn_01x02"
            if ref == "J1"
            else "Conn_01x06"
        )
        x, y, a = positions[ref]
        pp = pins(raw[name])
        expected = {r["pin"] for r in rows}
        if set(pp) != expected:
            raise ValueError((ref, set(pp), expected))
        pininst = []
        for n, (px, py, _ang) in pp.items():
            pos = (
                (round(x - py, 6), round(y - px, 6))
                if a == 90
                else (round(x + px, 6), round(y - py, 6))
            )
            coords[ref + "." + n] = pos
            pininst.append(f'(pin {q(n)}(uuid "{uid(ref + "pin" + n)}"))')
        val = rows[0]["value"]
        prop_a = 90 if a == 90 else 0
        rx, ry = (
            (x, y - 5.08)
            if a == 90
            else (x + 5.08, y - 1.27)
            if ref[0] in "RC"
            else (x, y - 22.86)
            if ref == "U1"
            else (x, y - 5.08)
        )
        vx, vy = (
            (x, y + 5.08)
            if a == 90
            else (x + 7.62, y + 2.54)
            if ref[0] in "RC"
            else (x, y + 22.86)
            if ref == "J2"
            else (x, y - 20.32)
            if ref == "U1"
            else (x, y + 5.08)
        )
        objects.append(f'''(symbol(lib_id "Sensor:{name}")(at {x} {y} {a})(unit 1)(in_bom yes)(on_board yes)(dnp no)(uuid "{uid(sensor + "/" + ref)}")
(property "Reference" {q(ref)}(at {rx} {ry} {prop_a})(effects(font(size 1.016 1.016))))
(property "Value" {q(val)}(at {vx} {vy} {prop_a})(effects(font(size 1.016 1.016))))
(property "MPN" {q(rows[0]["mpn"])}(at {x} {y} 0)(effects(font(size 1 1)) hide))
(property "Footprint" {q(rows[0]["footprint"])}(at {x} {y} 0)(effects(font(size 1 1)) hide))
{" ".join(pininst)}(instances(project "{sensor}-sensor"(path "/{uid(sensor + "-root")}"(reference "{ref}")(unit 1)))))''')
    linked = set()

    def link(*ids):
        for aa, bb in zip(ids, ids[1:]):  # noqa: B905 -- KiCad embeds Python 3.9; adjacent pairs intentionally differ in length.
            wire(
                coords[aa] if isinstance(aa, str) else aa, coords[bb] if isinstance(bb, str) else bb
            )
        linked.update(x for x in ids if isinstance(x, str))

    for i in range(1, count):
        link(f"R{i}.2", f"R{i + 1}.1")
    link(f"R{count}.2", (185.42, 86.36), "U1.6")
    link(f"R{count + 1}.1", (185.42, 86.36))
    link("C1.1", (198.12, 86.36))
    linked.add("U1.6")
    # Junctions make branches explicit in the native connectivity oracle.
    for x, y in [(185.42, 86.36), (198.12, 86.36)]:
        objects.append(
            f'(junction(at {x} {y})(diameter 0)(color 0 0 0 0)(uuid "{uid(str((x, y)))}"))'
        )
    for ref, rows in parts.items():
        for row in rows:
            key = ref + "." + row["pin"]
            xy = coords[key]
            if row["net"] == "NC":
                objects.append(f'(no_connect(at {xy[0]} {xy[1]})(uuid "{uid(key + "nc")}"))')
                continue
            if key in linked:
                if key in {f"R{i}.2" for i in range(1, count + 1)}:
                    label(row["net"], xy, 90)
                continue
            if ref == "R1" and row["pin"] == "1":
                end = (xy[0] - 10.16, xy[1])
            elif ref[0] in "RC":
                end = (xy[0], xy[1] - 7.62 if row["pin"] == "1" else xy[1] + 7.62)
            elif ref[0] == "J":
                end = (xy[0] - 10.16, xy[1])
            else:
                px, py, angle = pins(raw["AMC3330"])[row["pin"]]
                end = (
                    (xy[0] - 12.7, xy[1])
                    if px < -10
                    else (xy[0] + 12.7, xy[1])
                    if px > 10
                    else (xy[0], xy[1] - 7.62 if py > 0 else xy[1] + 7.62)
                )
            wire(xy, end)
            label(row["net"], end, 180 if ref[0] == "J" else 0)
    for txt, x, y in [
        (channel + " source-defined divider; conditional input range", 95, 65),
        (
            (
                "Independent catch supply; no connection to bleed midpoint"
                if sensor == "catch"
                else "Isolated " + channel + " measurement; see input rating hold"
            ),
            210,
            26,
        ),
        ("8.1 mm TI HV land pattern; PCB insulation rule remains provisional", 210, 165),
        ("High-side DC/DC bypass", 120, 118),
        ("High-side LDO bypass", 190, 118),
        ("Low-side supply / DC/DC", 310, 118),
        ("NOT FABRICATION OR POWERED TEST RELEASE", 210, 178),
    ]:
        objects.append(
            f'(text {q(txt)}(at {x} {y} 0)(effects(font(size 1.27 1.27)))(uuid "{uid(txt)}"))'
        )
    for i, (net, xy) in enumerate([("POD_3V3", (330.2, 45.72)), ("AUX_0V", (355.6, 45.72))], 1):
        ref = f"#FLG0{i}"
        x, y = xy
        label(net, xy)
        objects.append(
            f'(symbol(lib_id "Sensor:PWR_FLAG")(at {x} {y} 0)(unit 1)(in_bom no)(on_board no)(dnp no)(uuid "{uid(ref)}")(property "Reference" "{ref}"(at {x} {y} 0)(effects(font(size 1 1)) hide))(property "Value" "PWR_FLAG"(at {x} {y - 5.08} 0)(effects(font(size 1 1))))(pin "1"(uuid "{uid(ref + "pin")}"))(instances(project "{sensor}-sensor"(path "/{uid(sensor + "-root")}"(reference "{ref}")(unit 1)))))'
        )
    embedded = "\n".join(
        v.replace('(symbol "' + n + '"', '(symbol "Sensor:' + n + '"', 1) for n, v in raw.items()
    )
    (DST / "sensor.kicad_sym").write_text(
        '(kicad_symbol_lib(version 20250114)(generator "temper")' + "".join(raw.values()) + ")\n"
    )
    (DST / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Sensor") (type "KiCad") (uri "${KIPRJMOD}/sensor.kicad_sym") (options "") (descr "Vendored official KiCad symbols")))\n'
    )
    (DST / (sensor + "-sensor.kicad_sch")).write_text(
        f'(kicad_sch(version 20250114)(generator "temper")(uuid "{uid(sensor + "-root")}")(paper "A3")(title_block(title "Temper isolated {sensor} voltage sensor")(date "2026-10-05")(rev "R5 candidate"))(lib_symbols {embedded})'
        + "".join(objects)
        + '(sheet_instances(path "/"(page "1"))))\n'
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "catch")
