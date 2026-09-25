#!/usr/bin/env python3
"""Measure KiCad footprints and ask Rust to place a provisional native shelf.

The pcbnew process supplies observed geometry. Rust owns packing, gap and
outline decisions. This shelf is staging for native generation, not layout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
REPO = UNIT.parents[1]
KICAD_PYTHON = Path(
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
    "Python.framework/Versions/Current/bin/python3"
)
# Must match the audited source (build-receipt.json "components").
EXPECTED_COMPONENTS = 102
STOCK = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")


def _measure(request: list[dict[str, str]]) -> list[dict[str, object]]:
    """Run only under KiCad's Python, which provides pcbnew."""
    import pcbnew  # type: ignore[import-not-found]

    measured: list[dict[str, object]] = []
    for item in request:
        source = Path(item["file"])
        footprint = pcbnew.FootprintLoad(str(source.parent), source.stem)
        if footprint is None:
            raise ValueError(f"pcbnew could not load {source}")
        courtyard = [
            graphic.GetBoundingBox()
            for graphic in footprint.GraphicalItems()
            if graphic.GetLayer() == pcbnew.F_CrtYd
            and graphic.GetClass() == "PCB_SHAPE"
        ]
        boxes = courtyard
        if not boxes:
            boxes = [pad.GetBoundingBox() for pad in footprint.Pads()]
            if not boxes:
                raise ValueError(f"footprint has neither F.CrtYd nor pads: {source}")
            print(f"WARNING: no F.CrtYd in {source}; using pad extents plus 1 mm", file=sys.stderr)
        left = min(box.GetX() for box in boxes)
        top = min(box.GetY() for box in boxes)
        right = max(box.GetX() + box.GetWidth() for box in boxes)
        bottom = max(box.GetY() + box.GetHeight() for box in boxes)
        measured.append(
            {
                "path": item["path"],
                "fallback_from_pads": not courtyard,
                "bounds": {
                    "min_x": pcbnew.ToMM(left),
                    "min_y": pcbnew.ToMM(top),
                    "max_x": pcbnew.ToMM(right),
                    "max_y": pcbnew.ToMM(bottom),
                },
            }
        )
    return measured


def _footprint_file(name: str, libraries: Path) -> Path:
    nickname, separator, stem = name.partition(":")
    if not separator or not nickname or not stem or "/" in name or ".." in name:
        raise ValueError(f"invalid footprint nickname: {name!r}")
    root = libraries if nickname in {"temper", "lib"} else STOCK
    path = root / f"{nickname}.pretty" / f"{stem}.kicad_mod"
    if not path.is_file():
        raise FileNotFoundError(f"footprint {name!r} not found at {path}")
    return path


def generate(source: Path, libraries: Path, outline: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite shelf poses: {output}")
    export = json.loads(source.read_text(encoding="utf-8"))
    components = export["components"]
    if len(components) != EXPECTED_COMPONENTS:
        raise ValueError(
            f"expected {EXPECTED_COMPONENTS} source components, found {len(components)}"
        )
    outline_mm = json.loads(outline.read_text(encoding="utf-8"))["outline_mm"]
    paths: set[str] = set()
    request = []
    for component in components:
        address = component["address"]
        marker = "PowerStage120V::"
        if address.count(marker) != 1:
            raise ValueError(f"unexpected component address: {address!r}")
        instance = address.split(marker, 1)[1]
        if not instance or instance in paths:
            raise ValueError(f"empty or duplicate instance path: {instance!r}")
        paths.add(instance)
        footprint = component["attributes"]["footprint"]
        request.append({"path": instance, "file": str(_footprint_file(footprint, libraries))})
    probe = subprocess.run(
        [str(KICAD_PYTHON), str(Path(__file__).resolve()), "--probe-footprints"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.stderr:
        print(probe.stderr, file=sys.stderr, end="")
    if probe.returncode:
        raise RuntimeError(f"pcbnew footprint probe failed with exit {probe.returncode}")
    parts = json.loads(probe.stdout)
    shelf = subprocess.run(
        [
            "cargo", "run", "--quiet", "--locked", "--manifest-path",
            str(REPO / "zapote/Cargo.toml"), "-p", "zapote-harness",
            "--bin", "zapote-shelf",
        ],
        input=json.dumps({"outline_mm": outline_mm, "parts": parts}),
        text=True,
        capture_output=True,
        check=False,
    )
    if shelf.returncode:
        raise RuntimeError(shelf.stderr.strip() or f"Rust shelf failed with exit {shelf.returncode}")
    result = json.loads(shelf.stdout)
    poses = result["poses"]
    if set(poses) != paths:
        raise ValueError("Rust shelf output does not cover every source instance")
    # Do not create or replace the output until both external stages succeed.
    output.write_text(json.dumps(poses, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"parts": len(poses), "required_height_mm": result["required_height_mm"], "output": str(output)}))


def main() -> None:
    if sys.argv[1:] == ["--probe-footprints"]:
        print(json.dumps(_measure(json.load(sys.stdin))))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=UNIT / "source-build-01/resolved-components.json")
    parser.add_argument("--libraries", type=Path, default=UNIT / "libraries")
    parser.add_argument("--outline", type=Path, default=UNIT / "outline.json")
    parser.add_argument("--output", type=Path, default=UNIT / "poses.json")
    args = parser.parse_args()
    generate(args.source, args.libraries, args.outline, args.output)


if __name__ == "__main__":
    main()
