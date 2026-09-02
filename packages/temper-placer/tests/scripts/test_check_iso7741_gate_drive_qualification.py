"""Focused tests for the ISO7741 replay shim and its single Rust boundary."""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_iso7741_gate_drive_qualification as gate  # noqa: E402


def test_candidate_build_publication_is_root_independent_and_byte_checked(
    tmp_path: Path,
) -> None:
    for relative in gate.PROTECTED_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    project = tmp_path / "candidate-copy"
    build = project / "build"
    build.mkdir(parents=True)
    (build / "default.csv").write_bytes(b"Comment,Designator\r\npart,U1\r\n")
    (build / "default.net").write_text(
        f'(sheetpath (names "{project.resolve().as_posix()}/src/main.ato"))\n',
        encoding="utf-8",
    )
    canonical = tmp_path / gate.OUTPUT_ROOT / "generated"
    canonical.mkdir(parents=True)

    gate.publish_candidate_build(project, repo_root=tmp_path)
    gate.verify_candidate_build(project, repo_root=tmp_path)
    assert b"\r\n" not in (canonical / "iso7741_gate_drive.csv").read_bytes()
    assert gate.CANDIDATE_ROOT.as_posix() in (
        canonical / "iso7741_gate_drive.net"
    ).read_text()

    (build / "default.net").write_text("drift", encoding="utf-8")
    with pytest.raises(gate.QualificationGateError, match="differs"):
        gate.verify_candidate_build(project, repo_root=tmp_path)


def test_runner_uses_only_iso7741_rust_registration(monkeypatch) -> None:
    calls: list[str] = []

    class FakeOracle:
        @staticmethod
        def evaluate_iso7741_gate_drive_qualification_json(value: str) -> str:
            calls.append(value)
            return json.dumps({"schema_version": 1, "stage": "stopped-indeterminate"})

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", FakeOracle)
    result = gate._evaluate_in_rust({"schema_version": 1})
    assert json.loads(result)["stage"] == "stopped-indeterminate"
    assert len(calls) == 1


def test_runner_rejects_missing_iso7741_registration(monkeypatch) -> None:
    class MissingOracle:
        pass

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", MissingOracle)
    with pytest.raises(gate.QualificationGateError, match="ISO7741 Rust evaluator"):
        gate._evaluate_in_rust({"schema_version": 1})


def test_manifest_parser_is_single_buffer_and_fail_closed() -> None:
    assert gate._parse_manifest_bytes(b'{"schema_version":1}') == {"schema_version": 1}
    with pytest.raises(gate.QualificationGateError, match="invalid ISO7741 manifest JSON"):
        gate._parse_manifest_bytes(b"not-json")


