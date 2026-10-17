"""Resolve the snapshot template inside this package before calling cadgen."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def local_path(value: str) -> str:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"Snapshot template must use a relative path: {value}")
    resolved = (ROOT / relative).resolve()
    resolved.relative_to(ROOT)
    return str(resolved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    job = json.loads((ROOT / "checks/snapshots.json").read_text())
    for item in job["jobs"]:
        item["input"] = local_path(item["input"])
        for output in item["outputs"]:
            output["path"] = local_path(output["path"])
    target = ROOT / "snapshot-job.resolved.json"
    target.write_text(json.dumps(job, indent=2) + "\n")
    if args.prepare_only:
        print(target)
        return
    subprocess.run(
        [sys.executable, "-m", "cadgen.cli", "step", "snapshot", "--job", str(target), "--json"],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
