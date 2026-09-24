"""Project a frozen Rev38 Atopile build through the strict native bridge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSIVE = ROOT.parents[1]
REPO = ROOT.parents[4]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Frozen successful Atopile source build")
    parser.add_argument("output", type=Path, help="New native output directory")
    parser.add_argument("--poses", type=Path, default=ROOT / "poses.json")
    parser.add_argument("--outline", type=Path, default=ROOT / "outline.json")
    args = parser.parse_args()
    build(
        REPO,
        args.source.resolve(),
        args.output.resolve(),
        args.poses.resolve(),
        args.outline.resolve(),
        ("power_entry_integrated_38",),
        entry_module="PowerEntryIntegrated38",
        entry_file="elec/src/power_entry_integrated_38.ato",
        title="Rev38 source-to-PFC power-entry engineering candidate",
        local_libraries=PASSIVE / "libraries",
    )


if __name__ == "__main__":
    main()
