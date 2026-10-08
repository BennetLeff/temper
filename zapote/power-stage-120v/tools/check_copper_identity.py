#!/usr/bin/env python3
"""Ask Rust whether saved KiCad track/via UUIDs still carry their authored nets.

    KICAD_PY tools/check_copper_identity.py native-06/section.kicad_pcb

The route receipts are made before DRC/refill. This adapter only carries the
saved KiCad copper, current route-file hashes, and receipts to the Rust judge.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]

UNIT = Path(__file__).resolve().parents[1]
ZAPOTE = UNIT.parent
SCHEMA = "temper.power-stage-120v.copper-identity.v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(board_path: Path) -> dict:
    board_hash = sha256(board_path)
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
    items = []
    for item in board.GetTracks():
        kind = "via" if item.Type() == pcbnew.PCB_VIA_T else "track"
        if kind == "track" and item.GetClass() != "PCB_TRACK":
            raise ValueError(f"unsupported saved copper kind: {item.GetClass()}")
        items.append({"uuid": item.m_Uuid.AsString(), "kind": kind,
                      "net": item.GetNetname()})
    if sha256(board_path) != board_hash:
        raise ValueError("board changed during copper identity extraction")
    return {"board_sha256": board_hash, "observed": items}


def evidence(board_path: Path, route_dir: Path = UNIT / "routes") -> dict:
    board_path = board_path.resolve()
    extracted = extract(board_path)
    placement_manifest = json.loads((board_path.parent / "source-manifest.json").read_text())
    receipt_dir = board_path.parent / "route-receipts"
    route_files = sorted(route_dir.glob("routes-*.json"))
    if not route_files or not receipt_dir.is_dir():
        raise ValueError("missing authored route files or route receipts")
    expected_receipts = {p.name.replace("routes-", "receipt-") for p in route_files}
    actual_receipts = {p.name for p in receipt_dir.glob("receipt-*.json")}
    if actual_receipts != expected_receipts:
        raise ValueError("route receipt set differs from current authored route files")
    batches = []
    for route_path in route_files:
        receipt = json.loads((receipt_dir / route_path.name.replace("routes-", "receipt-")).read_text())
        instruction = json.loads(route_path.read_text())
        batches.append({
            "name": route_path.name,
            "current_instruction_sha256": sha256(route_path),
            "instruction_sha256": receipt["instruction_sha256"],
            "input_board_sha256": receipt["input_board_sha256"],
            "output_board_sha256": receipt["output_board_sha256"],
            "instruction_operations": [
                {"net": op["net"], "mode": op.get("mode", "replace"),
                 "segments": sum(len(path["points"]) - 1 for path in op["paths"]),
                 "vias": len(op.get("vias", []))}
                for op in instruction["nets"]
            ],
            "operations": receipt["operations"],
        })
    return {"schema": SCHEMA,
            "placement_board_sha256": placement_manifest["board_sha256"],
            "board_sha256": extracted["board_sha256"],
            "observed_board_sha256": extracted["board_sha256"],
            "batches": batches, "observed": extracted["observed"]}


def check(board_path: Path, route_dir: Path = UNIT / "routes") -> dict:
    payload = evidence(board_path, route_dir)
    binary = os.environ.get("ZAPOTE_POWER_COPPER_IDENTITY_BIN")
    command = ([binary] if binary else [
        "cargo", "run", "--quiet", "--locked", "--manifest-path", str(ZAPOTE / "Cargo.toml"),
        "-p", "zapote-harness", "--bin", "zapote-power-copper-identity",
    ])
    result = subprocess.run(command, input=json.dumps(payload, allow_nan=False),
                            text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"Rust copper identity check rejected saved board: {result.stderr.strip()}")
    if sha256(board_path) != payload["board_sha256"]:
        raise ValueError("board changed during copper identity check")
    return json.loads(result.stdout)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_copper_identity.py <routed-board.kicad_pcb>")
    print(json.dumps(check(Path(sys.argv[1])), indent=2))


if __name__ == "__main__":
    main()
