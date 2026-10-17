#!/usr/bin/env python3
"""Pin or verify every local ignored D1 raw file and the authoritative inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
SOURCE_HEAD = "91888bb29e318eef09c0a292245de88b9016d250"
MANIFEST = HERE / "raw-manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(solver: Path) -> dict:
    if not solver.is_file():
        raise FileNotFoundError(f"FastHenry binary not found: {solver}; pass --solver or set FASTHENRY")
    board = UNIT / "native-17/section.kicad_pcb"
    exporter = UNIT / "tools/export_power_copper.py"
    plane = UNIT / "validation-results/round3-coordination/decision-review/fieldsolver/plane_pair_80/plane_pair_80.inp"
    raw = HERE / "extraction"
    files = sorted(path for path in raw.rglob("*") if path.is_file())
    sources = sorted(path for path in HERE.iterdir() if path.suffix == ".py" or path.name == ".gitignore")
    reports = sorted(path for path in HERE.iterdir()
                     if path.name == "README.md" or (path.suffix == ".json" and path != MANIFEST))
    return {
        "source_checkout_head": SOURCE_HEAD,
        "native_board_sha256": sha(board),
        "approved_exporter_sha256": sha(exporter),
        "solver_binary_sha256": sha(solver),
        "source_plane_fixture_sha256": sha(plane),
        "raw_file_count": len(files),
        "raw_total_bytes": sum(path.stat().st_size for path in files),
        "raw_files": [{"relative_path": str(path.relative_to(HERE)), "sha256": sha(path),
                       "bytes": path.stat().st_size} for path in files],
        "task_scripts": [{"relative_path": path.name, "sha256": sha(path)} for path in sources],
        "compact_reports": [{"relative_path": path.name, "sha256": sha(path)} for path in reports],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--solver", type=Path, help="FastHenry binary; defaults to FASTHENRY environment variable")
    args = parser.parse_args()
    solver = args.solver or (Path(os.environ["FASTHENRY"]) if os.environ.get("FASTHENRY") else None)
    if solver is None:
        parser.error("FastHenry binary required: pass --solver or set FASTHENRY")
    current = build(solver)
    if args.verify:
        saved = json.loads(MANIFEST.read_text())
        if saved != current:
            raise ValueError("raw/source manifest mismatch")
        print(f"PASS {current['raw_file_count']} raw, {len(current['task_scripts'])} source, {len(current['compact_reports'])} report files")
    else:
        MANIFEST.write_text(json.dumps(current, indent=2) + "\n")
        print(f"WROTE {current['raw_file_count']} raw files, {current['raw_total_bytes']} bytes")


if __name__ == "__main__":
    main()
