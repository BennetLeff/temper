#!/usr/bin/env python3
"""Extract a saved KiCad board for the Rust source-to-native parity gate.

Use KiCad's Python (pcbnew), not a generic Python interpreter. The Rust binary
owns the source contract; this adapter only reports what KiCad loaded.

    KICAD_PY tools/check_native_parity.py <board> <source-manifest> \
        <frozen/default.net> <zapote-power-native-parity binary>
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]


def extract(board_path: Path) -> dict:
    board_sha256 = hashlib.sha256(board_path.read_bytes()).hexdigest()
    board = pcbnew.LoadBoard(str(board_path))
    copper = list(board.GetEnabledLayers().CuStack())
    components = []
    for footprint in board.GetFootprints():
        pads = []
        for pad in footprint.Pads():
            # KiCad footprints can include NPTH holes and mask-only solder
            # features. Neither is an electrical copper connection.
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not any(
                pad.IsOnLayer(layer) for layer in copper
            ):
                continue
            pads.append({
                "number": pad.GetNumber(),
                "net": pad.GetNetname(),
                "uuid": pad.m_Uuid.AsString(),
            })
        components.append({
            "reference": footprint.GetReference(),
            "instance_path": footprint.GetFieldText("SourceInstance"),
            "mpn": footprint.GetFieldText("MPN"),
            "value": footprint.GetValue(),
            "footprint": footprint.GetFPIDAsString(),
            "pads": pads,
        })
    if hashlib.sha256(board_path.read_bytes()).hexdigest() != board_sha256:
        raise ValueError("board changed during native pad extraction")
    return {
        "schema": "zapote.power-stage-120v.native-pad-extract.v1",
        "board_sha256": board_sha256,
        "components": components,
    }


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    board, manifest, netlist, binary = map(Path, sys.argv[1:])
    bom = netlist.with_name("default.csv")
    resolved = netlist.with_name("resolved-components.json")
    with tempfile.TemporaryDirectory(prefix="zapote-power-parity-") as directory:
        extracted = Path(directory) / "native-pads.json"
        extracted.write_text(json.dumps(extract(board), sort_keys=True), encoding="utf-8")
        return subprocess.run(
            [str(binary), str(manifest), str(board), str(netlist), str(bom),
             str(resolved), str(extracted)],
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
