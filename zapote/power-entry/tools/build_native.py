#!/usr/bin/env python3
"""Power-entry adapter around the shared source-bound native builder."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--poses", type=Path, required=True)
    ap.add_argument("--outline", type=Path, required=True)
    ap.add_argument("--module", dest="modules", action="append", default=["power_entry"])
    args = ap.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "zapote/current-sense/tools"))
    import build_current_sense_native as shared
    shared.build(repo, args.source.resolve(), args.output.resolve(), args.poses.resolve(), args.outline.resolve(), tuple(args.modules), entry_module="PowerEntryUnit", entry_file="elec/src/power_entry_unit.ato", title="Standalone PFC Power-Entry Unit", local_libraries=repo / "zapote/power-entry/libraries")

if __name__ == "__main__":
    main()
