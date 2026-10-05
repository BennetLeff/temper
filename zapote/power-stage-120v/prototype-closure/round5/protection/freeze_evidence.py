"""Serialize the completed adapter/calculation receipts and reject stale inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/protection"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    receipt = OUT / "replay.json"
    receipt.write_text('{"status":"INCOMPLETE"}\n')
    cad = json.loads((OUT / "hardware-geometry.json").read_text())
    for name, expected in cad["inputs"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"geometry input drift: {name}")
    for exported in cad["exports"]:
        if sha(ROOT / exported["path"]) != exported["sha256"]:
            raise ValueError("STEP bytes drifted")
    calc = json.loads((OUT / "calculation-status.json").read_text())
    if calc["status"] != "COMPLETED_CONDITIONAL_DEMANDS":
        raise ValueError("calculation not complete")
    if "6 passed; 0 failed" not in (OUT / "calculation-tests.txt").read_text():
        raise ValueError("calculation tests not complete")
    if cad["precharge_context_collisions"]:
        raise ValueError("new precharge overlaps remain")
    files = sorted(
        p for folder in (HERE, OUT) for p in folder.iterdir() if p.is_file() and p != receipt
    )
    result = {
        "status": "REPRODUCED_WITH_ENGINEERING_HOLDS",
        "fabrication_release": False,
        "powered_release": False,
        "tests": 6,
        "conditional_calculation_rows": 54,
        "owned_files": [
            {"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in files
        ],
        "unresolved": [
            "DC fuse and source-contact coordination",
            "qualified thermal interfaces and cutoff coupling",
            "full installed field geometry",
            "local conductor insulation rule",
            "sensor board assembly join",
        ],
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "owned_files"}, indent=2))


if __name__ == "__main__":
    main()
