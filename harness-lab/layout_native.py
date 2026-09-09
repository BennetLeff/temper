"""KiCad 10 native evidence collector for engineering layout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _worker(board: Path) -> dict[str, Any]:
    import pcbnew  # type: ignore

    import buck_native  # type: ignore

    native = buck_native.measure(board)
    loaded = pcbnew.LoadBoard(str(board))
    labels = []
    models = {}
    footprint_map = {fp.GetReference(): fp for fp in loaded.GetFootprints()}
    for item in native["footprints"]:
        fp = footprint_map[item["reference"]]
        pad_map = {p.GetNumber(): p for p in fp.Pads()}
        for pad in item["pads"]:
            pad["layer"] = loaded.GetLayerName(pad_map[pad["number"]].GetLayer())
        for field in (fp.Reference(), fp.Value()):
            if field.IsVisible():
                box = field.GetBoundingBox()
                labels.append(
                    {
                        "text": field.GetShownText(),
                        "layer": loaded.GetLayerName(field.GetLayer()),
                        "height_mm": pcbnew.ToMM(field.GetTextSize().y),
                        "bounds_mm": [
                            pcbnew.ToMM(box.GetLeft()),
                            pcbnew.ToMM(box.GetTop()),
                            pcbnew.ToMM(box.GetRight()),
                            pcbnew.ToMM(box.GetBottom()),
                        ],
                    }
                )
        models[fp.GetReference()] = [model.m_Filename for model in fp.Models()]
    native["presentation"] = {
        "labels": labels,
        "model_paths": models,
        "missing_3d_models": sorted(ref for ref, paths in models.items() if not paths),
        "model_files_resolved": False,
    }
    return native


def collect(
    repo: Path, output: Path, board: Path, base_result: dict[str, Any] | None = None
) -> dict[str, Any]:
    del repo
    output, board = Path(output).resolve(), Path(board).resolve()
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True)
    worker = os.environ.get(
        "TEMPER_KICAD_PYTHON",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9",
    )
    proc = subprocess.run(
        [worker, str(Path(__file__).resolve()), "measure", str(board)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode:
        return {
            "profile": "engineering-layout",
            "stage": "layout",
            "status": "blocked",
            "findings": [
                {"id": "native_measurement_failed", "message": proc.stderr[-4000:]}
            ],
        }
    native = json.loads(proc.stdout)
    payload = {
        "profile": "engineering-layout",
        "stage": "layout",
        "measurement": {k: v for k, v in native.items() if k != "presentation"},
        "presentation": native.get("presentation", {}),
        "base_result": base_result,
    }
    (output / "measurement.json").write_text(
        json.dumps(payload["measurement"], indent=2, sort_keys=True) + "\n"
    )
    (output / "presentation.json").write_text(
        json.dumps(payload["presentation"], indent=2, sort_keys=True) + "\n"
    )
    (output / "input.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    return payload


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "measure":
        raise SystemExit("usage: layout_native.py measure BOARD")
    print(json.dumps(_worker(Path(sys.argv[2])), sort_keys=True, allow_nan=False))