def _receipt_fixture(tmp_path: Path, *, revision: str = "rev-1", owners=None) -> Path:
    for path in gate.PROTECTED_PATHS:
        protected = tmp_path / path
        protected.parent.mkdir(parents=True, exist_ok=True)
        protected.write_bytes(b"protected")
    source = tmp_path / gate.CANDIDATE_ROOT / "source.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"candidate")
    receipt_path = tmp_path / "power_pcb_dataset" / "qualification" / "iso7741_gate_drive" / "source_receipts.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owners": owners if owners is not None else ["A6", "A7"],
                "sources": [
                    {
                        "path": "elec/qualification/iso7741_gate_drive/source.txt",
                        "sha256": hashlib.sha256(b"candidate").hexdigest(),
                        "revision": revision,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return receipt_path


def test_source_receipts_require_current_revision_and_semantic_owners(tmp_path: Path) -> None:
    receipt_path = _receipt_fixture(tmp_path, revision="pending", owners=["A6", "A7"])
    with pytest.raises(gate.QualificationGateError, match="revision"):
        gate._validate_source_receipts({}, tmp_path, receipt_path.with_name("manifest.json"))

    receipt_path = _receipt_fixture(tmp_path, owners=["A6"])
    with pytest.raises(gate.QualificationGateError, match="A6 and A7"):
        gate._validate_source_receipts({}, tmp_path, receipt_path.with_name("manifest.json"))


def test_u6_index_materializes_evidence_and_signature_bytes_once(tmp_path: Path) -> None:
    evidence = tmp_path / gate.CANDIDATE_ROOT / "truth.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(b"truth-pending")
    signature = tmp_path / gate.OUTPUT_ROOT / "authority" / "signed" / "a1.sig"
    signature.parent.mkdir(parents=True, exist_ok=True)
    signature.write_bytes(b"signature-bytes")
    index = {
        "schema_version": 1,
        "evidence_objects": [
            {
                "id": "truth",
                "path": "elec/qualification/iso7741_gate_drive/truth.json",
                "axis": "state.truth_table",
            }
        ],
        "owner_signoffs": [
            {
                "role": "iso.board_architecture",
                "status": "pass",
                "signature_artifact": {
                    "artifact_id": "a1",
                    "path": "power_pcb_dataset/qualification/iso7741_gate_drive/authority/signed/a1.sig",
                },
            }
        ],
    }

    payload = gate._payload_from_evidence_index(index, tmp_path)

    assert payload["evidence_objects"][0]["id"] == "truth"
    assert payload["evidence_objects"][0]["bytes"] == list(b"truth-pending")
    assert payload["signature_artifacts"][0]["artifact_id"] == "a1"
    assert payload["signature_artifacts"][0]["bytes"] == list(b"signature-bytes")


def test_u6_signature_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "outside.sig"
    target.write_bytes(b"signature-bytes")
    signature = tmp_path / gate.OUTPUT_ROOT / "authority" / "signed" / "a1.sig"
    signature.parent.mkdir(parents=True, exist_ok=True)
    signature.symlink_to(target)
    index = {
        "schema_version": 1,
        "evidence_objects": [],
        "owner_signoffs": [
            {
                "role": "iso.board_architecture",
                "status": "pass",
                "signature_artifact": {
                    "artifact_id": "a1",
                    "path": "power_pcb_dataset/qualification/iso7741_gate_drive/authority/signed/a1.sig",
                },
            }
        ],
    }

    with pytest.raises(gate.QualificationGateError, match="symlink"):
        gate._payload_from_evidence_index(index, tmp_path)


def test_u6_replay_defaults_to_evidence_index() -> None:
    assert gate.DEFAULT_MANIFEST.name == "evidence_index.json"


def test_u6_owner_signoff_sidecar_must_match_dag(tmp_path: Path) -> None:
    manifest_path = tmp_path / gate.OUTPUT_ROOT / "evidence_index.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "candidate": {"candidate_id": "candidate", "envelope_digest": "e" * 64},
        "evidence_root_digest": "f" * 64,
        "owner_signoffs": [
            {
                "role": "iso.board_architecture",
                "status": "pending",
                "scope_node_id": "scope-board",
                "scope_digest": "a" * 64,
                "signature_artifact": None,
            }
        ],
    }
    sidecar = {
        "schema_version": 1,
        "candidate_id": "candidate",
        "envelope_digest": "e" * 64,
        "evidence_root_digest": "f" * 64,
        "signoffs": [
            {
                "role": "iso.board_architecture",
                "status": "pass",
                "scope_node_id": "scope-board",
                "scope_digest": "a" * 64,
                "signature_artifact": None,
            }
        ],
    }
    manifest_path.write_text("{}", encoding="utf-8")
    manifest_path.with_name("owner_signoffs.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )

    with pytest.raises(gate.QualificationGateError, match="diverges in status"):
        gate._validate_owner_signoffs_sidecar(manifest, tmp_path, manifest_path)


def test_u7_authority_packet_is_attached_without_inventing_receipt_bytes(tmp_path: Path) -> None:
    output = tmp_path / gate.OUTPUT_ROOT
    authority = output / "authority"
    authority.mkdir(parents=True)
    (authority / "submission_index.json").write_text(
        json.dumps({"schema_version": 1, "submission_digest": "a" * 64}),
        encoding="utf-8",
    )
    (authority / "preliminary_ruling.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "disposition": "unresolved",
                "response_kind": "construction",
                "receipt_artifact": None,
            }
        ),
        encoding="utf-8",
    )
    observations: dict[str, object] = {}
    payload = gate._payload_from_preliminary_authority(
        {"evidence_objects": [], "owner_signoffs": []},
        {},
        tmp_path,
        tmp_path / gate.OUTPUT_ROOT / "evidence_index.json",
        observations,
    )
    assert payload["submission_index"]["submission_digest"] == "a" * 64
    assert payload["preliminary_ruling"]["receipt_artifact"] is None
    assert not (authority / "signed").exists()


def test_u7_authority_path_escape_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(gate.QualificationGateError, match="authority path"):
        gate._payload_from_preliminary_authority(
            {"evidence_objects": [], "owner_signoffs": []},
            {"submission_index": "../submission.json"},
            tmp_path,
            tmp_path / "evidence_index.json",
            {},
        )
