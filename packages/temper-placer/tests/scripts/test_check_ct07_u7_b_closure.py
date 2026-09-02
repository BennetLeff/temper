"""Proof for the CT07 U7-B final owner/FMEA closure boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_ct07_u7_b_closure as gate  # noqa: E402


def _install_stopped_oracle(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    class FakeOracle:
        @staticmethod
        def evaluate_ct07_u7_b_closure_json(value: str) -> str:
            package = json.loads(value)
            calls.append(package)
            return json.dumps(
                {
                    "schema_version": package["schema_version"],
                    "candidate_id": package["candidate_id"],
                    "construction_id": package["construction_id"],
                    "construction_digest": package["construction_digest"],
                    "status": "stopped-indeterminate",
                    "construction_release_eligible": False,
                    "reasons": ["u5.evidence"],
                }
            )

    monkeypatch.setattr(gate, "temper_quality_oracle", FakeOracle)
    return calls


def test_u7_b_binds_complete_fault_and_owner_projections_without_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stopped_oracle(monkeypatch)

    result = json.loads(gate.replay(repo_root=gate.REPO_ROOT))

    assert result["status"] == "stopped-indeterminate"
    assert result["construction_release_eligible"] is False
    assert len(calls) == 1
    package = calls[0]
    assert len(package["fault_analysis"]["rows"]) == 30
    assert len(package["internal_dispositions"]["dispositions"]) == 16
    assert {
        row["owner_role"] for row in package["internal_dispositions"]["dispositions"]
    } >= {"ct07.verification", "ct07.board_product_safety"}
    assert all(
        blob["sha256"]
        for blob in package["raw_evidence"]
    )


def test_u7_b_rejects_an_unbound_u7_a_identity_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stopped_oracle(monkeypatch)
    original = gate._read_json

    def altered(path: Path, *, root: Path):
        value, raw = original(path, root=root)
        if path.name == "identity_eligibility.json":
            value = dict(value)
            value["identity_digest"] = "0" * 64
        return value, raw

    monkeypatch.setattr(gate, "_read_json", altered)
    with pytest.raises(gate.U7BClosureGateError, match="identity digest"):
        gate.replay(repo_root=gate.REPO_ROOT)


def test_u7_b_does_not_allow_output_outside_qualification_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_stopped_oracle(monkeypatch)
    with pytest.raises(gate.U7BClosureGateError, match="under the CT07 qualification root"):
        gate.replay(output_path=tmp_path / "decision.json", repo_root=gate.REPO_ROOT)
