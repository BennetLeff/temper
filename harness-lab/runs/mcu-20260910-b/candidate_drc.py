"""Direct kicad-cli DRC (with schematic parity) on a generated candidate dir.

Used as a fast generator-level check before the apparatus construction. Mirrors
the file layout native_check.py assembles for the parity/ERC step.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    work = args.out.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copyfile(
        candidate / "mcu_candidate.kicad_pcb", work / "candidate.kicad_pcb"
    )
    shutil.copyfile(
        candidate / "mcu_candidate.kicad_sch", work / "candidate.kicad_sch"
    )
    shutil.copyfile(
        candidate / "mcu_candidate.kicad_pro", work / "candidate.kicad_pro"
    )
    shutil.copyfile(candidate / "fp-lib-table", work / "fp-lib-table")
    shutil.copytree(candidate / "candidate-libs", work / "candidate-libs")
    cfg = work / "kicad-config"
    cfg.mkdir()
    (cfg / "kicad_common.json").write_text('{"environment":{"vars":{}}}\n')
    (cfg / "kicad_advanced").write_text("MaximumThreads=1\n")
    env = {**os.environ, "KICAD_CONFIG_HOME": str(cfg)}
    drc_path = work / "drc.json"
    proc = subprocess.run(
        [
            "kicad-cli", "pcb", "drc", "--format", "json",
            "--all-track-errors", "--schematic-parity", "--severity-all",
            "--output", str(drc_path), str(work / "candidate.kicad_pcb"),
        ],
        capture_output=True, text=True, env=env, timeout=300,
    )
    erc_path = work / "erc.json"
    erc_proc = subprocess.run(
        [
            "kicad-cli", "sch", "erc", "--format", "json", "--severity-all",
            "--output", str(erc_path), str(work / "candidate.kicad_sch"),
        ],
        capture_output=True, text=True, env=env, timeout=300,
    )
    drc = json.loads(drc_path.read_text())
    erc = json.loads(erc_path.read_text()) if erc_path.is_file() else {}
    erc_violations = [v for sheet in erc.get("sheets", []) for v in sheet.get("violations", [])]
    summary = {
        "candidate": str(candidate.relative_to(REPO)),
        "board": "mcu_candidate.kicad_pcb",
        "kicad_cli": subprocess.run(
            ["kicad-cli", "version"], capture_output=True, text=True
        ).stdout.strip(),
        "drc_returncode": proc.returncode,
        "drc_violations": len(drc["violations"]),
        "drc_unconnected": len(drc["unconnected_items"]),
        "schematic_parity": len(drc["schematic_parity"]),
        "erc_returncode": erc_proc.returncode,
        "erc_violations": len(erc_violations),
        "parity": drc["schematic_parity"],
        "erc": erc_violations,
    }
    (work / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("parity", "erc")}, sort_keys=True))


if __name__ == "__main__":
    main()
