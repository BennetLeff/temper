#!/usr/bin/env python3
"""Replay the immutable net-41 corridor declaration through its Rust owners."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PREDECESSOR = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"

from temper_placer.validation import regional_topology  # noqa: E402


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
    predecessor = json.loads(manifest_path.read_bytes())
    placements = {}
    for row in predecessor["results"]:
        if row["east_shift_mm"] == 4.0:
            placement_id = row["predecessor_placement_id"]
            placements[placement_id] = {
                "placement_id": placement_id,
                "j1_position": row["placements"]["J1"][:2],
            }
    family = declaration["family"]
    request = {
        "schema_version": family["schema_version"],
        "declaration_hash": declaration["declaration_authority_digest"],
        "board_hash": declaration["production_board_sha256"],
        "generated_input_hashes": sorted(declaration["generated_inputs"].values()),
        "placements": list(placements.values()),
        "endpoint_x_mm": family["endpoint_x_mm"],
        "corridor_x_mm": family["corridor_x_mm"],
        "entry_y_mm": family["entry_y_mm"],
        "endpoint_y_mm": family["endpoint_y_mm"],
        "fixed_start": family["fixed_start"],
        "knee_y_mm": family["knee_y_mm"],
        "layer": family["layer"],
        "route_width_mm": family["route_width_mm"],
        "via_diameter_mm": family["via_diameter_mm"],
        "via_drill_mm": family["via_drill_mm"],
        "via_span": family["via_span"],
        "candidate_budget": family["candidate_budget"],
    }
    candidate_set = json.loads(
        regional_topology.declare_corridor_candidates_json_py(json.dumps(request))
    )
    rust_receipt = json.loads(
        regional_topology.validate_regional_topology_declaration_json_py(
            declaration_bytes,
            basis_path.read_bytes(),
            board_path.read_bytes(),
            receipt_path.read_bytes(),
            manifest_path.read_bytes(),
            domain_path.read_bytes(),
            generated_paths["netlist_sha256"].read_bytes(),
            generated_paths["kicad_dru_sha256"].read_bytes(),
            json.dumps(candidate_set).encode(),
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
