#!/usr/bin/env python3
"""Show that the approved exporter rejects the native-15 missing-land control."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
BOARD = UNIT / "native-15/section.kicad_pcb"
EXPORTER = UNIT / "tools/export_power_copper.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    spec = importlib.util.spec_from_file_location("power_export_negative", EXPORTER)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import approved exporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.export(BOARD)
    except ValueError as exc:
        message = str(exc)
        if "PTH pad without both outer lands" not in message:
            raise
    else:
        raise AssertionError("native-15 missing-land control unexpectedly passed")
    result = {"status": "EXPECTED_REJECTION", "board_sha256": sha(BOARD),
              "approved_exporter_sha256": sha(EXPORTER), "reason": message}
    (HERE / "native15-negative-control.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
