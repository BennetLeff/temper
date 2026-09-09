"""Version-pinned KiCad adapter. Geometry comes from pcbnew, never local trig."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pcbnew


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def position(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def save(board: pcbnew.BOARD, path: Path) -> None:
    if not pcbnew.SaveBoard(str(path), board, True):
        raise RuntimeError(f"KiCad could not save {path}")


def footprints(board: pcbnew.BOARD) -> dict:
    return {f.GetReference(): f for f in board.GetFootprints()}


def place(path: Path, x: float, y: float, angle: int) -> None:
    board = pcbnew.LoadBoard(str(path))
    cap = footprints(board)["C9"]
    cap.SetOrientationDegrees(angle)
    cap.SetPosition(position(x, y))
    save(board, path)


def bounds(box: pcbnew.BOX2I) -> list:
    return [
        pcbnew.ToMM(v)
        for v in (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom())
    ]


def measure(path: Path) -> dict:
    board = pcbnew.LoadBoard(str(path))
    items = []
    for fp in board.GetFootprints():
        items.append(
            {
                "reference": fp.GetReference(),
                "position_mm": list(pcbnew.ToMM(fp.GetPosition())),
                "angle_deg": fp.GetOrientationDegrees(),
                "bounds_mm": bounds(fp.GetBoundingBox(False, False)),
                "pads": [
                    {
                        "number": p.GetNumber(),
                        "net": p.GetNetname(),
                        "position_mm": list(pcbnew.ToMM(p.GetPosition())),
                        "bounds_mm": bounds(p.GetBoundingBox()),
                    }
                    for p in fp.Pads()
                ],
            }
        )
    # Normalize only the admitted degrees of freedom before serializing through
    # KiCad. Everything else (pads, nets, U3, outline, tracks...) stays protected.
    cap = footprints(board)["C9"]
    cap.SetOrientationDegrees(0)
    cap.SetPosition(position(10, 10))
    with tempfile.TemporaryDirectory(prefix="temper-e00-canonical-") as tmp:
        canonical = Path(tmp) / "canonical.kicad_pcb"
        save(board, canonical)
        protected = digest(canonical)
    return {
        "kicad_version": pcbnew.GetBuildVersion(),
        "board_sha256": digest(path),
        "protected_sha256": protected,
        "footprints": sorted(items, key=lambda f: f["reference"]),
    }


def build(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=False)
    original = pcbnew.LoadBoard(str(source))
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    net_names = ("+15V", "gnd", "sw", "fb", "boot")
    nets = {}
    for index, name in enumerate(net_names, 1):
        net = pcbnew.NETINFO_ITEM(board, name, index)
        board.Add(net)
        nets[name] = net
    library = dest / "fixture.pretty"
    library.mkdir()
    for ref in ("U3", "C9"):
        fp = pcbnew.FOOTPRINT(footprints(original)[ref])
        board.Add(fp)
        fp.SetOrientationDegrees(0)
        fp.SetPosition(position(10, 10) if ref == "U3" else position(22, 15))
        for pad in fp.Pads():
            pad.SetNet(nets[pad.GetNetname()])
        fp.SetFPID(pcbnew.LIB_ID("fixture", ref))
        pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library.resolve()), fp)
    for start, end in (
        ((1, 1), (29, 1)),
        ((29, 1), (29, 19)),
        ((29, 19), (1, 19)),
        ((1, 19), (1, 1)),
    ):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(position(*start))
        edge.SetEnd(position(*end))
        edge.SetWidth(pcbnew.FromMM(0.05))
        board.Add(edge)
    save(board, dest / "candidate.kicad_pcb")
    (dest / "candidate.kicad_pro").write_text(
        json.dumps(
            {
                "meta": {"version": 1},
                "board": {
                    "design_settings": {
                        "rules": {
                            "min_clearance": 0.2,
                            "min_copper_edge_clearance": 0.2,
                        },
                        "rule_severities": {"courtyards_overlap": "error"},
                    }
                },
                "net_settings": {
                    "classes": [
                        {"name": "Default", "clearance": 0.2, "track_width": 0.25}
                    ],
                    "version": 4,
                },
            },
            indent=2,
        )
        + "\n"
    )
    (dest / "candidate.kicad_dru").write_text(
        '(version 1)\n(rule "E00 copper clearance" (constraint clearance (min 0.2mm)))\n'
    )
    (dest / "fp-lib-table").write_text(
        '(fp_lib_table (version 7) (lib (name "fixture")(type "KiCad")'
        '(uri "${KIPRJMOD}/fixture.pretty")(options "")(descr "Frozen source geometry")))\n'
    )
    (dest / "source.json").write_text(
        json.dumps(
            {
                "source_board_sha256": digest(source),
                "kicad_version": pcbnew.GetBuildVersion(),
                "admitted_references": ["U3", "C9"],
                "U3_pose_mm_deg": [10, 10, 0],
                "outline_mm": [1, 1, 29, 19],
                "copper_layers": 2,
                "source_net_mapping": {
                    "C9.1": "+15V",
                    "U3.3": "+15V",
                    "C9.2": "gnd",
                    "U3.1": "gnd",
                },
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Experiment 00 is qualified only against KiCad 10.0.4")
    command, path, *args = sys.argv[1:]
    if command == "build":
        build(Path(path), Path(args[0]))
    elif command == "measure":
        print(json.dumps(measure(Path(path)), allow_nan=False))
    elif command == "place":
        place(Path(path), float(args[0]), float(args[1]), int(args[2]))
    else:
        raise ValueError(f"Unknown adapter operation: {command}")


if __name__ == "__main__":
    main()
