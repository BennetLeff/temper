#!/usr/bin/env python3
"""Build and export the standalone CurrentSenseUnit source.

This is a bounded source transport wrapper.  It copies the current canonical
``elec/src`` tree into a fresh output directory, invokes the pinned Atopile
compiler and the existing resolved-component exporter, and retains stdout,
stderr and hashes.  It never creates a source file and never reports success
when the pending source entry is absent or the compiler reports a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

PINNED_ATOPILE = "0.2.69"
ENTRY_FILE = "elec/src/current_sense_unit.ato"
ENTRY_MODULE = "CurrentSenseUnit"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_block_source(repo: Path):
    lab = repo / "harness-lab"
    scripts = repo / "scripts"
    sys.path[:0] = [str(lab), str(scripts)]
    import block_source  # type: ignore[import-not-found]

    return block_source


def build(repo: Path, output: Path, entry_file: str = ENTRY_FILE, entry_module: str = ENTRY_MODULE) -> None:
    source = repo / entry_file
    if not source.is_file():
        raise FileNotFoundError(
            f"pending source entry is absent: {source}; refusing pretend build"
        )
    if output.exists():
        raise FileExistsError(f"refusing to overwrite source build: {output}")

    block_source = load_block_source(repo)
    (output / "elec").mkdir(parents=True)
    shutil.copytree(repo / "elec" / "src", output / "elec" / "src")
    (output / "ato.yaml").write_text(
        f"ato-version: {PINNED_ATOPILE}\nbuilds:\n"
        f"  default:\n    entry: {entry_file}:{entry_module}\n",
        encoding="utf-8",
    )

    proc = block_source.run_atopile_build(output, entry_file, entry_module)
    (output / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    receipt = {
        "schema": "zapote.current-sense.source-build-receipt.v1",
        "status": "compiled" if proc.returncode == 0 else "compiler-failed",
        "command": (
            f"uv tool run --offline --from atopile=={PINNED_ATOPILE} "
            f"ato --non-interactive build {entry_file}:{entry_module}"
        ),
        "entry": f"{entry_file}:{entry_module}",
        "returncode": proc.returncode,
        "build_report_failed": "FAILED" in proc.stdout,
        "adapter_sha256": sha256(Path(__file__).resolve()),
        "block_source_sha256": sha256(repo / "harness-lab" / "block_source.py"),
        "source_hashes": block_source.workspace_hashes(output),
    }
    (output / "build-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    block_source.gate_build(proc)

    export_path = output / "resolved-components.json"
    block_source.run_resolved_export(
        output, entry_file, entry_module, export_path
    )
    receipt["status"] = "compiled-and-exported"
    receipt["export_sha256"] = sha256(export_path)
    (output / "build-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": receipt["status"], "output": str(output)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.repo.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
