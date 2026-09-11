#!/usr/bin/env python3
"""Replay flat CurrentSenseUnit schematic closure and native ERC.

This is a filesystem/KiCad transport wrapper. It copies no PCB data into the
output, emits the local source symbol library/table, then checks ERC and the
existing schematic connectivity oracle. Optional PCB parity is attempted only
when ``--board`` is supplied; its raw command result is recorded unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from native_report import load_kicad_report, require_success


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(repo: Path, source: Path, template: Path, output: Path, receipt: Path, board: Path | None) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite replay output: {output}")
    output.mkdir(parents=True)
    for name in ("fp-lib-table", "section.kicad_pro"):
        candidate = template / name
        if candidate.is_file():
            shutil.copyfile(candidate, output / name)
    libraries = template / "candidate-libs"
    if libraries.is_dir():
        shutil.copytree(libraries, output / "candidate-libs")

    closer = Path(__file__).with_name("close_current_sense_schematic_erc.py")
    subprocess.run(
        ["python3", str(closer), "--repo", str(repo), "--source", str(source),
         "--output", str(output), "--receipt", str(output / "closure-receipt.json")],
        check=True,
    )

    erc = output / "erc.json"
    erc_result = subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-all", "--format", "json",
         "-o", str(erc), str(output / "section.kicad_sch")],
        capture_output=True,
        text=True,
        check=False,
    )
    require_success("ERC", erc_result.returncode, erc_result.stdout, erc_result.stderr)
    erc_data = load_kicad_report(erc, "erc")
    violations = [v for sheet in erc_data.get("sheets", []) for v in sheet.get("violations", [])]

    import sys
    sys.path.insert(0, str(repo / "scripts"))
    import gen_schematics as donor  # type: ignore[import-not-found]

    source_netlist = donor.parse_netlist(source / "build/default.net")
    donor.apply_bom_values(source_netlist, donor.load_bom_values(source / "build/default.csv"))
    modules = {component.sheet_module for component in source_netlist.components.values()}
    layout = donor.SchematicLayout(
        root_sheet="section.kicad_sch",
        sheets=("CurrentSense",),
        sheet_files={"CurrentSense": "section.kicad_sch"},
        module_to_sheet=dict.fromkeys(modules, "CurrentSense"),
        title="Standalone Current-Sensing Unit",
        sheet_description="Generated from CurrentSenseUnit Atopile source",
        flat=True,
    )
    oracle_pass = donor.oracle_verify(source / "build/default.net", output, layout=layout)

    parity = None
    if board is not None:
        parity_report = output / "drc-parity.json"
        parity_result = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--schematic-parity", "--all-track-errors",
             "--severity-all", "--format", "json", "-o", str(parity_report), str(board)],
            capture_output=True,
            text=True,
            check=False,
        )
        require_success("DRC/parity", parity_result.returncode,
                        parity_result.stdout, parity_result.stderr)
        load_kicad_report(parity_report, "drc")
        parity = {
            "returncode": parity_result.returncode,
            "status": "report-generated" if parity_report.is_file() else "command-failed",
            "stdout": parity_result.stdout,
            "stderr": parity_result.stderr,
            "report": str(parity_report) if parity_report.is_file() else None,
        }

    result = {
        "schema": "zapote.current-sense.schematic-replay-receipt.v1",
        "status": "erc-and-schematic-oracle-pass" if not violations and oracle_pass else "failed",
        "source_netlist_sha256": sha256(source / "build/default.net"),
        "schematic_sha256": sha256(output / "section.kicad_sch"),
        "erc_returncode": erc_result.returncode,
        "erc_violations": len(violations),
        "schematic_oracle": "PASS" if oracle_pass else "FAIL",
        "pcb_parity": parity,
        "pcb_touched": False,
        "physical_tests": "NOT RUN",
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--board", type=Path)
    args = parser.parse_args()
    run(args.repo.resolve(), args.source.resolve(), args.template.resolve(), args.output.resolve(), args.receipt.resolve(), args.board.resolve() if args.board else None)


if __name__ == "__main__":
    main()
