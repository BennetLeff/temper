"""Apply authored designator positions without changing electrical geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pcbnew


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mm_position(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def apply(board_path: Path, labels_path: Path, output_path: Path, receipt_path: Path) -> None:
    labels = json.loads(labels_path.read_text())
    if labels.get("schema") != "temper.power-stage-120v.labels.v1":
        raise ValueError("unexpected reference-label schema")
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    board = io.LoadBoard(str(board_path), None)
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    positions = labels["references"]
    if len(footprints) != 114 or set(footprints) != set(positions):
        raise ValueError("reference labels must cover the exact 114-footprint board")

    for name, instruction in positions.items():
        fp = footprints[name]
        for field_name in ("Sheetpath", "SourceInstance", "MPN"):
            field = fp.GetField(field_name)
            if field is None or not field.GetText():
                raise ValueError(f"{name} is missing {field_name}")
            field.SetPosition(fp.GetPosition())
            field.SetVisible(False)
        fp.Value().SetVisible(False)

        ref = fp.Reference()
        if instruction["layer"] != "F.SilkS":
            raise ValueError(f"{name} label must be on F.SilkS")
        x, y = instruction["at"]
        if not (0 < x < 240 and 0 < y < 160):
            raise ValueError(f"{name} label lies outside the board")
        size = instruction["size"]
        if not (0.7 <= size <= 1.2):
            raise ValueError(f"{name} label size outside allowed range")
        ref.SetLayer(pcbnew.F_SilkS)
        ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        ref.SetPosition(mm_position(x, y))
        ref.SetTextSize(mm_position(size, size))
        ref.SetTextThickness(pcbnew.FromMM(0.12))
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
    args = parser.parse_args()
    apply(args.board, args.labels, args.output, args.receipt)
