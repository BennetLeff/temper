"""Freeze and compile the power-stage unit source for native export."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
ENTRY_FILE = "elec/src/power_stage_120v.ato"
ENTRY_MODULE = "PowerStage120V"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite source build: {output}")
    sys.path.insert(0, str(REPO / "harness-lab"))
    import block_source  # type: ignore[import-not-found]

    (output / "elec").mkdir(parents=True)
    shutil.copytree(ROOT / "elec" / "src", output / "elec" / "src")
    (output / "ato.yaml").write_text(
        "ato-version: 0.2.69\nbuilds:\n"
        f"  default:\n    entry: {ENTRY_FILE}:{ENTRY_MODULE}\n",
        encoding="utf-8",
    )
    proc = block_source.run_atopile_build(output, ENTRY_FILE, ENTRY_MODULE)
    (output / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    receipt = {
        "schema": "temper.power-stage-120v.source-build.v1",
        "status": "compiled" if proc.returncode == 0 else "compiler-failed",
        "entry": f"{ENTRY_FILE}:{ENTRY_MODULE}",
        "returncode": proc.returncode,
        "build_report_failed": "FAILED" in proc.stdout,
        "source_hashes": block_source.workspace_hashes(output),
        "adapter_sha256": sha256(Path(__file__).resolve()),
    }
    receipt_path = output / "build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    block_source.gate_build(proc)
    export_path = output / "resolved-components.json"
    block_source.run_resolved_export(output, ENTRY_FILE, ENTRY_MODULE, export_path)
    receipt["status"] = "compiled-and-exported"
    receipt["export_sha256"] = sha256(export_path)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "output": str(output)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New source snapshot directory")
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
