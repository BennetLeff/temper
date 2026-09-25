"""Serialize the approved stackup onto a newly generated, unrouted shelf.

Adapted from the archived Rev38 interface-integration-38 native adapter.
The existing Zapote Rust physical-stackup validator remains the acceptance
rule; this adapter only transports the explicit configuration into KiCad.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sexpr_end(text: str, start: int) -> int:
    """Locate an expression boundary, respecting quoted text and escapes."""
    depth = 0
    quoted = escaped = False
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
    raise ValueError("unterminated generated KiCad expression")


def apply_planning_stackup(output: Path, stackup_path: Path) -> None:
    config = json.loads(stackup_path.read_text())
    if config.get("schema") != "temper.power-stage-120v.stackup.v1":
        raise ValueError("unexpected power-stage stackup schema")
    layers = config["layers"]
    if [layer["name"] for layer in layers] != [
        "F.Mask", "F.Cu", "dielectric 1", "B.Cu", "B.Mask"
    ]:
        raise ValueError("unsupported two-layer stackup layer order")
    records = ["    (stackup"]
    for layer in layers:
        fields = [f'(layer {json.dumps(layer["name"])}',
                  f'(type {json.dumps(layer["type"])})',
                  f'(thickness {layer["thickness_mm"]})']
        for key in ("material", "epsilon_r", "loss_tangent"):
            if key in layer:
                fields.append(f'({key} {json.dumps(layer[key], allow_nan=False)})')
        records.append("      " + " ".join(fields) + ")")
    records.append("    )")

    board_path = output / "section.kicad_pcb"
    manifest_path = output / "source-manifest.json"
    board = board_path.read_text()
    manifest = json.loads(manifest_path.read_text())
    if sha256(board_path) != manifest["board_sha256"]:
        raise ValueError("generated board differs from source manifest")
    if re.search(r'\((?:segment|via|zone)\s', board):
        raise ValueError("stackup projection requires an unrouted source board")
    if '(stackup' in board or '(property "SourceInstance" ' in board:
        raise ValueError("stackup projection requires a fresh generated board")
    components = manifest["bridge"]["components"]
    if board.count('(property "Sheetpath" ') != len(components):
        raise ValueError("generated footprint census differs from manifest")
    for component in components:
        instance = component["instance_path"]
        mpn = manifest["source_attributes"][instance]["mpn"]
        field = f'    (property "Sheetpath" {json.dumps(instance)})'
        if board.count(field) != 1 or not mpn:
            raise ValueError(f"missing unique source identity: {instance}")
        board = board.replace(field, field
                              + f'\n    (property "SourceInstance" {json.dumps(instance)})'
                              + f'\n    (property "MPN" {json.dumps(mpn)})', 1)

    footprints = list(re.finditer(r"\n  \(footprint ", board))
    if len(footprints) != len(components):
        raise ValueError("generated footprint count differs from manifest")
    refs: set[str] = set()
    for footprint in reversed(footprints):
        start = footprint.start() + 3
        end = sexpr_end(board, start)
        block = board[start:end]
        match = re.search(r'\(property "Reference" "([A-Z]+\d+)"', block)
        if match is None or match[1] in refs:
            raise ValueError("missing or repeated footprint reference")
        ref = match[1]
        refs.add(ref)
        pads = list(re.finditer(r"\n    \(pad ", block))
        if not pads:
            raise ValueError(f"footprint has no physical pads: {ref}")
        for index, pad in reversed(list(enumerate(pads))):
            pad_start = pad.start() + 5
            pad_end = sexpr_end(block, pad_start)
            if '(uuid ' in block[pad_start:pad_end]:
                raise ValueError(f"generated pad already has a UUID: {ref}/{index}")
            identity = uuid.uuid5(uuid.NAMESPACE_URL, f"temper/power-stage-120v/{ref}/pad/{index}")
            block = block[:pad_end - 1] + f' (uuid "{identity}")' + block[pad_end - 1:]
        board = board[:start] + block + board[end:]

    # Remove the archived skeleton's four inner-layer declarations. Refuse
    # unexpected input instead of silently retaining phantom copper layers.
    for number, name in ((3, "In3.Cu"), (1, "In1.Cu"), (2, "In2.Cu"), (4, "In4.Cu")):
        line = f'    ({number} "{name}" signal)\n'
        if board.count(line) != 1:
            raise ValueError("generated copper layer declarations changed")
        board = board.replace(line, "", 1)
    old_setup = "  (setup\n    (pad_to_mask_clearance 0.0)"
    if board.count(old_setup) != 1 or board.count('(thickness 1.6)') != 1:
        raise ValueError("generated board skeleton changed")
    board = board.replace('(thickness 1.6)', f'(thickness {config["board_thickness_mm"]})', 1)
    board = board.replace(old_setup, "  (setup\n" + "\n".join(records)
                          + "\n    (pad_to_mask_clearance 0.0)", 1)
    manifest["input_hashes"]["stackup.json"] = sha256(stackup_path)
    manifest["input_hashes"]["planning_stackup.py"] = sha256(Path(__file__))
    manifest["board_sha256"] = hashlib.sha256(board.encode()).hexdigest()
    board_path.write_text(board)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
