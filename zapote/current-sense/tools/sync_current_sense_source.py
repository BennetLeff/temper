#!/usr/bin/env python3
"""Stamp exact compiled source identity fields onto native footprints."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(repo: Path, board_path: Path, manifest_path: Path, receipt_path: Path) -> None:
    sys.path.insert(0, str(repo / "harness-lab"))
    import pcbnew  # type: ignore[import-not-found]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components = {
        item["instance_path"]: item for item in manifest["bridge"]["components"]
    }
    attrs = manifest["source_attributes"]
    before = sha256(board_path)
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    board = io.LoadBoard(str(board_path), None)
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    expected_refs = {item["reference"] for item in components.values()}
    observed_refs = set(footprints)
    if observed_refs != expected_refs:
        raise ValueError(
            "native/source reference census differs: "
            + json.dumps(
                {
                    "missing": sorted(expected_refs - observed_refs),
                    "extra": sorted(observed_refs - expected_refs),
                }
            )
        )
    by_ref = {item["reference"]: (instance, item) for instance, item in components.items()}
    operations = []
    for reference, fp in sorted(footprints.items()):
        instance, component = by_ref[reference]
        source_attrs = attrs[instance]
        mpn = str(source_attrs["mpn"])
        value = str(source_attrs.get("value") or "")
        footprint = component["footprint"]
        if str(fp.GetFPID().GetLibNickname()) + ":" + str(fp.GetFPID().GetLibItemName()) != footprint:
            raise ValueError(f"native footprint differs from source for {instance}")
        fp.SetValue(mpn)
        for name, field_value in (
            ("MPN", mpn),
            ("SourceInstance", instance),
            ("SourceValue", value),
        ):
            fp.SetField(name, field_value)
        operations.append(
            {
                "reference": reference,
                "instance_path": instance,
                "mpn": mpn,
                "source_value": value,
                "footprint": footprint,
            }
        )
    io.SaveBoard(str(board_path), board)
    reloaded = io.LoadBoard(str(board_path), None)
    for operation in operations:
        fp = next(fp for fp in reloaded.GetFootprints() if fp.GetReference() == operation["reference"])
        if fp.GetFieldText("MPN") != operation["mpn"]:
            raise ValueError(f"MPN did not survive native reload: {operation['reference']}")
        if fp.GetFieldText("SourceInstance") != operation["instance_path"]:
            raise ValueError(f"SourceInstance did not survive native reload: {operation['reference']}")
        if fp.GetFieldText("SourceValue") != operation["source_value"]:
            raise ValueError(f"SourceValue did not survive native reload: {operation['reference']}")
        native_footprint = (
            str(fp.GetFPID().GetLibNickname())
            + ":"
            + str(fp.GetFPID().GetLibItemName())
        )
        if native_footprint != operation["footprint"]:
            raise ValueError(f"Footprint identity did not survive native reload: {operation['reference']}")
        if fp.GetValue() != operation["mpn"]:
            raise ValueError(f"Value did not survive native reload: {operation['reference']}")
    receipt = {
        "schema": "zapote.current-sense.source-property-sync-receipt.v1",
        "status": "source-properties-synchronized",
        "input_board_sha256": before,
        "output_board_sha256": sha256(board_path),
        "manifest_sha256": sha256(manifest_path),
        "kicad_version": pcbnew.Version(),
        "component_count": len(operations),
        "operations": operations,
        "physical_tests": "NOT RUN",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    sync(args.repo.resolve(), args.board.resolve(), args.manifest.resolve(), args.receipt.resolve())


if __name__ == "__main__":
    main()
