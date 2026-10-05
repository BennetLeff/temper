#!/usr/bin/env python3
"""Thin native19 adapter to the audited upstream KiCad copper exporter.

No geometry arithmetic: pad locations and flashed polygons come from pcbnew.
The hash guard must run before importing upstream executable source.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pcbnew

BOARD_SHA = "3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    board = ROOT / "zapote/power-stage-120v/native-19/section.kicad_pcb"
    if digest(board) != BOARD_SHA:
        raise ValueError("native19 board identity mismatch; do not reuse extraction")
    upstream = args.oracle / "zapote/power-stage-120v/validation-results/01-switching-parasitics"
    exporter = upstream / "round4/d1-extraction/export_native_copper.py"
    expected = json.loads((HERE / "upstream-inputs.json").read_text())
    for relative, want in expected.items():
        if digest(args.oracle / relative) != want:
            raise ValueError("upstream identity mismatch: " + relative)
    args.out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("audited_copper_export", exporter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.EXPECTED_BOARD_SHA256 = BOARD_SHA
    sys.argv = [
        str(exporter),
        "--board",
        str(board),
        "--output",
        str(args.out / "native19-all-copper.json.gz"),
    ]
    module.main()
    native = pcbnew.LoadBoard(str(board))
    pads = {
        f"{fp.GetReference()}.{p.GetNumber()}": {
            "xy_mm": [pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)],
            "net": p.GetNetname(),
        }
        for fp in native.GetFootprints()
        for p in fp.Pads()
    }
    updates = {}
    for leg in ("A", "B"):
        closures = json.loads((upstream / f"round17/closures-leg{leg}.json").read_text())
        for row in closures:
            refs = re.findall(r"\b([A-Z]+[0-9]+\.[0-9]+)\b", row["note"])
            if len(refs) != 2:
                # Bridge notes omit pin numbers; derive these from named device semantics.
                ref = row["name"].split("_")[0]
                if row["name"].endswith("_DS"):
                    refs = [ref + ".2", ref + ".3"]
                elif row["name"].endswith("_GS"):
                    refs = [ref + ".1", ref + ".3"]
                elif row["name"].startswith("R"):
                    refs = [ref + ".1", ref + ".2"]
                else:
                    raise ValueError("unresolved closure " + row["name"])
            old = [row["a"], row["b"]]
            row["a"], row["b"] = [pads[ref]["xy_mm"] for ref in refs]
            row["native19_pads"] = refs
            row["native19_nets"] = [pads[ref]["net"] for ref in refs]
            if old != [row["a"], row["b"]]:
                updates[f"{leg}:{row['name']}"] = {"old": old, "new": [row["a"], row["b"]]}
        (args.out / f"closures-leg{leg}.json").write_text(json.dumps(closures, indent=2) + "\n")
    (args.out / "pads.json").write_text(json.dumps(pads, indent=2, sort_keys=True) + "\n")
    receipt = {
        "board_sha256": BOARD_SHA,
        "adapter_sha256": digest(Path(__file__)),
        "exporter_sha256": digest(exporter),
        "kicad_version": pcbnew.Version(),
        "updated_closures": updates,
        "status": "GEOMETRY_EXPORTED_NOT_FIELD_SOLVED",
        "files": {
            p.name: digest(p)
            for p in sorted(args.out.iterdir())
            if p.is_file() and p.suffix in (".json", ".gz") and p.name != "extraction.json"
        },
    }
    (args.out / "extraction.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
