#!/usr/bin/env python3
"""Inspect the frozen cooker-mate source before strict native projection.

This is a diagnostic adapter around the existing netlist and footprint
readers. It does not create or qualify a PCB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

MATE = Path(__file__).resolve().parent
INTEGRATION = MATE.parent
REPO = INTEGRATION.parents[4]
sys.path[:0] = [str(REPO / "harness-lab"), str(REPO / "scripts")]
import block_source  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source(source: Path) -> tuple[Path, Path, dict]:
    receipt = json.loads((source / "build-receipt.json").read_text())
    netlist = source / "build/default.net"
    bom = source / "build/default.csv"
    for path, key in (
        (netlist, "netlist_sha256"),
        (bom, "bom_sha256"),
        (source / "resolved-components.json", "export_sha256"),
    ):
        if sha256(path) != receipt[key]:
            raise ValueError(f"frozen source hash mismatch: {path}")
    for relative, expected in receipt["source_hashes"].items():
        path = (source / relative).resolve()
        if not path.is_relative_to(source.resolve()) or sha256(path) != expected:
            raise ValueError(f"frozen source hash mismatch: {relative}")
    if receipt["status"] != "compiled-and-exported" or receipt["build_report_failed"]:
        raise ValueError("frozen source is not a successful compiler export")
    return netlist, bom, receipt


def footprint_source(nickname: str) -> Path:
    lib, separator, stem = nickname.partition(":")
    if not separator:
        lib, stem = "lib", lib
    local = REPO / "pcb/libs" / f"{lib}.pretty" / f"{stem}.kicad_mod"
    if local.is_file():
        return local
    if lib in {"lib", "temper", "Temper_RTD"}:
        raise FileNotFoundError(str(local))
    return block_source._stock_footprint_source(f"{lib}:{stem}", REPO)[0]


def probe(source: Path) -> dict:
    netlist, bom_path, receipt = verify_source(source)
    bridge = block_source.bridge_netlist(netlist, "CookerMate38")
    bom = block_source.parse_bom_mpn(bom_path.read_text())
    exported = json.loads((source / "resolved-components.json").read_text())
    by_path = {
        component["address"].split("::", 1)[1]: component["attributes"]
        for component in exported["components"]
    }
    if len(by_path) != len(bridge["components"]) or len(bom) != len(by_path):
        raise ValueError("compiled netlist, BOM, and resolved export counts disagree")

    connected: dict[str, set[str]] = defaultdict(set)
    for net in bridge["nets"]:
        for ref, pin in net["nodes"]:
            connected[ref].add(pin)

    missing_footprints = []
    missing_connected_pads = []
    footprint_hashes = {}
    esp_pad_numbers = []
    esp_footprint_hash = None
    for component in bridge["components"]:
        ref = component["reference"]
        path = component["instance_path"]
        nickname = component["footprint"]
        attributes = by_path[path]
        if bom[ref] != attributes["mpn"]:
            raise ValueError(f"BOM MPN differs from resolved source: {ref} {path}")
        if nickname.split(":")[-1] != attributes["footprint"].split(":")[-1]:
            raise ValueError(f"footprint differs from resolved source: {ref} {path}")
        try:
            footprint = footprint_source(nickname)
        except (FileNotFoundError, block_source.BlockSourceError):
            missing_footprints.append(
                {"reference": ref, "instance_path": path, "footprint": nickname}
            )
            continue
        footprint_hashes[nickname] = sha256(footprint)
        pads = {match.group(1) for match in block_source._PAD_RE.finditer(footprint.read_text())}
        absent = sorted(connected[ref] - pads)
        if absent:
            missing_connected_pads.append(
                {"reference": ref, "instance_path": path, "missing_pads": absent}
            )
        if path == "cooker.mcu.mcu":
            esp_pad_numbers = sorted(pads, key=int)
            esp_footprint_hash = footprint_hashes[nickname]

    return {
        "schema": "temper.power-entry.cooker-native-readiness.v1",
        "scope": "static source/footprint/pin probe; no native PCB or package qualification",
        "source": str(source.relative_to(REPO)),
        "netlist_sha256": receipt["netlist_sha256"],
        "component_count": len(bridge["components"]),
        "footprint_count": len(footprint_hashes),
        "missing_footprints": missing_footprints,
        "connected_pins_without_pads": missing_connected_pads,
        "esp_module_footprint_pad_numbers": esp_pad_numbers,
        "esp_module_footprint_sha256": esp_footprint_hash,
        "esp_module_missing_datasheet_ground_pads": sorted({"40", "41"} - set(esp_pad_numbers)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=INTEGRATION / "cooker-source-02")
    parser.add_argument("--output", type=Path, help="Write a new JSON report; never overwrite")
    args = parser.parse_args()
    report = probe(args.source.resolve())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
