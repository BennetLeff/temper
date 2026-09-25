"""Project a frozen Rev38 Atopile build through the strict native bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSIVE = ROOT.parents[1]
REPO = ROOT.parents[4]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402


def apply_planning_stackup(output: Path, stackup_path: Path) -> None:
    """Bind the provisional Rev38 CAD stackup to the generated board receipt."""
    config = json.loads(stackup_path.read_text(encoding="utf-8"))
    if config.get("schema") != "temper.rev38.planning-stackup.v1":
        raise ValueError("unexpected Rev38 stackup schema")
    layers = config["layers"]
    expected = ["F.Mask", "F.Cu", "dielectric 1", "In3.Cu",
                "dielectric 2", "In1.Cu", "dielectric 3", "In2.Cu",
                "dielectric 4", "In4.Cu", "dielectric 5", "B.Cu", "B.Mask"]
    if [layer["name"] for layer in layers] != expected:
        raise ValueError("Rev38 stackup layer order differs from generated board")

    records = ['    (stackup',
               '      (layer "F.SilkS" (type "Top Silk Screen"))',
               '      (layer "F.Paste" (type "Top Solder Paste"))']
    for layer in layers:
        record = (f'      (layer {json.dumps(layer["name"])} '
                  f'(type {json.dumps(layer["type"])}) '
                  f'(thickness {layer["thickness_mm"]})')
        if "material" in layer:
            record += f' (material {json.dumps(layer["material"])})'
            record += f' (epsilon_r {layer["epsilon_r"]})'
            record += f' (loss_tangent {layer["loss_tangent"]})'
        records.append(record + ')')
    records.extend(['      (layer "B.Paste" (type "Bottom Solder Paste"))',
                    '      (layer "B.SilkS" (type "Bottom Silk Screen"))',
                    '      (copper_finish "ENIG")',
                    '      (dielectric_constraints no)', '    )'])

    board_path = output / "section.kicad_pcb"
    board = board_path.read_text(encoding="utf-8")
    thickness_old = "(thickness 1.6)"
    setup_old = "  (setup\n    (pad_to_mask_clearance 0.0)"
    if board.count(thickness_old) != 1 or board.count(setup_old) != 1:
        raise ValueError("generated Rev38 board skeleton changed; stackup not applied")
    board = board.replace(thickness_old, f'(thickness {config["board_thickness_mm"]})', 1)
    board = board.replace(setup_old,
                          "  (setup\n" + "\n".join(records) + "\n    (pad_to_mask_clearance 0.0)", 1)
    board_path.write_text(board, encoding="utf-8")

    manifest_path = output / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_hashes"]["stackup.json"] = hashlib.sha256(stackup_path.read_bytes()).hexdigest()
    manifest["board_sha256"] = hashlib.sha256(board_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Frozen successful Atopile source build")
    parser.add_argument("output", type=Path, help="New native output directory")
    parser.add_argument("--poses", type=Path, default=ROOT / "poses.json")
    parser.add_argument("--outline", type=Path, default=ROOT / "outline.json")
    parser.add_argument("--stackup", type=Path, default=ROOT / "stackup.json")
    args = parser.parse_args()
    build(
        REPO,
        args.source.resolve(),
        args.output.resolve(),
        args.poses.resolve(),
        args.outline.resolve(),
        ("power_entry_integrated_38",),
        entry_module="PowerEntryIntegrated38",
        entry_file="elec/src/power_entry_integrated_38.ato",
        title="Rev38 source-to-PFC power-entry engineering candidate",
        local_libraries=PASSIVE / "libraries",
        assembly_only=(
            {
                "instance_path": "pfc_power.f2",
                "mpn": "A70QS50-14F",
                "footprint": "TBD_REVIEW_ONLY:PFC_F2_OFFBOARD_ASSEMBLY",
            },
        ),
    )
    apply_planning_stackup(args.output.resolve(), args.stackup.resolve())


if __name__ == "__main__":
    main()
