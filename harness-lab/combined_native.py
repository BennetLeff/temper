"""Native C9 placement plus explicit copper; moving never shoves or repairs tracks."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pcbnew

import native
import routing_native


def place(path: Path, x: float, y: float, angle: int) -> None:
    board = routing_native.load(path)
    cap = native.footprints(board)["C9"]
    cap.SetOrientationDegrees(angle)
    cap.SetPosition(native.position(x, y))
    routing_native.save(board, path)


def measure(path: Path) -> dict:
    measured = routing_native.measure(path)
    board = routing_native.load(path)
    for track in list(board.GetTracks()):
        board.Delete(track)
    cap = native.footprints(board)["C9"]
    cap.SetOrientationDegrees(0)
    cap.SetPosition(native.position(10, 10))
    with tempfile.TemporaryDirectory(prefix="temper-00pr-canonical-") as tmp:
        canonical = Path(tmp) / "canonical.kicad_pcb"
        routing_native.save(board, canonical)
        measured["protected_sha256"] = native.digest(canonical)
    return measured


if __name__ == "__main__":
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Combined adapter requires KiCad 10.0.4")
    command, path, *args = sys.argv[1:]
    if command == "measure":
        print(json.dumps(measure(Path(path)), allow_nan=False))
    elif command == "place":
        place(Path(path), float(args[0]), float(args[1]), int(args[2]))
    elif command == "route":
        routing_native.route(Path(path), args[0], json.loads(args[1]))
    else:
        raise ValueError("Unknown combined operation")
