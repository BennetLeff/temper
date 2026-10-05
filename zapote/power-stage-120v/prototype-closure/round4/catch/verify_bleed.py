"""Check KiCad-exported netlist against the two independent physical bleed chains."""

from __future__ import annotations

import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round4/catch"


def validate(xml: ET.Element) -> None:
    components = {c.attrib["ref"]: c.findtext("value") for c in xml.findall("./components/comp")}
    if set(components) != {f"R{i}" for i in range(1, 9)} | {f"J{i}" for i in range(1, 5)}:
        raise ValueError("Missing or extra components")
    if any(components[f"R{i}"] != "100k" for i in range(1, 9)):
        raise ValueError("Wrong bleed value")
    actual = {}
    for net in xml.findall("./nets/net"):
        nodes = {(node.attrib["ref"], node.attrib["pin"]) for node in net.findall("node")}
        if net.attrib["name"] in actual:
            raise ValueError("Duplicate net name")
        actual[net.attrib["name"]] = nodes
    expected = {}
    for branch, suffix, base, plus_j, minus_j in ((1, "A", 1, "J1", "J2"), (2, "B", 5, "J3", "J4")):
        expected[f"CATCH_P_{suffix}"] = {(plus_j, "1"), (f"R{base}", "1")}
        expected[f"HV_RET_{suffix}"] = {(minus_j, "1"), (f"R{base + 3}", "2")}
        for i in range(1, 4):
            expected[f"B{branch}_{i}"] = {(f"R{base + i - 1}", "2"), (f"R{base + i}", "1")}
    if actual != expected:
        raise ValueError("The exported circuit is not two separately wired four-resistor chains")


def main() -> None:
    destination = OUT / "bleed-verification.json"
    destination.write_text('{"status":"INCOMPLETE"}\n')
    source = OUT / "bleed-netlist.xml"
    xml = ET.parse(source).getroot()
    validate(xml)
    negative_results = {}
    for name in ("cross_connected_branch", "wrong_resistance", "missing_component"):
        altered = copy.deepcopy(xml)
        if name == "cross_connected_branch":
            node = altered.find("./nets/net/node")
            if node is None:
                raise ValueError("Empty source netlist")
            node.set("ref", "J9")
        elif name == "wrong_resistance":
            node = altered.find("./components/comp[@ref='R1']/value")
            if node is None:
                raise ValueError("Missing R1")
            node.text = "10k"
        else:
            components = altered.find("components")
            if components is None:
                raise ValueError("Missing components")
            components.remove(components[0])
        try:
            validate(altered)
        except ValueError:
            negative_results[name] = "REJECTED"
        else:
            raise ValueError(f"Negative control accepted: {name}")
    inputs = [
        source,
        HERE / "native/catch-bleed.kicad_pcb",
        HERE / "native/catch-bleed.kicad_sch",
        HERE / "native/catch-bleed.kicad_dru",
    ]
    destination.write_text(
        json.dumps(
            {
                "status": "PASS_EXPORTED_CONNECTIVITY_ONLY",
                "component_count": 12,
                "resistors": 8,
                "separate_400k_branches": 2,
                "negative_controls": negative_results,
                "inputs": [
                    {
                        "path": str(p.relative_to(ROOT)),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in inputs
                ],
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
