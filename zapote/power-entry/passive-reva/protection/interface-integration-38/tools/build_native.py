"""Project a frozen Rev38 Atopile build through the strict native bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSIVE = ROOT.parents[1]
REPO = ROOT.parents[4]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402


def sexpr_end(text: str, start: int) -> int:
    """Find one generated KiCad S-expression without interpreting its content."""
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("unterminated generated KiCad S-expression")


def stamp_pad_uuids(board: str, expected_footprints: int) -> str:
    """Give repeated physical pads stable identities for strict native binding."""
    footprints = list(re.finditer(r"\n  \(footprint ", board))
    if len(footprints) != expected_footprints:
        raise ValueError("generated Rev38 footprint count differs from manifest")
    output = board
    seen_refs: set[str] = set()
    for footprint in reversed(footprints):
        start = footprint.start() + 3
        end = sexpr_end(output, start)
        block = output[start:end]
        reference = re.search(r'\(property "Reference" "(U\d+)"', block)
        if reference is None or reference.group(1) in seen_refs:
            raise ValueError("generated Rev38 footprint reference is missing or repeated")
        ref = reference.group(1)
        seen_refs.add(ref)
        pads = list(re.finditer(r"\n    \(pad ", block))
        if not pads:
            raise ValueError(f"generated Rev38 footprint has no physical pads: {ref}")
        for index, pad in reversed(list(enumerate(pads))):
            pad_start = pad.start() + 5
            pad_end = sexpr_end(block, pad_start)
            pad_text = block[pad_start:pad_end]
            if "(uuid " in pad_text:
                raise ValueError(f"generated Rev38 pad already has a UUID: {ref}/{index}")
            identity = uuid.uuid5(uuid.NAMESPACE_URL, f"temper/rev38/{ref}/pad/{index}")
            block = block[:pad_end - 1] + f' (uuid "{identity}")' + block[pad_end - 1:]
        output = output[:start] + block + output[end:]
    return output


def apply_planning_stackup(output: Path, stackup_path: Path) -> None:
    """Bind source identity and provisional CAD stackup to the generated board."""
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
    manifest_path = output / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components = manifest["bridge"]["components"]
    if (board.count('(property "Sheetpath" ') != len(components)
            or '(property "SourceInstance" ' in board
            or '(property "MPN" ' in board):
        raise ValueError("generated Rev38 footprint source fields differ from manifest")
    for component in components:
        instance = component["instance_path"]
        mpn = manifest["source_attributes"][instance]["mpn"]
        sheetpath = f'    (property "Sheetpath" {json.dumps(instance)})'
        if board.count(sheetpath) != 1 or not mpn:
            raise ValueError(f"missing unique native source identity for {instance}")
        board = board.replace(
            sheetpath,
            sheetpath + f'\n    (property "SourceInstance" {json.dumps(instance)})'
            + f'\n    (property "MPN" {json.dumps(mpn)})',
            1,
        )
    board = stamp_pad_uuids(board, len(components))
    thickness_old = "(thickness 1.6)"
    setup_old = "  (setup\n    (pad_to_mask_clearance 0.0)"
    if board.count(thickness_old) != 1 or board.count(setup_old) != 1:
        raise ValueError("generated Rev38 board skeleton changed; stackup not applied")
    board = board.replace(thickness_old, f'(thickness {config["board_thickness_mm"]})', 1)
    board = board.replace(setup_old,
                          "  (setup\n" + "\n".join(records) + "\n    (pad_to_mask_clearance 0.0)", 1)
    board_path.write_text(board, encoding="utf-8")

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
