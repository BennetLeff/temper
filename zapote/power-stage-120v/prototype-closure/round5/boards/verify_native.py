"""Independent native KiCad export oracle for source-derived board pin tables.

Run with KiCad's Python. This verifies emitted artifacts; it is not circuit or
placement authority. Negative controls prove missing/wrong pins are rejected.
"""

from __future__ import annotations

import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/boards"


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def normalize(net):
    return "NC" if net.startswith("unconnected-(") else net.lstrip("/")


def compare(expected, actual):
    assert expected == actual, {
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "wrong": {
            k: [expected[k], actual[k]]
            for k in expected.keys() & actual.keys()
            if expected[k] != actual[k]
        },
    }


def main():
    results = {}
    for name in ["catch", "bus", "line", "pre", "out", "tank", "iproof", "iline", "central"]:
        central = name == "central"
        table = HERE / ("central/generated/pins.tsv" if central else f"{name}-pins.tsv")
        board_path = HERE / (
            "central/native/supervisor.kicad_pcb"
            if central
            else f"native/{name}-sensor/{name}-sensor.kicad_pcb"
        )
        pin_rows = rows(table)
        expected = {(r["reference"], r["pin"]): r["net"] for r in pin_rows}
        schematic = ET.parse(OUT / f"{name}-netlist.xml").getroot()
        exported = {
            (node.attrib["ref"], node.attrib["pin"]): normalize(net.attrib["name"])
            for net in schematic.findall("./nets/net")
            for node in net.findall("node")
            if not node.attrib["ref"].startswith("#")
        }
        compare(expected, exported)
        board = pcbnew.LoadBoard(str(board_path))
        actual = {
            (fp.GetReference(), pad.GetNumber()): normalize(pad.GetNetname())
            for fp in board.GetFootprints()
            for pad in fp.Pads()
            if pad.GetNumber()
        }
        compare(expected, actual)
        footprints = {
            fp.GetReference(): str(fp.GetFPID().GetLibNickname())
            + ":"
            + str(fp.GetFPID().GetLibItemName())
            for fp in board.GetFootprints()
            if not fp.GetReference().startswith("H")
        }
        compare({r["reference"]: r["footprint"] for r in pin_rows}, footprints)
        key = next(iter(expected))
        negatives = [dict(exported), dict(exported)]
        negatives[0].pop(key)
        negatives[1][key] = "WRONG_NEGATIVE_CONTROL_NET"
        for mutated in negatives:
            try:
                compare(expected, mutated)
            except AssertionError:
                pass
            else:
                raise AssertionError("Native pin oracle failed its negative control")
        results[name] = {
            "parts": len(footprints),
            "pins": len(expected),
            "netlist_exact": True,
            "board_pins_exact": True,
            "footprint_identity_exact": True,
            "missing_pin_negative_control": True,
            "wrong_net_negative_control": True,
            "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
            "pins_sha256": hashlib.sha256(table.read_bytes()).hexdigest(),
        }
    source = {
        (r["reference"], r["pin"]): r["net"]
        for r in rows(HERE / "../../round4/supervisor/generated/pins.tsv")
    }
    preserved = {}
    for row in rows(HERE / "central/generated/pins.tsv"):
        key = (row["source_ref"], row["pin"])
        if key in source:
            preserved[key] = row["net"]
    for row in rows(HERE / "external-pins.tsv"):
        key = (row["reference"], row["pin"])
        assert key not in preserved
        preserved[key] = row["net"]
    eco = json.loads((HERE / "power-eco.json").read_text())
    revised_source = dict(source)
    for change in eco["net_changes"]:
        key = (change["source_ref"], change["pin"])
        assert revised_source[key] == change["before"], change
        revised_source[key] = change["after"]
    compare(revised_source, preserved)
    for sensor in ["catch", "bus", "line", "pre", "out", "tank", "iproof", "iline"]:
        refmap = json.loads((HERE / f"{sensor}-ref-map.json").read_text())
        actual = {(r["reference"], r["pin"]): r["net"] for r in rows(HERE / f"{sensor}-pins.tsv")}
        for (ref, pin), net in source.items():
            if ref in refmap:
                expected_net = "VPRE_DIV3" if (sensor, ref, pin) == ("pre", "R_VPREH3", "2") else net
                assert actual[(refmap[ref], pin)] == expected_net, (sensor, ref, pin)
    central_pins = {
        (r["source_ref"], r["pin"]): r["net"] for r in rows(HERE / "central/generated/pins.tsv")
    }
    harnesses = {
        "catch": "J_CATCH_POD",
        "bus": "J_VBUS_POD",
        "line": "J_VLINE_POD",
        "pre": "J_VPRE_POD",
        "out": "J_VOUT_POD",
        "tank": "J_VTANK_POD",
        "iproof": "J_IPROOF_BURDEN",
        "iline": "J_ILINE_BURDEN",
    }
    for sensor, connector in harnesses.items():
        remote_ref = "J1" if sensor in {"iproof", "iline"} else "J2"
        remote = {
            r["pin"]: r["net"]
            for r in rows(HERE / f"{sensor}-pins.tsv")
            if r["reference"] == remote_ref
        }
        central = {pin: net for (ref, pin), net in central_pins.items() if ref == connector}
        compare(central, remote)
    results["harness_parity"] = {"eight_straight_through_sensor_harnesses_exact": True}
    results["source_partition"] = {
        "original_pins": len(source),
        "all_original_pin_identities_accounted_for": True,
        "explicit_power_eco_net_changes": len(eco["net_changes"]),
        "all_other_original_nets_preserved": True,
        "all_sensor_nets_except_explicit_vpre_ladder_extension_preserved": True,
        "vpre_range_ratio": 801,
    }
    reports = {}
    for name in ["central", "catch", "bus", "line", "pre", "out", "tank", "iproof", "iline"]:
        samples = []
        for sample in [1, 2, 3]:
            report = json.loads((OUT / f"{name}-drc-{sample}.json").read_text())
            counts = [
                len(report["violations"]),
                len(report["unconnected_items"]),
                len(report.get("schematic_parity", [])),
            ]
            assert counts == [0, 0, 0], (name, sample, counts)
            samples.append(counts)
        erc = json.loads((OUT / f"{name}-erc.json").read_text())
        violations = [v for sheet in erc["sheets"] for v in sheet["violations"]]
        assert all(v["severity"] != "error" for v in violations), (name, violations)
        kinds = dict(Counter(v["type"] for v in violations))
        # Five ISO1211 SUB pins terminate in deliberately floating thermal islands.
        assert kinds == ({"ground_pin_not_ground": 9, "isolated_pin_label": 5} if name == "central" else {}), (name, kinds)
        reports[name] = {"native_drc_samples": samples, "erc_violations": kinds}
    (OUT / "verification-summary.json").write_text(json.dumps(reports, indent=2) + "\n")
    (OUT / "native-pin-oracle.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
