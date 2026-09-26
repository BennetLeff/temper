#!/usr/bin/env python3
"""Rebuild the routed board from the approved placement plus route batches.

    KICAD_PY tools/route_board.py native-04 native-05

Copies the approved placement board (D4) into a fresh output directory, then
replays routes/routes-NN.json in order through tools/apply_routes.py, each
with its own receipt, and writes the insulation rules. Routes are explicit
authored polylines, vias and zone outlines (tools/routes.py); nothing here
searches for paths. Zones are filled by KiCad DRC (--refill-zones).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]


def main() -> None:
    placement, output = (UNIT / a for a in sys.argv[1:3])
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()
    for name in ("section.kicad_pcb", "section.kicad_sch", "fp-lib-table",
                 "source-manifest.json", "schematic_layout.json"):
        shutil.copy2(placement / name, output / name)
    shutil.copytree(placement / "candidate-libs", output / "candidate-libs")
    receipts = output / "route-receipts"
    receipts.mkdir()
    for batch in sorted((UNIT / "routes").glob("routes-*.json")):
        subprocess.run(
            [sys.executable, str(UNIT / "tools/apply_routes.py"), str(output / "section.kicad_pcb"),
             str(batch), str(receipts / batch.name.replace("routes-", "receipt-"))],
            check=True,
        )
    subprocess.run(["python3", str(UNIT / "tools/write_rules.py"), str(output / "section.kicad_pcb")],
                   check=True, stdout=subprocess.DEVNULL)
    print(output)


if __name__ == "__main__":
    main()
