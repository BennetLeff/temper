"""Apply authored designator positions without changing electrical geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pcbnew


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


UNIT = Path(__file__).resolve().parents[1]
# JLCPCB legend minimums (https://jlcpcb.com/capabilities/pcb-capabilities,
# read 2026-09-26): text height >= 1.0 mm, line width >= 0.15 mm.
MIN_SIZE_MM = 1.0
MIN_THICKNESS_MM = 0.15


def mm_position(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def apply(board_path: Path, labels_path: Path, output_path: Path, receipt_path: Path,
          components: int | None = None, bounds: tuple = (0, 0, 240, 160)) -> None:
    labels = json.loads(labels_path.read_text())
    if labels.get("schema") != "temper.power-stage-120v.labels.v1":
        raise ValueError("unexpected reference-label schema")
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    board = io.LoadBoard(str(board_path), None)
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    positions = labels["references"]
    expected = components if components is not None else \
        json.loads((UNIT / "build-receipt.json").read_text())["components"]
    if len(footprints) != expected or set(footprints) != set(positions):
        raise ValueError(f"reference labels must cover the exact {expected}-footprint board")

    for name, instruction in positions.items():
        fp = footprints[name]
        for field_name in ("Sheetpath", "SourceInstance", "MPN"):
            field = fp.GetField(field_name)
            if (field is None or not field.GetText()) and field_name == "Sheetpath" and components is not None:
                continue            # boards built straight from the netlist (native-21) carry no Sheetpath
            if field is None or not field.GetText():
                raise ValueError(f"{name} is missing {field_name}")
            field.SetPosition(fp.GetPosition())
            field.SetVisible(False)
        fp.Value().SetVisible(False)

        ref = fp.Reference()
        if instruction["layer"] not in ("F.SilkS", "F.Fab"):
            raise ValueError(f"{name} label must be on F.SilkS (or F.Fab where no legend spot clears)")
        x, y = instruction["at"]
        if not (bounds[0] < x < bounds[2] and bounds[1] < y < bounds[3]):
            raise ValueError(f"{name} label lies outside the board")
        size = instruction["size"]
        thickness = instruction.get("thickness", MIN_THICKNESS_MM)
        if not (MIN_SIZE_MM <= size <= 1.5) or thickness < MIN_THICKNESS_MM:
            raise ValueError(f"{name} label below the fabricator legend minimum")
        ref.SetLayer(pcbnew.F_SilkS if instruction["layer"] == "F.SilkS" else pcbnew.F_Fab)
        ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        ref.SetPosition(mm_position(x, y))
        ref.SetTextSize(mm_position(size, size))
        ref.SetTextThickness(pcbnew.FromMM(thickness))
        ref.SetVisible(True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    io.SaveBoard(str(output_path), board)
    receipt_path.write_text(
        json.dumps(
            {
                "source_board_sha256": digest(board_path),
                "labeled_board_sha256": digest(output_path),
                "reference_labels_sha256": digest(labels_path),
                "adapter_sha256": digest(Path(__file__)),
                "kicad_version": pcbnew.Version(),
                "references_labeled": len(positions),
                "scope": "reference and metadata fields only",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--components", type=int, help="footprint count (default: build-receipt.json)")
    parser.add_argument("--bounds", type=float, nargs=4, default=(0, 0, 240, 160), metavar=("X0", "Y0", "X1", "Y1"))
    args = parser.parse_args()
    apply(args.board, args.labels, args.output, args.receipt, args.components, tuple(args.bounds))
