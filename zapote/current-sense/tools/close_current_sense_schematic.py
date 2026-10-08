#!/usr/bin/env python3
"""Close a flat source-derived schematic against its compiled netlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(repo: Path, source: Path, schematic_dir: Path, receipt_path: Path) -> None:
    sys.path.insert(0, str(repo / "scripts"))
    import gen_schematics as schematics  # type: ignore[import-not-found]

    netlist_path = source / "build" / "default.net"
    schematic_path = schematic_dir / "section.kicad_sch"
    if not netlist_path.is_file() or not schematic_path.is_file():
        raise FileNotFoundError("source netlist and flat section.kicad_sch are required")
    source_netlist = schematics.parse_netlist(netlist_path)
    layout_path = schematic_dir / "schematic_layout.json"
    if layout_path.is_file():
        layout = schematics._load_layout_config(layout_path)
    else:
        modules = {component.sheet_module for component in source_netlist.components.values()}
        layout = schematics.SchematicLayout(
            root_sheet="section.kicad_sch",
            sheets=("CurrentSense",),
            sheet_files={"CurrentSense": "section.kicad_sch"},
            module_to_sheet=dict.fromkeys(modules, "CurrentSense"),
            title="Standalone Current-Sensing Unit",
            sheet_description="Generated from CurrentSenseUnit Atopile source",
            flat=True,
        )
    if not layout.flat:
        raise ValueError("schematic closure requires a flat standalone layout")
    text = schematic_path.read_text(encoding="utf-8")
    if "(hierarchical_label " in text:
        raise ValueError("flat standalone schematic contains hierarchical labels")
    if "(global_label " not in text:
        raise ValueError("flat standalone schematic contains no global labels")
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as temporary:
        exported_path = Path(temporary.name)
    try:
        schematics._export_netlist(schematic_dir, exported_path, layout=layout)
        generated_netlist = schematics.parse_netlist(exported_path)
    finally:
        exported_path.unlink(missing_ok=True)
    source_refs = set(source_netlist.components)
    generated_refs = set(generated_netlist.components)
    if source_refs != generated_refs:
        raise ValueError(
            "schematic/source component census differs: "
            + json.dumps(
                {
                    "missing": sorted(source_refs - generated_refs),
                    "extra": sorted(generated_refs - source_refs),
                }
            )
        )
    if not schematics.oracle_verify(netlist_path, schematic_dir, layout=layout):
        raise ValueError("generated schematic connectivity does not match source netlist")
    receipt = {
        "schema": "zapote.current-sense.schematic-closure-receipt.v1",
        "status": "schematic-closed",
        "source_netlist_sha256": sha256(netlist_path),
        "schematic_sha256": sha256(schematic_path),
        "layout_sha256": sha256(layout_path) if layout_path.is_file() else None,
        "component_count": len(source_refs),
        "flat": True,
        "global_labels": text.count("(global_label "),
        "native_netlist_export": "kicad-cli sch export netlist",
        "physical_tests": "NOT RUN",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--schematic-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    close(args.repo.resolve(), args.source.resolve(), args.schematic_dir.resolve(), args.receipt.resolve())


if __name__ == "__main__":
    main()
