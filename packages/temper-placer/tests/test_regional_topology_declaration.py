from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "docs/evidence/net41-route-layer-corridor-20260831/validate_declaration.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("net41_corridor_declaration", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_declaration_replays_exact_candidate_family():
    receipt = load_harness().validate()
    assert receipt["valid"] is True
    assert receipt["candidate_count"] == 2880
    assert receipt["predecessor_placement_count"] == 60
    assert receipt["net41"] == {"segments": 15, "vias": 1, "zones": 0}
    assert receipt["production_board_changed"] is False


def test_rust_validator_rejects_stale_board_and_predecessor_status():
    import temper_design_bundle_python as design_bundle

    evidence = HARNESS.parent
    predecessor = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"
    args = [
        (evidence / "declaration.json").read_bytes(),
        (evidence / "design-basis.json").read_bytes(),
        (ROOT / "pcb/temper.kicad_pcb").read_bytes(),
        (predecessor / "terminal-receipt.json").read_bytes(),
        (predecessor / "pre-route-manifest.json").read_bytes(),
        (ROOT / "elec/domain_manifest.yaml").read_bytes(),
        (ROOT / "elec/build/default.net").read_bytes(),
        (ROOT / "pcb/temper.kicad_dru").read_bytes(),
        b"{}",
    ]
    stale_board = list(args)
    stale_board[2] += b"\n"
    with pytest.raises(ValueError, match="stale authority binding"):
        design_bundle.validate_regional_topology_declaration_json_py(*stale_board)

    stale_receipt = list(args)
    receipt = json.loads(stale_receipt[3])
    receipt["status"] = "exhausted"
    stale_receipt[3] = json.dumps(receipt).encode()
    with pytest.raises(ValueError, match="non-exhaustive successor"):
        design_bundle.validate_regional_topology_declaration_json_py(*stale_receipt)
