"""Physics-contract checks for the authoritative U1 -> U7 early stop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
QUAL = ROOT / "power_pcb_dataset/qualification/split_board_feasibility"
UPSTREAM = ROOT / "power_pcb_dataset/qualification/isolation_joint"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _assert_bindings(document: dict) -> None:
    for binding in document["bindings"].values():
        path = ROOT / binding["path"]
        assert path.is_file(), path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]


def test_early_terminal_is_indeterminate_and_does_not_admit_geometry() -> None:
    admission = _json(QUAL / "admission_decision.json")
    decision = _json(QUAL / "decision.json")
    combined = _json(UPSTREAM / "combined_candidate.json")

    assert admission["verdict"] == "stopped-indeterminate"
    assert admission["admission_authorized"] is False
    assert admission["geometry_admitted"] is False
    assert admission["domain_results"] == {
        "iso": "rejected",
        "ct07": "stopped-indeterminate",
    }
    assert decision["verdict"] == "stopped-indeterminate"
    assert decision["terminal_unit"] == "U1"
    assert decision["stage"] == "u7-terminal-decision"
    assert decision["stop_witness"] == "admission.upstream_joint_not_eligible"
    assert decision["geometry_admitted"] is False
    assert decision["production_authorization"] is False
    assert decision["production_authorized"] is False
    assert decision["candidate_rejection"] is False
    assert decision["architecture_no_go"] is False
    assert combined["status"] == "not-materialized"
    assert combined["combined_candidate_digest"] is None


def test_early_stop_has_complete_reached_and_not_reached_witnesses() -> None:
    evidence = _json(QUAL / "evidence_index.json")
    decision = _json(QUAL / "decision.json")

    requirements = {item["requirement"]: item for item in evidence["requirements"]}
    assert set(requirements) == {f"R{i}" for i in range(1, 31)}
    assert {
        requirement
        for requirement, item in requirements.items()
        if item["status"] == "stopped-indeterminate"
    } == {"R22", "R23", "R24", "R25", "R28", "R29", "R30"}
    assert {
        requirement
        for requirement, item in requirements.items()
        if item["status"] == "not-reached"
    } == {f"R{i}" for i in range(1, 22)} | {"R26", "R27"}
    for requirement in ("R22", "R23", "R24", "R25", "R28", "R29", "R30"):
        assert requirements[requirement]["stop_witness"] == decision["stop_witness"]
    assert decision["reached_stop_requirements"] == [
        "R22",
        "R23",
        "R24",
        "R25",
        "R28",
        "R29",
        "R30",
    ]
    assert set(decision["not_reached_units"]) == {"U2", "U3", "U4", "U5", "U6"}


def test_no_physical_candidate_or_architecture_rejection_is_claimed() -> None:
    decision = _json(QUAL / "decision.json")
    evidence = _json(QUAL / "evidence_index.json")

    assert evidence["raw_evidence"] == []
    assert evidence["evidence_root_digest"] is None
    assert evidence["signed_scope_digest"] is None
    assert decision["not_claimed"] == [
        "spatial feasibility",
        "candidate rejection",
        "architecture no-go",
        "production readiness",
        "production authorization",
    ]
    candidate_root = ROOT / "elec/qualification/split_board_feasibility"
    assert not candidate_root.exists()
    assert not list(candidate_root.rglob("*.kicad_pcb"))


def test_terminal_artifacts_bind_their_upstream_and_local_inputs() -> None:
    decision = _json(QUAL / "decision.json")
    evidence = _json(QUAL / "evidence_index.json")
    signoffs = _json(QUAL / "owner_signoffs.json")

    _assert_bindings(decision)
    _assert_bindings(evidence)
    _assert_bindings(signoffs)
