#!/usr/bin/env python3
"""Project a reviewed cooker-mate source through the existing strict bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MATE = Path(__file__).resolve().parent
REPO = MATE.parent.parents[4]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Frozen successful cooker source build")
    parser.add_argument("output", type=Path, help="New native output directory")
    parser.add_argument("--poses", type=Path, required=True)
    parser.add_argument("--outline", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    exported = json.loads((source / "resolved-components.json").read_text())
    modules = tuple(
        sorted(
            {
                component["address"].split("::", 1)[1].split(".")[0]
                for component in exported["components"]
            }
        )
    )
    build(
        REPO,
        source,
        args.output.resolve(),
        args.poses.resolve(),
        args.outline.resolve(),
        modules,
        entry_module="CookerMate38",
        entry_file=(
            "zapote/power-entry/passive-reva/protection/"
            "interface-integration-38/cooker-mate/elec/src/cooker_mate.ato"
        ),
        title="Rev38 existing-cooker mating-port derivative",
        local_libraries=REPO / "pcb/libs",
    )


if __name__ == "__main__":
    main()
