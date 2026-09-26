#!/usr/bin/env python3
"""Replay authored routes onto the current, unrouted four-layer placement.

    KICAD_PY tools/route_board.py native-05 native-06

Both paths may be absolute. The output must not exist: replay never deletes an
older result. Generate native-05 with build_native.py and --stackup first.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]

UNIT = Path(__file__).resolve().parents[1]
COPPER_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
SOURCE_INPUTS = {
    "poses.json": UNIT / "poses.json",
    "outline.json": UNIT / "outline.json",
    "stackup.json": UNIT / "stackup.json",
    "planning_stackup.py": UNIT / "tools/planning_stackup.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(placement: Path, output: Path) -> None:
    placement = placement.resolve()
    output = output.resolve()
    if output == placement or placement in output.parents or output in placement.parents:
        raise ValueError("placement and output paths must be separate directories")
    if output.exists():
        raise FileExistsError(f"refusing to replace existing output: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"output parent does not exist: {output.parent}")

    board_path = placement / "section.kicad_pcb"
    manifest = json.loads((placement / "source-manifest.json").read_text())
    if sha256(board_path) != manifest.get("board_sha256"):
        raise ValueError("placement board differs from its source manifest or is already routed")
    for name, path in SOURCE_INPUTS.items():
        if manifest.get("input_hashes", {}).get(name) != sha256(path):
            raise ValueError(f"placement was generated from stale {name}")
    receipt = json.loads((UNIT / "build-receipt.json").read_text())
    for name in ("default.net", "default.csv", "resolved-components.json"):
        path = UNIT / "frozen" / name
        if receipt.get("sha256", {}).get(f"frozen/{name}") != sha256(path):
            raise ValueError(f"frozen source differs from its build receipt: {name}")
    outline = json.loads((UNIT / "outline.json").read_text())["outline_mm"]
    expected_layers = tuple(
        layer["name"] for layer in json.loads((UNIT / "stackup.json").read_text())["layers"]
        if layer["type"] == "copper"
    )
    if expected_layers != COPPER_LAYERS:
        raise ValueError(f"route batches require four copper layers: {COPPER_LAYERS}")
    if tuple(manifest.get("board", {}).get("layers", ())) != expected_layers:
        raise ValueError("source manifest copper layers differ from current stackup")
    if manifest.get("outline_mm") != outline:
        raise ValueError("placement outline differs from current outline")
    if manifest.get("poses") != json.loads((UNIT / "poses.json").read_text()):
        raise ValueError("placement poses differ from current poses")

    board = pcbnew.LoadBoard(str(board_path))
    layers = tuple(board.GetLayerName(lid) for lid in board.GetEnabledLayers().CuStack())
    if layers != expected_layers:
        raise ValueError(f"wrong enabled copper layers: {layers}; expected {expected_layers}")
    box = board.GetBoardEdgesBoundingBox()
    actual_outline = [pcbnew.ToMM(v) for v in
                      (box.GetX(), box.GetY(), box.GetRight(), box.GetBottom())]
    if len(actual_outline) != len(outline) or any(
        # The bounding box includes the 0.1 mm Edge.Cuts stroke.
        abs(a - b) > 0.06 for a, b in zip(actual_outline, outline)
    ):
        raise ValueError(f"wrong board outline: {actual_outline}; expected {outline}")
    if len(list(board.GetFootprints())) != manifest["board"]["footprints"]:
        raise ValueError("board footprint census differs from source manifest")
    if list(board.GetTracks()) or list(board.Zones()):
        raise ValueError("placement input already contains routed copper")


def replay(placement: Path, output: Path) -> None:
    preflight(placement, output)
    placement = placement.resolve()
    output = output.resolve()
    output.mkdir()
    try:
        for name in ("section.kicad_pcb", "section.kicad_sch", "fp-lib-table",
                     "source-manifest.json", "schematic_layout.json"):
            shutil.copy2(placement / name, output / name)
        shutil.copy2(UNIT / "stackup.json", output / "stackup.json")
        shutil.copytree(placement / "candidate-libs", output / "candidate-libs")
        receipts = output / "route-receipts"
        receipts.mkdir()
        batches = sorted((UNIT / "routes").glob("routes-*.json"))
        if not batches:
            raise ValueError("no route batches found")
        for batch in batches:
            subprocess.run(
                [sys.executable, str(UNIT / "tools/apply_routes.py"), str(output / "section.kicad_pcb"),
                 str(batch), str(receipts / batch.name.replace("routes-", "receipt-"))],
                check=True,
            )
        subprocess.run([sys.executable, str(UNIT / "tools/write_rules.py"),
                        str(output / "section.kicad_pcb")], check=True, stdout=subprocess.DEVNULL)
    except BaseException:
        # The only directory we remove is the fresh output this invocation created.
        shutil.rmtree(output)
        raise


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: route_board.py <unrouted-placement-dir> <new-routed-dir>")
    placement, output = (Path(arg) if Path(arg).is_absolute() else UNIT / arg
                         for arg in sys.argv[1:])
    replay(placement, output)
    print(output.resolve())


if __name__ == "__main__":
    main()
