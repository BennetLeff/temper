"""Derive same-topology sensor board data from pinned round4 component pins.

No electrical values are invented; schematic component rows come from the Rust
circuit capture. Layout transforms preserve named pad endpoints and are checked
by KiCad on every emitted board.
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "round4/supervisor/generated/pins.tsv"


def main():
    rows = list(csv.DictReader(SOURCE.open(), delimiter="\t"))
    base = json.loads((HERE / "catch-layout.json").read_text())
    for channel, name, count in [
        ("VBUS", "bus", 8),
        ("VLINE", "line", 4),
        ("VPRE", "pre", 4),
        ("VOUT", "out", 4),
        ("VTANK", "tank", 12),
    ]:
        selected = [dict(r) for r in rows if r["sheet"] == channel]
        refs = {}
        seq = {}
        for r in selected:
            old = r["reference"]
            if old not in refs:
                kind = old[0]
                seq[kind] = seq.get(kind, 0) + 1
                refs[old] = kind + str(seq[kind])
            r["reference"] = refs[old]
        # VLINE/VPRE/VOUT have no board-edge HV connector in round4.
        hi, low = {
            "VBUS": ("BUS_P", "HV_RET"),
            "VLINE": ("L_AUX", "N_AUX"),
            "VPRE": ("L_SER", "L_PRE"),
            "VOUT": ("L_PRE", "N_PRE"),
            "VTANK": ("RES_A", "SW_B"),
        }[channel]
        if not any(r["reference"] == "J1" for r in selected):
            for i, n in enumerate([hi, low], 1):
                selected.append(
                    {
                        "reference": "J1",
                        "mpn": "HV_SOLDER_LEADS_WITH_EXTERNAL_STRAIN_RELIEF",
                        "footprint": "Round5:HV_WirePair_P25",
                        "sheet": channel,
                        "pin": str(i),
                        "function": str(i),
                        "type": "passive",
                        "net": n,
                    }
                )
        for r in selected:
            if r["reference"] == "J1":
                r["mpn"] = "HV_SOLDER_LEADS_WITH_EXTERNAL_STRAIN_RELIEF"
                r["footprint"] = "Round5:HV_WirePair_P25"
            if r["reference"] == "U1":
                r["footprint"] = "Round5:AMC3330_DWE_HV"
        for i, n in enumerate(
            ["POD_3V3", "AUX_0V", channel + "_P", channel + "_N", channel + "_DIAG_N", "AUX_0V"], 1
        ):
            selected.append(
                {
                    "reference": "J2",
                    "mpn": "B6B-XH-A(LF)(SN)",
                    "footprint": "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
                    "sheet": channel,
                    "pin": str(i),
                    "function": str(i),
                    "type": "passive",
                    "net": n,
                }
            )
        for r in selected:
            ref = r["reference"]
            r["value"] = (
                "249kR 0.1%"
                if ref in {f"R{i}" for i in range(1, count + 1)}
                else {
                    "VBUS": "2.49kR",
                    "VLINE": "4.02kR",
                    "VPRE": "4.02kR",
                    "VOUT": "4.02kR",
                    "VTANK": "1kR",
                }[channel]
                + " 0.1%"
                if ref == f"R{count + 1}"
                else r["mpn"].split()[0]
                if ref[0] in "RC"
                else "HV leads"
                if ref == "J1"
                else "B6B-XH-A"
                if ref == "J2"
                else r["mpn"]
            )
        with (HERE / (name + "-pins.tsv")).open("w") as f:
            w = csv.DictWriter(f, fieldnames=selected[0], delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(selected)
        spec = copy.deepcopy(base)

        def refmap(ref, count=count):
            a, *rest = ref.split(".")
            a = (
                f"R{count + 1}"
                if a == "R9"
                else f"R{count + 2}"
                if a == "R10"
                else f"R{count}"
                if a == "R8" and count < 8
                else a
            )
            return ".".join([a] + rest)

        def netmap(n, channel=channel, hi=hi, low=low):
            return n.replace("VCATCH", channel).replace("CATCH_P", hi).replace("HV_RET", low)

        def xy(pt, count=count):
            if count != 12:
                return pt
            x, y = pt
            return [x + 72, y + 12]

        spec["placement"] = {
            refmap(ref): xy(p[:2]) + p[2:]
            for ref, p in spec["placement"].items()
            if not (ref.startswith("R") and ref[1:].isdigit() and 1 <= int(ref[1:]) <= 8)
        }
        for i in range(1, count + 1):
            if count == 12:
                spec["placement"][f"R{i}"] = [7 + 8 * (i - 1), 8, 0]
            else:
                spec["placement"][f"R{i}"] = base["placement"][f"R{i}"]
        spec["placement"]["J1"] = [3, 3, 0]
        routes = []
        for net, layer, pts in base["routes"]:
            if net.startswith("VCATCH_DIV"):
                continue
            if net == "CATCH_P":
                routes.append([hi, "F", ["J1.1", [5.5375, 3], "R1.1"]])
                continue
            converted = []
            for pt in pts:
                if isinstance(pt, str):
                    if pt == "R8.2":
                        converted.append(f"R{count}.2")
                    else:
                        converted.append(refmap(pt))
                else:
                    converted.append(xy(pt))
            if count == 4 and pts[0] == "R8.2":
                converted = [f"R{count}.2", [25.4625, 10], [4.5375, 10]] + converted[1:]
            if count == 12 and pts[0] == "R8.2":
                converted = [f"R{count}.2", [96.4625, 20], [89.5375, 20], f"R{count + 1}.1"]
            routes.append([netmap(net), layer, converted])
        for i in range(1, count):
            routes.append([f"{channel}_DIV{i - 1}", "F", [f"R{i}.2", f"R{i + 1}.1"]])
        spec["routes"] = routes
        spec["vias"] = [[netmap(n)] + xy([x, y]) for n, x, y in base["vias"]]
        spec["zones"] = [[netmap(n), [xy(pt) for pt in poly]] for n, poly in base["zones"]]
        if count == 12:
            spec["size_mm"] = [135, 55, 1.6]
            spec["hv_pitch_mm"] = 47
            spec["mounts"] = [[17, 52, 2.7], [132, 52, 2.7], [132, 3, 2.7]]
            # Keep the return near the sensing IC; its separate bottom strap reaches J1.
            spec["zones"][0][1] = [[88, 24], [101, 24], [101, 51], [2, 51], [2, 48], [88, 48]]
        spec["hv_nets"] = [hi, low, channel + "_TAP", channel + "_DCDC_H", channel + "_HLDO"] + [
            f"{channel}_DIV{i}" for i in range(count - 1)
        ]
        spec["channel"] = channel
        spec["source_sheet"] = channel
        (HERE / (name + "-layout.json")).write_text(json.dumps(spec, indent=2) + "\n")
        (HERE / (name + "-ref-map.json")).write_text(json.dumps(refs, indent=2) + "\n")


if __name__ == "__main__":
    main()
