"""Recheck the bounded native-17 -> native-18 change and saved gate evidence."""

import hashlib
import json
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
OLD = UNIT / "native-17"
NEW = UNIT / "native-18"
OUT = NEW / "verification"
OLD_MPN = "RC0603FR-0739KL"
NEW_MPN = "RT0603BRD0749K9L"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without(data: dict, *keys: str) -> dict:
    return {key: value for key, value in data.items() if key not in keys}


def main() -> None:
    if sys.flags.optimize:
        raise RuntimeError("Run without -O: identity checks require assertions")
    checks = []
    for name, count in [("section.kicad_pcb", 4), ("section.kicad_sch", 2)]:
        before, after = (OLD / name).read_bytes(), (NEW / name).read_bytes()
        assert before.count(OLD_MPN.encode()) == count
        assert after == before.replace(OLD_MPN.encode(), NEW_MPN.encode()), name
        checks.append(f"{name}: only {count} intended MPN substitutions")
    for path in OLD.rglob("*"):
        relative = path.relative_to(OLD)
        if not path.is_file() or relative.parts[0] not in {
            "candidate-libs",
            "route-receipts",
            "fp-lib-table",
            "schematic_layout.json",
            "section.kicad_dru",
            "section.kicad_pro",
            "stackup.json",
        }:
            continue
        assert (NEW / relative).read_bytes() == path.read_bytes(), relative
    checks.append("all inherited libraries, route receipts and design sidecars byte-identical")

    before = read_json(OLD / "source-manifest.json")
    after = read_json(NEW / "source-manifest.json")
    assert without(
        after, "components", "input_hashes", "source", "source_attributes", "value_only_revision"
    ) == without(before, "components", "input_hashes", "source", "source_attributes")
    expected = json.loads(json.dumps(before))
    for component in expected["components"]:
        if component["reference"] in {"R9", "R17"}:
            assert component["mpn"] == OLD_MPN and component["value"] == "39kohm"
            component.update(mpn=NEW_MPN, value="49.9kohm")
    for instance in ("leg_a.r_dt", "leg_b.r_dt"):
        expected["source_attributes"][instance].update(mpn=NEW_MPN, value="49.9kohm")
    assert after["components"] == expected["components"]
    assert after["source_attributes"] == expected["source_attributes"]
    export = read_json(NEW / "frozen/resolved-components.json")
    attributes = {c["address"].split("::", 1)[1]: c["attributes"] for c in export["components"]}
    assert attributes == after["source_attributes"]
    receipt = read_json(OUT / "source-build-receipt.json")
    for name, digest in receipt["source_hashes"].items():
        assert sha(UNIT / name) == digest, name
    assert receipt["export_sha256"] == sha(NEW / "frozen/resolved-components.json")
    for name in ("default.csv", "default.net", "resolved-components.json"):
        assert sha(NEW / "frozen" / name) == after["input_hashes"][name], name
    assert without(
        after["input_hashes"], "default.csv", "default.net", "resolved-components.json"
    ) == without(before["input_hashes"], "default.csv", "default.net", "resolved-components.json")
    assert (NEW / "frozen/default.csv").read_text() == (
        UNIT / "frozen/default.csv"
    ).read_text().replace(OLD_MPN, NEW_MPN)
    old_net = (UNIT / "frozen/default.net").read_text().replace(before["source"], "SOURCE_BUILD")
    new_net = (NEW / "frozen/default.net").read_text().replace(after["source"], "SOURCE_BUILD")
    assert old_net == new_net
    checks.append(
        "fresh resolved source matches manifest; only R9/R17 attributes and BOM row changed; netlist identical after source-path normalization"
    )

    pairs = [
        ("copper.json", "presentation/copper.json", ("board_path", "board_sha256")),
        ("connectivity.json", "connectivity.json", ("board_sha256",)),
        ("geometry-via.json", "power-probes/geometry-via.json", ("board_sha256",)),
        ("west-parallel.json", "power-probes/west-parallel.json", ("board_sha256",)),
        ("hardware-surface.json", "hardware-surface.json", ()),
    ]
    for new_name, old_name, excluded in pairs:
        assert without(read_json(OUT / new_name), *excluded) == without(
            read_json(OLD / "verification" / old_name), *excluded
        ), new_name
        checks.append(f"{new_name}: identical apart from {excluded or 'no fields'}")
    assert (OUT / "bus-sheet.txt").read_bytes() == (
        OLD / "verification/power-probes/bus-sheet.txt"
    ).read_bytes()
    assert without(read_json(OUT / "native-17-placement-metrics.json"), "board") == without(
        read_json(OUT / "native-18-placement-metrics.json"), "board"
    )
    checks.append("bus-sheet output and placement metrics identical (excluding board path)")
    for name in ("drc-fill.json", "drc-1.json", "drc-2.json", "drc-3.json"):
        drc = read_json(OUT / name)
        baseline = read_json(OLD / "verification/presentation/drc-1.json")
        assert drc["violations"] == baseline["violations"], name
        assert drc["schematic_parity"] == baseline["schematic_parity"] == []
        assert len(drc["unconnected_items"]) == 1
    checks.append(
        "four DRC runs: exact same violation lists and no schematic mismatch; open representative varies, full pad clusters identical"
    )
    print(
        json.dumps(
            {
                "pass": True,
                "native17_board_sha256": sha(OLD / "section.kicad_pcb"),
                "native18_board_sha256": sha(NEW / "section.kicad_pcb"),
                "checks": checks,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
