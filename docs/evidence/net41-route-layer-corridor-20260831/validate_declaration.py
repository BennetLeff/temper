#!/usr/bin/env python3
"""Replay the immutable net-41 corridor declaration through its Rust owners."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PREDECESSOR = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"

import temper_design_bundle_python as design_bundle  # noqa: E402
import temper_quality_oracle as quality_oracle  # noqa: E402


def validate() -> dict[str, object]:
    declaration_path = EVIDENCE / "declaration.json"
    basis_path = EVIDENCE / "design-basis.json"
    board_path = ROOT / "pcb/temper.kicad_pcb"
    receipt_path = PREDECESSOR / "terminal-receipt.json"
    manifest_path = PREDECESSOR / "pre-route-manifest.json"
    domain_path = ROOT / "elec/domain_manifest.yaml"
    generated_paths = {
        "domain_manifest_sha256": domain_path,
        "netlist_sha256": ROOT / "elec/build/default.net",
        "kicad_dru_sha256": ROOT / "pcb/temper.kicad_dru",
    }
    missing = [str(path.relative_to(ROOT)) for path in generated_paths.values() if not path.is_file()]
    if missing:
        raise RuntimeError(
            "missing generated input(s): " + ", ".join(missing)
            + "; run `make netlist` and `uv run --no-sync python scripts/generate_kicad_dru.py`"
        )

    declaration_bytes = declaration_path.read_bytes()
    declaration = json.loads(declaration_bytes)
    manifest_bytes = manifest_path.read_bytes()
    candidate_set = json.loads(
        quality_oracle.declare_corridor_candidates_from_evidence_json_py(
            declaration_bytes, manifest_bytes
        )
    )
    rust_receipt = json.loads(
        design_bundle.validate_regional_topology_declaration_json_py(
            declaration_bytes=declaration_bytes,
            basis_bytes=basis_path.read_bytes(),
            board_bytes=board_path.read_bytes(),
            predecessor_receipt_bytes=receipt_path.read_bytes(),
            predecessor_manifest_bytes=manifest_bytes,
            domain_manifest_bytes=domain_path.read_bytes(),
            netlist_bytes=generated_paths["netlist_sha256"].read_bytes(),
            kicad_dru_bytes=generated_paths["kicad_dru_sha256"].read_bytes(),
            candidate_set_bytes=json.dumps(candidate_set).encode(),
        )
    )

    return {
        **rust_receipt,
        "candidate_set_digest": candidate_set["candidate_set_digest"],
        "first_candidate_id": candidate_set["candidates"][0]["candidate_id"],
        "last_candidate_id": candidate_set["candidates"][-1]["candidate_id"],
        "generated_inputs": declaration["generated_inputs"],
        "production_board_changed": False,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), indent=2, sort_keys=True))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
