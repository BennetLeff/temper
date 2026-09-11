#!/usr/bin/env python3
"""Run native KiCad ERC and DRC/parity checks for a current-sense candidate.

The reports and exact argv are retained for review.  This helper does not
interpret findings as an engineering acceptance verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from native_report import load_kicad_report, require_success


def _config(output: Path) -> dict[str, str]:
    config = output / "kicad-config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "kicad_common.json").write_text(
        '{"environment":{"vars":{}}}\n', encoding="utf-8"
    )
    (config / "kicad_advanced").write_text(
        "MaximumThreads=1\n", encoding="utf-8"
    )
    return {**os.environ, "KICAD_CONFIG_HOME": str(config)}


def _run(command: list[str], report: Path, output: Path, env: dict[str, str]) -> dict:
    proc = subprocess.run(
        command, capture_output=True, text=True, timeout=600, env=env, check=False
    )
    (output / f"{report.stem}-command.json").write_text(
        json.dumps(
            {
                "argv": command,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    require_success(report.stem, proc.returncode, proc.stdout, proc.stderr)
    if not report.is_file():
        raise RuntimeError(
            f"KiCad produced no {report.name} (returncode={proc.returncode})"
        )
    return load_kicad_report(report, "erc" if report.stem == "erc" else "drc")


def run(board: Path, schematic: Path, output: Path, cli: str) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite native check output: {output}")
    output.mkdir(parents=True)
    env = _config(output)
    erc = _run(
        [
            cli,
            "sch",
            "erc",
            "--severity-all",
            "--format",
            "json",
            "--output",
            str(output / "erc.json"),
            str(schematic),
        ],
        output / "erc.json",
        output,
        env,
    )
    drc = _run(
        [
            cli,
            "pcb",
            "drc",
            "--schematic-parity",
            "--all-track-errors",
            "--severity-all",
            "--format",
            "json",
            "--output",
            str(output / "drc.json"),
            str(board),
        ],
        output / "drc.json",
        output,
        env,
    )
    receipt = {
        "schema": "zapote.current-sense.native-check-receipt.v1",
        "status": "reports-generated",
        "scope": "native transport only; findings require independent review",
        "board": str(board),
        "schematic": str(schematic),
        "erc_report": str(output / "erc.json"),
        "drc_report": str(output / "drc.json"),
        "erc_sheets": len(erc.get("sheets", [])),
        "drc_violations": len(drc.get("violations", [])),
        "drc_unconnected_items": len(drc.get("unconnected_items", [])),
        "drc_schematic_parity": len(drc.get("schematic_parity", [])),
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--schematic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kicad-cli", default="kicad-cli")
    args = parser.parse_args()
    run(args.board.resolve(), args.schematic.resolve(), args.output.resolve(), args.kicad_cli)


if __name__ == "__main__":
    main()
