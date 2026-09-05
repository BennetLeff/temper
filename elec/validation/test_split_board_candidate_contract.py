"""Electrical-side contract checks for the U1 admission stop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUAL = ROOT / "power_pcb_dataset/qualification/split_board_feasibility"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_admission_does_not_materialize_a_candidate_electrical_contract() -> None:
    manifest = _json(QUAL / "manifest.json")
    admission = _json(QUAL / "admission_decision.json")

    assert manifest["status"] == "stopped-indeterminate"
    assert manifest["stage"] == "u1-admission"
    assert manifest["candidate_family"] == {"closed": True, "members": []}
    assert manifest["production_authorization"] is False
    assert admission["verdict"] == "stopped-indeterminate"
    assert admission["candidate_family"] == []
    assert admission["partial_result"] is None
    candidate_root = ROOT / "elec/qualification/split_board_feasibility"
    assert not candidate_root.exists()


def test_upstream_domain_results_are_the_only_admission_inputs() -> None:
    admission = _json(QUAL / "admission_decision.json")
    evidence = _json(QUAL / "evidence_index.json")

    assert admission["domain_results"] == {
        "iso": "rejected",
        "ct07": "stopped-indeterminate",
    }
    assert admission["upstream_verdict"] == "stopped-indeterminate"
    assert evidence["upstream"] == {
        "verdict": "stopped-indeterminate",
        "domain_results": {
            "iso": "rejected",
            "ct07": "stopped-indeterminate",
        },
        "combined_candidate": "absent",
        "required_verdict_for_admission": "eligible-for-refloorplan",
    }


def test_ktd9_role_matrix_is_closed_but_requires_no_signoff_after_prior_stop() -> None:
    signoffs = _json(QUAL / "owner_signoffs.json")

    assert signoffs["status"] == "not-required-after-prior-stop"
    assert signoffs["signoffs"] == []
    assert signoffs["signature_artifacts"] == []
    assert signoffs["construction_envelope_digest"] is None
    assert signoffs["signed_scope_digest"] is None
    matrix = signoffs["required_role_matrix"]
    statuses = {item["axis"]: item for item in signoffs["axis_statuses"]}
    assert len(matrix) == len({item["axis"] for item in matrix})
    assert {item["axis"] for item in matrix} == set(statuses)
    assert all(
        item["owner_role"]
        and item["independent_verifier_role"]
        and item["owner_role"] != item["independent_verifier_role"]
        for item in matrix
    )
    assert all(
        statuses[item["axis"]]["status"]
        in {"reached-no-signoff-required", "not-reached"}
        for item in matrix
    )
    assert all(
        item["status"] == "not-reached"
        for item in statuses.values()
        if item["axis"] not in {
            "admission.identity_and_limitations",
            "terminal_verdict_reproducibility",
        }
    )


def test_electrical_contract_inputs_are_digest_bound() -> None:
    for document_name in ("manifest.json", "evidence_index.json", "owner_signoffs.json"):
        document = _json(QUAL / document_name)
        for binding in document.get("bindings", {}).values():
            path = ROOT / binding["path"]
            assert path.is_file(), path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
