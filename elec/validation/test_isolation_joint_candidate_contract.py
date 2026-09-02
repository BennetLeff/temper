"""Contract checks for the blocked, candidate-only U9 integration envelope."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ELEC = ROOT / "elec/qualification/isolation_joint"
QUAL = ROOT / "power_pcb_dataset/qualification/isolation_joint"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_interface_contract_is_candidate_only_and_fail_closed() -> None:
    contract = _json(ELEC / "interface_contract.json")
    assert contract["status"] == "stopped-indeterminate"
    assert contract["production_authorization"] is False
    assert {item["endpoint"] for item in contract["domain_interfaces"]} == {
        "system_latch_assertion",
        "both_gates_safe",
    }
    assert contract["invariants"]["aggregate_owner"] == "isolation-joint-r24-r25-v1"


def test_fixture_contract_does_not_fabricate_a_board_or_capture() -> None:
    fixture = _json(ELEC / "validation/fixture_contract.json")
    assert fixture["status"] == "stopped-indeterminate"
    assert fixture["board_artifact"]["status"] == "not-materialized"
    assert fixture["board_artifact"]["sha256"] is None
    assert fixture["fixture_artifact"]["status"] == "not-materialized"
    assert fixture["fixture_artifact"]["sha256"] is None
    assert not (ELEC / "layout/isolation_joint_candidate.kicad_pcb").exists()


def test_u9_manifest_binds_rejected_iso_and_unfavorable_ct07_inputs() -> None:
    manifest = _json(QUAL / "manifest.json")
    assert manifest["status"] == "stopped-indeterminate"
    assert manifest["production_authorization"] is False
    assert manifest["inputs"]["iso"]["status"] == "rejected"
    assert manifest["inputs"]["iso"]["handoff_path"] is None
    assert manifest["inputs"]["ct07"]["status"] == "stopped-indeterminate"
    assert manifest["inputs"]["ct07"]["handoff_path"] is None


def test_u9_artifacts_have_no_favorable_handoff_or_joint_evidence() -> None:
    combined = _json(QUAL / "combined_candidate.json")
    signoffs = _json(QUAL / "owner_signoffs.json")
    decision = _json(QUAL / "decision.json")
    assert combined["status"] == "not-materialized"
    assert combined["combined_candidate_digest"] is None
    assert signoffs["signoffs"] == []
    assert decision["verdict"] == "stopped-indeterminate"
    assert decision["partial_result"] is None
    assert not (ROOT / "power_pcb_dataset/qualification/iso7741_gate_drive/joint_handoff.json").exists()
    assert not (ROOT / "power_pcb_dataset/qualification/ct07_t2/joint_handoff.json").exists()
