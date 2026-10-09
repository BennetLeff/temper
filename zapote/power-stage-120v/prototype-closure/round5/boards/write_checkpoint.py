"""Hash the final review candidates and receipts; never claim release acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/boards"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    files = []
    for directory in [HERE, OUT]:
        for path in sorted(directory.rglob("*")):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.name in {"checkpoint.json", ".DS_Store"}
            ):
                continue
            files.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": digest(path),
                    "bytes": path.stat().st_size,
                }
            )
    summary = json.loads((OUT / "verification-summary.json").read_text())
    receipt = {
        "schema": "temper-round5-boards/v1",
        "date": "2026-10-05",
        "release_status": "HOLD_DIGITAL_AND_PHYSICAL_QUALIFICATION",
        "native_tool": "KiCad 10.0.4",
        "source_capture": {
            "path": "zapote/power-stage-120v/prototype-closure/round4/supervisor/generated/pins.tsv",
            "sha256": digest(HERE / "../../round4/supervisor/generated/pins.tsv"),
        },
        "board_count": 9,
        "electrical_components": sum(sum(parts.values()) for parts in json.loads((HERE / "component-census.json").read_text()).values()),
        "drc_samples_per_board": 3,
        "checks": summary,
        "eco": [
            "Remote voltage and CT permanent-burden partition; explicit VPRE801:1 ladder ECO",
            "Five24V wetted mirror receivers;physical source-off and ADMIT token;corrected DCU flip-flop pinout;qualified retained-RUN timeout escape",
            "Manufacturer-based AMC3330 isolation land option and CT footprint",
            "Exact JST XH / Phoenix board connectors and eight straight-through harness contracts",
            "Direct24V R-78B5.0-1.0 plusTPS7A4700 postregulator;82ohm external5V preload;39ohm buck preload;300ohm3V3 preload;coil star and return planes;heartbeat fail-low;PA8 MCO series clock;191k proof timer",
        ],
        "files": files,
    }
    (HERE / "checkpoint.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Hashed", len(files), "artifacts; release remains HOLD")


if __name__ == "__main__":
    main()
