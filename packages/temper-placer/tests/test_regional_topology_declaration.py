from __future__ import annotations

import hashlib
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


def evidence_args(candidate_set: dict | None = None) -> list[bytes]:
    evidence = HARNESS.parent
    predecessor = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"
    if candidate_set is None:
        import temper_quality_oracle

        candidate_set = json.loads(
            temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
                (evidence / "declaration.json").read_bytes(),
                (predecessor / "pre-route-manifest.json").read_bytes(),
            )
        )
    return [
        (evidence / "declaration.json").read_bytes(),
        (evidence / "design-basis.json").read_bytes(),
        (ROOT / "pcb/temper.kicad_pcb").read_bytes(),
        (predecessor / "terminal-receipt.json").read_bytes(),
        (predecessor / "pre-route-manifest.json").read_bytes(),
        (ROOT / "elec/domain_manifest.yaml").read_bytes(),
        (ROOT / "elec/build/default.net").read_bytes(),
        (ROOT / "pcb/temper.kicad_dru").read_bytes(),
        json.dumps(candidate_set).encode(),
    ]


def call_validator(design_bundle, args: list[bytes]):
    names = [
        "declaration_bytes",
        "basis_bytes",
        "board_bytes",
        "predecessor_receipt_bytes",
        "predecessor_manifest_bytes",
        "domain_manifest_bytes",
        "netlist_bytes",
        "kicad_dru_bytes",
        "candidate_set_bytes",
    ]
    return design_bundle.validate_regional_topology_declaration_json_py(
        **dict(zip(names, args, strict=True))
    )


def test_committed_declaration_replays_exact_candidate_family():
    receipt = load_harness().validate()
    assert receipt["valid"] is True
    assert receipt["candidate_count"] == 2880
    assert receipt["predecessor_placement_count"] == 60
    assert receipt["net41"] == {"segments": 15, "vias": 1, "zones": 0}
    assert receipt["production_board_changed"] is False


def test_rust_validator_rejects_stale_board_and_predecessor_status():
    import temper_design_bundle_python as design_bundle

    args = evidence_args()
    stale_board = list(args)
    stale_board[2] += b"\n"
    with pytest.raises(ValueError, match="stale authority binding"):
        call_validator(design_bundle, stale_board)

    stale_receipt = list(args)
    receipt = json.loads(stale_receipt[3])
    receipt["status"] = "exhausted"
    stale_receipt[3] = json.dumps(receipt).encode()
    with pytest.raises(ValueError, match="non-exhaustive successor"):
        call_validator(design_bundle, stale_receipt)

    with pytest.raises(TypeError, match="positional"):
        design_bundle.validate_regional_topology_declaration_json_py(*args)


def test_rust_validator_reconstructs_candidate_geometry_from_predecessor():
    import temper_design_bundle_python as design_bundle

    args = evidence_args()
    declaration = json.loads(args[0])
    candidate_set = json.loads(args[8])
    candidate_set["candidates"][0]["j1_position"][0] += 0.5
    envelope = dict(candidate_set)
    envelope.pop("candidate_set_digest")
    digest = hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    candidate_set["candidate_set_digest"] = digest
    declaration["candidate_set_digest"] = digest
    args[0] = json.dumps(declaration).encode()
    args[8] = json.dumps(candidate_set).encode()
    with pytest.raises(ValueError, match="does not exactly reconstruct"):
        call_validator(design_bundle, args)


def test_rust_validator_rejects_weakened_screening_policy():
    import temper_design_bundle_python as design_bundle

    args = evidence_args()
    declaration = json.loads(args[0])
    declaration["screening"]["hard_vetoes"].remove("connectivity")
    args[0] = json.dumps(declaration).encode()
    with pytest.raises(ValueError, match="hard_vetoes changed"):
        call_validator(design_bundle, args)


def test_rust_validator_rejects_hollow_design_basis():
    import temper_design_bundle_python as design_bundle

    args = evidence_args()
    declaration = json.loads(args[0])
    basis = json.loads(args[1])
    basis["fixed_copper_categories"].remove("all zones")
    args[1] = json.dumps(basis, separators=(",", ":")).encode()
    declaration["design_basis_sha256"] = hashlib.sha256(args[1]).hexdigest()
    args[0] = json.dumps(declaration).encode()
    with pytest.raises(ValueError, match="fixed_copper_categories changed"):
        call_validator(design_bundle, args)


def test_topology_snapshot_pyo3_boundary_uses_production_inputs():
    import temper_design_bundle_python as design_bundle

    board = (ROOT / "pcb/temper.kicad_pcb").read_bytes()
    domain = (ROOT / "elec/domain_manifest.yaml").read_bytes()
    snapshot = json.loads(design_bundle.regional_topology_snapshot_json_py(board, domain))
    assert snapshot["net41_segment_count"] == 15
    assert snapshot["net41_isolated_pad_ids"] == ["C7.1"]
    duplicate = (
        b'  (segment (start 21.24 204.215) (end 21.84 204.215) (width 1) '
        b'(layer "F.Cu") (net 4) '
        b'(tstamp ca660326-f82c-541c-bb6b-3f21fb7ae705))\n'
    )
    duplicated_board = board.replace(b"\n)", b"\n" + duplicate + b")", 1)
    duplicated = json.loads(
        design_bundle.regional_topology_snapshot_json_py(duplicated_board, domain)
    )
    assert duplicated["selv_object_counts"]["tracks"] == 1799
    assert duplicated["selv_identity_digest"] != snapshot["selv_identity_digest"]
    with pytest.raises(ValueError, match="domain manifest"):
        design_bundle.regional_topology_snapshot_json_py(board, b"not: [valid")
