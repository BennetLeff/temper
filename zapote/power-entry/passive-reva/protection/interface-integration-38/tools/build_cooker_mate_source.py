"""Freeze the cooker-board Rev38 mate as a separate Atopile source export."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[4]
DERIVATIVE = Path(
    "zapote/power-entry/passive-reva/protection/"
    "interface-integration-38/cooker-mate/elec/src"
)
ENTRY_FILE = str(DERIVATIVE / "cooker_mate.ato")
ENTRY_MODULE = "CookerMate38"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_cooker_sources(output: Path) -> None:
    # This worktree can contain unrelated untracked experimental Atopile files.
    # Freeze the canonical cooker's tracked source bytes, including local edits.
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "elec/src"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    for name in tracked.split(b"\0"):
        if not name:
            continue
        relative = Path(name.decode("utf-8"))
        if relative.suffix != ".ato":
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, destination)


def build(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite cooker source build: {output}")
    sys.path.insert(0, str(REPO / "harness-lab"))
    import block_source  # type: ignore[import-not-found]

    copy_cooker_sources(output)
    shutil.copytree(ROOT / "cooker-mate/elec/src", output / DERIVATIVE)
    (output / "ato.yaml").write_text(
        "ato-version: 0.2.69\nbuilds:\n"
        f"  default:\n    entry: {ENTRY_FILE}:{ENTRY_MODULE}\n",
        encoding="utf-8",
    )
    proc = block_source.run_atopile_build(output, ENTRY_FILE, ENTRY_MODULE)
    (output / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    receipt = {
        "schema": "temper.power-entry.cooker-mate.source-build.v1",
        "status": "compiled" if proc.returncode == 0 else "compiler-failed",
        "entry": f"{ENTRY_FILE}:{ENTRY_MODULE}",
        "returncode": proc.returncode,
        "build_report_failed": "FAILED" in proc.stdout,
        "adapter_sha256": sha256(Path(__file__).resolve()),
        "source_hashes": block_source.workspace_hashes(output),
    }
    receipt_path = output / "build-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    block_source.gate_build(proc)
    net_path = output / "build/default.net"
    bom_path = output / "build/default.csv"
    if not net_path.is_file() or not bom_path.is_file():
        raise FileNotFoundError("cooker mate compiler omitted netlist or BOM")
    export_path = output / "resolved-components.json"
    block_source.run_resolved_export(output, ENTRY_FILE, ENTRY_MODULE, export_path)
    receipt["status"] = "compiled-and-exported"
    receipt["netlist_sha256"] = sha256(net_path)
    receipt["bom_sha256"] = sha256(bom_path)
    receipt["export_sha256"] = sha256(export_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": receipt["status"], "output": str(output)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New cooker source snapshot directory")
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
